from rest_framework import serializers

from .invitation_delivery import invitation_delivery_summary
from .models import FamilyInvitation


class SafeFamilyInvitationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True, allow_blank=False)
    active = serializers.BooleanField(source="is_active", read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.username", read_only=True)
    family_name = serializers.CharField(source="family.name", read_only=True)
    delivery_status = serializers.SerializerMethodField()
    last_sent_at = serializers.SerializerMethodField()

    class Meta:
        model = FamilyInvitation
        fields = [
            "id",
            "family",
            "family_name",
            "role",
            "email",
            "display_name",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "active",
            "delivery_status",
            "last_sent_at",
            "invited_by",
            "invited_by_name",
            "created_at",
        ]
        read_only_fields = ["accepted_at", "revoked_at", "invited_by", "delivery_status", "last_sent_at"]

    def get_delivery_status(self, obj):
        return invitation_delivery_summary(obj)["delivery_status"]

    def get_last_sent_at(self, obj):
        return invitation_delivery_summary(obj)["last_sent_at"]
