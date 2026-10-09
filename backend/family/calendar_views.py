from .models import FamilyEvent
from .views import FamilyEventViewSet as BaseFamilyEventViewSet
from rest_framework.exceptions import PermissionDenied


class FamilyEventViewSet(BaseFamilyEventViewSet):
    """Calendar contract: forecasts/current conditions are weather data, not appointments."""
    queryset=FamilyEvent.objects.exclude(type__in=["weather.current","weather.forecast"]).all().order_by("starts_at")

    def perform_create(self, serializer):
        if serializer.validated_data.get("type") == "school.holiday":
            raise PermissionDenied("Amtliche Ferien können nur über die Integration hinzugefügt werden.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if serializer.instance.type == "school.holiday" or serializer.validated_data.get("type") == "school.holiday":
            raise PermissionDenied("Amtliche Ferien sind schreibgeschützt.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.type == "school.holiday":
            raise PermissionDenied("Amtliche Ferien sind schreibgeschützt. Trenne die Integration, um sie zu entfernen.")
        super().perform_destroy(instance)
