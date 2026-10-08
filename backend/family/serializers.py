from rest_framework import serializers
from .models import Family, Membership, FamilyInvitation, TaskList, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem, AutomationRule, AutomationExecution


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    class Meta:
        model = Membership
        fields = ["id", "user", "username", "role", "display_name", "avatar"]


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
        fields = ["id", "name", "slug", "locale", "timezone", "memberships"]


class TaskListSerializer(serializers.ModelSerializer):
    open_count = serializers.SerializerMethodField()
    done_count = serializers.SerializerMethodField()
    def get_open_count(self, obj): return obj.tasks.filter(completed_at__isnull=True).count()
    def get_done_count(self, obj): return obj.tasks.filter(completed_at__isnull=False).count()
    class Meta:
        model = TaskList
        fields = ["id", "family", "name", "icon", "archived", "sort_order", "open_count", "done_count", "created_at", "updated_at"]


class TaskSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source="assignee.username", read_only=True)
    list_name = serializers.CharField(source="task_list.name", read_only=True)
    list_icon = serializers.CharField(source="task_list.icon", read_only=True)

    def validate(self, attrs):
        family = attrs.get("family") or (self.instance.family if self.instance else None)
        task_list = attrs.get("task_list")
        assignee = attrs.get("assignee")
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
            if not Membership.objects.filter(family=shopping_list.family, user=request.user).exists():
                raise serializers.ValidationError({"shopping_list": "Einkaufsliste gehört nicht zu deiner Familie."})
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
    def get_last_done_at(self, obj):
        log = obj.logs.order_by("-done_at").first()
        return log.done_at if log else None
    class Meta:
        model = Routine
        fields = ["id", "family", "name", "suggested_interval_days", "icon", "active", "last_done_at", "logs"]


class IntegrationSourceSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        config = dict(data.get("config") or {})
        for key in ("bot_token", "api_key", "access_token", "refresh_token", "password", "secret", "client_secret"):
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
    class Meta:
        model = FamilyEvent
        fields = "__all__"


class InboxItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboxItem
        fields = "__all__"


class AutomationExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationExecution
        fields = ["id", "fingerprint", "status", "message", "created_at"]


class AutomationRuleSerializer(serializers.ModelSerializer):
    executions = AutomationExecutionSerializer(many=True, read_only=True)
    class Meta:
        model = AutomationRule
        fields = ["id", "family", "name", "icon", "enabled", "trigger_type", "trigger_config", "action_type", "action_config", "created_by", "last_run_at", "executions", "created_at", "updated_at"]
        read_only_fields = ["created_by", "last_run_at"]
