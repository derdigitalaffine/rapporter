from django.db import transaction
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .memory import normalize_name
from .models import Family, Membership, ShoppingItem, ShoppingList
from .serializers import ShoppingListSerializer
from .shopping_models import (
    ShoppingListStoreProfile,
    ShoppingStore,
    ShoppingTemplate,
    ShoppingTemplateItem,
)


def _family_ids(user):
    return Membership.objects.filter(user=user, family__status=Family.Status.ACTIVE).values_list("family_id", flat=True)


def _require_family_member(user, family):
    if family.status != Family.Status.ACTIVE or not Membership.objects.filter(family=family, user=user).exists():
        raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")


def _safe_https(value):
    value = (value or "").strip()
    if value and not value.lower().startswith("https://"):
        raise serializers.ValidationError("Only HTTPS links are allowed.")
    return value


class ShoppingStoreSerializer(serializers.ModelSerializer):
    display_label = serializers.CharField(read_only=True)
    shopping_list_ids = serializers.SerializerMethodField()

    def get_shopping_list_ids(self, obj):
        return [str(row.shopping_list_id) for row in obj.list_assignments.all()]

    def validate_website_url(self, value):
        return _safe_https(value)

    def validate_offers_url(self, value):
        return _safe_https(value)

    def validate(self, attrs):
        family = attrs.get("family") or (self.instance.family if self.instance else None)
        if self.instance and family and family.id != self.instance.family_id:
            raise serializers.ValidationError({"family": "Geschäft kann nicht in eine andere Familie verschoben werden."})
        request = self.context.get("request")
        if family and request:
            _require_family_member(request.user, family)
        return attrs

    class Meta:
        model = ShoppingStore
        fields = [
            "id", "family", "name", "branch_label", "display_label", "address",
            "website_url", "offers_url", "note", "active", "sort_order",
            "shopping_list_ids", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by"]


class ShoppingTemplateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingTemplateItem
        fields = ["id", "name", "quantity", "category", "aisle", "note", "position", "normalized_name"]
        read_only_fields = ["id", "normalized_name"]


class ShoppingTemplateSerializer(serializers.ModelSerializer):
    items = ShoppingTemplateItemSerializer(many=True)
    item_count = serializers.SerializerMethodField()
    default_store_label = serializers.CharField(source="default_store.display_label", read_only=True)

    def get_item_count(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", {})
        return len(cache["items"]) if "items" in cache else obj.items.count()

    def validate(self, attrs):
        family = attrs.get("family") or (self.instance.family if self.instance else None)
        if self.instance and family and family.id != self.instance.family_id:
            raise serializers.ValidationError({"family": "Vorlage kann nicht in eine andere Familie verschoben werden."})
        request = self.context.get("request")
        if family and request:
            _require_family_member(request.user, family)
        store = attrs.get("default_store") if "default_store" in attrs else (self.instance.default_store if self.instance else None)
        if store and (not family or store.family_id != family.id or not store.active):
            raise serializers.ValidationError({"default_store": "Geschäft gehört nicht als aktives Profil zu dieser Familie."})
        items = attrs.get("items")
        if items is not None:
            if len(items) > 200:
                raise serializers.ValidationError({"items": "Maximum 200 template items."})
            seen = set()
            for item in items:
                key = normalize_name(item.get("name"))
                if not key:
                    raise serializers.ValidationError({"items": "Template items need a name."})
                if key in seen:
                    raise serializers.ValidationError({"items": f"Duplicate template item: {item.get('name')}"})
                seen.add(key)
        return attrs

    def _replace_items(self, template, rows):
        template.items.all().delete()
        ShoppingTemplateItem.objects.bulk_create([
            ShoppingTemplateItem(
                template=template,
                name=row["name"].strip(),
                normalized_name=normalize_name(row["name"]),
                quantity=row.get("quantity", ""),
                category=row.get("category", ""),
                aisle=row.get("aisle", ""),
                note=row.get("note", ""),
                position=row.get("position", index),
            )
            for index, row in enumerate(rows)
        ])

    def create(self, validated_data):
        rows = validated_data.pop("items", [])
        with transaction.atomic():
            instance = ShoppingTemplate.objects.create(**validated_data)
            self._replace_items(instance, rows)
        return instance

    def update(self, instance, validated_data):
        marker = object()
        rows = validated_data.pop("items", marker)
        with transaction.atomic():
            for key, value in validated_data.items():
                setattr(instance, key, value)
            instance.save()
            if rows is not marker:
                self._replace_items(instance, rows)
        return instance

    class Meta:
        model = ShoppingTemplate
        fields = [
            "id", "family", "name", "description", "default_store", "default_store_label",
            "archived", "sort_order", "items", "item_count", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by"]


def _target_list(user, template, list_id):
    target = ShoppingList.objects.filter(pk=list_id, family=template.family, archived=False).first()
    if not target or target.family_id not in set(_family_ids(user)):
        raise serializers.ValidationError({"shopping_list": "Einkaufsliste gehört nicht zu dieser Familie."})
    return target


def _visible_list_items(target):
    return list(target.items.filter(hidden_from_user__isnull=True, birthday_context__isnull=True).order_by("created_at", "id"))


def _template_plan(template, target):
    rows = _visible_list_items(target)
    by_name = {}
    for row in rows:
        by_name.setdefault(normalize_name(row.name), []).append(row)
    plan = []
    counts = {"created": 0, "reopened": 0, "already_open": 0}
    for item in template.items.all():
        matches = by_name.get(item.normalized_name, [])
        open_match = next((row for row in matches if not row.checked), None)
        if open_match:
            action_name, match = "already_open", open_match
        else:
            checked_match = next((row for row in reversed(matches) if row.checked), None)
            if checked_match:
                action_name, match = "reopened", checked_match
            else:
                action_name, match = "created", None
        counts[action_name] += 1
        plan.append((item, action_name, match))
    return counts, plan


def _fill_blank_fields(item, template_item):
    patch = {}
    for field in ("quantity", "category", "aisle", "note"):
        if not getattr(item, field) and getattr(template_item, field):
            patch[field] = getattr(template_item, field)
    return patch


def _apply_template(template, target, actor):
    counts, plan = _template_plan(template, target)
    to_create = []
    with transaction.atomic():
        ShoppingList.objects.select_for_update().get(pk=target.pk)
        # Re-plan under the list lock so repeated/concurrent applies stay idempotent.
        counts, plan = _template_plan(template, target)
        for template_item, action_name, match in plan:
            if action_name == "created":
                to_create.append(ShoppingItem(
                    shopping_list=target,
                    name=template_item.name,
                    quantity=template_item.quantity,
                    category=template_item.category,
                    aisle=template_item.aisle,
                    note=template_item.note,
                    added_by=actor,
                ))
                continue
            patch = _fill_blank_fields(match, template_item)
            if action_name == "reopened":
                patch.update({"checked": False, "checked_at": None})
            if patch:
                ShoppingItem.objects.filter(pk=match.pk).update(**patch)
        if to_create:
            ShoppingItem.objects.bulk_create(to_create)
    return counts


class ShoppingStoreViewSet(viewsets.ModelViewSet):
    serializer_class = ShoppingStoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        rows = ShoppingStore.objects.filter(family_id__in=_family_ids(self.request.user)).prefetch_related("list_assignments")
        family_id = self.request.query_params.get("family")
        return rows.filter(family_id=family_id) if family_id else rows

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        _require_family_member(self.request.user, family)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            store = serializer.save()
            # Keep the legacy display field useful for the existing shopping UI.
            ShoppingList.objects.filter(store_profile_assignment__store=store).update(store=store.display_label)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        store = self.get_object()
        if not store.active:
            raise serializers.ValidationError({"store": "Inactive stores cannot be assigned."})
        target = ShoppingList.objects.filter(pk=request.data.get("shopping_list"), family=store.family, archived=False).first()
        if not target:
            raise serializers.ValidationError({"shopping_list": "Einkaufsliste gehört nicht zu dieser Familie."})
        with transaction.atomic():
            ShoppingListStoreProfile.objects.update_or_create(shopping_list=target, defaults={"store": store})
            ShoppingList.objects.filter(pk=target.pk).update(store=store.display_label)
        return Response({"shopping_list": str(target.id), "store": str(store.id), "display_label": store.display_label})

    @action(detail=True, methods=["post"])
    def unassign(self, request, pk=None):
        store = self.get_object()
        list_id = request.data.get("shopping_list")
        deleted, _ = ShoppingListStoreProfile.objects.filter(shopping_list_id=list_id, shopping_list__family=store.family, store=store).delete()
        return Response({"unassigned": bool(deleted)})


class ShoppingTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = ShoppingTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        rows = ShoppingTemplate.objects.filter(family_id__in=_family_ids(self.request.user)).select_related("default_store").prefetch_related("items")
        family_id = self.request.query_params.get("family")
        return rows.filter(family_id=family_id) if family_id else rows

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="from-list")
    def from_list(self, request):
        target = ShoppingList.objects.filter(pk=request.data.get("shopping_list"), family_id__in=_family_ids(request.user)).first()
        if not target:
            raise serializers.ValidationError({"shopping_list": "Einkaufsliste gehört nicht zu deiner Familie."})
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
        target = _target_list(request.user, template, request.query_params.get("shopping_list"))
        counts, _ = _template_plan(template, target)
        return Response({**counts, "total": sum(counts.values())})

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        template = self.get_object()
        if template.archived:
            raise serializers.ValidationError({"template": "Archived templates cannot be applied."})
        target = _target_list(request.user, template, request.data.get("shopping_list"))
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
        return Response(ShoppingListSerializer(target, context={"request": request}).data, status=status.HTTP_201_CREATED)
