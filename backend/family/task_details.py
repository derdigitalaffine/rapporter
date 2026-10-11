from urllib.parse import urlsplit, urlunsplit

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from documents.access import visible_documents
from documents.models import DocumentLink

from .context_links import (
    ContextLinkError,
    create_context_link,
    list_context_links,
    remove_context_link,
)
from .models import Membership, Task
from .task_detail_models import TaskChecklistItem, TaskExternalLink


def _member(user, task):
    if not Membership.objects.filter(family=task.family, user=user, family__status="active").exists():
        raise PermissionDenied()


def normalize_external_url(value):
    raw = str(value or "").strip()
    if not raw or len(raw) > 2048 or any(ord(char) < 32 for char in raw):
        raise ValidationError({"url": "Enter a valid external URL."})
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError({"url": "Enter a valid external URL."}) from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError({"url": "Only http(s) URLs without embedded credentials are allowed."})
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValidationError({"url": "Local URLs are not allowed."})
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, parsed.fragment))


def serialize_substep(item):
    extracted = item.extracted_task
    return {
        "id": str(item.id),
        "title": item.title,
        "position": item.position,
        "completed": bool(extracted.completed_at) if extracted else bool(item.completed_at),
        "completed_at": extracted.completed_at if extracted else item.completed_at,
        "extracted_task_id": str(extracted.id) if extracted else None,
        "extracted_at": item.extracted_at,
        "editable": extracted is None,
    }


def extended_task_payload(user, task):
    _member(user, task)
    substeps = list(task.checklist_items.select_related("extracted_task").all())
    links = list(task.external_links.all())
    visible_doc_ids = set(visible_documents(user, task.family_id, include_domain_managed=True).values_list("id", flat=True))
    docs = DocumentLink.objects.filter(domain_type=DocumentLink.DomainType.TASK, object_id=task.id, document_id__in=visible_doc_ids).select_related("document")
    context = []
    try:
        rows = list_context_links(user=user, family=task.family, anchor_type="task", anchor_id=task.id, limit=100)
        for row in rows:
            counterpart = row.context if row.source.ref.type == "task" else row.source
            context.append({
                "link_id": str(row.link.id),
                "type": counterpart.ref.type,
                "id": str(counterpart.ref.id),
                "relationship": row.link.relation_key,
                "lifecycle": counterpart.lifecycle,
                "deep_link": counterpart.deep_link,
            })
    except ContextLinkError:
        context = []
    return {
        "substeps": [serialize_substep(item) for item in substeps],
        "external_links": [{"id": str(row.id), "url": row.url, "label": row.label, "position": row.position} for row in links],
        "documents": [{"link_id": str(row.id), "id": str(row.document_id), "title": row.document.title, "kind": row.document.kind} for row in docs],
        "context": context,
        "summary": {
            "substeps_total": len(substeps),
            "substeps_done": sum(1 for item in substeps if (item.extracted_task.completed_at if item.extracted_task else item.completed_at)),
            "link_count": len(links) + docs.count() + len(context),
        },
    }


def add_substep(user, task, *, title, position=None):
    _member(user, task)
    title = str(title or "").strip()
    if not title:
        raise ValidationError({"title": "Substep title is required."})
    if position is None:
        last = task.checklist_items.order_by("-position").values_list("position", flat=True).first()
        position = (last or 0) + 10
    return TaskChecklistItem.objects.create(task=task, title=title[:180], position=position, created_by=user)


def update_substep(user, task, item_id, *, title=None, completed=None, position=None):
    _member(user, task)
    item = task.checklist_items.select_related("extracted_task").filter(pk=item_id).first()
    if not item:
        raise ValidationError({"substep": "Substep not found."})
    if item.extracted_task_id:
        raise ValidationError({"substep": "This substep is backed by a canonical task and must be changed there."})
    fields = []
    if title is not None:
        value = str(title).strip()
        if not value:
            raise ValidationError({"title": "Substep title is required."})
        item.title = value[:180]
        fields.append("title")
    if completed is not None:
        item.completed_at = timezone.now() if bool(completed) else None
        fields.append("completed_at")
    if position is not None:
        item.position = position
        fields.append("position")
    if fields:
        fields.append("updated_at")
        item.save(update_fields=fields)
    return item


@transaction.atomic
def explode_substep(user, task, item_id):
    _member(user, task)
    item = TaskChecklistItem.objects.select_for_update().select_related("extracted_task").filter(task=task, pk=item_id).first()
    if not item:
        raise ValidationError({"substep": "Substep not found."})
    if item.extracted_task_id:
        return item.extracted_task
    child = Task.objects.create(
        family=task.family,
        task_list=task.task_list,
        title=item.title,
        priority=task.priority,
        assignee=task.assignee,
        created_by=user,
        source="substep",
        completed_at=item.completed_at,
    )
    item.extracted_task = child
    item.extracted_at = timezone.now()
    item.completed_at = None
    item.save(update_fields=["extracted_task", "extracted_at", "completed_at", "updated_at"])
    return child


def add_external_link(user, task, *, url, label="", position=None):
    _member(user, task)
    normalized = normalize_external_url(url)
    if position is None:
        last = task.external_links.order_by("-position").values_list("position", flat=True).first()
        position = (last or 0) + 10
    row, created = TaskExternalLink.objects.get_or_create(task=task, url=normalized, defaults={"label": str(label or "")[:120], "position": position, "created_by": user})
    return row, created


def link_document(user, task, document_id):
    _member(user, task)
    document = visible_documents(user, task.family_id, include_domain_managed=True).filter(pk=document_id).first()
    if not document:
        raise ValidationError({"document": "Document is unavailable."})
    return DocumentLink.objects.get_or_create(document=document, domain_type=DocumentLink.DomainType.TASK, object_id=task.id, relationship="reference")


def link_context(user, task, *, context_type, context_id):
    _member(user, task)
    try:
        if context_type == "decision":
            return create_context_link(user=user, family=task.family, source_type="decision", source_id=context_id, context_type="task", context_id=task.id, relation_key="decision.context")
        return create_context_link(user=user, family=task.family, source_type="task", source_id=task.id, context_type=context_type, context_id=context_id, relation_key="context")
    except ContextLinkError as exc:
        raise ValidationError({"context": "Context is unavailable or cannot be linked."}) from exc


def unlink_context(user, task, link_id):
    try:
        remove_context_link(user=user, family=task.family, link_id=link_id)
    except ContextLinkError as exc:
        raise ValidationError({"context": "Context link is unavailable."}) from exc
