from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import Family, Membership, FamilyInvitation, TaskList, Task, TaskWorkflowColumn, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem, InboxReceipt, AutomationRule, AutomationExecution
from .predictions import routine_prediction


CALENDAR_SOURCE_ICONS = {"calendar", "members", "school", "transit", "weather", "waste", "warning", "route"}
CALENDAR_SOURCE_COLORS = {"blue", "green", "purple", "orange", "red", "teal", "slate"}
CALENDAR_SOURCE_DEFAULTS = {
    IntegrationSource.Kind.ICS: {"icon": "calendar", "color": "blue"},
    IntegrationSource.Kind.WASTE: {"icon": "waste", "color": "orange"},
    IntegrationSource.Kind.WEATHER: {"icon": "weather", "color": "blue"},
    IntegrationSource.Kind.WARNING: {"icon": "warning", "color": "red"},
    IntegrationSource.Kind.TRANSIT: {"icon": "transit", "color": "purple"},
    IntegrationSource.Kind.SCHOOL: {"icon": "school", "color": "purple"},
}


def _validate_family_access(serializer, attrs):
    family = attrs.get("family") or (getattr(serializer.instance, "family", None) if serializer.instance else None)
    request = serializer.context.get("request")
    if family and request and request.user.is_authenticated:
        if family.status != Family.Status.ACTIVE or not Membership.objects.filter(family=family, user=request.user).exists():
            raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    return family


def _validate_source_config(config):
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise serializers.ValidationError({"config": "Integrationskonfiguration muss ein Objekt sein."})
    config = dict(config)
    presentation = config.get("presentation")
    if presentation is None:
        return config
    if not isinstance(presentation, dict):
        raise serializers.ValidationError({"config": {"presentation": "Darstellung muss ein Objekt sein."}})
    unknown = set(presentation) - {"icon", "color", "label"}
    if unknown:
        raise serializers.ValidationError({"config": {"presentation": f"Unbekannte Darstellungsfelder: {', '.join(sorted(unknown))}."}})
    normalized = {}
    icon = presentation.get("icon")
    if icon is not None:
        if icon not in CALENDAR_SOURCE_ICONS:
            raise serializers.ValidationError({"config": {"presentation": {"icon": "Nicht unterstütztes Kalender-Icon."}}})
        normalized["icon"] = icon
    color = presentation.get("color")
    if color is not None:
        if color not in CALENDAR_SOURCE_COLORS:
            raise serializers.ValidationError({"config": {"presentation": {"color": "Nicht unterstützte Kalenderfarbe."}}})
        normalized["color"] = color
    if "label" in presentation:
        label = str(presentation.get("label") or "").strip()
        if len(label) > 80:
            raise serializers.ValidationError({"config": {"presentation": {"label": "Kalenderbezeichnung darf höchstens 80 Zeichen lang sein."}}})
        if label:
            normalized["label"] = label
    config["presentation"] = normalized
    return config


def _source_presentation(source):
    defaults = CALENDAR_SOURCE_DEFAULTS.get(source.kind, {"icon": "calendar", "color": "slate"})
    configured = (source.config or {}).get("presentation") if isinstance(source.config, dict) else None
    configured = configured if isinstance(configured, dict) else {}
    icon = configured.get("icon") if configured.get("icon") in CALENDAR_SOURCE_ICONS else defaults["icon"]
    color = configured.get("color") if configured.get("color") in CALENDAR_SOURCE_COLORS else defaults["color"]
    label = str(configured.get("label") or source.name or "Kalender").strip()[:80]
    return {"icon": icon, "color": color, "label": label}


