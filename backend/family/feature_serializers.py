import re

from django.utils import timezone
from rest_framework import serializers

from .models import Membership
from .models_features import LoyaltyCard, NotificationPreference
from .pass_catalog import PASS_ICON_KEYS, auto_accent


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    family = serializers.UUIDField(source="membership.family_id", read_only=True)
    membership = serializers.UUIDField(source="membership_id", read_only=True)

    class Meta:
        model = NotificationPreference
        fields = [
            "membership", "family", "tasks", "task_assigned", "shopping", "calendar",
            "family_updates", "messages", "routines", "birthdays", "birthday_prepare",
            "detail_level", "quiet_hours_enabled", "quiet_start", "quiet_end", "updated_at",
        ]
        read_only_fields = ["membership", "family", "updated_at"]

    def validate(self, attrs):
        enabled = attrs.get("quiet_hours_enabled", getattr(self.instance, "quiet_hours_enabled", False))
        start = attrs.get("quiet_start", getattr(self.instance, "quiet_start", None))
        end = attrs.get("quiet_end", getattr(self.instance, "quiet_end", None))
        if enabled and start == end:
            raise serializers.ValidationError({"quiet_end": "Ruhezeit benötigt unterschiedliche Anfangs- und Endzeiten."})
        return attrs


class LoyaltyCardSerializer(serializers.ModelSerializer):
    shared_with = serializers.SerializerMethodField()
    shared_with_ids = serializers.PrimaryKeyRelatedField(
        source="shared_with",
        queryset=Membership.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )
    holder_membership = serializers.PrimaryKeyRelatedField(
        queryset=Membership.objects.all(),
        allow_null=True,
        required=False,
    )
    holder_display = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    can_edit = serializers.SerializerMethodField()
    resolved_color = serializers.SerializerMethodField()
    lifecycle_status = serializers.SerializerMethodField()
    can_restore = serializers.SerializerMethodField()

    class Meta:
        model = LoyaltyCard
        fields = [
            "id", "family", "name", "pass_type", "logo", "icon_key", "color", "color_mode", "resolved_color",
            "holder_name", "holder_membership", "holder_display", "customer_number", "barcode_value", "barcode_format",
            "note", "created_by", "created_by_name", "shared_with", "shared_with_ids", "favorite", "sort_order",
            "archived", "archived_at", "archive_reason", "used_at", "restore_until", "undo_window_minutes",
            "event_ends_at", "lifecycle_status", "can_restore", "can_edit", "created_at", "updated_at",
        ]
        read_only_fields = [
            "created_by", "archived", "archived_at", "archive_reason", "used_at", "restore_until",
            "lifecycle_status", "can_restore", "resolved_color", "created_at", "updated_at", "can_edit",
        ]
        extra_kwargs = {"barcode_value": {"write_only": False}}

    def get_shared_with(self, obj):
        return [
            {
                "id": str(member.id),
                "user": member.user_id,
                "name": member.display_name or member.user.get_short_name() or member.user.username,
                "role": member.role,
            }
            for member in obj.shared_with.select_related("user").all()
        ]

    def get_holder_display(self, obj):
        if obj.holder_name:
            return obj.holder_name
        member = obj.holder_membership
        if member:
            return member.display_name or member.user.get_short_name() or member.user.username
        return ""

    def get_can_edit(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if obj.created_by_id == request.user.id:
            return True
        return Membership.objects.filter(
            family=obj.family,
            user=request.user,
            role=Membership.Role.OWNER,
        ).exists()

    def get_resolved_color(self, obj):
        if obj.color_mode == LoyaltyCard.ColorMode.AUTO:
            return auto_accent(obj.icon_key, obj.color or "#6750A4")
        return obj.color or "#6750A4"

    def get_lifecycle_status(self, obj):
        if not obj.archived:
            return "active"
        if obj.archive_reason == LoyaltyCard.ArchiveReason.EVENT_ENDED:
            return "event_ended"
        if obj.used_at:
            return "used"
        return "archived"

    def get_can_restore(self, obj):
        return bool(
            obj.archived
            and obj.archive_reason == LoyaltyCard.ArchiveReason.USED
            and obj.restore_until
            and obj.restore_until > timezone.now()
        )

    def validate_logo(self, value):
        # Legacy values stay readable and can be round-tripped unchanged. New branding
        # must use icon_key so persisted data can never become a CSS/HTML class channel.
        if not value:
            return ""
        if self.instance and value == self.instance.logo:
            return value
        raise serializers.ValidationError("Neue Icons müssen aus der festen Icon-Registry gewählt werden.")

    def validate_icon_key(self, value):
        value = str(value or "").strip()
        if value and value not in PASS_ICON_KEYS:
            raise serializers.ValidationError("Unbekanntes Icon.")
        return value

    def validate_color(self, value):
        value = str(value or "").strip()
        if not HEX_COLOR.fullmatch(value):
            raise serializers.ValidationError("Farbe muss als #RRGGBB angegeben werden.")
        return value.upper()

    def validate_undo_window_minutes(self, value):
        if value < 1 or value > 1440:
            raise serializers.ValidationError("Undo-Zeitfenster muss zwischen 1 und 1440 Minuten liegen.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or (self.instance.family if self.instance else None)
        if not family or not request or not Membership.objects.filter(family=family, user=request.user).exists():
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})

        holder = attrs.get("holder_membership", self.instance.holder_membership if self.instance else None)
        if holder and holder.family_id != family.id:
            raise serializers.ValidationError({"holder_membership": "Karteninhaber gehört nicht zu dieser Familie."})
        for member in attrs.get("shared_with", []):
            if member.family_id != family.id:
                raise serializers.ValidationError({"shared_with_ids": "Freigaben dürfen nur Mitglieder derselben Familie enthalten."})

        value = str(attrs.get("barcode_value", self.instance.barcode_value if self.instance else "") or "").strip()
        fmt = attrs.get("barcode_format", self.instance.barcode_format if self.instance else LoyaltyCard.BarcodeFormat.CODE128)
        if not value:
            raise serializers.ValidationError({"barcode_value": "Barcode-Wert fehlt."})
        numeric_lengths = {
            LoyaltyCard.BarcodeFormat.EAN13: 13,
            LoyaltyCard.BarcodeFormat.EAN8: 8,
            LoyaltyCard.BarcodeFormat.UPCA: 12,
            LoyaltyCard.BarcodeFormat.UPCE: 8,
        }
        if fmt in numeric_lengths and (not value.isdigit() or len(value) != numeric_lengths[fmt]):
            raise serializers.ValidationError({"barcode_value": f"{fmt} benötigt {numeric_lengths[fmt]} Ziffern."})
        if fmt == LoyaltyCard.BarcodeFormat.ITF and (not value.isdigit() or len(value) % 2):
            raise serializers.ValidationError({"barcode_value": "ITF benötigt eine gerade Anzahl Ziffern."})
        attrs["barcode_value"] = value
        return attrs
