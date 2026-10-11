from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from documents.models import DocumentLink

from .models import Membership, Task
from .task_detail_models import TaskExternalLink
from .task_details import (
    add_external_link,
    add_substep,
    explode_substep,
    extended_task_payload,
    link_context,
    link_document,
    serialize_substep,
    unlink_context,
    update_substep,
)
from .serializers import TaskSerializer


def _task(request, task_id):
    task = Task.objects.select_related("family", "task_list", "assignee", "workflow_column").filter(
        pk=task_id,
        family__memberships__user=request.user,
        family__status="active",
    ).exclude(hidden_from_user=request.user).first()
    if not task:
        raise NotFound("Task not found.")
    return task


@api_view(["GET"])
def task_extended(request, task_id):
    return Response(extended_task_payload(request.user, _task(request, task_id)))


@api_view(["POST"])
def task_substeps(request, task_id):
    task = _task(request, task_id)
    item = add_substep(request.user, task, title=request.data.get("title"), position=request.data.get("position"))
    return Response(serialize_substep(item), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
def task_substep_detail(request, task_id, item_id):
    task = _task(request, task_id)
    if request.method == "DELETE":
        item = task.checklist_items.filter(pk=item_id).first()
        if not item:
            raise NotFound("Substep not found.")
        if item.extracted_task_id:
            raise ValidationError({"substep": "Extracted substeps remain as references to their canonical task."})
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    item = update_substep(
        request.user,
        task,
        item_id,
        title=request.data.get("title") if "title" in request.data else None,
        completed=request.data.get("completed") if "completed" in request.data else None,
        position=request.data.get("position") if "position" in request.data else None,
    )
    return Response(serialize_substep(item))


@api_view(["POST"])
def task_substep_explode(request, task_id, item_id):
    task = _task(request, task_id)
    child = explode_substep(request.user, task, item_id)
    return Response(TaskSerializer(child, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def task_external_links(request, task_id):
    task = _task(request, task_id)
    row, created = add_external_link(
        request.user,
        task,
        url=request.data.get("url"),
        label=request.data.get("label", ""),
        position=request.data.get("position"),
    )
    return Response({"id": str(row.id), "url": row.url, "label": row.label, "position": row.position}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["DELETE"])
def task_external_link_detail(request, task_id, link_id):
    task = _task(request, task_id)
    deleted, _ = TaskExternalLink.objects.filter(task=task, pk=link_id).delete()
    if not deleted:
        raise NotFound("External link not found.")
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def task_documents(request, task_id):
    task = _task(request, task_id)
    row, created = link_document(request.user, task, request.data.get("document_id"))
    return Response({"link_id": str(row.id), "document_id": str(row.document_id)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["DELETE"])
def task_document_detail(request, task_id, link_id):
    task = _task(request, task_id)
    deleted, _ = DocumentLink.objects.filter(pk=link_id, domain_type=DocumentLink.DomainType.TASK, object_id=task.id).delete()
    if not deleted:
        raise NotFound("Document link not found.")
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def task_context(request, task_id):
    task = _task(request, task_id)
    row, created = link_context(request.user, task, context_type=request.data.get("type"), context_id=request.data.get("id"))
    return Response({"link_id": str(row.id)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["DELETE"])
def task_context_detail(request, task_id, link_id):
    task = _task(request, task_id)
    unlink_context(request.user, task, link_id)
    return Response(status=status.HTTP_204_NO_CONTENT)
