"""Subscription grants are credentials, never account sessions or calendar copies."""
import hashlib
import secrets
from urllib.parse import urlsplit
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .caldav_secrets import encrypt_credentials, decrypt_credentials
from .models import Family, Membership
from .calendar_subscription_models import CalendarSubscription

MANAGER_ROLES = (Membership.Role.OWNER, Membership.Role.ADULT)


def origin():
    value = settings.APP_URL.rstrip('/')
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment and parsed.port != 0)
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError({'code': 'calendar_subscription_https_required'})
    return value


def digest(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def rotate_credentials(grant):
    token = secrets.token_urlsafe(32)
    grant.token_digest = digest(token)
    grant.credentials_encrypted = encrypt_credentials(server_url=origin(), username=str(grant.pk), password=token)
    grant.save()
    return token


def authorized(grant):
    return (grant is not None and grant.revoked_at is None and grant.created_by.is_active
            and grant.family.status == Family.Status.ACTIVE and Membership.objects.filter(
                family_id=grant.family_id, user_id=grant.created_by_id, role__in=MANAGER_ROLES).exists())


def resolve_token(token, username=None):
    if len(token) != 43 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in token):
        return None
    grant = CalendarSubscription.objects.select_related('family', 'created_by').filter(token_digest=digest(token)).first()
    if not authorized(grant) or (username is not None and username != str(grant.pk)):
        return None
    now = timezone.now()
    if grant.last_used_at is None or (now - grant.last_used_at).total_seconds() >= 300:
        CalendarSubscription.objects.filter(pk=grant.pk).update(last_used_at=now)
    return grant


def metadata(grant):
    included = grant.included_member_ids if isinstance(grant.included_member_ids, list) else []
    return {'id': str(grant.pk), 'family': str(grant.family_id), 'name': grant.name,
            'detail_level': grant.detail_level, 'included_member_ids': [str(value) for value in included],
            'created_at': grant.created_at, 'revoked_at': grant.revoked_at, 'last_used_at': grant.last_used_at}


def reveal(grant):
    token = decrypt_credentials(grant.credentials_encrypted)['password']
    base = origin()
    feed = f'{base}/calendar-feed/{token}/family.ics'
    return {**metadata(grant), 'subscription_url': feed, 'webcal_url': 'webcal://' + feed.split('://', 1)[1],
            'caldav_url': f'{base}/caldav/{grant.pk}/principal/', 'username': str(grant.pk), 'password': token}
