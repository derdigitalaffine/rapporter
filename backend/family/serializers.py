from rest_framework import serializers
from .models import Family, Membership, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem

class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    class Meta:
        model = Membership
        fields = ["id", "user", "username", "role", "display_name", "avatar"]

class FamilySerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)
    class Meta:
        model = Family
        fields = ["id", "name", "slug", "locale", "timezone", "memberships"]

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ["created_by"]

class ShoppingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingItem
        fields = "__all__"
        read_only_fields = ["added_by"]

class ShoppingListSerializer(serializers.ModelSerializer):
    items = ShoppingItemSerializer(many=True, read_only=True)
    class Meta:
        model = ShoppingList
        fields = ["id", "family", "name", "store", "archived", "items", "created_at", "updated_at"]

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
        for key in ("bot_token", "api_key", "access_token", "password", "secret"):
            if key in config:
                config[key] = "••••••••"
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
