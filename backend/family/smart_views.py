from urllib.parse import urlencode

from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .extended_integrations import INTEGRATION_CATALOG, sync_source
from .models import Family, IntegrationSource, Membership, ShoppingItem, ShoppingList, Task, TaskList
from .oauth import authorization_url, complete_oauth, oauth_available
from .serializers import IntegrationSourceSerializer, ShoppingItemSerializer, TaskSerializer


def _family(user, family_id):
    return Family.objects.filter(id=family_id, memberships__user=user).first()


def _can_manage(user, family):
    return Membership.objects.filter(
        family=family,
        user=user,
        role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
    ).exists()


def _catalog_item(catalog_id):
    return next((item for item in INTEGRATION_CATALOG if item["id"] == catalog_id), None)


@api_view(["GET"])
def smart_integration_catalog(request):
    result = []
    for item in INTEGRATION_CATALOG:
        row = dict(item)
        if row.get("oauth_provider"):
            row["oauth_ready"] = oauth_available(row["oauth_provider"])
        result.append(row)
    return Response(result)


@api_view(["POST"])
def smart_integration_connect(request):
    family = _family(request.user, request.data.get("family"))
    if not family or not _can_manage(request.user, family):
        raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
    item = _catalog_item(request.data.get("catalog_id"))
    if not item:
        return Response({"detail": "Unbekannte Integration."}, status=status.HTTP_400_BAD_REQUEST)
    if item.get("oauth_provider"):
        return Response({"detail": "Diese Integration wird über OAuth verbunden."}, status=status.HTTP_400_BAD_REQUEST)
    values = dict(request.data.get("values") or {})
    endpoint = values.pop("endpoint", "")
    config = {**item.get("defaults", {}), **values}
    source = IntegrationSource.objects.create(
        family=family,
        kind=item["kind"],
        name=item["name"],
        endpoint=endpoint,
        config=config,
        enabled=True,
    )
    try:
        count = sync_source(source)
    except Exception as exc:
        source.delete()
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"source": IntegrationSourceSerializer(source).data, "synced": count}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def smart_integration_sync(request, source_id):
    source = IntegrationSource.objects.filter(id=source_id, family__memberships__user=request.user).first()
    if not source:
        return Response({"detail": "Integration nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    try:
        count = sync_source(source)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    source.refresh_from_db()
    return Response({"synced": count, "last_synced_at": source.last_synced_at})


@api_view(["POST"])
def smart_integration_sync_all(request):
    total, errors = 0, []
    sources = IntegrationSource.objects.filter(family__memberships__user=request.user, enabled=True).distinct()
    for source in sources:
        try:
            total += sync_source(source)
        except Exception as exc:
            errors.append({"id": str(source.id), "name": source.name, "detail": str(exc)})
    return Response({"synced": total, "errors": errors})


@api_view(["POST"])
def integration_oauth_start(request):
    family = _family(request.user, request.data.get("family"))
    provider = request.data.get("provider")
    if not family or not _can_manage(request.user, family):
        raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
    redirect_uri = request.build_absolute_uri("/api/integration-oauth/callback/")
    try:
        url = authorization_url(provider, family, request.user, redirect_uri)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"provider": provider, "authorization_url": url})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def integration_oauth_callback(request):
    if request.query_params.get("error"):
        params = urlencode({"integration_error": request.query_params.get("error_description") or request.query_params["error"]})
        return redirect(f"/?{params}")
    code, state_value = request.query_params.get("code"), request.query_params.get("state")
    if not code or not state_value:
        return redirect("/?integration_error=oauth_missing_code")
    redirect_uri = request.build_absolute_uri("/api/integration-oauth/callback/")
    try:
        source, provider = complete_oauth(code, state_value, redirect_uri)
        sync_source(source)
    except Exception as exc:
        return redirect(f"/?{urlencode({'integration_error': str(exc)})}")
    return redirect(f"/?{urlencode({'integration_connected': provider})}")


@api_view(["POST"])
def task_quick_add(request):
    family = _family(request.user, request.data.get("family"))
    if not family:
        raise PermissionDenied()
    title = str(request.data.get("title") or request.data.get("name") or "").strip()
    if not title:
        return Response({"detail": "Aufgabentitel fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    task_list = None
    if request.data.get("task_list"):
        task_list = TaskList.objects.filter(id=request.data["task_list"], family=family, archived=False).first()
        if not task_list:
            return Response({"detail": "Aufgabenliste nicht gefunden."}, status=status.HTTP_400_BAD_REQUEST)
    task_list = task_list or TaskList.objects.filter(family=family, archived=False).first()
    task_list = task_list or TaskList.objects.create(family=family, name="Allgemein", icon="list-check")
    task = Task.objects.filter(family=family, task_list=task_list, title__iexact=title, completed_at__isnull=True).order_by("-updated_at").first()
    reused = bool(task)
    if not task:
        task = Task(family=family, task_list=task_list, title=title, created_by=request.user)
    for field in ("notes", "priority", "estimate_minutes", "recurrence", "tags"):
        if field in request.data and request.data[field] not in (None, ""):
            setattr(task, field, request.data[field])
    if request.data.get("due_at"):
        task.due_at = request.data["due_at"]
    if request.data.get("assignee"):
        member = Membership.objects.filter(family=family, user_id=request.data["assignee"]).first()
        if member:
            task.assignee_id = request.data["assignee"]
    task.save()
    return Response({"task": TaskSerializer(task).data, "reused": reused}, status=status.HTTP_200_OK if reused else status.HTTP_201_CREATED)


@api_view(["POST"])
def shopping_quick_add(request):
    family = _family(request.user, request.data.get("family"))
    if not family:
        raise PermissionDenied()
    name = str(request.data.get("name") or "").strip()
    if not name:
        return Response({"detail": "Artikelname fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    shopping = None
    if request.data.get("shopping_list"):
        shopping = ShoppingList.objects.filter(id=request.data["shopping_list"], family=family, archived=False).first()
        if not shopping:
            return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_400_BAD_REQUEST)
    shopping = shopping or ShoppingList.objects.filter(family=family, archived=False).order_by("sort_order", "created_at").first()
    shopping = shopping or ShoppingList.objects.create(family=family, name="Einkauf")
    item = ShoppingItem.objects.filter(shopping_list=shopping, name__iexact=name).order_by("checked", "-updated_at").first()
    reused = bool(item)
    if not item:
        item = ShoppingItem(shopping_list=shopping, name=name, added_by=request.user)
    else:
        item.checked = False
        item.checked_at = None
        item.added_by = request.user
    for field in ("quantity", "category", "aisle", "note"):
        if field in request.data and request.data[field] not in (None, ""):
            setattr(item, field, request.data[field])
    if "favorite" in request.data:
        item.favorite = bool(request.data["favorite"])
    item.save()
    return Response({"item": ShoppingItemSerializer(item).data, "reused": reused}, status=status.HTTP_200_OK if reused else status.HTTP_201_CREATED)


@api_view(["POST"])
def shopping_toggle_favorite(request, item_id):
    item = ShoppingItem.objects.filter(id=item_id, shopping_list__family__memberships__user=request.user).first()
    if not item:
        return Response({"detail": "Artikel nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    item.favorite = not item.favorite
    item.save(update_fields=["favorite", "updated_at"])
    return Response(ShoppingItemSerializer(item).data)


@api_view(["POST"])
def shopping_clear_checked(request, list_id):
    shopping = ShoppingList.objects.filter(id=list_id, family__memberships__user=request.user).first()
    if not shopping:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    count, _ = shopping.items.filter(checked=True).delete()
    return Response({"deleted": count})
