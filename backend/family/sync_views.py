from uuid import UUID

from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Family, Membership
from .sync_service import synchronize


@api_view(['POST'])
def sync(request):
    data = request.data
    if data.get('protocol_version') != 1 or type(data.get('protocol_version')) is not int:
        return Response({'code': 'unsupported_protocol', 'supported_versions': [1]}, status=409, headers={'Cache-Control': 'no-store'})
    try:
        family_id = UUID(str(data.get('family_id')))
    except (ValueError, TypeError):
        raise ValidationError({'family_id': 'Expected a family UUID.'})
    membership = Membership.objects.select_related('family').filter(user=request.user, family_id=family_id, family__status=Family.Status.ACTIVE).first()
    if not membership:
        raise PermissionDenied()
    cursor = data.get('cursor')
    mutations = data.get('mutations', [])
    if cursor is not None and (type(cursor) is not int or cursor < 0):
        raise ValidationError({'cursor': 'Expected a nonnegative integer or null.'})
    if not isinstance(mutations, list) or len(mutations) > 100:
        raise ValidationError({'mutations': 'At most 100 mutations per request.'})
    response = Response(synchronize(request, membership.family, cursor, mutations))
    response['Cache-Control'] = 'no-store'
    return response
