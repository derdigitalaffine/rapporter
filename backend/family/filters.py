from .models import Family


class ActiveTenantFilterBackend:
    """Apply tenant lifecycle status to every DRF queryset automatically."""

    def filter_queryset(self, request, queryset, view):
        model = queryset.model
        if model is Family:
            return queryset.filter(status=Family.Status.ACTIVE)
        field_names = {field.name for field in model._meta.get_fields()}
        if "family" in field_names:
            return queryset.filter(family__status=Family.Status.ACTIVE)
        if "shopping_list" in field_names:
            return queryset.filter(shopping_list__family__status=Family.Status.ACTIVE)
        if "routine" in field_names:
            return queryset.filter(routine__family__status=Family.Status.ACTIVE)
        if "rule" in field_names:
            return queryset.filter(rule__family__status=Family.Status.ACTIVE)
        return queryset
