from uuid import UUID

from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Family, Membership
from .pin_adapters import get_pin_adapter, legacy_kind_for_adapter_key


PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_OFFSET = 10_000
SEARCH_FIELDS = {
    'calendar_event': ('title',),
    'task': ('title',),
    'routine': ('name',),
    'note': ('title', 'body'),
    'shopping_item': ('name',),
    'shopping_list': ('name', 'store'),
    'trip': ('title', 'destination'),
    'document': ('title', 'correspondent'),
}


def _positive_int(value, *, default, maximum=None, field):
    if value in (None, ''):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: 'Muss eine positive Ganzzahl sein.'})
    if parsed < 1:
        raise ValidationError({field: 'Muss eine positive Ganzzahl sein.'})
    return min(parsed, maximum) if maximum else parsed


def _search(queryset, adapter_key, query):
    query = (query or '').strip()
    if not query:
        return queryset
    fields = SEARCH_FIELDS.get(adapter_key, ())
    predicate = Q()
    for field in fields:
        predicate |= Q(**{f'{field}__icontains': query})
    return queryset.filter(predicate) if fields else queryset.none()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pin_picker(request):
    family_id = request.query_params.get('family')
    requested_key = request.query_params.get('adapter_key') or request.query_params.get('kind')
    if not family_id:
        raise ValidationError({'family': 'Familie fehlt.'})
    try:
        family_id = UUID(family_id)
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({'family': 'Ungültige Familien-ID.'})
    if not requested_key:
        raise ValidationError({'kind': 'Pin-Typ fehlt.'})

    adapter = get_pin_adapter(requested_key)
    if adapter is None:
        raise ValidationError({'kind': 'Unbekannter Pin-Typ.'})

    membership = Membership.objects.filter(
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
        user=request.user,
    ).first()
    if membership is None:
        raise PermissionDenied('Kein Zugriff auf diese Familie.')
    if membership.role == Membership.Role.GUEST:
        raise PermissionDenied('Diese Rolle darf keine Pins erstellen.')

    page = _positive_int(request.query_params.get('page'), default=1, field='page')
    page_size = _positive_int(
        request.query_params.get('page_size'),
        default=PAGE_SIZE,
        maximum=MAX_PAGE_SIZE,
        field='page_size',
    )
    start = (page - 1) * page_size
    if start > MAX_OFFSET:
        raise ValidationError({'page': 'Auswahlgrenze erreicht. Bitte Suche eingrenzen.'})
    queryset = _search(adapter.pinnable_queryset(request.user, family_id), adapter.key, request.query_params.get('q'))
    queryset = queryset.order_by('-updated_at', '-id')

    # Admission and lifecycle filtering happen before pagination in the same
    # adapter selector used by can_pin. Only this page plus one sentinel is read.
    candidates = list(queryset[start : start + page_size + 1])
    selected = candidates[:page_size]
    has_next = len(candidates) > page_size

    return Response({
        'kind': legacy_kind_for_adapter_key(adapter.key),
        'adapter_key': adapter.key,
        'page': page,
        'page_size': page_size,
        'has_next': has_next,
        'results': [adapter.preview(row) for row in selected],
    })
