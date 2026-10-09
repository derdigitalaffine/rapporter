from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import Family, Membership, FamilyInvitation, TaskList, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem, InboxReceipt, AutomationRule, AutomationExecution
from .predictions import routine_prediction


def _validate_family_access(serializer, attrs):
    family = attrs.get("family") or (getattr(serializer.instance, "family", None) if serializer.instance else None)
    request = serializer.context.get("request")
    if family and request and request.user.is_authenticated:
        if family.status != Family.Status.ACTIVE or not Membership.objects.filter(family=family, user=request.user).exists():
            raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    return family


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    class Meta:
        model = Membership
        fields = ["id", "family", "user", "username", "role", "display_name", "avatar"]
        read_only_fields = ["family", "user"]


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


class TaskListSerializer(serializers.ModelSerializer):
    open_count = serializers.SerializerMethodField()
    done_count = serializers.SerializerMethodField()
    def get_open_count(self, obj): return obj.tasks.filter(completed_at__isnull=True).count()
    def get_done_count(self, obj): return obj.tasks.filter(completed_at__isnull=False).count()
    def validate(self, attrs):
        _validate_family_access(self, attrs)
        return attrs
    class Meta:
        model = TaskList
        fields = ["id", "family", "name", "icon", "archived", "sort_order", "open_count", "done_count", "created_at", "updated_at"]


class TaskSerializer(serializers.ModelSerializer):
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
        return attrs

    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ["created_by"]


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
    items = ShoppingItemSerializer(many=True, read_only=True)
    open_count = serializers.SerializerMethodField()
    checked_count = serializers.SerializerMethodField()
    def get_open_count(self, obj): return obj.items.filter(checked=False).count()
    def get_checked_count(self, obj): return obj.items.filter(checked=True).count()
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
    logs = RoutineLogSerializer(many=True, read_only=True)
    last_done_at = serializers.SerializerMethodField()
    prediction = serializers.SerializerMethodField()

    def get_last_done_at(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", {})
        logs = list(cache.get("logs") or obj.logs.all())
        return max((log.done_at for log in logs if log.done_at), default=None)

    def get_prediction(self, obj):
        return routine_prediction(obj)

    def validate(self, attrs):
        _validate_family_access(self, attrs)
        return attrs

    class Meta:
        model = Routine
        fields = ["id", "family", "name", "icon", "active", "last_done_at", "prediction", "logs"]


class IntegrationSourceSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        _validate_family_access(self, attrs)
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
