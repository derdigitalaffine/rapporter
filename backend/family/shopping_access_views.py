from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .memory import normalize_name
from .models import Family, Membership, ShoppingItem, ShoppingList
from .serializers import ShoppingItemSerializer, ShoppingListSerializer
from .shopping_access import (
    can_access_shopping_list,
    can_manage_shopping_access,
    serialize_shopping_access,
    set_shopping_access,
    visible_shopping_lists,
)
from .shopping_models import ShoppingListAccess, ShoppingListStoreProfile
from .shopping_template_views import (
    ShoppingStoreSerializer as BaseShoppingStoreSerializer,
    ShoppingStoreViewSet as BaseShoppingStoreViewSet,
    ShoppingTemplateViewSet as BaseShoppingTemplateViewSet,
    _apply_template,
    _template_plan,
)
from .views import ShoppingItemViewSet as BaseShoppingItemViewSet
from .views import ShoppingListViewSet as BaseShoppingListViewSet
from .views import _smart_history


ACCESS_KEYS = {"visibility", "visible_members", "responsible_members", "audience_group"}


class ShoppingListWithAccessSerializer(ShoppingListSerializer):
    access = serializers.SerializerMethodField()

    def get_access(self, obj):
        request = self.context.get("request")
        return serialize_shopping_access(obj, actor=request.user if request else None)

    class Meta(ShoppingListSerializer.Meta):
        fields = [*ShoppingListSerializer.Meta.fields, "access"]


class ShoppingStoreWithAccessSerializer(BaseShoppingStoreSerializer):
    def get_shopping_list_ids(self, obj):
        request = self.context.get("request")
        if not request:
            return []
        rows = visible_shopping_lists(
            request.user,
            ShoppingList.objects.filter(store_profile_assignment__store=obj),
        )
        return [str(value) for value in rows.values_list("id", flat=True)]


def _list_payload_value(data, key, default=None):
    if hasattr(data, "getlist"):
        values = data.getlist(key)
        if key in {"visible_members", "responsible_members"}:
            return values if key in data else default
        return values[-1] if values else default
    return data.get(key, default)


def _clean_list_payload(data):
    mutable = data.copy()
    for key in ACCESS_KEYS:
        if key in mutable:
            mutable.pop(key)
    return mutable


def _family_for_user(user, family_id):
    return Family.objects.filter(id=family_id, memberships__user=user).first()


def _target_visible_list(user, family, list_id):
    return visible_shopping_lists(
        user,
        ShoppingList.objects.filter(family=family, archived=False),
    ).filter(pk=list_id).first()


