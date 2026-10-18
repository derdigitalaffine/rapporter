from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .meal_models import (
    MealDish,
    MealIngredient,
    MealPlanDayTag,
    MealPlanEntry,
    MealPlanTemplate,
    MealPlanTemplateDayTag,
    MealPlanTemplateEntry,
    MealTag,
)
from .meal_service import (
    aggregate_meal_demand,
    build_transfer_diff,
    commit_transfer,
    family_for_user,
    shopping_list_for_user,
)
from .models import Family, Membership


class FamilyScopedSerializer(serializers.ModelSerializer):
    family = serializers.PrimaryKeyRelatedField(queryset=Family.objects.all())

    def validate_family(self, family):
        request = self.context.get("request")
        if not request or not Membership.objects.filter(user=request.user, family=family).exists():
            raise serializers.ValidationError("Familie nicht gefunden oder nicht freigegeben.")
        if self.instance and getattr(self.instance, "family_id", None) != family.id:
            raise serializers.ValidationError("Die Familie eines bestehenden Eintrags kann nicht geändert werden.")
        return family

    def _validate_family_object(self, family, obj, field_name):
        if obj and getattr(obj, "family_id", None) != family.id:
            raise serializers.ValidationError({field_name: "Objekt muss zur ausgewählten Familie gehören."})

    def _validate_family_objects(self, family, objects, field_name):
        for obj in objects or []:
            self._validate_family_object(family, obj, field_name)


