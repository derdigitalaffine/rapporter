import plistlib
import uuid
from urllib.parse import urlsplit
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.response import Response
from auth_abuse.service import enforce
from auth_sessions.service import require_fresh_session
from telemetry.service import record_audit_event
from .models import Family, Membership
from .calendar_subscription_models import CalendarSubscription
from .calendar_subscription_service import MANAGER_ROLES, origin, metadata, reveal, rotate_credentials


def private(response):
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


def manage(request, family_id):
    family = get_object_or_404(Family, pk=family_id, status=Family.Status.ACTIVE)
    if not Membership.objects.filter(family=family, user=request.user, role__in=MANAGER_ROLES).exists():
        raise PermissionDenied()
    return family


def sensitive(request):
    require_fresh_session(request)
    decision = enforce('calendar.subscription.manage', request=request, user=request.user)
    if not decision.allowed:
        raise Throttled(wait=decision.retry_after)


def audit(request, grant, action):
    record_audit_event(f'calendar.subscription.{action}', actor=request.user, actor_class='user',
                       family=grant.family, target_type='export', target_id=str(grant.pk))


def member_label(member):
    return (member.display_name or member.user.get_full_name() or member.user.get_username()).strip()


class SubscriptionInput(serializers.Serializer):
    name = serializers.CharField(max_length=80, trim_whitespace=True)
    detail_level = serializers.ChoiceField(choices=CalendarSubscription.DetailLevel.choices, default=CalendarSubscription.DetailLevel.TITLE)


class SubscriptionUpdateInput(serializers.Serializer):
    detail_level = serializers.ChoiceField(choices=CalendarSubscription.DetailLevel.choices)


@api_view(['GET', 'POST'])
def subscriptions(request, family_id):
    family = manage(request, family_id)
    if request.method == 'GET':
        rows = CalendarSubscription.objects.filter(family=family, created_by=request.user, revoked_at__isnull=True)
        configured = True
        try:
            origin()
        except serializers.ValidationError:
            configured = False
        return private(Response({'subscriptions': [metadata(row) for row in rows], 'configured': configured}))
    sensitive(request)
    data = SubscriptionInput(data=request.data); data.is_valid(raise_exception=True)
    with transaction.atomic():
        Family.objects.select_for_update().get(pk=family.pk)
        if CalendarSubscription.objects.filter(family=family, created_by=request.user, revoked_at__isnull=True).count() >= 10:
            raise serializers.ValidationError({'code': 'subscription_limit'})
        grant = CalendarSubscription(family=family, created_by=request.user, name=data.validated_data['name'], detail_level=data.validated_data['detail_level'])
        rotate_credentials(grant)
        audit(request, grant, 'created')
    return private(Response(reveal(grant), status=201))


@api_view(['POST', 'DELETE', 'GET', 'PATCH'])
def subscription_detail(request, family_id, subscription_id, operation=''):
    family = manage(request, family_id)
    with transaction.atomic():
        grant = get_object_or_404(CalendarSubscription.objects.select_for_update(), pk=subscription_id,
                                 family=family, created_by=request.user, revoked_at__isnull=True)
        if request.method == 'DELETE' and not operation:
            grant.revoked_at = timezone.now(); grant.credentials_encrypted = ''
            grant.save(update_fields=['revoked_at', 'credentials_encrypted', 'updated_at'])
            audit(request, grant, 'revoked')
            return private(Response(status=204))
        if request.method == 'PATCH' and not operation:
            sensitive(request)
            data = SubscriptionUpdateInput(data=request.data); data.is_valid(raise_exception=True)
            grant.detail_level = data.validated_data['detail_level']
            grant.save(update_fields=['detail_level', 'updated_at'])
            audit(request, grant, 'updated')
            return private(Response(metadata(grant)))
        if operation not in ('reveal', 'rotate', 'profile') or (operation == 'profile') != (request.method == 'GET'):
            return private(Response(status=405))
        sensitive(request)
        if operation == 'rotate':
            rotate_credentials(grant); audit(request, grant, 'rotated')
        elif operation == 'reveal':
            audit(request, grant, 'revealed')
        if operation != 'profile':
            return private(Response(reveal(grant)))

        credentials = reveal(grant)
        parsed = urlsplit(origin())
        account = {
            'PayloadType': 'com.apple.caldav.account',
            'PayloadVersion': 1,
            'PayloadIdentifier': f'org.familyos.calendar.{grant.pk}.caldav',
            'PayloadUUID': str(uuid.uuid5(grant.pk, 'caldav')).upper(),
            'PayloadDisplayName': f'FamilyOS · {family.name}',
            'CalDAVAccountDescription': f'FamilyOS · {family.name}',
            'CalDAVHostName': parsed.hostname,
            'CalDAVPort': parsed.port or 443,
            'CalDAVUseSSL': True,
            'CalDAVUsername': credentials['username'],
            'CalDAVPassword': credentials['password'],
        }
        profile = {
            'PayloadType': 'Configuration', 'PayloadVersion': 1,
            'PayloadIdentifier': f'org.familyos.calendar.{grant.pk}', 'PayloadUUID': str(grant.pk).upper(),
            'PayloadDisplayName': f'FamilyOS · {family.name}', 'PayloadOrganization': 'FamilyOS',
            'PayloadDescription': 'FamilyOS CalDAV calendar. Changes made in Apple Calendar are synchronized back to FamilyOS.',
            'PayloadRemovalDisallowed': False, 'PayloadContent': [account],
        }
        audit(request, grant, 'profile')
        response = HttpResponse(plistlib.dumps(profile), content_type='application/x-apple-aspen-config')
        response['Content-Disposition'] = 'attachment; filename="familyos-calendar.mobileconfig"'
        return private(response)
