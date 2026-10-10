import io
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from baby.models import FamilyModuleSetting
from family.models import Family, Membership
from .models import PetCareAccess, PetCareLog, PetDocument, PetMedication, PetProfile, PetReminderDelivery
from .ocr import extract_pet_fields, process_pet_document


class PetCareTests(TestCase):
    def setUp(self):
        User=get_user_model(); self.owner=User.objects.create_user(username="pet-owner",password="test"); self.adult=User.objects.create_user(username="pet-adult",password="test"); self.outsider=User.objects.create_user(username="pet-outsider",password="test")
        self.family=Family.objects.create(name="Pets",slug="pets-test"); self.other_family=Family.objects.create(name="Other",slug="pets-other")
        self.owner_membership=Membership.objects.create(family=self.family,user=self.owner,role=Membership.Role.OWNER,display_name="Owner"); self.adult_membership=Membership.objects.create(family=self.family,user=self.adult,role=Membership.Role.ADULT,display_name="Adult"); Membership.objects.create(family=self.other_family,user=self.outsider,role=Membership.Role.OWNER)
        self.client=APIClient(); self.client.force_authenticate(self.owner)

    def enable(self):
        setting,_=FamilyModuleSetting.objects.get_or_create(family=self.family,module_key="pet_care"); setting.enabled=True; setting.save(update_fields=["enabled","updated_at"])
        PetCareAccess.objects.get_or_create(family=self.family,membership=self.owner_membership,defaults={"can_care":True,"health_manage":True}); return setting

    def pet(self,name="Luna"):
        self.enable(); return PetProfile.objects.create(family=self.family,name=name,species="dog",created_by=self.owner)

    def test_module_is_off_by_default_and_activation_grants_manager_access(self):
        r=self.client.get(f"/api/pets/module/?family={self.family.id}"); self.assertEqual(r.status_code,200); self.assertFalse(r.data["enabled"])
        r=self.client.patch(f"/api/pets/module/?family={self.family.id}",{"enabled":True},format="json"); self.assertEqual(r.status_code,200); self.assertTrue(r.data["enabled"]); self.assertTrue(PetCareAccess.objects.get(family=self.family,membership=self.owner_membership).health_manage)

    def test_care_circle_lists_ungranted_members_and_can_grant_them(self):
        self.enable(); r=self.client.get(f"/api/pets/care-circle/?family={self.family.id}"); adult=next(x for x in r.data["care_circle"] if x["membership"]==str(self.adult_membership.id)); self.assertFalse(adult["can_care"])
        rows=[{"membership":str(self.owner_membership.id),"can_care":True,"health_manage":True},{"membership":str(self.adult_membership.id),"can_care":True,"health_manage":True}]
        self.assertEqual(self.client.put(f"/api/pets/care-circle/?family={self.family.id}",{"care_circle":rows},format="json").status_code,200); self.assertTrue(PetCareAccess.objects.get(membership=self.adult_membership).health_manage)

    def test_two_pets_never_mix_care_and_client_id_is_idempotent(self):
        first=self.pet(); second=PetProfile.objects.create(family=self.family,name="Milo",species="cat",created_by=self.owner); payload={"kind":"feed","client_event_id":"2655ad4e-691d-4f10-89dc-0bc30f52a421","value":{"amount":80}}
        self.assertEqual(self.client.post(f"/api/pets/{first.id}/care/",payload,format="json").status_code,201); self.assertEqual(self.client.post(f"/api/pets/{first.id}/care/",payload,format="json").status_code,200); self.assertEqual(PetCareLog.objects.filter(pet=first).count(),1); self.assertEqual(PetCareLog.objects.filter(pet=second).count(),0)

    def test_care_member_can_give_documented_medication_but_not_change_plan(self):
        pet=self.pet(); PetCareAccess.objects.create(family=self.family,membership=self.adult_membership,can_care=True,health_manage=False); med=PetMedication.objects.create(family=self.family,pet=pet,name="Plan A",starts_at=timezone.now(),created_by=self.owner); client=APIClient(); client.force_authenticate(self.adult)
        self.assertEqual(client.post(f"/api/pets/{pet.id}/medications/",{"name":"New plan"},format="json").status_code,403); dose=client.post(f"/api/pets/medications/{med.id}/dose/",{"state":"given"},format="json"); self.assertEqual(dose.status_code,201); self.assertEqual(dose.data["given_by"],self.adult.id)

    def test_cross_family_pet_is_not_visible(self):
        pet=self.pet(); other=APIClient(); other.force_authenticate(self.outsider); self.assertEqual(other.get(f"/api/pets/profiles/{pet.id}/").status_code,404)

    def test_ocr_only_surfaces_explicit_due_date(self):
        self.assertEqual(extract_pet_fields("Tollwutimpfung 12.03.2026\nNächste Fälligkeit 12.03.2027")["fields"]["next_due_at"],"2027-03-12"); self.assertNotIn("next_due_at",extract_pet_fields("Tollwutimpfung 12.03.2026\nCharge ABC")["fields"])

    def test_document_duplicate_is_reviewed_and_not_silently_applied(self):
        pet=self.pet(); buf=io.BytesIO(); Image.new("RGB",(800,800),"white").save(buf,format="PNG"); upload=SimpleUploadedFile("pass.png",buf.getvalue(),content_type="image/png")
        self.assertEqual(self.client.post(f"/api/pets/{pet.id}/documents/",{"file":upload},format="multipart").status_code,201); doc=PetDocument.objects.get(); self.assertEqual(doc.extraction_status,PetDocument.ExtractionStatus.QUEUED)
        with patch("pets.ocr._ocr_image",return_value="Tollwutimpfung 12.03.2026"): process_pet_document(doc.id)
        doc.refresh_from_db(); self.assertEqual(doc.extraction_status,PetDocument.ExtractionStatus.REVIEW); self.assertFalse(pet.health_events.exists())
        upload=SimpleUploadedFile("pass.png",buf.getvalue(),content_type="image/png"); self.assertEqual(self.client.post(f"/api/pets/{pet.id}/documents/",{"file":upload},format="multipart").status_code,409)

    def test_document_medication_requires_confirmed_name(self):
        pet=self.pet(); doc=PetDocument.objects.create(family=self.family,pet=pet,kind="prescription",title="Plan",filename="plan.pdf",content_type="application/pdf",content=b"%PDF-test",sha256="0"*64,extraction_status=PetDocument.ExtractionStatus.REVIEW,extraction_data={"documented_dose":"5 mg"},created_by=self.owner)
        self.assertEqual(self.client.post(f"/api/pets/documents/{doc.id}/apply/",{"actions":["medication"],"reviewed":{}},format="json").status_code,400); self.assertFalse(pet.medications.exists())

    def test_sitter_share_is_scoped_read_only_and_revocable(self):
        pet=self.pet(); other_pet=PetProfile.objects.create(family=self.family,name="Milo",species="cat",created_by=self.owner); created=self.client.post(f"/api/pets/{pet.id}/shares/",{"expires_at":(timezone.now()+timedelta(days=2)).isoformat(),"permissions":{"care":True}},format="json"); token=created.data["token"]; public=APIClient(); read=public.get(f"/api/pets/share/{token}/"); self.assertEqual(read.data["pet"]["id"],str(pet.id)); self.assertNotEqual(read.data["pet"]["id"],str(other_pet.id)); self.assertEqual(public.post(f"/api/pets/share/{token}/",{"kind":"feed"},format="json").status_code,403); self.client.post(f"/api/pets/shares/{created.data['id']}/revoke/",{},format="json"); self.assertEqual(public.get(f"/api/pets/share/{token}/").status_code,404)

    def test_disabling_module_invalidates_existing_sitter_share(self):
        pet=self.pet(); created=self.client.post(f"/api/pets/{pet.id}/shares/",{"expires_at":(timezone.now()+timedelta(days=1)).isoformat(),"permissions":{"care":True}},format="json"); self.client.patch(f"/api/pets/module/?family={self.family.id}",{"enabled":False},format="json"); self.assertEqual(APIClient().get(f"/api/pets/share/{created.data['token']}/").status_code,404)

    def test_write_share_only_allows_safe_quick_logs(self):
        pet=self.pet(); created=self.client.post(f"/api/pets/{pet.id}/shares/",{"expires_at":(timezone.now()+timedelta(days=1)).isoformat(),"permissions":{"care":True,"write_care":True}},format="json"); public=APIClient(); token=created.data["token"]; self.assertEqual(public.post(f"/api/pets/share/{token}/",{"kind":"feed"},format="json").status_code,201); self.assertEqual(public.post(f"/api/pets/share/{token}/",{"kind":"medication"},format="json").status_code,403)

    def test_report_excludes_documents_by_default(self):
        pet=self.pet(); PetDocument.objects.create(family=self.family,pet=pet,title="Private report",filename="r.pdf",content_type="application/pdf",content=b"x",sha256="1"*64,created_by=self.owner); self.assertNotIn("documents",self.client.get(f"/api/pets/{pet.id}/report/").data); self.assertEqual(self.client.get(f"/api/pets/{pet.id}/report/?sections=documents").data["documents"][0]["title"],"Private report")

    def test_pet_reminders_are_per_member_and_idempotent(self):
        pet=self.pet(); access=PetCareAccess.objects.get(family=self.family,membership=self.owner_membership); access.remind_prevention=False; access.save(update_fields=["remind_prevention","updated_at"]); clock=(timezone.localtime(timezone.now())-timedelta(minutes=1)).strftime("%H:%M"); PetMedication.objects.create(family=self.family,pet=pet,name="Tablette",instruction_text="laut Plan",schedule={"times":[clock]},starts_at=timezone.now()-timedelta(days=1),created_by=self.owner)
        from pets.reminders import process_pet_reminders
        with patch("pets.reminders.send_user_push",return_value={"sent":1,"errors":0}) as push: process_pet_reminders(); process_pet_reminders()
        self.assertEqual(push.call_count,1); self.assertEqual(PetReminderDelivery.objects.filter(membership=self.owner_membership).count(),1)

    def test_vet_questions_and_emergency_contact_stay_private(self):
        pet=self.pet(); pet.emergency_contact_name="Alex"; pet.emergency_contact_phone="+49 123"; pet.save(); self.assertEqual(self.client.post(f"/api/pets/{pet.id}/vet-questions/",{"question":"Ist die Pfote abgeheilt?"},format="json").status_code,201); self.assertEqual(self.client.get(f"/api/pets/{pet.id}/report/?sections=questions").data["questions"][0]["question"],"Ist die Pfote abgeheilt?"); self.assertEqual(self.client.get(f"/api/pets/{pet.id}/emergency-card/").data["emergency_contact"]["name"],"Alex"); other=APIClient(); other.force_authenticate(self.outsider); self.assertEqual(other.get(f"/api/pets/{pet.id}/vet-questions/").status_code,404)

    def test_vet_appointment_is_real_family_calendar_event(self):
        pet=self.pet(); r=self.client.post(f"/api/pets/{pet.id}/vet-event/",{"starts_at":(timezone.now()+timedelta(days=3)).isoformat(),"provider_name":"Praxis"},format="json"); event=self.family.events.get(pk=r.data["id"]); self.assertEqual(event.type,"pet.vet_visit"); self.assertEqual(event.payload["pet_id"],str(pet.id))
