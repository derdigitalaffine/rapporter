from .shopping_reference_models import ReferenceDataset


_RUNTIME_REDISTRIBUTION = (
    ReferenceDataset.Redistribution.ADOPT,
    ReferenceDataset.Redistribution.ADAPT,
)


def reference_dataset_versions(*, dataset_id=None, dataset_type=None):
    """Return registered public package versions without assuming any exist."""
    queryset = ReferenceDataset.objects.all()
    if dataset_id:
        queryset = queryset.filter(dataset_id=dataset_id)
    if dataset_type:
        queryset = queryset.filter(dataset_type=dataset_type)
    return queryset


def active_reference_datasets(*, dataset_type=None):
    """Return runtime-safe active packages; an empty queryset is the core default."""
    queryset = ReferenceDataset.objects.filter(
        state=ReferenceDataset.State.ACTIVE,
        redistribution__in=_RUNTIME_REDISTRIBUTION,
    )
    if dataset_type:
        queryset = queryset.filter(dataset_type=dataset_type)
    return queryset
