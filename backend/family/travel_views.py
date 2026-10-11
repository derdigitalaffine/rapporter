from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import FamilyEvent, Membership
from .private_images import image_path, optimize_image, remove_image, store_image
from .travel_models import Trip, TripPhoto


CONCRETE_DATE_PRECISIONS = frozenset(
    {Trip.DatePrecision.RANGE, Trip.DatePrecision.EXACT}
)


class TripConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "trip_conflict"
    default_detail = {
        "code": "trip_conflict",
        "detail": "Die Reise wurde zwischenzeitlich geändert. Bitte den aktuellen Stand neu laden.",
    }


def _can_manage(user, family_id):
    return Membership.objects.filter(
        family_id=family_id,
        user=user,
        role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
    ).exists()


def _can_add_photos(user, family_id):
    return Membership.objects.filter(family_id=family_id, user=user).exclude(role=Membership.Role.GUEST).exists()


def _family_zone(family):
    try:
        return ZoneInfo(family.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _derived_stage(family, precision, starts_on, ends_on):
    if precision not in CONCRETE_DATE_PRECISIONS or not starts_on or not ends_on:
        return Trip.Stage.PLANNING
    today = datetime.now(_family_zone(family)).date()
    if ends_on < today:
        return Trip.Stage.COMPLETED
    if starts_on <= today <= ends_on:
        return Trip.Stage.ACTIVE
    return Trip.Stage.SCHEDULED


def _event_bounds(trip):
    zone = _family_zone(trip.family)
    start = datetime.combine(trip.starts_on, time.min, tzinfo=zone)
    end = datetime.combine(trip.ends_on + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def _clear_trip_event(trip):
    event_id = trip.calendar_event_id
    if not event_id:
        return
    # Detach first so an unrelated event could never be deleted through a stale
    # relation. Only canonical travel.trip projections are removed.
    Trip.objects.filter(pk=trip.pk, calendar_event_id=event_id).update(calendar_event=None)
    trip.calendar_event = None
    trip.calendar_event_id = None
    FamilyEvent.objects.filter(pk=event_id, type="travel.trip").delete()


def sync_trip_event(trip):
    if (
        trip.date_precision not in CONCRETE_DATE_PRECISIONS
        or not trip.starts_on
        or not trip.ends_on
    ):
        _clear_trip_event(trip)
        return None

    start, end = _event_bounds(trip)
    event = trip.calendar_event or FamilyEvent(family=trip.family)
    event.family = trip.family
    event.type = "travel.trip"
    event.title = trip.title
    event.starts_at = start
    event.ends_at = end
    event.actionable = False
    event.external_id = f"trip:{trip.id}"
    event.payload = {
        "trip_id": str(trip.id),
        "all_day": True,
        "date_start": trip.starts_on.isoformat(),
        "date_end_exclusive": (trip.ends_on + timedelta(days=1)).isoformat(),
        "location": trip.destination,
        "read_only": True,
    }
    event.save()
    if trip.calendar_event_id != event.id:
        Trip.objects.filter(pk=trip.pk).update(calendar_event=event)
        trip.calendar_event = event
    return event


class TripSerializer(serializers.ModelSerializer):
    photos = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    can_add_photos = serializers.SerializerMethodField()
    creator_name = serializers.SerializerMethodField()
    calendar_event_id = serializers.UUIDField(source="calendar_event.id", read_only=True)
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)
    participants = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Membership.objects.none(),
        required=False,
    )

    class Meta:
        model = Trip
        fields = [
            "id",
            "family",
            "participants",
            "title",
            "destination",
            "stage",
            "date_precision",
            "date_year",
            "date_month",
            "date_season",
            "starts_on",
            "ends_on",
            "notes",
            "archived",
            "created_by",
            "creator_name",
            "calendar_event_id",
            "photos",
            "can_manage",
            "can_add_photos",
            "created_at",
            "updated_at",
            "expected_updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at", "calendar_event_id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["participants"].child_relation.queryset = Membership.objects.filter(
                family__memberships__user=request.user,
                family__status="active",
            ).distinct()

    def _current(self, attrs, field, default=None):
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field)
        return default

    @staticmethod
    def _has_value(value):
        return value is not None and value != ""

    def _reject_explicit(self, attrs, fields, message):
        errors = {
            field: message
            for field in fields
            if field in attrs and self._has_value(attrs[field])
        }
        if errors:
            raise serializers.ValidationError(errors)

    def validate(self, attrs):
        if self.instance and "family" in attrs and attrs["family"].id != self.instance.family_id:
            raise serializers.ValidationError({"family": "Die Familie einer Reise kann nicht geändert werden."})

        family = self._current(attrs, "family")
        if "participants" in attrs and any(row.family_id != family.id for row in attrs["participants"]):
            raise serializers.ValidationError(
                {"participants": "Teilnehmende müssen Mitglied derselben Familie wie die Reise sein."}
            )

        starts_on = self._current(attrs, "starts_on")
        ends_on = self._current(attrs, "ends_on")
        date_year = self._current(attrs, "date_year")
        date_month = self._current(attrs, "date_month")
        date_season = self._current(attrs, "date_season", "")

        precision_explicit = "date_precision" in attrs
        date_bounds_touched = "starts_on" in attrs or "ends_on" in attrs
        if precision_explicit:
            precision = attrs["date_precision"]
        elif self.instance is None:
            if starts_on or ends_on:
                precision = Trip.DatePrecision.EXACT
            elif date_season:
                precision = Trip.DatePrecision.SEASON
            elif date_month:
                precision = Trip.DatePrecision.MONTH
            elif date_year:
                precision = Trip.DatePrecision.YEAR
            else:
                precision = Trip.DatePrecision.UNKNOWN
        elif date_bounds_touched and (starts_on or ends_on):
            # Legacy clients that start supplying concrete dates do not need to
            # know about date_precision yet.
            precision = Trip.DatePrecision.EXACT
        else:
            precision = self.instance.date_precision
        attrs["date_precision"] = precision

        if precision == Trip.DatePrecision.UNKNOWN:
            self._reject_explicit(
                attrs,
                ("starts_on", "ends_on", "date_year", "date_month", "date_season"),
                "Für eine Reise ohne Datumsangabe darf dieses Feld nicht gesetzt sein.",
            )
            starts_on = ends_on = date_year = date_month = None
            date_season = ""
            attrs.update(
                starts_on=None,
                ends_on=None,
                date_year=None,
                date_month=None,
                date_season="",
            )
        elif precision == Trip.DatePrecision.YEAR:
            self._reject_explicit(
                attrs,
                ("starts_on", "ends_on", "date_month", "date_season"),
                "Für die Präzision Jahr ist nur date_year zulässig.",
            )
            if not date_year:
                raise serializers.ValidationError({"date_year": "Für die Präzision Jahr ist ein Jahr erforderlich."})
            if not 1 <= date_year <= 9999:
                raise serializers.ValidationError({"date_year": "Das Jahr muss zwischen 1 und 9999 liegen."})
            starts_on = ends_on = date_month = None
            date_season = ""
            attrs.update(starts_on=None, ends_on=None, date_month=None, date_season="")
        elif precision == Trip.DatePrecision.SEASON:
            self._reject_explicit(
                attrs,
                ("starts_on", "ends_on", "date_month"),
                "Für die Präzision Saison sind nur Jahr und Saison zulässig.",
            )
            if not date_year:
                raise serializers.ValidationError({"date_year": "Für eine Saison ist ein Jahr erforderlich."})
            if not 1 <= date_year <= 9999:
                raise serializers.ValidationError({"date_year": "Das Jahr muss zwischen 1 und 9999 liegen."})
            if not date_season:
                raise serializers.ValidationError({"date_season": "Für die Präzision Saison ist eine Saison erforderlich."})
            starts_on = ends_on = date_month = None
            attrs.update(starts_on=None, ends_on=None, date_month=None)
        elif precision == Trip.DatePrecision.MONTH:
            self._reject_explicit(
                attrs,
                ("starts_on", "ends_on", "date_season"),
                "Für die Präzision Monat sind nur Jahr und Monat zulässig.",
            )
            if not date_year:
                raise serializers.ValidationError({"date_year": "Für einen Monat ist ein Jahr erforderlich."})
            if not 1 <= date_year <= 9999:
                raise serializers.ValidationError({"date_year": "Das Jahr muss zwischen 1 und 9999 liegen."})
            if date_month is None or not 1 <= date_month <= 12:
                raise serializers.ValidationError({"date_month": "Der Monat muss zwischen 1 und 12 liegen."})
            starts_on = ends_on = None
            date_season = ""
            attrs.update(starts_on=None, ends_on=None, date_season="")
        elif precision in CONCRETE_DATE_PRECISIONS:
            self._reject_explicit(
                attrs,
                ("date_year", "date_month", "date_season"),
                "Bei konkreten Reisedaten dürfen keine ungefähren Datumsfelder gesetzt sein.",
            )
            if not starts_on or not ends_on:
                raise serializers.ValidationError(
                    {"ends_on": "Für konkrete Reisedaten sind Start- und Enddatum erforderlich."}
                )
            if ends_on < starts_on:
                raise serializers.ValidationError({"ends_on": "Das Enddatum darf nicht vor dem Startdatum liegen."})
            date_year = date_month = None
            date_season = ""
            attrs.update(date_year=None, date_month=None, date_season="")
        else:
            raise serializers.ValidationError({"date_precision": "Unbekannte Datumspräzision."})

        stage_explicit = "stage" in attrs
        archived_explicit = "archived" in attrs
        archived = self._current(attrs, "archived", False)
        stage = self._current(attrs, "stage")

        if stage_explicit and archived_explicit and (
            (attrs["stage"] == Trip.Stage.ARCHIVED) != bool(attrs["archived"])
        ):
            raise serializers.ValidationError(
                {"archived": "archived und stage müssen denselben Archivstatus beschreiben."}
            )

        if stage_explicit:
            stage = attrs["stage"]
            archived = stage == Trip.Stage.ARCHIVED
            attrs["archived"] = archived
        elif archived_explicit:
            archived = bool(attrs["archived"])
            if archived:
                stage = Trip.Stage.ARCHIVED
            elif self.instance is None or self.instance.stage == Trip.Stage.ARCHIVED:
                stage = _derived_stage(family, precision, starts_on, ends_on)
            attrs["stage"] = stage
        elif self.instance is None:
            stage = _derived_stage(family, precision, starts_on, ends_on)
            attrs["stage"] = stage
            attrs["archived"] = stage == Trip.Stage.ARCHIVED
        else:
            stage = self.instance.stage

        if stage in {Trip.Stage.SCHEDULED, Trip.Stage.ACTIVE, Trip.Stage.COMPLETED}:
            if precision not in CONCRETE_DATE_PRECISIONS:
                raise serializers.ValidationError(
                    {"stage": "Scheduled, active und completed benötigen konkrete Reisedaten."}
                )

        return attrs

    def get_photos(self, obj):
        return [
            {
                "id": str(row.id),
                "url": f"/api/trip-photos/{row.id}/",
                "width": row.width,
                "height": row.height,
                "caption": row.caption,
                "uploaded_by": row.uploaded_by_id,
                "created_at": row.created_at,
                "can_delete": row.uploaded_by_id == self.context["request"].user.id
                or _can_manage(self.context["request"].user, obj.family_id),
            }
            for row in obj.photos.all()
        ]

    def get_can_manage(self, obj):
        return _can_manage(self.context["request"].user, obj.family_id)

    def get_can_add_photos(self, obj):
        return _can_add_photos(self.context["request"].user, obj.family_id)

    def get_creator_name(self, obj):
        if not obj.created_by:
            return "FamilyOS"
        membership = Membership.objects.filter(family=obj.family, user=obj.created_by).only("display_name").first()
        if membership and membership.display_name:
            return membership.display_name
        return obj.created_by.get_short_name() or obj.created_by.username


