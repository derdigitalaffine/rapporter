from .models import FamilyEvent
from .views import FamilyEventViewSet as BaseFamilyEventViewSet


class FamilyEventViewSet(BaseFamilyEventViewSet):
    """Calendar contract: forecasts/current conditions are weather data, not appointments."""
    queryset=FamilyEvent.objects.exclude(type__in=["weather.current","weather.forecast"]).all().order_by("starts_at")
