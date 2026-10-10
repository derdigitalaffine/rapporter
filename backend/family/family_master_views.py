import uuid
from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .family_master_models import FamilyMasterData
from .models import Family, Membership
from .private_images import image_path, optimize_image, remove_image, store_image


class FamilyMasterUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False, allow_blank=False, trim_whitespace=True)
    address_street = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    address_house_number = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    address_postal_code = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    address_city = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    address_region = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    address_country_code = serializers.CharField(max_length=2, required=False, allow_blank=True, trim_whitespace=True)

    def validate_address_country_code(self, value):
        value = value.upper()
        if value and (len(value) != 2 or not value.isalpha() or not value.isascii()):
            raise serializers.ValidationError("Ländercode muss aus zwei Buchstaben bestehen.")
        return value


def _membership(user, family_id, *, hide=False):
    row = Membership.objects.filter(
        user=user,
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
    ).select_related("family").first()
    if row:
        return row
    if hide:
        raise Http404()
    raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")


def _family_id(request):
    family_id = request.query_params.get("family") or request.data.get("family")
    if not family_id:
        raise serializers.ValidationError({"family": "Familie fehlt."})
    return family_id


def _master(family):
    return FamilyMasterData.objects.filter(family=family).first()


def _blank_location_context():
    address = {"street": "", "house_number": "", "postal_code": "", "city": "", "region": "", "country_code": ""}
    return {"source": "family_address", "address": address, "has_address": False, "ready_for_geocoding": False, "coordinates": None}


def _payload(family, membership, master=None):
    master = master or _master(family)
    address = master.address_payload() if master else _blank_location_context()["address"]
    image_url = f"/api/family-settings/image/{family.id}/?v={master.image_version}" if master and master.image_key else ""
    return {
        "family": str(family.id),
        "name": family.name,
        "slug": family.slug,
        "can_edit": membership.role == Membership.Role.OWNER,
        "image_url": image_url,
        "address_street": address["street"],
        "address_house_number": address["house_number"],
        "address_postal_code": address["postal_code"],
        "address_city": address["city"],
        "address_region": address["region"],
        "address_country_code": address["country_code"],
        "location_context": master.location_context() if master else _blank_location_context(),
    }


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def family_master_detail(request):
    membership = _membership(request.user, _family_id(request))
    family = membership.family
    master = _master(family)
    if request.method == "GET":
        return Response(_payload(family, membership, master))
    if membership.role != Membership.Role.OWNER:
        raise PermissionDenied("Nur Owner dürfen Familienstammdaten ändern.")
    update = FamilyMasterUpdateSerializer(data=request.data, partial=True)
    update.is_valid(raise_exception=True)
    values = update.validated_data
    with transaction.atomic():
        family = Family.objects.select_for_update().get(pk=family.pk)
        master, _ = FamilyMasterData.objects.select_for_update().get_or_create(family=family)
        if "name" in values:
            family.name = values["name"]
            family.save(update_fields=["name", "updated_at"])
        for field in (
            "address_street",
            "address_house_number",
            "address_postal_code",
            "address_city",
            "address_region",
            "address_country_code",
        ):
            if field in values:
                setattr(master, field, values[field])
        master.save()
    membership.family = family
    return Response(_payload(family, membership, master))


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def family_master_image(request):
    membership = _membership(request.user, _family_id(request))
    if membership.role != Membership.Role.OWNER:
        raise PermissionDenied("Nur Owner dürfen das Familienbild ändern.")
    family = membership.family
    master, _ = FamilyMasterData.objects.get_or_create(family=family)
    if request.method == "DELETE":
        old_key = master.image_key
        master.image_key = ""
        master.image_version = uuid.uuid4()
        master.save(update_fields=["image_key", "image_version", "updated_at"])
        if old_key:
            remove_image(old_key)
        return Response(_payload(family, membership, master))
    upload = request.FILES.get("image")
    if not upload:
        return Response({"detail": "Familienbild fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    data, _, _ = optimize_image(upload, max_dimension=1600)
    try:
        new_key = store_image(data)
    except OSError:
        return Response({"detail": "Familienbild konnte nicht gespeichert werden."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    old_key = master.image_key
    try:
        with transaction.atomic():
            master = FamilyMasterData.objects.select_for_update().get(pk=master.pk)
            old_key = master.image_key
            master.image_key = new_key
            master.image_version = uuid.uuid4()
            master.save(update_fields=["image_key", "image_version", "updated_at"])
    except Exception:
        remove_image(new_key)
        raise
    if old_key:
        remove_image(old_key)
    return Response(_payload(family, membership, master))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def family_master_image_file(request, family_id):
    membership = _membership(request.user, family_id, hide=True)
    master = _master(membership.family)
    if not master or not master.image_key:
        raise Http404()
    try:
        path = image_path(master.image_key)
    except ValueError:
        raise Http404()
    if not path.is_file():
        raise Http404()
    response = FileResponse(path.open("rb"), content_type="image/webp")
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    response["ETag"] = f'"{master.image_version}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