class ShoppingListViewSet(BaseShoppingListViewSet):
    serializer_class = ShoppingListWithAccessSerializer
    queryset = (
        ShoppingList.objects.prefetch_related(
            "items",
            "access_settings__visible_members__user",
            "access_settings__responsible_members__user",
        )
        .all()
        .order_by("sort_order", "created_at")
    )

    def get_queryset(self):
        return visible_shopping_lists(self.request.user, self.queryset)

    def create(self, request, *args, **kwargs):
        raw = request.data
        serializer = self.get_serializer(data=_clean_list_payload(raw))
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
            set_shopping_access(
                serializer.instance,
                actor=request.user,
                visibility=_list_payload_value(raw, "visibility", "family"),
                visible_member_ids=_list_payload_value(raw, "visible_members", []),
                responsible_member_ids=_list_payload_value(raw, "responsible_members", []),
                audience_group=_list_payload_value(raw, "audience_group"),
                allow_initialize=True,
            )
        serializer.instance.refresh_from_db()
        response_serializer = self.get_serializer(serializer.instance)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(response_serializer.data),
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        raw = request.data
        changes_access = any(key in raw for key in ACCESS_KEYS)
        if changes_access and not can_manage_shopping_access(request.user, instance):
            raise PermissionDenied("Du kannst die Freigabe dieser Liste nicht ändern.")
        serializer = self.get_serializer(instance, data=_clean_list_payload(raw), partial=partial)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_update(serializer)
            if changes_access:
                set_shopping_access(
                    serializer.instance,
                    actor=request.user,
                    visibility=_list_payload_value(raw, "visibility"),
                    visible_member_ids=_list_payload_value(raw, "visible_members"),
                    responsible_member_ids=_list_payload_value(raw, "responsible_members"),
                    audience_group=_list_payload_value(raw, "audience_group"),
                )
        serializer.instance.refresh_from_db()
        return Response(self.get_serializer(serializer.instance).data)

    @action(detail=False, methods=["get"], url_path="audience-options")
    def audience_options(self, request):
        family = _family_for_user(request.user, request.query_params.get("family"))
        if not family:
            return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
        members = Membership.objects.filter(family=family).select_related("user").order_by("created_at")
        return Response(
            {
                "groups": [
                    {"id": "family", "label": "Ganze Familie"},
                    {"id": "adults", "label": "Erwachsene"},
                    {"id": "children", "label": "Kinder & Jugendliche"},
                ],
                "members": [
                    {
                        "id": str(member.id),
                        "user_id": member.user_id,
                        "name": member.display_name or member.user.get_short_name() or member.user.username,
                        "role": member.role,
                        "avatar": member.avatar,
                    }
                    for member in members
                ],
            }
        )

    @action(detail=True, methods=["get", "patch"], url_path="access")
    def access(self, request, pk=None):
        shopping_list = self.get_object()
        if request.method == "GET":
            return Response(serialize_shopping_access(shopping_list, actor=request.user))
        if not can_manage_shopping_access(request.user, shopping_list):
            raise PermissionDenied("Du kannst die Freigabe dieser Liste nicht ändern.")
        access = set_shopping_access(
            shopping_list,
            actor=request.user,
            visibility=request.data.get("visibility"),
            visible_member_ids=request.data.get("visible_members"),
            responsible_member_ids=request.data.get("responsible_members"),
            audience_group=request.data.get("audience_group"),
        )
        return Response(serialize_shopping_access(access.shopping_list, actor=request.user))


class ShoppingItemViewSet(BaseShoppingItemViewSet):
    def get_queryset(self):
        lists = visible_shopping_lists(self.request.user)
        return (
            self.queryset.filter(shopping_list__in=lists)
            .exclude(hidden_from_user=self.request.user)
            .distinct()
        )

    def perform_create(self, serializer):
        shopping_list = serializer.validated_data["shopping_list"]
        if not can_access_shopping_list(self.request.user, shopping_list):
            raise PermissionDenied("Einkaufsliste nicht gefunden.")
        serializer.save(added_by=self.request.user)

    def perform_update(self, serializer):
        item = serializer.instance
        shopping_list = serializer.validated_data.get("shopping_list", item.shopping_list)
        if not can_access_shopping_list(self.request.user, shopping_list):
            raise PermissionDenied("Einkaufsliste nicht gefunden.")
        checked = serializer.validated_data.get("checked", item.checked)
        if checked != item.checked:
            serializer.save(checked_at=timezone.now() if checked else None)
        else:
            serializer.save()

    @action(detail=False, methods=["get"])
    def suggestions(self, request):
        family = _family_for_user(request.user, request.query_params.get("family"))
        if not family:
            return Response([])
        lists = visible_shopping_lists(request.user, ShoppingList.objects.filter(family=family))
        rows = (
            ShoppingItem.objects.filter(shopping_list__in=lists)
            .exclude(hidden_from_user=request.user)
            .order_by("-updated_at")[:1000]
        )
        return Response(
            _smart_history(rows, request.query_params.get("q"), ["quantity", "category", "aisle", "note"], 12)
        )


class ShoppingStoreViewSet(BaseShoppingStoreViewSet):
    serializer_class = ShoppingStoreWithAccessSerializer

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        store = self.get_object()
        if not store.active:
            raise serializers.ValidationError({"store": "Inactive stores cannot be assigned."})
        target = _target_visible_list(request.user, store.family, request.data.get("shopping_list"))
        if not target:
            raise serializers.ValidationError({"shopping_list": "Einkaufsliste nicht gefunden."})
        with transaction.atomic():
            ShoppingListStoreProfile.objects.update_or_create(shopping_list=target, defaults={"store": store})
            ShoppingList.objects.filter(pk=target.pk).update(store=store.display_label)
        return Response({"shopping_list": str(target.id), "store": str(store.id), "display_label": store.display_label})

    @action(detail=True, methods=["post"])
    def unassign(self, request, pk=None):
        store = self.get_object()
        target = _target_visible_list(request.user, store.family, request.data.get("shopping_list"))
        if not target:
            raise serializers.ValidationError({"shopping_list": "Einkaufsliste nicht gefunden."})
        deleted, _ = ShoppingListStoreProfile.objects.filter(shopping_list=target, store=store).delete()
        return Response({"unassigned": bool(deleted)})


