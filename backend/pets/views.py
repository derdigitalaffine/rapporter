import hashlib
import html
import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from baby.models import FamilyModuleSetting
from expenses.models import Expense
from family.models import Family, FamilyEvent, Membership
from .models import PetCareAccess, PetCareLog, PetCareShare, PetDocument, PetHandoverNote, PetHealthEvent, PetMedication, PetMedicationDose, PetObservation, PetProfile, PetWeightMeasurement, PetVetQuestion
from .ocr import prepare_pet_upload
from .permissions import MODULE_KEY, active_membership, module_setting, pet_access, require_manager, require_module, set_care_circle, set_module
from .services import PUBLIC_CARE_KINDS, audit_report, care_summary, create_share, emergency_card, family_zone, record_care, report_csv, report_payload, share_from_token


class PetShareThrottle(SimpleRateThrottle):
    rate = "120/hour"
    def get_cache_key(self, request, view):
        token = str(getattr(view, "kwargs", {}).get("token") or request.parser_context.get("kwargs", {}).get("token") or "")
        key = hashlib.sha256(token.encode()).hexdigest()[:16]
        return self.cache_format % {"scope": "pet_share", "ident": f"{self.get_ident(request)}:{key}"}


class CareInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PetCareLog.Kind.values)
    occurred_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False, allow_null=True)
    value = serializers.JSONField(required=False)
    client_event_id = serializers.UUIDField(required=False, allow_null=True)


def _family(request):
    value = request.query_params.get("family") or request.data.get("family")
    try:
        family = Family.objects.filter(pk=value, status=Family.Status.ACTIVE, memberships__user=request.user).first()
    except (ValueError, DjangoValidationError):
        family = None
    if not family:
        raise NotFound("Family not found.")
    return family


def _pet(request, pet_id, health=False):
    pet = PetProfile.objects.select_related("family").filter(pk=pet_id, family__memberships__user=request.user, family__status=Family.Status.ACTIVE).first()
    if not pet:
        raise NotFound("Pet not found.")
    pet_access(request.user, pet.family, health=health)
    return pet


def _profile(row, private=True):
    data = {"id": str(row.id), "family": str(row.family_id), "name": row.name, "species": row.species, "breed": row.breed, "sex": row.sex, "birth_date": row.birth_date.isoformat() if row.birth_date else None, "adoption_date": row.adoption_date.isoformat() if row.adoption_date else None, "color_description": row.color_description, "quick_actions": row.quick_actions, "active": row.active}
    if private:
        data.update({"microchip_id": row.microchip_id, "insurance_provider": row.insurance_provider, "insurance_number": row.insurance_number, "primary_vet_name": row.primary_vet_name, "primary_vet_phone": row.primary_vet_phone, "emergency_contact_name": row.emergency_contact_name, "emergency_contact_phone": row.emergency_contact_phone, "allergies": row.allergies, "important_notes": row.important_notes})
    return data


def _access(row):
    return {"id": str(row.id), "membership": str(row.membership_id), "display_name": row.membership.display_name or row.membership.user.get_username(), "role": row.membership.role, "can_care": row.can_care, "health_manage": row.health_manage, "remind_medications": row.remind_medications, "remind_prevention": row.remind_prevention}


def _care(row):
    return {"id": str(row.id), "pet": str(row.pet_id), "kind": row.kind, "occurred_at": row.occurred_at.isoformat(), "ended_at": row.ended_at.isoformat() if row.ended_at else None, "value": row.value, "created_by": row.created_by_id, "external_caregiver": row.external_caregiver}


