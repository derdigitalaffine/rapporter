from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import FamilyEvent, Membership
from .private_images import image_path, optimize_image, remove_image, store_image
from .travel_models import Trip, TripPhoto


def _can_manage(user, family_id):
    return Membership.objects.filter(
        family_id=family_id,
        user=user,
        role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
    ).exists()


def _can_add_photos(user, family_id):
    return Membership.objects.filter(family_id=family_id, user=user).exclude(role=Membership.Role.GUEST).exists()


def _event_bounds(trip):
    try:
        zone = ZoneInfo(trip.family.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    start = datetime.combine(trip.starts_on, time.min, tzinfo=zone)
    end = datetime.combine(trip.ends_on + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def sync_trip_event(trip):
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

    class Meta:
        model = Trip
        fields = [
            "id",
            "family",
            "title",
            "destination",
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
        ]
        read_only_fields = ["created_by", "created_at", "updated_at", "calendar_event_id"]

    def validate(self, attrs):
        starts_on = attrs.get("starts_on", getattr(self.instance, "starts_on", None))
        ends_on = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError({"ends_on": "Das Enddatum darf nicht vor dem Startdatum liegen."})
        if self.instance and "family" in attrs and attrs["family"].id != self.instance.family_id:
            raise serializers.ValidationError({"family": "Die Familie einer Reise kann nicht geändert werden."})
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
    queryset = Trip.objects.select_related("family", "created_by", "calendar_event").prefetch_related("photos").all()
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
        trip = serializer.save(created_by=self.request.user)
        sync_trip_event(trip)

    @transaction.atomic
    def perform_update(self, serializer):
        trip = Trip.objects.select_for_update().select_related("family").get(pk=serializer.instance.pk)
        if not _can_manage(self.request.user, trip.family_id):
            raise PermissionDenied("Nur Erwachsene dürfen Reisen ändern.")
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
