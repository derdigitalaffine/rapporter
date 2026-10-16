import hashlib
import hmac

from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .caldav_discovery import CalDavDiscoveryError, discover_calendars
from .caldav_models import CalDavConnection
from .caldav_secrets import decrypt_credentials, encrypt_credentials
from .caldav_sync import sync_connection
from .models import Family, IntegrationSource, Membership


MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}


def calendar_key(connection, href):
    secret = settings.SECRET_KEY.encode("utf-8")
    value = f"{connection.id}:{href}".encode("utf-8")
    return hmac.new(secret, value, hashlib.sha256).hexdigest()[:32]


class CalDavConnectionSerializer(serializers.ModelSerializer):
    credential_state = serializers.CharField(read_only=True)
    calendar_selected = serializers.SerializerMethodField()
    server_url = serializers.CharField(write_only=True, required=False, allow_blank=False, max_length=2048)
    username = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=512)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=2048, trim_whitespace=False)

    class Meta:
        model = CalDavConnection
        fields = [
            "id", "scope", "name", "family", "member", "access_mode",
            "enabled", "credential_state", "calendar_selected", "server_url", "username", "password",
            "last_discovered_at", "last_error_code", "created_at", "updated_at",
        ]
        read_only_fields = ["last_discovered_at", "last_error_code", "created_at", "updated_at"]

    def get_calendar_selected(self, instance):
        return bool(instance.calendar_href)

    def _family_membership(self, family):
        return Membership.objects.filter(
            family=family,
            family__status=Family.Status.ACTIVE,
            user=self.context["request"].user,
            role__in=MANAGER_ROLES,
        ).first()

    def validate(self, attrs):
        scope = attrs.get("scope", getattr(self.instance, "scope", None))
        family = attrs.get("family", getattr(self.instance, "family", None))
        member = attrs.get("member", getattr(self.instance, "member", None))
        if self.instance is not None:
            if "scope" in attrs and attrs["scope"] != self.instance.scope:
                raise ValidationError({"scope": "Der Connection-Scope kann nicht direkt geändert werden."})
            if "family" in attrs and attrs["family"] != self.instance.family:
                raise ValidationError({"family": "Die Connection-Familie kann nicht direkt geändert werden."})
        if scope == CalDavConnection.Scope.PERSONAL:
            if family is not None or member is not None:
                raise ValidationError({"family": "Persönliche Connections besitzen keine Family- oder Mitglied-Zuordnung."})
        elif scope == CalDavConnection.Scope.FAMILY:
            if family is None:
                raise ValidationError({"family": "Für Family-Connections ist eine Familie erforderlich."})
            if not self._family_membership(family):
                raise PermissionDenied("Nur Owner/Adults dürfen Family-Integrationen verwalten.")
            if member is not None and member.family_id != family.id:
                raise ValidationError({"member": "Das Mitglied muss zur gewählten Familie gehören."})
            if member is not None:
                duplicate = CalDavConnection.objects.filter(family=family, member=member)
                if self.instance is not None:
                    duplicate = duplicate.exclude(pk=self.instance.pk)
                if duplicate.exists():
                    raise ValidationError({"member": "Für dieses Familienmitglied ist bereits ein CalDAV-Kalender verbunden."})
        else:
            raise ValidationError({"scope": "Ungültiger Connection-Scope."})

        credential_fields = {key for key in ("server_url", "username", "password") if key in attrs}
        if self.instance is None and credential_fields != {"server_url", "username", "password"}:
            raise ValidationError({"credential_state": "Server-URL, Benutzername und Passwort sind erforderlich."})
        return attrs

    def _credentials(self, validated_data):
        supplied = {key: validated_data.pop(key) for key in ("server_url", "username", "password") if key in validated_data}
        if not supplied:
            return None
        current = {"server_url": "", "username": "", "password": ""}
        if self.instance and self.instance.credentials_encrypted:
            try:
                current.update(decrypt_credentials(self.instance.credentials_encrypted))
            except ValueError:
                if set(supplied) != {"server_url", "username", "password"}:
                    raise ValidationError({"credential_state": "Credentials müssen vollständig neu gesetzt werden."})
        current.update(supplied)
        if not current["server_url"]:
            raise ValidationError({"server_url": "Server-URL fehlt."})
        return encrypt_credentials(**current)

    def create(self, validated_data):
        encrypted = self._credentials(validated_data)
        request = self.context["request"]
        scope = validated_data["scope"]
        return CalDavConnection.objects.create(
            **validated_data,
            owner=request.user if scope == CalDavConnection.Scope.PERSONAL else None,
            created_by=request.user,
            credentials_encrypted=encrypted or "",
        )

    def update(self, instance, validated_data):
        encrypted = self._credentials(validated_data)
        if encrypted is not None:
            validated_data["credentials_encrypted"] = encrypted
            validated_data["last_error_code"] = ""
            validated_data["calendar_href"] = ""
        return super().update(instance, validated_data)