class TripViewSet(viewsets.ModelViewSet):
    serializer_class = TripSerializer
    queryset = Trip.objects.select_related("family", "created_by", "calendar_event").prefetch_related(
        "photos", "participants"
    ).all()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        rows = self.queryset.filter(
            family__memberships__user=self.request.user,
            family__status="active",
        ).distinct()
        family_id = self.request.query_params.get("family")
        if family_id:
            rows = rows.filter(family_id=family_id)
        return rows

    @transaction.atomic
    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not _can_manage(self.request.user, family.id):
            raise PermissionDenied("Nur Erwachsene dürfen Reisen anlegen.")
        serializer.validated_data.pop("expected_updated_at", None)
        trip = serializer.save(created_by=self.request.user)
        sync_trip_event(trip)

    @transaction.atomic
    def perform_update(self, serializer):
        expected_updated_at = serializer.validated_data.pop("expected_updated_at", None)
        trip = Trip.objects.select_for_update().select_related("family").get(pk=serializer.instance.pk)
        if not _can_manage(self.request.user, trip.family_id):
            raise PermissionDenied("Nur Erwachsene dürfen Reisen ändern.")
        if expected_updated_at is not None and expected_updated_at != trip.updated_at:
            raise TripConflict()
        serializer.instance = trip
        trip = serializer.save()
        sync_trip_event(trip)

    @transaction.atomic
    def perform_destroy(self, instance):
        trip = Trip.objects.select_for_update().select_related("family").get(pk=instance.pk)
        if not _can_manage(self.request.user, trip.family_id):
            raise PermissionDenied("Nur Erwachsene dürfen Reisen löschen.")
        event_id = trip.calendar_event_id
        trip.delete()
        if event_id:
            FamilyEvent.objects.filter(pk=event_id, type="travel.trip").delete()

    @action(detail=True, methods=["post"], url_path="photos")
    def photos(self, request, pk=None):
        trip = self.get_object()
        if not _can_add_photos(request.user, trip.family_id):
            raise PermissionDenied("Diese Rolle darf keine Reisefotos hinzufügen.")
        uploads = request.FILES.getlist("images")
        if not uploads:
            raise ValidationError({"images": "Bitte mindestens ein Bild auswählen."})
        if len(uploads) > 12:
            raise ValidationError({"images": "Maximal zwölf Bilder pro Upload."})
        caption = str(request.data.get("caption", "")).strip()
        if len(caption) > 240:
            raise ValidationError({"caption": "Maximal 240 Zeichen."})
        optimized = [optimize_image(upload) for upload in uploads]
        keys = []
        try:
            with transaction.atomic():
                locked = Trip.objects.select_for_update().get(pk=trip.pk)
                for data, width, height in optimized:
                    key = store_image(data)
                    keys.append(key)
                    TripPhoto.objects.create(
                        trip=locked,
                        key=key,
                        width=width,
                        height=height,
                        caption=caption,
                        uploaded_by=request.user,
                    )
        except Exception:
            for key in keys:
                remove_image(key)
            raise
        trip = self.get_queryset().get(pk=trip.pk)
        return Response(self.get_serializer(trip).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "DELETE"])
@transaction.atomic
def trip_photo(request, photo_id):
    row = TripPhoto.objects.select_related("trip__family", "uploaded_by").filter(
        id=photo_id,
        trip__family__memberships__user=request.user,
        trip__family__status="active",
    ).first()
    if not row:
        raise Http404()
    if request.method == "DELETE":
        if row.uploaded_by_id != request.user.id and not _can_manage(request.user, row.trip.family_id):
            raise PermissionDenied("Nur Uploader oder Erwachsene dürfen das Foto löschen.")
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    path = image_path(row.key)
    if not path.exists():
        raise Http404()
    try:
        response = FileResponse(path.open("rb"), content_type="image/webp")
    except FileNotFoundError:
        raise Http404()
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
