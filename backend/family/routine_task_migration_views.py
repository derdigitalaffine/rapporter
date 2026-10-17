from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Family, Membership, Routine
from .routine_task_migration_models import RoutineTaskMigration
from .routine_task_migration_service import migrate_routine_to_task
from .serializers import RoutineSerializer, TaskSerializer


def _membership(user, family_id):
    try:
        return Membership.objects.select_related("family").filter(
            user=user,
            family_id=family_id,
            family__status=Family.Status.ACTIVE,
        ).first()
    except (ValueError, DjangoValidationError):
        return None


def _task_payload(request, migration):
    return TaskSerializer(migration.task, context={"request": request}).data


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def routine_task_migrations(request):
    family_id = request.query_params.get("family")
    membership = _membership(request.user, family_id)
    if membership is None:
        return Response(
            {"detail": "Familie ist für diesen Benutzer nicht verfügbar."},
            status=status.HTTP_403_FORBIDDEN,
        )
    rows = RoutineTaskMigration.objects.filter(family=membership.family).select_related("task").order_by("created_at")
    return Response({
        "results": [
            {
                "routine_id": str(row.routine_id),
                "task_id": str(row.task_id),
            }
            for row in rows
        ]
    })


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def routine_task_migration_detail(request, routine_id):
    routine = Routine.objects.select_related("family").filter(
        pk=routine_id,
        family__status=Family.Status.ACTIVE,
        family__memberships__user=request.user,
    ).first()
    if routine is None:
        return Response({"detail": "Routine ist nicht verfügbar."}, status=status.HTTP_404_NOT_FOUND)

    migration = RoutineTaskMigration.objects.select_related("task").filter(routine=routine).first()
    if request.method == "GET":
        if migration is None:
            return Response({"migrated": False, "routine_id": str(routine.id)})
        return Response({
            "migrated": True,
            "routine_id": str(routine.id),
            "task_id": str(migration.task_id),
            "task": _task_payload(request, migration),
        })

    current_values = request.data.get("routine") if isinstance(request.data, dict) else None
    if current_values is not None:
        if not isinstance(current_values, dict):
            return Response({"routine": "Expected an object."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = RoutineSerializer(
            routine,
            data=current_values,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        routine = serializer.save()

    try:
        task, created = migrate_routine_to_task(routine=routine, user=request.user)
    except PermissionError:
        return Response({"detail": "Routine ist nicht verfügbar."}, status=status.HTTP_404_NOT_FOUND)
    migration = RoutineTaskMigration.objects.select_related("task").get(task=task)
    return Response(
        {
            "migrated": True,
            "created": created,
            "routine_id": str(routine.id),
            "task_id": str(task.id),
            "task": _task_payload(request, migration),
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )