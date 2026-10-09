"""Private, versioned Today layouts. Layouts contain presentation settings only."""
from copy import deepcopy
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Family, Membership, TodayLayout

WIDGET_IDS = ('weather', 'priority', 'waste', 'next', 'tasks', 'shopping', 'routines', 'birthdays', 'notes')
DEFAULT_WIDGETS = [{'id': key, 'visible': True, 'size': 'full'} for key in WIDGET_IDS]


def payload(layout=None):
    return {'version': 1, 'revision': layout.revision if layout else 0,
            'widgets': deepcopy(layout.widgets if layout else DEFAULT_WIDGETS)}


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def today_layout(request):
    family_id = request.query_params.get('family')
    try:
        family = Family.objects.filter(id=family_id, memberships__user=request.user).first() if family_id else None
    except (ValidationError, ValueError, TypeError):
        family = None
    if not family:
        return Response({'detail': 'Family not found.'}, status=404)
    if request.method == 'GET':
        return Response(payload(TodayLayout.objects.filter(family=family, user=request.user).first()))
    data = request.data
    if not isinstance(data, dict) or set(data) != {'version', 'revision', 'widgets'}:
        return Response({'detail': 'Expected version, revision and widgets.'}, status=400)
    if type(data['version']) is not int or data['version'] != 1 or type(data['revision']) is not int or data['revision'] < 0:
        return Response({'detail': 'Invalid layout version or revision.'}, status=400)
    widgets = data['widgets']
    if not isinstance(widgets, list) or len(widgets) != len(WIDGET_IDS):
        return Response({'detail': 'Supply each supported widget exactly once.'}, status=400)
    seen = set()
    for widget in widgets:
        if (not isinstance(widget, dict) or set(widget) != {'id', 'visible', 'size'} or
                not isinstance(widget['id'], str) or widget['id'] not in WIDGET_IDS or widget['id'] in seen or
                type(widget['visible']) is not bool or widget['size'] not in ('full', 'compact')):
            return Response({'detail': 'Invalid widget configuration.'}, status=400)
        seen.add(widget['id'])
    with transaction.atomic():
        # Lock membership: serializes first-save as well as updates without locking all family layouts.
        Membership.objects.select_for_update().get(family=family, user=request.user)
        layout = TodayLayout.objects.filter(family=family, user=request.user).first()
        if data['revision'] != (layout.revision if layout else 0):
            return Response({'detail': 'Layout changed on another device.', 'current': payload(layout)}, status=409)
        if not layout:
            layout = TodayLayout(family=family, user=request.user)
        layout.widgets = widgets
        layout.revision += 1
        layout.save()
    return Response(payload(layout))