def _membership_profile(obj):
    try:
        return obj.user.familyos_profile
    except Exception:
        return None


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    avatar = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    birth_month = serializers.SerializerMethodField()
    birth_day = serializers.SerializerMethodField()
    birth_year = serializers.SerializerMethodField()

    def _birthday_visible(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.id == obj.user_id:
            return "full_date"
        return obj.birthday_visibility

    def get_avatar(self, obj):
        return self.get_avatar_url(obj)

    def get_avatar_url(self, obj):
        profile = _membership_profile(obj)
        if profile and profile.avatar_key:
            return f"/api/profile/avatar/{obj.user_id}/128/?v={profile.avatar_version}"
        return obj.avatar or ""

    def get_birth_month(self, obj):
        profile = _membership_profile(obj)
        return profile.birth_month if profile and self._birthday_visible(obj) != Membership.BirthdayVisibility.HIDDEN else None

    def get_birth_day(self, obj):
        profile = _membership_profile(obj)
        return profile.birth_day if profile and self._birthday_visible(obj) != Membership.BirthdayVisibility.HIDDEN else None

    def get_birth_year(self, obj):
        profile = _membership_profile(obj)
        return profile.birth_year if profile and self._birthday_visible(obj) == Membership.BirthdayVisibility.FULL_DATE else None

    class Meta:
        model = Membership
        fields = ["id", "family", "user", "username", "role", "display_name", "avatar", "avatar_url", "birthday_visibility", "birth_month", "birth_day", "birth_year"]
        read_only_fields = ["family", "user", "avatar", "avatar_url", "birth_month", "birth_day", "birth_year"]


class FamilyInvitationSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source="is_active", read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.username", read_only=True)
    family_name = serializers.CharField(source="family.name", read_only=True)
    class Meta:
        model = FamilyInvitation
        fields = ["id", "family", "family_name", "token", "role", "email", "display_name", "expires_at", "accepted_at", "revoked_at", "active", "invited_by", "invited_by_name", "created_at"]
        read_only_fields = ["token", "accepted_at", "revoked_at", "invited_by"]


class FamilySerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)
    class Meta:
        model = Family
        fields = ["id", "name", "slug", "locale", "timezone", "status", "memberships"]
        read_only_fields = ["status"]


class WorkflowColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskWorkflowColumn
        fields = ["id", "task_list", "name", "key", "position", "kind", "is_terminal", "archived"]
        read_only_fields = ["task_list", "key"]


class TaskListSerializer(serializers.ModelSerializer):
    workflow_columns = WorkflowColumnSerializer(many=True, read_only=True)
    open_count = serializers.SerializerMethodField()
    done_count = serializers.SerializerMethodField()
    def get_open_count(self, obj): return self._visible_tasks(obj).filter(completed_at__isnull=True).count()
    def get_done_count(self, obj): return self._visible_tasks(obj).filter(completed_at__isnull=False).count()
    def _visible_tasks(self,obj):
        request=self.context.get("request")
        return obj.tasks.exclude(hidden_from_user=request.user) if request else obj.tasks.filter(hidden_from_user__isnull=True)
    def validate(self, attrs):
        _validate_family_access(self, attrs)
        if "workflow_enabled" in attrs:
            family = attrs.get("family") or self.instance.family
            request = self.context.get("request")
            if request and not Membership.objects.filter(family=family, user=request.user, role__in=["owner", "adult"]).exists():
                raise PermissionDenied("Only owners/adults can configure workflows.")
        return attrs
    def create(self, validated_data):
        from .task_workflow import configure_workflow
        from django.db import transaction
        with transaction.atomic():
            enabled = validated_data.pop("workflow_enabled", False)
            instance = super().create(validated_data)
            return configure_workflow(instance, True) if enabled else instance
    def update(self, instance, validated_data):
        from .task_workflow import configure_workflow
        from django.db import transaction
        with transaction.atomic():
            enabled = validated_data.pop("workflow_enabled", instance.workflow_enabled)
            instance = super().update(instance, validated_data)
            return configure_workflow(instance, enabled)
    class Meta:
        model = TaskList
        fields = ["id", "family", "name", "icon", "archived", "sort_order", "workflow_enabled", "workflow_columns", "open_count", "done_count", "created_at", "updated_at"]


