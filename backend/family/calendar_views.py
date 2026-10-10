from .models import FamilyEvent
from .views import FamilyEventViewSet as BaseFamilyEventViewSet
from datetime import date, timedelta
from rest_framework.exceptions import ValidationError, PermissionDenied
from .birthdays import calendar_projection, local_now
from .models import Family


READ_ONLY_EVENT_TYPES = {"school.holiday", "travel.trip"}


class FamilyEventViewSet(BaseFamilyEventViewSet):
    """Calendar contract: forecasts/current conditions are weather data, not appointments."""
    queryset=FamilyEvent.objects.exclude(type__in=["weather.current","weather.forecast"]).all().order_by("starts_at")

    def list(self, request, *args, **kwargs):
        response = super().list(request,*args,**kwargs)
        if request.query_params.get("birthdays")=="0":
            return response
        families=Family.objects.filter(memberships__user=request.user,status="active").distinct()
        if request.query_params.get("family"):
            families=families.filter(pk=request.query_params["family"])
        virtual=[]
        # Occurrences are included once, on the first page. They are projections,
        # not persisted duplicate FamilyEvent records.
        if request.query_params.get("page","1")=="1":
            for family in families:
                try:
                    start=date.fromisoformat(request.query_params["start"]) if request.query_params.get("start") else local_now(family).date()
                    end=date.fromisoformat(request.query_params["end"]) if request.query_params.get("end") else start+timedelta(days=366)
                    if end<start or (end-start).days>732:raise ValueError()
                except ValueError:
                    raise ValidationError("Use a calendar range of at most two years.")
                virtual.extend(calendar_projection(family,request.user,start,end))
        if isinstance(response.data,dict):
            response.data["results"].extend(virtual)
            response.data["results"].sort(key=lambda row:row.get("starts_at") or "9999")
            response.data["count"]+=len(virtual)
        else:
            response.data.extend(virtual)
        return response

    def perform_create(self, serializer):
        if serializer.validated_data.get("type") in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin wird von seinem Fachbereich verwaltet.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if serializer.instance.type in READ_ONLY_EVENT_TYPES or serializer.validated_data.get("type") in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin ist hier schreibgeschützt.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.type in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin muss in seinem Fachbereich gelöscht werden.")
        super().perform_destroy(instance)
