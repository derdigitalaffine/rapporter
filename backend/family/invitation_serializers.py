from rest_framework import serializers

from .models import FamilyInvitation


class SafeFamilyInvitationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True, allow_blank=False)
    active = serializers.BooleanField(source="is_active", read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.username", read_only=True)
    family_name = serializers.CharField(source="family.name", read_only=True)

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
            "invited_by",
            "invited_by_name",
            "created_at",
        ]
        read_only_fields = ["accepted_at", "revoked_at", "invited_by"]
