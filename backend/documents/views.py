import json
from pathlib import Path
from uuid import UUID

from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from family.models import Membership

from .access import active_membership, can_manage_document, can_view_document, visible_documents
from .models import Document, DocumentAccess, DocumentLink
from .serializers import document_payload
from .storage import canonicalize_upload, open_canonical, remove_canonical, store_canonical


def _truthy(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


def _date(value):
    if value is None or value == "":
        return None
    parsed = parse_date(str(value))
    if not parsed:
        raise ValidationError({"document_date": "Ungültiges Datum."})
    return parsed


def _json_list(value, field):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Ungültiges JSON."}) from exc
    if not isinstance(decoded, list):
        raise ValidationError({field: "Eine Liste wird erwartet."})
    return decoded


def _prepare_access(family_id, value):
    rows = []
    for raw in _json_list(value, "access"):
        if not isinstance(raw, dict) or not raw.get("membership"):
            raise ValidationError({"access": "Jeder Zugriff benötigt eine Mitgliedschaft."})
        membership = Membership.objects.filter(id=raw["membership"], family_id=family_id).first()
        if not membership:
            raise ValidationError({"access": "Mitgliedschaft gehört nicht zu dieser Familie."})
        can_manage = bool(raw.get("can_manage", False))
        rows.append((membership, bool(raw.get("can_view", True)) or can_manage, can_manage))
    return rows


def _prepare_links(value):
    rows = []
    allowed = {choice for choice, _ in DocumentLink.DomainType.choices}
    for raw in _json_list(value, "links"):
        if not isinstance(raw, dict) or raw.get("domain_type") not in allowed or not raw.get("object_id"):
            raise ValidationError({"links": "Ungültige Domain-Verknüpfung."})
        try:
            object_id = UUID(str(raw["object_id"]))
        except ValueError as exc:
            raise ValidationError({"links": "Ungültige Objekt-ID."}) from exc
        rows.append((raw["domain_type"], object_id, str(raw.get("relationship") or "source")[:48]))
    return rows


def _replace_access(document, rows):
    document.access_entries.all().delete()
    DocumentAccess.objects.bulk_create([
        DocumentAccess(document=document, membership=membership, can_view=can_view, can_manage=can_manage)
        for membership, can_view, can_manage in rows
        if membership.id != document.owner_membership_id
    ])


def _replace_links(document, rows):
    document.domain_links.all().delete()
    DocumentLink.objects.bulk_create([
        DocumentLink(document=document, domain_type=domain_type, object_id=object_id, relationship=relationship)
        for domain_type, object_id, relationship in rows
    ])


def _document_or_404(user, document_id, require_manage=False):
    document = Document.objects.select_related("family", "owner_membership").prefetch_related(
        "access_entries", "domain_links"
    ).filter(id=document_id).first()
    if not document:
        raise Http404
    allowed = can_manage_document(user, document) if require_manage else can_view_document(user, document)
    if not allowed or (document.archived_at and not can_manage_document(user, document)):
        # Privacy boundary: callers cannot distinguish a missing UUID from an
        # existing document they are not allowed to know about.
        raise Http404
    return document


@api_view(["GET", "POST"])
def document_collection(request):
    if request.method == "GET":
        family_id = request.query_params.get("family")
        if not family_id:
            return Response({"detail": "family is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not active_membership(request.user, family_id):
            raise Http404
        documents = visible_documents(request.user, family_id).select_related("owner_membership").prefetch_related(
            "access_entries", "domain_links"
        )
        return Response([document_payload(document, request.user) for document in documents])

    family_id = request.data.get("family")
    membership = active_membership(request.user, family_id)
    if not membership:
        raise Http404
    upload = request.FILES.get("file")
    if not upload:
        raise ValidationError({"file": "Datei fehlt."})
    visibility = request.data.get("visibility", Document.Visibility.PRIVATE)
    if visibility not in {choice for choice, _ in Document.Visibility.choices}:
        raise ValidationError({"visibility": "Ungültige Sichtbarkeit."})
    access_rows = _prepare_access(family_id, request.data.get("access"))
    link_rows = _prepare_links(request.data.get("links"))
    canonical = canonicalize_upload(upload)

    duplicate = visible_documents(request.user, family_id).filter(sha256=canonical.sha256).first()
    if duplicate and not _truthy(request.data.get("allow_duplicate")):
        return Response(
            {
                "code": "duplicate_document",
                "detail": "Dieses Dokument scheint bereits vorhanden zu sein.",
                "existing_document_id": str(duplicate.id),
            },
            status=status.HTTP_409_CONFLICT,
        )

    raw_title = str(request.data.get("title") or Path(getattr(upload, "name", "") or "").stem or "Dokument").strip()
    document = Document(
        family_id=family_id,
        kind=str(request.data.get("kind") or "generic").strip()[:64] or "generic",
        title=raw_title[:240],
        document_date=_date(request.data.get("document_date")),
        correspondent=str(request.data.get("correspondent") or "").strip()[:180],
        visibility=visibility,
        owner_membership=membership,
        mime_type=canonical.mime_type,
        size=len(canonical.content),
        sha256=canonical.sha256,
        page_count=canonical.page_count,
        pinned=_truthy(request.data.get("pinned")),
        created_by=request.user,
    )
    key = store_canonical(document.id, canonical)
    document.canonical_file = key
    try:
        with transaction.atomic():
            document.save(force_insert=True)
            _replace_access(document, access_rows)
            _replace_links(document, link_rows)
    except Exception:
        remove_canonical(key)
        raise
    document = _document_or_404(request.user, document.id)
    return Response(document_payload(document, request.user), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
def document_detail(request, document_id):
    document = _document_or_404(request.user, document_id, require_manage=request.method != "GET")
    if request.method == "GET":
        return Response(document_payload(document, request.user))
    if request.method == "DELETE":
        if not document.archived_at:
            document.archived_at = timezone.now()
            document.save(update_fields=["archived_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    updates = []
    if "title" in request.data:
        document.title = str(request.data.get("title") or "").strip()[:240] or "Dokument"
        updates.append("title")
    if "kind" in request.data:
        document.kind = str(request.data.get("kind") or "generic").strip()[:64] or "generic"
        updates.append("kind")
    if "document_date" in request.data:
        document.document_date = _date(request.data.get("document_date"))
        updates.append("document_date")
    if "correspondent" in request.data:
        document.correspondent = str(request.data.get("correspondent") or "").strip()[:180]
        updates.append("correspondent")
    if "visibility" in request.data:
        visibility = request.data.get("visibility")
        if visibility not in {choice for choice, _ in Document.Visibility.choices}:
            raise ValidationError({"visibility": "Ungültige Sichtbarkeit."})
        document.visibility = visibility
        updates.append("visibility")
    if "pinned" in request.data:
        document.pinned = bool(request.data.get("pinned"))
        updates.append("pinned")
    access_rows = _prepare_access(document.family_id, request.data.get("access")) if "access" in request.data else None
    link_rows = _prepare_links(request.data.get("links")) if "links" in request.data else None
    with transaction.atomic():
        if updates:
            document.save(update_fields=[*updates, "updated_at"])
        if access_rows is not None:
            _replace_access(document, access_rows)
        if link_rows is not None:
            _replace_links(document, link_rows)
    document = _document_or_404(request.user, document.id, require_manage=True)
    return Response(document_payload(document, request.user))


@api_view(["GET"])
def document_file(request, document_id):
    document = _document_or_404(request.user, document_id)
    try:
        handle = open_canonical(document.canonical_file)
    except (FileNotFoundError, OSError):
        raise Http404
    extension = "pdf" if document.mime_type == "application/pdf" else "webp"
    response = FileResponse(handle, content_type=document.mime_type, as_attachment=False, filename=f"document-{document.id}.{extension}")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Length"] = str(document.size)
    return response


@api_view(["POST"])
def document_restore(request, document_id):
    document = _document_or_404(request.user, document_id, require_manage=True)
    if document.archived_at:
        document.archived_at = None
        document.save(update_fields=["archived_at", "updated_at"])
    return Response(document_payload(document, request.user))


@api_view(["POST"])
def document_purge(request, document_id):
    document = _document_or_404(request.user, document_id, require_manage=True)
    if not document.archived_at:
        return Response({"detail": "Dokument muss vor dem endgültigen Löschen archiviert werden."}, status=status.HTTP_409_CONFLICT)
    key = document.canonical_file
    remove_canonical(key)
    document.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