def _health(row):
    return {"id": str(row.id), "pet": str(row.pet_id), "kind": row.kind, "title": row.title, "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None, "next_due_at": row.next_due_at.isoformat() if row.next_due_at else None, "provider_name": row.provider_name, "note": row.note, "source": row.source, "source_document": str(row.source_document_id) if row.source_document_id else None}


def _med(row, doses=False):
    data = {"id": str(row.id), "pet": str(row.pet_id), "name": row.name, "instruction_text": row.instruction_text, "dose_value": str(row.dose_value) if row.dose_value is not None else None, "dose_unit": row.dose_unit, "schedule": row.schedule, "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat() if row.ends_at else None, "active": row.active, "prescribing_provider": row.prescribing_provider, "note": row.note}
    if doses:
        data["doses"] = [{"id": str(d.id), "scheduled_for": d.scheduled_for.isoformat() if d.scheduled_for else None, "given_at": d.given_at.isoformat() if d.given_at else None, "state": d.state, "given_by": d.given_by_id, "note": d.note} for d in row.doses.all()[:200]]
    return data


def _doc(row):
    duplicate = PetDocument.objects.filter(pet=row.pet, sha256=row.sha256).exclude(pk=row.pk).first()
    return {"id": str(row.id), "pet": str(row.pet_id), "kind": row.kind, "title": row.title, "filename": row.filename, "content_type": row.content_type, "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None, "provider_name": row.provider_name, "extraction_status": row.extraction_status, "extraction_error": row.extraction_error, "fields": row.extraction_data, "field_confidences": row.field_confidences, "pinned": row.pinned, "possible_duplicate": str(duplicate.id) if duplicate else None, "download_url": f"/api/pets/documents/{row.id}/?download=1"}


def _dt(value, allow_null=True):
    return serializers.DateTimeField(allow_null=allow_null).run_validation(value)


def _date_aware(value, family):
    if not value:
        return None
    if isinstance(value, str):
        value = parse_date(value)
    return timezone.make_aware(datetime.combine(value, time.min), family_zone(family)) if value else None


def _range(request, default_hours=12):
    to_at = _dt(request.query_params.get("to")) if request.query_params.get("to") else timezone.now()
    from_at = _dt(request.query_params.get("from")) if request.query_params.get("from") else to_at - timedelta(hours=default_hours)
    if from_at >= to_at:
        raise ValidationError("from must be before to")
    return from_at, to_at


@api_view(["GET", "PATCH", "DELETE"])
def module_detail(request):
    family = _family(request); membership = active_membership(request.user, family); setting = module_setting(family)
    access = PetCareAccess.objects.filter(family=family, membership=membership).first() if setting.enabled else None
    if request.method == "GET":
        return Response({"key": MODULE_KEY, "enabled": setting.enabled, "show_in_main_navigation": setting.show_in_main_navigation, "authorized": bool(access and access.can_care), "can_manage": membership.role in {Membership.Role.OWNER, Membership.Role.ADULT}, "permissions": _access(access) if access else None, "pet_count": PetProfile.objects.filter(family=family, active=True).count() if access else 0})
    require_manager(request.user, family)
    if request.method == "DELETE":
        if request.data.get("confirm") != "DELETE": raise ValidationError({"confirm": "Send DELETE to permanently remove pet-care data."})
        with transaction.atomic():
            PetProfile.objects.filter(family=family).delete(); PetCareAccess.objects.filter(family=family).delete(); FamilyModuleSetting.objects.filter(family=family, module_key=MODULE_KEY).delete()
        return Response(status=204)
    setting = set_module(request.user, family, enabled=bool(request.data.get("enabled", setting.enabled)), show_in_main_navigation=request.data.get("show_in_main_navigation"))
    return Response({"key": MODULE_KEY, "enabled": setting.enabled, "show_in_main_navigation": setting.show_in_main_navigation})


@api_view(["GET", "PUT"])
def care_circle(request):
    family = _family(request); require_manager(request.user, family); require_module(family)
    if request.method == "PUT": set_care_circle(request.user, family, request.data.get("care_circle", []))
    existing = {row.membership_id: row for row in PetCareAccess.objects.filter(family=family).select_related("membership__user")}
    rows = []
    for membership in Membership.objects.filter(family=family).select_related("user").order_by("display_name", "id"):
        row = existing.get(membership.id)
        rows.append(_access(row) if row else {"id": f"available-{membership.id}", "membership": str(membership.id), "display_name": membership.display_name or membership.user.get_username(), "role": membership.role, "can_care": False, "health_manage": False, "remind_medications": True, "remind_prevention": True})
    return Response({"care_circle": rows})


@api_view(["GET", "POST"])
def pet_profiles(request):
    family = _family(request); require_module(family); pet_access(request.user, family)
    if request.method == "GET": return Response({"pets": [_profile(x) for x in PetProfile.objects.filter(family=family, active=True)]})
    require_manager(request.user, family)
    allowed = ["name","species","breed","sex","birth_date","adoption_date","color_description","microchip_id","insurance_provider","insurance_number","primary_vet_name","primary_vet_phone","emergency_contact_name","emergency_contact_phone","allergies","important_notes","quick_actions"]
    if not request.data.get("name") or not request.data.get("species"): raise ValidationError("name and species are required")
    data = {k: request.data[k] for k in allowed if k in request.data}; row = PetProfile.objects.create(family=family, created_by=request.user, **data)
    return Response(_profile(row), status=201)


@api_view(["GET", "PATCH", "DELETE"])
def pet_detail(request, pet_id):
    pet = _pet(request, pet_id)
    if request.method == "GET": return Response(_profile(pet))
    require_manager(request.user, pet.family)
    if request.method == "DELETE": pet.active=False; pet.save(update_fields=["active","updated_at"]); return Response(status=204)
    for key in ["name","species","breed","sex","birth_date","adoption_date","color_description","microchip_id","insurance_provider","insurance_number","primary_vet_name","primary_vet_phone","emergency_contact_name","emergency_contact_phone","allergies","important_notes","quick_actions","active"]:
        if key in request.data: setattr(pet, key, request.data[key] or None if key in {"birth_date","adoption_date"} else request.data[key])
    pet.save(); return Response(_profile(pet))


@api_view(["GET", "POST"])
def pet_care(request, pet_id):
    pet = _pet(request, pet_id)
    if request.method == "POST":
        s=CareInput(data=request.data); s.is_valid(raise_exception=True); row, created=record_care(pet, request.user, **s.validated_data); return Response(_care(row), status=201 if created else 200)
    a,b=_range(request,24); summary=care_summary(pet,a,b); return Response({"pet":_profile(pet,False),"summary":summary,"events":summary["timeline"]})


@api_view(["PATCH", "DELETE"])
def pet_care_detail(request, log_id):
    row=PetCareLog.objects.select_related("pet__family").filter(pk=log_id).first()
    if not row: raise NotFound()
    membership,_=pet_access(request.user,row.family)
    if row.created_by_id!=request.user.id and membership.role not in {Membership.Role.OWNER,Membership.Role.ADULT}: raise PermissionDenied()
    if request.method=="DELETE": row.delete(); return Response(status=204)
    if "occurred_at" in request.data: row.occurred_at=_dt(request.data["occurred_at"],False)
    if "ended_at" in request.data: row.ended_at=_dt(request.data["ended_at"])
    if row.ended_at and row.ended_at<row.occurred_at: raise ValidationError({"ended_at":"End must be after start."})
    if "value" in request.data: row.value=request.data.get("value") or {}
    row.save(); return Response(_care(row))


@api_view(["GET", "POST"])
def pet_health_events(request, pet_id):
    pet=_pet(request,pet_id,health=request.method=="POST")
    if request.method=="GET": return Response({"events":[_health(x) for x in pet.health_events.all()[:300]]})
    if not request.data.get("title"): raise ValidationError({"title":"required"})
    row=PetHealthEvent.objects.create(family=pet.family,pet=pet,kind=request.data.get("kind",PetHealthEvent.Kind.OTHER),title=request.data["title"][:180],occurred_at=_dt(request.data["occurred_at"]) if request.data.get("occurred_at") else None,next_due_at=_dt(request.data["next_due_at"]) if request.data.get("next_due_at") else None,provider_name=str(request.data.get("provider_name") or "")[:180],note=str(request.data.get("note") or "")[:8000],created_by=request.user)
    return Response(_health(row),status=201)


@api_view(["PATCH", "DELETE"])
def pet_health_event_detail(request,event_id):
    row=PetHealthEvent.objects.select_related("pet__family").filter(pk=event_id).first()
    if not row: raise NotFound()
    pet_access(request.user,row.family,health=True)
    if request.method=="DELETE": row.delete(); return Response(status=204)
    for k in ["kind","title","provider_name","note"]:
        if k in request.data: setattr(row,k,request.data[k])
    for k in ["occurred_at","next_due_at"]:
        if k in request.data: setattr(row,k,_dt(request.data[k]) if request.data[k] else None)
    row.save(); return Response(_health(row))


@api_view(["GET", "POST"])
def pet_medications(request,pet_id):
    pet=_pet(request,pet_id,health=request.method=="POST")
    if request.method=="GET": return Response({"medications":[_med(x,True) for x in pet.medications.prefetch_related("doses").all()]})
    if not request.data.get("name"): raise ValidationError({"name":"required"})
    row=PetMedication.objects.create(family=pet.family,pet=pet,name=str(request.data["name"])[:180],instruction_text=str(request.data.get("instruction_text") or "")[:8000],dose_value=request.data.get("dose_value") or None,dose_unit=str(request.data.get("dose_unit") or "")[:40],schedule=request.data.get("schedule") if isinstance(request.data.get("schedule"),dict) else {},starts_at=_dt(request.data["starts_at"]) if request.data.get("starts_at") else timezone.now(),ends_at=_dt(request.data["ends_at"]) if request.data.get("ends_at") else None,prescribing_provider=str(request.data.get("prescribing_provider") or "")[:180],note=str(request.data.get("note") or "")[:8000],created_by=request.user)
    return Response(_med(row),status=201)


@api_view(["PATCH", "DELETE"])
def pet_medication_detail(request,medication_id):
    row=PetMedication.objects.select_related("pet__family").filter(pk=medication_id).first()
    if not row: raise NotFound()
    pet_access(request.user,row.family,health=True)
    if request.method=="DELETE": row.active=False; row.save(update_fields=["active","updated_at"]); return Response(status=204)
    for k in ["name","instruction_text","dose_value","dose_unit","schedule","active","prescribing_provider","note"]:
        if k in request.data: setattr(row,k,request.data[k])
    for k in ["starts_at","ends_at"]:
        if k in request.data: setattr(row,k,_dt(request.data[k]) if request.data[k] else None)
    row.save(); return Response(_med(row,True))


@api_view(["POST"])
def pet_medication_dose(request,medication_id):
    med=PetMedication.objects.select_related("pet__family").filter(pk=medication_id,active=True).first()
    if not med: raise NotFound()
    pet_access(request.user,med.family)
    state=request.data.get("state",PetMedicationDose.State.GIVEN)
    if state not in PetMedicationDose.State.values: raise ValidationError({"state":"invalid"})
    given=_dt(request.data["given_at"]) if request.data.get("given_at") else (timezone.now() if state==PetMedicationDose.State.GIVEN else None)
    row=PetMedicationDose.objects.create(medication=med,scheduled_for=_dt(request.data["scheduled_for"]) if request.data.get("scheduled_for") else None,given_at=given,state=state,given_by=request.user,note=str(request.data.get("note") or "")[:4000])
    return Response({"id":str(row.id),"medication":str(med.id),"state":row.state,"scheduled_for":row.scheduled_for,"given_at":row.given_at,"given_by":row.given_by_id,"note":row.note},status=201)


@api_view(["GET", "POST"])
def pet_weights(request,pet_id):
    pet=_pet(request,pet_id,health=request.method=="POST")
    if request.method=="GET": return Response({"weights":[{"id":str(x.id),"measured_at":x.measured_at,"weight_kg":str(x.weight_kg),"source":x.source,"note":x.note} for x in pet.weights.all()[:300]]})
    try: weight=Decimal(str(request.data.get("weight_kg")))
    except (InvalidOperation,TypeError): raise ValidationError({"weight_kg":"invalid"})
    if weight<=0: raise ValidationError({"weight_kg":"invalid"})
    row=PetWeightMeasurement.objects.create(family=pet.family,pet=pet,measured_at=_dt(request.data["measured_at"]) if request.data.get("measured_at") else timezone.now(),weight_kg=weight,source=str(request.data.get("source") or "")[:120],note=str(request.data.get("note") or "")[:4000],created_by=request.user)
    return Response({"id":str(row.id),"measured_at":row.measured_at,"weight_kg":str(row.weight_kg),"source":row.source,"note":row.note},status=201)


@api_view(["GET", "POST"])
def pet_observations(request,pet_id):
    pet=_pet(request,pet_id)
    if request.method=="GET": return Response({"observations":[{"id":str(x.id),"observed_at":x.observed_at,"category":x.category,"severity":x.severity,"note":x.note} for x in pet.observations.all()[:300]]})
    if not request.data.get("note"): raise ValidationError({"note":"required"})
    row=PetObservation.objects.create(family=pet.family,pet=pet,observed_at=_dt(request.data["observed_at"]) if request.data.get("observed_at") else timezone.now(),category=request.data.get("category",PetObservation.Category.OTHER),severity=request.data.get("severity","") or "",note=str(request.data["note"])[:8000],created_by=request.user)
    return Response({"id":str(row.id),"observed_at":row.observed_at,"category":row.category,"severity":row.severity,"note":row.note},status=201)


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
def pet_documents(request,pet_id):
    pet=_pet(request,pet_id,health=request.method=="POST")
    if request.method=="GET": return Response({"documents":[_doc(x) for x in pet.documents.all()[:300]]})
    upload=request.FILES.get("file")
    if not upload: raise ValidationError({"file":"A photo/image/PDF is required."})
    try: prepared=prepare_pet_upload(upload)
    except ValueError as exc: raise ValidationError({"file":str(exc)}) from exc
    duplicate=PetDocument.objects.filter(pet=pet,sha256=prepared["sha256"]).first()
    if duplicate and str(request.data.get("force","")).lower() not in {"1","true","yes"}: return Response({"possible_duplicate":str(duplicate.id),"document":_doc(duplicate)},status=409)
    row=PetDocument.objects.create(family=pet.family,pet=pet,kind=request.data.get("kind") or PetDocument.Kind.OTHER,title=str(request.data.get("title") or prepared["filename"] or "Dokument")[:180],filename=prepared["filename"],content_type=prepared["content_type"],content=prepared["content"],sha256=prepared["sha256"],extraction_status=PetDocument.ExtractionStatus.QUEUED,extraction_data={"warnings":prepared["warnings"]},created_by=request.user)
    return Response(_doc(row),status=201)


@api_view(["GET", "PATCH", "DELETE"])
def pet_document_detail(request,document_id):
    row=PetDocument.objects.select_related("pet__family").filter(pk=document_id).first()
    if not row: raise NotFound()
    pet_access(request.user,row.family,health=True)
    if request.method=="DELETE": row.delete(); return Response(status=204)
    if request.method=="PATCH":
        for k in ["title","provider_name","pinned"]:
            if k in request.data: setattr(row,k,request.data[k])
        if request.data.get("kind") in PetDocument.Kind.values: row.kind=request.data["kind"]
        if "occurred_at" in request.data: row.occurred_at=serializers.DateField(allow_null=True).run_validation(request.data["occurred_at"])
        row.save(); return Response(_doc(row))
    if request.query_params.get("download")=="1":
        response=HttpResponse(bytes(row.content),content_type=row.content_type or "application/octet-stream"); response["Content-Disposition"]=f'attachment; filename="{row.filename.replace(chr(34),"")}"'; response["Cache-Control"]="private, no-store"; response["X-Content-Type-Options"]="nosniff"; return response
    return Response(_doc(row))


@api_view(["POST"])
def pet_document_apply(request,document_id):
    doc=PetDocument.objects.select_related("pet__family").filter(pk=document_id).first()
    if not doc: raise NotFound()
    pet_access(request.user,doc.family,health=True)
    if doc.extraction_status not in {PetDocument.ExtractionStatus.REVIEW,PetDocument.ExtractionStatus.READY}: raise ValidationError({"document":"Extraction is not ready for review."})
    actions=request.data.get("actions") or []; reviewed=request.data.get("reviewed") or {}
    if not isinstance(actions,list) or not isinstance(reviewed,dict): raise ValidationError("actions/reviewed invalid")
    fields={**(doc.extraction_data or {}),**reviewed}; pet=doc.pet; created={}
    with transaction.atomic():
        if "health_event" in actions:
            title=str(fields.get("health_title") or fields.get("vaccination") or doc.title).strip()[:180]
            kind=fields.get("health_kind") or (PetHealthEvent.Kind.VACCINATION if doc.kind==PetDocument.Kind.VACCINATION else PetHealthEvent.Kind.OTHER)
            if kind not in PetHealthEvent.Kind.values: kind=PetHealthEvent.Kind.OTHER
            row=PetHealthEvent.objects.create(family=pet.family,pet=pet,kind=kind,title=title or "Gesundheitsereignis",occurred_at=_date_aware(fields.get("occurred_at"),pet.family),next_due_at=_date_aware(fields.get("next_due_at"),pet.family),provider_name=str(fields.get("provider_name") or doc.provider_name)[:180],note=str(fields.get("health_note") or "")[:8000],source=PetHealthEvent.Source.DOCUMENT,source_document=doc,created_by=request.user); created["health_event"]=str(row.id)
        if "medication" in actions:
            name=str(fields.get("medication_name") or "").strip()
            if not name: raise ValidationError({"reviewed.medication_name":"Confirm the medication name before creating a plan."})
            try: dose=Decimal(str(fields.get("dose_value"))) if fields.get("dose_value") not in (None,"") else None
            except InvalidOperation as exc: raise ValidationError({"reviewed.dose_value":"Invalid confirmed dose value."}) from exc
            schedule=fields.get("schedule") if isinstance(fields.get("schedule"),dict) else {}
            row=PetMedication.objects.create(family=pet.family,pet=pet,name=name[:180],instruction_text=str(fields.get("instruction_text") or fields.get("medication_text") or "")[:8000],dose_value=dose,dose_unit=str(fields.get("dose_unit") or "")[:40],schedule=schedule,starts_at=timezone.now(),active=True,prescribing_provider=str(fields.get("provider_name") or doc.provider_name)[:180],source_document=doc,created_by=request.user); created["medication"]=str(row.id)
        if "weight" in actions:
            try: weight=Decimal(str(fields.get("weight_kg")))
            except (InvalidOperation,TypeError) as exc: raise ValidationError({"reviewed.weight_kg":"Confirm a valid weight before importing."}) from exc
            row=PetWeightMeasurement.objects.create(family=pet.family,pet=pet,measured_at=_date_aware(fields.get("occurred_at"),pet.family) or timezone.now(),weight_kg=weight,source="document",source_document=doc,created_by=request.user); created["weight"]=str(row.id)
        if "microchip" in actions:
            chip=str(fields.get("microchip_id") or "").strip()
            if not chip: raise ValidationError({"reviewed.microchip_id":"Confirm a chip number before importing."})
            pet.microchip_id=chip[:120]; pet.save(update_fields=["microchip_id","updated_at"]); created["microchip"]=pet.microchip_id
        if "expense" in actions:
            payer=Membership.objects.filter(pk=fields.get("paid_by"),family=pet.family).first()
            if not payer: raise ValidationError({"reviewed.paid_by":"Choose who paid before creating the expense."})
            try: total=Decimal(str(fields.get("total")))
            except (InvalidOperation,TypeError) as exc: raise ValidationError({"reviewed.total":"Confirm the invoice total before creating the expense."}) from exc
            expense=Expense.objects.create(family=pet.family,title=(str(fields.get("provider_name") or doc.provider_name or doc.title)+f" · {pet.name}")[:180],merchant=str(fields.get("provider_name") or doc.provider_name)[:180],occurred_at=_date_aware(fields.get("occurred_at"),pet.family) or timezone.now(),total_amount=total,currency=str(fields.get("currency") or "EUR")[:3],paid_by=payer,created_by=request.user,source=Expense.Source.RECEIPT,notes=f"Haustier: {pet.name} · Quelldokument {doc.id}"); created["expense"]=str(expense.id)
        doc.extraction_status=PetDocument.ExtractionStatus.READY; doc.extraction_data=fields; doc.save(update_fields=["extraction_status","extraction_data","updated_at"])
    return Response({"document":_doc(doc),"created":created})


@api_view(["POST"])
def pet_vet_event(request,pet_id):
    pet=_pet(request,pet_id,health=True); starts=_dt(request.data.get("starts_at"),False); ends=_dt(request.data["ends_at"]) if request.data.get("ends_at") else None
    if ends and ends<starts: raise ValidationError({"ends_at":"End must be after start."})
    provider=str(request.data.get("provider_name") or pet.primary_vet_name or "")[:180]
    event=FamilyEvent.objects.create(family=pet.family,type="pet.vet_visit",title=f"Tierarzttermin · {pet.name}"[:200],starts_at=starts,ends_at=ends,actionable=True,payload={"location":str(request.data.get("location") or provider)[:240],"description":str(request.data.get("note") or "")[:2000],"pet_id":str(pet.id),"pet_name":pet.name,"url":f"/?page=pets&pet={pet.id}"})
    PetHealthEvent.objects.create(family=pet.family,pet=pet,kind=PetHealthEvent.Kind.VET,title="Tierarzttermin",next_due_at=starts,provider_name=provider,note=str(request.data.get("note") or "")[:8000],source=PetHealthEvent.Source.CALENDAR,created_by=request.user)
    return Response({"id":str(event.id),"title":event.title,"starts_at":event.starts_at,"ends_at":event.ends_at},status=201)


@api_view(["GET", "POST"])
def pet_vet_questions(request,pet_id):
    pet=_pet(request,pet_id)
    if request.method=="GET": return Response({"questions":[{"id":str(x.id),"question":x.question,"answered_at":x.answered_at,"answer_note":x.answer_note} for x in pet.vet_questions.all()[:200]]})
    question=str(request.data.get("question") or "").strip()
    if not question: raise ValidationError({"question":"required"})
    row=PetVetQuestion.objects.create(family=pet.family,pet=pet,question=question[:4000],created_by=request.user); return Response({"id":str(row.id),"question":row.question,"answered_at":None,"answer_note":""},status=201)


@api_view(["PATCH", "DELETE"])
def pet_vet_question_detail(request,question_id):
    row=PetVetQuestion.objects.select_related("pet__family").filter(pk=question_id).first()
    if not row: raise NotFound()
    membership,_=pet_access(request.user,row.family)
    if request.method=="DELETE":
        if row.created_by_id!=request.user.id and membership.role not in {Membership.Role.OWNER,Membership.Role.ADULT}: raise PermissionDenied()
        row.delete(); return Response(status=204)
    if "question" in request.data: row.question=str(request.data["question"])[:4000]
    if "answered_at" in request.data: row.answered_at=_dt(request.data["answered_at"]) if request.data["answered_at"] else None
    if "answer_note" in request.data: row.answer_note=str(request.data["answer_note"])[:8000]
    row.save(); return Response({"id":str(row.id),"question":row.question,"answered_at":row.answered_at,"answer_note":row.answer_note})


@api_view(["GET", "POST"])
def pet_handover(request,pet_id):
    pet=_pet(request,pet_id)
    if request.method=="POST":
        start=_dt(request.data.get("from_at"),False); end=_dt(request.data.get("to_at"),False)
        if start>=end: raise ValidationError("from must be before to")
        row=PetHandoverNote.objects.create(family=pet.family,pet=pet,from_at=start,to_at=end,note=str(request.data.get("note") or "")[:4000],created_by=request.user); return Response({"id":str(row.id),"from_at":row.from_at,"to_at":row.to_at,"note":row.note},status=201)
    start,end=_range(request,12); notes=pet.handover_notes.filter(to_at__gte=start,from_at__lte=end)[:50]
    return Response({"pet":_profile(pet,False),"summary":care_summary(pet,start,end),"notes":[{"id":str(x.id),"from_at":x.from_at,"to_at":x.to_at,"note":x.note,"created_by":x.created_by_id} for x in notes]})


@api_view(["GET"])
def pet_emergency_card(request,pet_id):
    pet=_pet(request,pet_id,health=True); payload=emergency_card(pet,include_insurance=request.query_params.get("insurance")=="1")
    if request.query_params.get("format")=="html":
        meds="".join(f"<li>{html.escape(x['name'])}: {html.escape(x.get('instruction_text') or '')}</li>" for x in payload.get("active_medications",[])); contact=payload.get("emergency_contact") or {}; insurance=payload.get("insurance")
        body=f"<!doctype html><meta charset='utf-8'><title>Notfallkarte {html.escape(pet.name)}</title><h1>Notfallkarte · {html.escape(pet.name)}</h1><p>{html.escape(pet.species)} · {html.escape(pet.breed)}</p><p><strong>Mikrochip:</strong> {html.escape(payload.get('microchip_id') or '–')}</p><p><strong>Tierarzt:</strong> {html.escape(pet.primary_vet_name or '–')} · {html.escape(pet.primary_vet_phone or '')}</p><p><strong>Notfallkontakt:</strong> {html.escape(contact.get('name') or '–')} · {html.escape(contact.get('phone') or '')}</p><p><strong>Allergien/Hinweise:</strong> {html.escape(pet.allergies or '–')} {html.escape(pet.important_notes or '')}</p><h2>Aktive Medikamente</h2><ul>{meds or '<li>–</li>'}</ul>"+(f"<p><strong>Versicherung:</strong> {html.escape(insurance.get('provider') or '')} {html.escape(insurance.get('number') or '')}</p>" if insurance else "")
        response=HttpResponse(body,content_type="text/html; charset=utf-8"); response["Cache-Control"]="private, no-store"; return response
    return Response(payload)


@api_view(["GET"])
def pet_report(request,pet_id):
    pet=_pet(request,pet_id,health=True); membership,_=pet_access(request.user,pet.family,health=True); start,end=_range(request,24*30); sections=[x for x in request.query_params.get("sections","").split(",") if x]; payload=report_payload(pet,start,end,sections); fmt=request.query_params.get("format","json")
    if fmt=="csv": audit_report(pet,membership,"csv",payload["sections"],start,end); response=HttpResponse(report_csv(payload),content_type="text/csv; charset=utf-8"); response["Content-Disposition"]=f'attachment; filename="pet-report-{pet.id}.csv"'; response["Cache-Control"]="private, no-store"; return response
    if fmt=="html":
        audit_report(pet,membership,"html",payload["sections"],start,end); parts=[f"<!doctype html><meta charset='utf-8'><title>Tierarzt-Bericht {html.escape(pet.name)}</title><h1>Tierarzt-Bericht · {html.escape(pet.name)}</h1><p>{html.escape(payload['from_at'])} – {html.escape(payload['to_at'])}</p>"]
        for key,title in [("medications","Medikamente"),("observations","Beobachtungen"),("weights","Gewicht"),("health","Gesundheit"),("questions","Fragen"),("documents","Dokumente")]:
            if key in payload: parts.append(f"<h2>{title}</h2><pre>{html.escape(json.dumps(payload[key],ensure_ascii=False,indent=2))}</pre>")
        if "care" in payload: parts.append("<h2>Versorgung</h2><pre>"+html.escape(json.dumps(payload["care"],ensure_ascii=False,indent=2))+"</pre>")
        parts.append("<p><small>FamilyOS dokumentiert gespeicherte Angaben und stellt keine veterinärmedizinische Diagnose.</small></p>"); response=HttpResponse("".join(parts),content_type="text/html; charset=utf-8"); response["Cache-Control"]="private, no-store"; return response
    return Response(payload)


@api_view(["GET", "POST"])
def pet_shares(request,pet_id):
    pet=_pet(request,pet_id,health=True)
    if request.method=="GET": return Response({"shares":[{"id":str(x.id),"permissions":x.permissions,"starts_at":x.starts_at,"expires_at":x.expires_at,"revoked_at":x.revoked_at,"last_access_at":x.last_access_at,"label":x.label} for x in pet.care_shares.all()[:100]]})
    expires=_dt(request.data.get("expires_at"),False); starts=_dt(request.data["starts_at"]) if request.data.get("starts_at") else timezone.now(); share,raw=create_share(request.user,pet,permissions=request.data.get("permissions") if isinstance(request.data.get("permissions"),dict) else {},starts_at=starts,expires_at=expires,label=str(request.data.get("label") or ""))
    return Response({"id":str(share.id),"token":raw,"url":f"/api/pets/share/{raw}/","permissions":share.permissions,"starts_at":share.starts_at,"expires_at":share.expires_at,"label":share.label},status=201)


@api_view(["POST"])
def pet_share_revoke(request,share_id):
    row=PetCareShare.objects.select_related("pet__family").filter(pk=share_id).first()
    if not row: raise NotFound()
    pet_access(request.user,row.family,health=True); row.revoked_at=timezone.now(); row.save(update_fields=["revoked_at","updated_at"]); return Response({"revoked":True,"id":str(row.id)})


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@throttle_classes([PetShareThrottle])
def public_pet_share(request,token):
    share=share_from_token(token)
    if not share: raise NotFound("This pet-care share is expired or revoked.")
    pet=share.pet; require_module(pet.family); permissions=share.permissions or {}
    if request.method=="POST":
        if not permissions.get("write_care"): raise PermissionDenied("This share is read-only.")
        s=CareInput(data=request.data); s.is_valid(raise_exception=True); kind=s.validated_data["kind"]
        if kind not in PUBLIC_CARE_KINDS: raise PermissionDenied("This care action cannot be recorded from an external share.")
        row,created=record_care(pet,None,external_caregiver=str(request.data.get("caregiver_name") or share.label or "Tiersitter")[:120],**s.validated_data); return Response(_care(row),status=201 if created else 200)
    payload={"pet":_profile(pet,False),"expires_at":share.expires_at,"permissions":permissions}
    if permissions.get("care"): payload["care"]=care_summary(pet,timezone.now()-timedelta(hours=24),timezone.now())
    if permissions.get("medications"): payload["medications"]=[_med(x) for x in pet.medications.filter(active=True)]
    if permissions.get("vet_contact"): payload["vet"]={"name":pet.primary_vet_name,"phone":pet.primary_vet_phone}
    if permissions.get("emergency"): payload["emergency"]=emergency_card(pet,include_insurance=False)
    response=Response(payload); response["Cache-Control"]="private, no-store"; return response