class ShoppingTemplateViewSet(BaseShoppingTemplateViewSet):
    def _target(self, request, template, list_id):
        target = _target_visible_list(request.user, template.family, list_id)
        if not target:
            raise serializers.ValidationError({"shopping_list": "Einkaufsliste nicht gefunden."})
        return target

    @action(detail=False, methods=["post"], url_path="from-list")
    def from_list(self, request):
        family_ids = Membership.objects.filter(user=request.user).values_list("family_id", flat=True)
        target = visible_shopping_lists(
            request.user,
            ShoppingList.objects.filter(family_id__in=family_ids),
        ).filter(pk=request.data.get("shopping_list")).first()
        if not target:
            raise serializers.ValidationError({"shopping_list": "Einkaufsliste nicht gefunden."})
        try:
            access = target.access_settings
        except ShoppingListAccess.DoesNotExist:
            access = None
        if access and access.visibility != ShoppingListAccess.Visibility.FAMILY:
            raise serializers.ValidationError({"shopping_list": "Private oder ausgewählte Listen können nicht als familienweite Vorlage gespeichert werden."})
        selected = request.data.get("item_ids")
        items = target.items.filter(hidden_from_user__isnull=True, birthday_context__isnull=True).order_by("created_at", "id")
        if selected is not None:
            items = items.filter(id__in=selected)
        seen = set()
        rows = []
        for item in items:
            key = normalize_name(item.name)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append({
                "name": item.name,
                "quantity": item.quantity,
                "category": item.category,
                "aisle": item.aisle,
                "note": item.note,
                "position": len(rows),
            })
        default_store = None
        try:
            default_store = target.store_profile_assignment.store
        except ShoppingListStoreProfile.DoesNotExist:
            pass
        payload = {
            "family": str(target.family_id),
            "name": (request.data.get("name") or target.name).strip(),
            "description": request.data.get("description", ""),
            "default_store": request.data.get("default_store") or (str(default_store.id) if default_store and default_store.active else None),
            "items": rows,
        }
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        template = serializer.save(created_by=request.user)
        return Response(self.get_serializer(template).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        template = self.get_object()
        if template.archived:
            raise serializers.ValidationError({"template": "Archived templates cannot be applied."})
        target = self._target(request, template, request.query_params.get("shopping_list"))
        counts, _ = _template_plan(template, target)
        return Response({**counts, "total": sum(counts.values())})

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        template = self.get_object()
        if template.archived:
            raise serializers.ValidationError({"template": "Archived templates cannot be applied."})
        target = self._target(request, template, request.data.get("shopping_list"))
        counts = _apply_template(template, target, request.user)
        return Response({**counts, "total": sum(counts.values())})

    @action(detail=True, methods=["post"], url_path="create-list")
    def create_list(self, request, pk=None):
        template = self.get_object()
        if template.archived:
            raise serializers.ValidationError({"template": "Archived templates cannot be applied."})
        name = str(request.data.get("name") or template.name).strip()
        if not name:
            raise serializers.ValidationError({"name": "List name is required."})
        store = template.default_store if template.default_store_id and template.default_store.active else None
        with transaction.atomic():
            target = ShoppingList.objects.create(
                family=template.family,
                name=name,
                store=store.display_label if store else "",
                icon="cart-shopping",
            )
            set_shopping_access(
                target,
                actor=request.user,
                visibility=request.data.get("visibility", "family"),
                visible_member_ids=request.data.get("visible_members", []),
                responsible_member_ids=request.data.get("responsible_members", []),
                audience_group=request.data.get("audience_group"),
                allow_initialize=True,
            )
            if store:
                ShoppingListStoreProfile.objects.create(shopping_list=target, store=store)
            ShoppingItem.objects.bulk_create([
                ShoppingItem(
                    shopping_list=target,
                    name=item.name,
                    quantity=item.quantity,
                    category=item.category,
                    aisle=item.aisle,
                    note=item.note,
                    added_by=request.user,
                )
                for item in template.items.all()
            ])
        target.refresh_from_db()
        return Response(ShoppingListWithAccessSerializer(target, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def shopping_quick_add(request):
    family = _family_for_user(request.user, request.data.get("family"))
    if not family:
        raise PermissionDenied()
    name = str(request.data.get("name") or "").strip()
    if not name:
        return Response({"detail": "Artikelname fehlt."}, status=status.HTTP_400_BAD_REQUEST)

    lists = visible_shopping_lists(request.user, ShoppingList.objects.filter(family=family, archived=False))
    shopping = None
    if request.data.get("shopping_list"):
        shopping = lists.filter(id=request.data["shopping_list"]).first()
        if not shopping:
            return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    shopping = shopping or lists.order_by("sort_order", "created_at").first()
    if not shopping:
        with transaction.atomic():
            shopping = ShoppingList.objects.create(family=family, name="Einkauf")
            set_shopping_access(shopping, actor=request.user, visibility="family", allow_initialize=True)

    item = (
        ShoppingItem.objects.filter(
            birthday_context__isnull=True,
            shopping_list=shopping,
            name__iexact=name,
        )
        .exclude(hidden_from_user=request.user)
        .order_by("checked", "-updated_at")
        .first()
    )
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
    return Response(
        {"item": ShoppingItemSerializer(item, context={"request": request}).data, "reused": reused},
        status=status.HTTP_200_OK if reused else status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def shopping_toggle_favorite(request, item_id):
    lists = visible_shopping_lists(request.user)
    item = (
        ShoppingItem.objects.exclude(hidden_from_user=request.user)
        .filter(id=item_id, shopping_list__in=lists)
        .first()
    )
    if not item:
        return Response({"detail": "Artikel nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    item.favorite = not item.favorite
    item.save(update_fields=["favorite", "updated_at"])
    return Response(ShoppingItemSerializer(item, context={"request": request}).data)


@api_view(["POST"])
def shopping_clear_checked(request, list_id):
    shopping = visible_shopping_lists(request.user).filter(id=list_id).first()
    if not shopping:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    rows = shopping.items.exclude(hidden_from_user=request.user).filter(checked=True)
    count = rows.count()
    rows.delete()
    return Response({"deleted": count})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shopping_reorder(request, list_id):
    item_ids = request.data.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        return Response({"item_ids": "Eine vollständige Artikelfolge ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
    normalized = [str(value) for value in item_ids]
    if len(normalized) != len(set(normalized)):
        return Response({"item_ids": "Artikel dürfen nur einmal vorkommen."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        shopping_list = ShoppingList.objects.select_for_update().filter(id=list_id).first()
        if not shopping_list or not can_access_shopping_list(request.user, shopping_list):
            return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

        all_rows = list(shopping_list.items.select_for_update().order_by("position", "created_at", "id"))
        visible = [item for item in all_rows if item.hidden_from_user_id != request.user.id]
        visible_by_id = {str(item.id): item for item in visible}
        if set(normalized) != set(visible_by_id):
            return Response({"item_ids": "Die Reihenfolge muss alle sichtbaren Artikel dieser Liste enthalten."}, status=status.HTTP_400_BAD_REQUEST)

        visible_queue = [visible_by_id[item_id] for item_id in normalized]
        queue_index = 0
        merged = []
        for item in all_rows:
            if item.hidden_from_user_id == request.user.id:
                merged.append(item)
            else:
                merged.append(visible_queue[queue_index])
                queue_index += 1

        changed_at = timezone.now()
        for index, item in enumerate(merged, start=1):
            item.position = index * 1000
            item.updated_at = changed_at
        ShoppingItem.objects.bulk_update(merged, ["position", "updated_at"])

    ordered_visible = [item for item in merged if item.hidden_from_user_id != request.user.id]
    return Response(ShoppingItemSerializer(ordered_visible, many=True, context={"request": request}).data)
