from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .memory import suggestions
from .models import EntryMemory, Family


def _family(request):
    family_id = request.query_params.get("family")
    family = Family.objects.filter(id=family_id, memberships__user=request.user).first() if family_id else Family.objects.filter(memberships__user=request.user).first()
    if not family:
        raise PermissionDenied()
    return family


@api_view(["GET"])
def task_memory_suggestions(request):
    return Response(suggestions(_family(request), EntryMemory.Kind.TASK, request.query_params.get("q", ""), 12))


@api_view(["GET"])
def shopping_memory_suggestions(request):
    return Response(suggestions(_family(request), EntryMemory.Kind.SHOPPING, request.query_params.get("q", ""), 16))