class MealTagSerializer(FamilyScopedSerializer):
    class Meta:
        model = MealTag
        fields = ["id", "family", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class MealIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealIngredient
        fields = ["id", "name", "quantity", "unit", "normally_on_hand", "position"]
        read_only_fields = ["id"]


class MealTagDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealTag
        fields = ["id", "name"]


class MealDishSerializer(FamilyScopedSerializer):
    ingredients = MealIngredientSerializer(many=True, required=False)
    tags = serializers.PrimaryKeyRelatedField(queryset=MealTag.objects.all(), many=True, required=False)
    tag_details = MealTagDetailSerializer(source="tags", many=True, read_only=True)

    class Meta:
        model = MealDish
        fields = [
            "id",
            "family",
            "name",
            "default_servings",
            "favorite",
            "notes",
            "tags",
            "tag_details",
            "ingredients",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        family = attrs.get("family") or getattr(self.instance, "family", None)
        tags = attrs.get("tags")
        if family and tags is not None:
            self._validate_family_objects(family, tags, "tags")
        return attrs

    def create(self, validated_data):
        ingredients = validated_data.pop("ingredients", [])
        tags = validated_data.pop("tags", [])
        request = self.context["request"]
        dish = MealDish.objects.create(created_by=request.user, **validated_data)
        dish.tags.set(tags)
        for index, ingredient in enumerate(ingredients):
            ingredient.setdefault("position", index)
            MealIngredient.objects.create(dish=dish, **ingredient)
        return dish

    def update(self, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)
        tags = validated_data.pop("tags", None)
        instance = super().update(instance, validated_data)
        if tags is not None:
            instance.tags.set(tags)
        if ingredients is not None:
            instance.ingredients.all().delete()
            for index, ingredient in enumerate(ingredients):
                ingredient.setdefault("position", index)
                MealIngredient.objects.create(dish=instance, **ingredient)
        return instance


class MealDishSummarySerializer(serializers.ModelSerializer):
    tag_details = MealTagDetailSerializer(source="tags", many=True, read_only=True)

    class Meta:
        model = MealDish
        fields = ["id", "name", "default_servings", "favorite", "tag_details"]


class MealPlanEntrySerializer(FamilyScopedSerializer):
    dish = serializers.PrimaryKeyRelatedField(queryset=MealDish.objects.all(), allow_null=True, required=False)
    tags = serializers.PrimaryKeyRelatedField(queryset=MealTag.objects.all(), many=True, required=False)
    dish_detail = MealDishSummarySerializer(source="dish", read_only=True)
    tag_details = MealTagDetailSerializer(source="tags", many=True, read_only=True)
    display_title = serializers.CharField(read_only=True)

    class Meta:
        model = MealPlanEntry
        fields = [
            "id",
            "family",
            "date",
            "slot",
            "dish",
            "dish_detail",
            "title",
            "display_title",
            "servings",
            "note",
            "tags",
            "tag_details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        family = attrs.get("family") or getattr(self.instance, "family", None)
        dish = attrs.get("dish", getattr(self.instance, "dish", None))
        tags = attrs.get("tags")
        title = attrs.get("title", getattr(self.instance, "title", ""))
        if family:
            self._validate_family_object(family, dish, "dish")
            if tags is not None:
                self._validate_family_objects(family, tags, "tags")
        if not dish and not str(title or "").strip():
            raise serializers.ValidationError({"title": "Freie Einträge brauchen einen Titel."})
        return attrs

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        request = self.context["request"]
        entry = MealPlanEntry.objects.create(created_by=request.user, **validated_data)
        entry.tags.set(tags)
        return entry

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        instance = super().update(instance, validated_data)
        if tags is not None:
            instance.tags.set(tags)
        return instance


class MealPlanDayTagSerializer(FamilyScopedSerializer):
    tag = serializers.PrimaryKeyRelatedField(queryset=MealTag.objects.all())
    tag_detail = MealTagDetailSerializer(source="tag", read_only=True)

    class Meta:
        model = MealPlanDayTag
        fields = ["id", "family", "date", "tag", "tag_detail", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        family = attrs.get("family") or getattr(self.instance, "family", None)
        tag = attrs.get("tag", getattr(self.instance, "tag", None))
        if family:
            self._validate_family_object(family, tag, "tag")
        return attrs


class MealTemplateEntrySerializer(serializers.ModelSerializer):
    dish_detail = MealDishSummarySerializer(source="dish", read_only=True)
    tag_details = MealTagDetailSerializer(source="tags", many=True, read_only=True)

    class Meta:
        model = MealPlanTemplateEntry
        fields = ["id", "weekday", "slot", "dish", "dish_detail", "title", "servings", "note", "tag_details", "position"]


class MealTemplateDayTagSerializer(serializers.ModelSerializer):
    tag_detail = MealTagDetailSerializer(source="tag", read_only=True)

    class Meta:
        model = MealPlanTemplateDayTag
        fields = ["id", "weekday", "tag", "tag_detail"]


class MealPlanTemplateSerializer(FamilyScopedSerializer):
    entries = MealTemplateEntrySerializer(many=True, read_only=True)
    day_tags = MealTemplateDayTagSerializer(many=True, read_only=True)

    class Meta:
        model = MealPlanTemplate
        fields = ["id", "family", "name", "entries", "day_tags", "created_at", "updated_at"]
        read_only_fields = ["id", "entries", "day_tags", "created_at", "updated_at"]

    def create(self, validated_data):
        return MealPlanTemplate.objects.create(created_by=self.context["request"].user, **validated_data)


class FamilyScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset().filter(family__memberships__user=self.request.user).distinct()
        family_id = self.request.query_params.get("family")
        if family_id:
            queryset = queryset.filter(family_id=family_id)
        return queryset


class MealTagViewSet(FamilyScopedViewSet):
    queryset = MealTag.objects.all()
    serializer_class = MealTagSerializer


class MealDishViewSet(FamilyScopedViewSet):
    queryset = MealDish.objects.prefetch_related("ingredients", "tags").all()
    serializer_class = MealDishSerializer


class MealPlanEntryViewSet(FamilyScopedViewSet):
    queryset = MealPlanEntry.objects.select_related("dish").prefetch_related("tags", "dish__tags").all()
    serializer_class = MealPlanEntrySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        exact_date = parse_date(self.request.query_params.get("date", ""))
        start = parse_date(self.request.query_params.get("start", ""))
        end = parse_date(self.request.query_params.get("end", ""))
        if exact_date:
            queryset = queryset.filter(date=exact_date)
        else:
            if start:
                queryset = queryset.filter(date__gte=start)
            if end:
                queryset = queryset.filter(date__lte=end)
        return queryset


class MealPlanDayTagViewSet(FamilyScopedViewSet):
    queryset = MealPlanDayTag.objects.select_related("tag").all()
    serializer_class = MealPlanDayTagSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        exact_date = parse_date(self.request.query_params.get("date", ""))
        start = parse_date(self.request.query_params.get("start", ""))
        end = parse_date(self.request.query_params.get("end", ""))
        if exact_date:
            queryset = queryset.filter(date=exact_date)
        else:
            if start:
                queryset = queryset.filter(date__gte=start)
            if end:
                queryset = queryset.filter(date__lte=end)
        return queryset


class MealPlanTemplateViewSet(FamilyScopedViewSet):
    queryset = MealPlanTemplate.objects.prefetch_related("entries__tags", "entries__dish__tags", "day_tags__tag").all()
    serializer_class = MealPlanTemplateSerializer


def _required_date(value, field):
    parsed = parse_date(str(value or ""))
    if not parsed:
        raise serializers.ValidationError({field: "Gültiges Datum im Format YYYY-MM-DD erforderlich."})
    return parsed


def _week_start(value):
    day = _required_date(value, "week_start")
    return day - timedelta(days=day.weekday())


class MealPlanTodayView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        family = family_for_user(request.user, request.query_params.get("family"))
        now = timezone.now().astimezone(ZoneInfo(family.timezone))
        day = now.date()
        entries = MealPlanEntry.objects.filter(family=family, date=day).select_related("dish").prefetch_related("tags", "dish__tags")
        day_tags = MealPlanDayTag.objects.filter(family=family, date=day).select_related("tag")
        return Response(
            {
                "date": day.isoformat(),
                "entries": MealPlanEntrySerializer(entries, many=True, context={"request": request}).data,
                "day_tags": MealPlanDayTagSerializer(day_tags, many=True, context={"request": request}).data,
            }
        )


class MealTemplateFromWeekView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        family = family_for_user(request.user, request.data.get("family"))
        start = _week_start(request.data.get("week_start"))
        name = str(request.data.get("name") or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "Name erforderlich."})
        template = MealPlanTemplate.objects.create(family=family, name=name, created_by=request.user)
        entries = MealPlanEntry.objects.filter(family=family, date__range=(start, start + timedelta(days=6))).prefetch_related("tags")
        for position, entry in enumerate(entries):
            template_entry = MealPlanTemplateEntry.objects.create(
                template=template,
                weekday=(entry.date - start).days,
                slot=entry.slot,
                dish=entry.dish,
                title=entry.title,
                servings=entry.servings,
                note=entry.note,
                position=position,
            )
            template_entry.tags.set(entry.tags.all())
        for assignment in MealPlanDayTag.objects.filter(family=family, date__range=(start, start + timedelta(days=6))):
            MealPlanTemplateDayTag.objects.create(
                template=template,
                weekday=(assignment.date - start).days,
                tag=assignment.tag,
            )
        template.refresh_from_db()
        return Response(MealPlanTemplateSerializer(template, context={"request": request}).data, status=status.HTTP_201_CREATED)


class MealTemplateApplyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        start = _week_start(request.data.get("week_start"))
        template = MealPlanTemplate.objects.filter(pk=pk, family__memberships__user=request.user).first()
        if not template:
            return Response(status=status.HTTP_404_NOT_FOUND)
        applied = []
        for entry in template.entries.prefetch_related("tags").all():
            day = start + timedelta(days=entry.weekday)
            plan_entry, _ = MealPlanEntry.objects.update_or_create(
                family=template.family,
                date=day,
                slot=entry.slot,
                defaults={
                    "dish": entry.dish,
                    "title": entry.title,
                    "servings": entry.servings,
                    "note": entry.note,
                    "created_by": request.user,
                },
            )
            plan_entry.tags.set(entry.tags.all())
            applied.append(plan_entry)
        for assignment in template.day_tags.select_related("tag").all():
            MealPlanDayTag.objects.get_or_create(
                family=template.family,
                date=start + timedelta(days=assignment.weekday),
                tag=assignment.tag,
            )
        return Response(
            {
                "week_start": start.isoformat(),
                "entries": MealPlanEntrySerializer(applied, many=True, context={"request": request}).data,
            }
        )


class MealShoppingPreviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        family = family_for_user(request.user, request.query_params.get("family"))
        start = _required_date(request.query_params.get("start"), "start")
        end = _required_date(request.query_params.get("end"), "end")
        if end < start:
            raise serializers.ValidationError({"end": "Ende muss am oder nach dem Start liegen."})
        rows = aggregate_meal_demand(family, start, end)
        for row in rows:
            row["missing_default"] = not row["normally_on_hand"]
        return Response({"start": start.isoformat(), "end": end.isoformat(), "rows": rows})


class MealShoppingDiffView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        family = family_for_user(request.user, request.data.get("family"))
        start = _required_date(request.data.get("start"), "start")
        end = _required_date(request.data.get("end"), "end")
        shopping_list = shopping_list_for_user(request.user, family, request.data.get("shopping_list"))
        actions = build_transfer_diff(
            user=request.user,
            family=family,
            start_date=start,
            end_date=end,
            shopping_list=shopping_list,
            selection=request.data.get("selection", {}),
        )
        return Response({"actions": actions})


class MealShoppingCommitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        family = family_for_user(request.user, request.data.get("family"))
        start = _required_date(request.data.get("start"), "start")
        end = _required_date(request.data.get("end"), "end")
        shopping_list = shopping_list_for_user(request.user, family, request.data.get("shopping_list"))
        result = commit_transfer(
            user=request.user,
            family=family,
            start_date=start,
            end_date=end,
            shopping_list=shopping_list,
            selection=request.data.get("selection", {}),
        )
        return Response(result)