class TaskSerializer(serializers.ModelSerializer):
    workflow_status = serializers.CharField(source="workflow_column.name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True)
    list_name = serializers.CharField(source="task_list.name", read_only=True)
    list_icon = serializers.CharField(source="task_list.icon", read_only=True)

    def validate(self, attrs):
        family = _validate_family_access(self, attrs)
        task_list = attrs.get("task_list") or (self.instance.task_list if self.instance else None)
        assignee = attrs.get("assignee") if "assignee" in attrs else (self.instance.assignee if self.instance else None)
        if family and task_list and task_list.family_id != family.id:
            raise serializers.ValidationError({"task_list": "Aufgabenliste gehört nicht zu dieser Familie."})
        if family and assignee and not Membership.objects.filter(family=family, user=assignee).exists():
            raise serializers.ValidationError({"assignee": "Person gehört nicht zu dieser Familie."})
        column = attrs.get("workflow_column")
        if column and (not task_list or not task_list.workflow_enabled or column.task_list_id != task_list.id or column.archived):
            raise serializers.ValidationError({"workflow_column": "Column does not belong to this active workflow."})
        return attrs

    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ["created_by", "workflow_position"]


class ShoppingItemSerializer(serializers.ModelSerializer):
    added_by_name = serializers.CharField(source="added_by.username", read_only=True)

    def validate(self, attrs):
        shopping_list = attrs.get("shopping_list") or (self.instance.shopping_list if self.instance else None)
        request = self.context.get("request")
        if shopping_list and request and request.user.is_authenticated:
            if shopping_list.family.status != Family.Status.ACTIVE or not Membership.objects.filter(family=shopping_list.family, user=request.user).exists():
                raise PermissionDenied("Einkaufsliste gehört nicht zu deiner Familie.")
        return attrs

    class Meta:
        model = ShoppingItem
        fields = "__all__"
        read_only_fields = ["added_by", "checked_at"]


class ShoppingListSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    def _visible_items(self,obj):
        request=self.context.get("request")
        return obj.items.exclude(hidden_from_user=request.user) if request else obj.items.filter(hidden_from_user__isnull=True)
    def get_items(self,obj): return ShoppingItemSerializer(self._visible_items(obj),many=True,context=self.context).data
    open_count = serializers.SerializerMethodField()
    checked_count = serializers.SerializerMethodField()
    def get_open_count(self, obj): return self._visible_items(obj).filter(checked=False).count()
    def get_checked_count(self, obj): return self._visible_items(obj).filter(checked=True).count()
    def validate(self, attrs):
        _validate_family_access(self, attrs)
        return attrs
    class Meta:
        model = ShoppingList
        fields = ["id", "family", "name", "store", "icon", "archived", "sort_order", "items", "open_count", "checked_count", "created_at", "updated_at"]


class RoutineLogSerializer(serializers.ModelSerializer):
    done_by_name = serializers.CharField(source="done_by.username", read_only=True)
    class Meta:
        model = RoutineLog
        fields = ["id", "routine", "done_at", "done_by", "done_by_name", "note", "created_at"]
        read_only_fields = ["done_by"]


class RoutineSerializer(serializers.ModelSerializer):
    logs = serializers.SerializerMethodField()
    last_done_at = serializers.SerializerMethodField()
    prediction = serializers.SerializerMethodField()
    log_count = serializers.SerializerMethodField()
    period_count = serializers.SerializerMethodField()
    snoozed_until = serializers.SerializerMethodField()

    def _logs(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", {})
        return list(cache["logs"] if "logs" in cache else obj.logs.all())

    def get_logs(self, obj):
        return RoutineLogSerializer(sorted(self._logs(obj), key=lambda x:x.done_at, reverse=True)[:10], many=True).data

    def get_log_count(self, obj):
        return len(self._logs(obj))

    def get_period_count(self, obj):
        from datetime import timedelta
        from django.utils import timezone
        start = timezone.now()-timedelta(days=obj.target_period_days)
        return sum(log.done_at>=start for log in self._logs(obj))

    def get_snoozed_until(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        state = next((x for x in obj.reminder_states.all() if x.membership.user_id==request.user.id), None)
        from django.utils import timezone
        return state.snoozed_until if state and state.snoozed_until and state.snoozed_until>timezone.now() else None

    def get_last_done_at(self, obj):
        logs = self._logs(obj)
        return max((log.done_at for log in logs if log.done_at), default=None)

    def get_prediction(self, obj):
        return routine_prediction(obj)

    def validate(self, attrs):
        _validate_family_access(self, attrs)
        count = attrs.get("target_count", self.instance.target_count if self.instance else None)
        period = attrs.get("target_period_days", self.instance.target_period_days if self.instance else 7)
        if count is not None and (count<1 or count>100 or period/count<1/24):
            raise serializers.ValidationError({"target_count": "Choose 1–100 times, at most once per hour."})
        if not 1<=period<=365:
            raise serializers.ValidationError({"target_period_days": "Choose 1–365 days."})
        return attrs

    class Meta:
        model = Routine
        fields = ["id", "family", "name", "icon", "active", "target_count", "target_period_days", "reminder_enabled", "last_done_at", "prediction", "logs", "log_count", "period_count", "snoozed_until"]


class IntegrationSourceSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        _validate_family_access(self, attrs)
        if "config" in attrs:
            attrs["config"] = _validate_source_config(attrs.get("config"))
        return attrs
    def to_representation(self, instance):
        data = super().to_representation(instance)
        config = dict(data.get("config") or {})
        for key in ("bot_token", "api_key", "access_token", "refresh_token", "password", "secret", "client_secret", "ics_content"):
            if key in config and config[key]:
                config[key] = "••••••••"
        if config.get("secret_endpoint") and data.get("endpoint"):
            data["endpoint"] = "••••••••"
        data["config"] = config
        data["presentation"] = _source_presentation(instance)
        return data
    class Meta:
        model = IntegrationSource
        fields = "__all__"


class FamilyEventSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        _validate_family_access(self, attrs)
        source = attrs.get("source") if "source" in attrs else (self.instance.source if self.instance else None)
        family = attrs.get("family") or (self.instance.family if self.instance else None)
        if source and family and source.family_id != family.id:
            raise serializers.ValidationError({"source": "Quelle gehört nicht zu dieser Familie."})
        return attrs
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.source_id:
            data["source_name"] = instance.source.name
            data["source_kind"] = instance.source.kind
            data["source_presentation"] = _source_presentation(instance.source)
        else:
            data["source_name"] = None
            data["source_kind"] = None
            data["source_presentation"] = None
        return data
    class Meta:
        model = FamilyEvent
        fields = "__all__"


class InboxItemSerializer(serializers.ModelSerializer):
    title = serializers.CharField(required=False, allow_blank=True)
    recipient_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    recipients = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()

    def validate(self, attrs):
        family = _validate_family_access(self, attrs)
        recipient_ids = attrs.get("recipient_ids") or []
        if family and recipient_ids:
            found = Membership.objects.filter(family=family, id__in=recipient_ids).count()
            if found != len(set(recipient_ids)):
                raise serializers.ValidationError({"recipient_ids": "Mindestens ein Empfänger gehört nicht zu dieser Familie."})
        return attrs

    def _membership(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        return Membership.objects.filter(family=obj.family, user=request.user).first()

    def _receipt(self, obj):
        membership = self._membership(obj)
        if not membership:
            return None
        return next((row for row in obj.receipts.all() if row.membership_id == membership.id), None)

    def get_recipients(self, obj):
        return [{"id": str(row.membership_id), "display_name": row.membership.display_name or row.membership.user.username, "username": row.membership.user.username} for row in obj.receipts.all()]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return "FamilyOS"
        membership = Membership.objects.filter(family=obj.family, user=obj.created_by).first()
        return (membership.display_name if membership else "") or obj.created_by.get_short_name() or obj.created_by.username

    def get_unread(self, obj):
        request = self.context.get("request")
        if request and obj.created_by_id == request.user.id:
            return False
        receipt = self._receipt(obj)
        if receipt:
            return receipt.read_at is None
        return obj.status == "new"

    def get_read_at(self, obj):
        receipt = self._receipt(obj)
        return receipt.read_at if receipt else None

    def get_can_withdraw(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if obj.created_by_id == request.user.id:
            return True
        return Membership.objects.filter(family=obj.family, user=request.user, role=Membership.Role.OWNER).exists()

    def create(self, validated_data):
        validated_data.pop("recipient_ids", None)
        return super().create(validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.withdrawn_at:
            data["status"] = "withdrawn"
        elif instance.status == "new":
            request = self.context.get("request")
            data["status"] = "sent" if request and instance.created_by_id == request.user.id else ("new" if data["unread"] else "read")
        return data

    class Meta:
        model = InboxItem
        fields = ["id", "family", "title", "body", "source", "status", "parsed", "created_by", "created_by_name", "audience", "important", "context", "withdrawn_at", "recipient_ids", "recipients", "unread", "read_at", "can_withdraw", "created_at", "updated_at"]
        read_only_fields = ["source", "status", "created_by", "withdrawn_at"]


class AutomationExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationExecution
        fields = ["id", "fingerprint", "status", "message", "created_at"]


class AutomationRuleSerializer(serializers.ModelSerializer):
    executions = AutomationExecutionSerializer(many=True, read_only=True)
    def validate(self, attrs):
        _validate_family_access(self, attrs)
        return attrs
    class Meta:
        model = AutomationRule
        fields = ["id", "family", "name", "icon", "enabled", "trigger_type", "trigger_config", "action_type", "action_config", "created_by", "last_run_at", "executions", "created_at", "updated_at"]
        read_only_fields = ["created_by", "last_run_at"]