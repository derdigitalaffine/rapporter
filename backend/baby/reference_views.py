from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .reference_models import PediatricReferencePackage
from .reference_service import (
    DEFAULT_SOURCE_KEY,
    create_reference_draft,
    publish_reference_package,
    published_reference_package,
    reactivate_reference_package,
    reference_package_by_id,
    require_superadmin,
    serialize_reference_package,
    supersede_reference_package,
    update_reference_draft,
    validate_reference_package,
)


class ReferenceDraftInput(serializers.Serializer):
    source_key = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", max_length=64)
    source_title = serializers.CharField(max_length=200)
    source_version = serializers.CharField(max_length=96)
    locale = serializers.CharField(max_length=16, default="de-DE")
    effective_from = serializers.DateField(required=False, allow_null=True)
    effective_to = serializers.DateField(required=False, allow_null=True)
    payload = serializers.JSONField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=240)
    notes = serializers.CharField(required=False, allow_blank=True)


class ReferenceDraftPatch(serializers.Serializer):
    source_title = serializers.CharField(required=False, max_length=200)
    source_version = serializers.CharField(required=False, max_length=96)
    locale = serializers.CharField(required=False, max_length=16)
    effective_from = serializers.DateField(required=False, allow_null=True)
    effective_to = serializers.DateField(required=False, allow_null=True)
    payload = serializers.JSONField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=240)
    notes = serializers.CharField(required=False, allow_blank=True)


@api_view(["GET", "POST"])
def reference_packages(request):
    require_superadmin(request.user)
    if request.method == "POST":
        serializer = ReferenceDraftInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = create_reference_draft(request.user, **serializer.validated_data)
        return Response(serialize_reference_package(package), status=201)
    rows = PediatricReferencePackage.objects.select_related("created_by", "published_by").all()[:200]
    return Response({"packages": [serialize_reference_package(row, include_payload=False) for row in rows]})


@api_view(["GET"])
def current_reference_package(request):
    source_key = request.query_params.get("source_key") or DEFAULT_SOURCE_KEY
    locale = request.query_params.get("locale") or "de-DE"
    on_date = None
    if request.query_params.get("on"):
        on_date = serializers.DateField().run_validation(request.query_params["on"])
    package = published_reference_package(source_key=source_key, locale=locale, on_date=on_date)
    if not package:
        raise NotFound("No published pediatric reference package is effective for this date.")
    return Response(serialize_reference_package(package))


@api_view(["GET", "PATCH"])
def reference_package_detail(request, package_id):
    package = reference_package_by_id(package_id)
    if request.method == "GET":
        return Response(serialize_reference_package(package))
    require_superadmin(request.user)
    serializer = ReferenceDraftPatch(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    package = update_reference_draft(package, request.user, **serializer.validated_data)
    return Response(serialize_reference_package(package))


@api_view(["POST"])
def validate_reference(request, package_id):
    require_superadmin(request.user)
    package = reference_package_by_id(package_id)
    return Response(validate_reference_package(package))


@api_view(["POST"])
def publish_reference(request, package_id):
    try:
        package = publish_reference_package(request.user, package_id)
    except DjangoValidationError as exc:
        raise ValidationError({"effective_from": exc.messages}) from exc
    return Response(serialize_reference_package(package))


@api_view(["POST"])
def supersede_reference(request, package_id):
    package = supersede_reference_package(request.user, package_id)
    return Response(serialize_reference_package(package))


@api_view(["POST"])
def reactivate_reference(request, package_id):
    package = reactivate_reference_package(request.user, package_id)
    return Response(serialize_reference_package(package))
