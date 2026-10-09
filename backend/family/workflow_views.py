import uuid

from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Membership, TaskList, TaskWorkflowColumn
from .serializers import WorkflowColumnSerializer
from .views import family_ids


def manage(user, task_list):
    if not Membership.objects.filter(family=task_list.family, user=user, role__in=["owner", "adult"]).exists():
        raise PermissionDenied("Only owners/adults can configure workflows.")


class WorkflowColumnViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowColumnSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return TaskWorkflowColumn.objects.filter(task_list__family_id__in=family_ids(self.request.user), task_list__family__status="active")

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        column = self.get_object()
        task_list = TaskList.objects.select_for_update().get(pk=column.task_list_id)
        manage(request.user, task_list)
        serializer = self.get_serializer(column, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        archived = values.get("archived", column.archived)
        terminal = values.get("is_terminal", column.is_terminal)
        if (archived or terminal != column.is_terminal) and column.tasks.exists():
            raise ValidationError("Move tasks to another column first.")
        others = task_list.workflow_columns.filter(archived=False).exclude(pk=column.pk)
        if not others.filter(is_terminal=True).exists() and (archived or not terminal):
            raise ValidationError("At least one done column is required.")
        if not others.filter(is_terminal=False).exists() and (archived or terminal):
            raise ValidationError("At least one open column is required.")
        if not archived and column.archived and others.count()>=8:
            raise ValidationError("Maximum eight active columns.")
        serializer.save()
        return Response(serializer.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        column = self.get_object()
        TaskList.objects.select_for_update().get(pk=column.task_list_id)
        manage(request.user, column.task_list)
        if column.tasks.exists():
            raise ValidationError("Move tasks to another column first.")
        others = column.task_list.workflow_columns.filter(archived=False).exclude(pk=column.pk)
        if not others.filter(is_terminal=column.is_terminal).exists():
            raise ValidationError("Keep at least one open and one done column.")
        column.archived = True
        column.save(update_fields=["archived", "updated_at"])
        return Response(status=204)


@transaction.atomic
def list_columns(view, request):
    task_list = view.get_object()
    TaskList.objects.select_for_update().get(pk=task_list.pk)
    if request.method == "GET":
        return Response(WorkflowColumnSerializer(task_list.workflow_columns.filter(archived=False), many=True).data)
    manage(request.user, task_list)
    if not task_list.workflow_enabled or task_list.workflow_columns.filter(archived=False).count()>=8:
        raise ValidationError("Enable the workflow; maximum eight active columns.")
    serializer = WorkflowColumnSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(task_list=task_list, key=uuid.uuid4().hex)
    return Response(serializer.data, status=201)