class CalDavConnectionViewSet(viewsets.ModelViewSet):
    serializer_class = CalDavConnectionSerializer
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        managed_family_ids = Membership.objects.filter(
            user=user,
            family__status=Family.Status.ACTIVE,
            role__in=MANAGER_ROLES,
        ).values_list("family_id", flat=True)
        return CalDavConnection.objects.filter(
            models.Q(scope=CalDavConnection.Scope.PERSONAL, owner=user, family__isnull=True)
            | models.Q(scope=CalDavConnection.Scope.FAMILY, owner__isnull=True, family_id__in=managed_family_ids, family__status=Family.Status.ACTIVE)
        ).distinct()

    def _discover(self, connection):
        try:
            credentials = decrypt_credentials(connection.credentials_encrypted)
            return discover_calendars(**credentials)
        except CalDavDiscoveryError as exc:
            code = str(exc)
            connection.last_error_code = code
            connection.save(update_fields=["last_error_code", "updated_at"])
            raise ValidationError({"detail": code})
        except ValueError as exc:
            code = str(exc) if str(exc).startswith("caldav_credentials_") else "caldav_credentials_unreadable"
            connection.last_error_code = code
            connection.save(update_fields=["last_error_code", "updated_at"])
            raise ValidationError({"detail": code})

    @action(detail=True, methods=["post"])
    def discover(self, request, pk=None):
        connection = self.get_object()
        calendars = self._discover(connection)
        connection.last_discovered_at = timezone.now()
        connection.last_error_code = ""
        connection.save(update_fields=["last_discovered_at", "last_error_code", "updated_at"])
        return Response({
            "connection": str(connection.id),
            "credential_state": connection.credential_state,
            "access_mode": connection.access_mode,
            "member": str(connection.member_id) if connection.member_id else None,
            "calendar_count": len(calendars),
            "calendars": [
                {
                    "calendar_key": calendar_key(connection, row["href"]),
                    "display_name": row["display_name"],
                    "components": row["components"],
                    "sync_token_supported": row["sync_token_supported"],
                }
                for row in calendars
            ],
        })

    @action(detail=True, methods=["post"], url_path="select-calendar")
    def select_calendar(self, request, pk=None):
        connection = self.get_object()
        key = str(request.data.get("calendar_key") or "")
        if not key:
            raise ValidationError({"calendar_key": "Kalenderauswahl fehlt."})
        calendars = self._discover(connection)
        selected = next((row for row in calendars if hmac.compare_digest(calendar_key(connection, row["href"]), key)), None)
        if not selected:
            raise ValidationError({"calendar_key": "Kalender wurde nicht in der aktuellen Discovery gefunden."})
        components = set(selected.get("components") or [])
        if components and "VEVENT" not in components:
            raise ValidationError({"calendar_key": "Diese Collection unterstützt keine Termine."})
        connection.calendar_href = selected["href"]
        connection.last_discovered_at = timezone.now()
        connection.last_error_code = ""
        connection.save(update_fields=["calendar_href", "last_discovered_at", "last_error_code", "updated_at"])
        return Response({
            "id": str(connection.id),
            "calendar_selected": True,
            "display_name": selected.get("display_name") or connection.name,
            "access_mode": connection.access_mode,
        })

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        connection = self.get_object()
        if connection.scope != CalDavConnection.Scope.FAMILY:
            raise ValidationError({"detail": "caldav_family_scope_required"})
        try:
            result = sync_connection(connection)
        except (CalDavDiscoveryError, ValueError) as exc:
            code = str(exc)
            connection.last_error_code = code[:64]
            connection.save(update_fields=["last_error_code", "updated_at"])
            raise ValidationError({"detail": code})
        connection.last_error_code = "caldav_conflict" if result.get("conflicts") else ""
        connection.save(update_fields=["last_error_code", "updated_at"])
        return Response({"connection": str(connection.id), "access_mode": connection.access_mode, **result})

    def perform_destroy(self, instance):
        if instance.family_id:
            sources = IntegrationSource.objects.filter(
                family=instance.family,
                config__caldav_connection=str(instance.id),
            )
            for source in sources:
                source.events.all().delete()
                source.delete()
        super().perform_destroy(instance)
