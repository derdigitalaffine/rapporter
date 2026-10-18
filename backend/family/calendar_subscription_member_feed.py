from django.views.decorators.csrf import csrf_exempt

from .calendar_subscription_dav import ics_response, limited, response
from .calendar_subscription_ics import CalendarCapacityError, shared_events
from .calendar_subscription_service import resolve_token
from .models import Membership


@csrf_exempt
def member_feed(request, token, member_id):
    if request.method not in ('GET', 'HEAD'):
        return response(status=405)
    blocked = limited(request, token)
    if blocked:
        return blocked
    grant = resolve_token(token)
    if grant is None:
        return response(status=404)
    member = Membership.objects.select_related('user').filter(
        pk=member_id,
        family_id=grant.family_id,
        user__is_active=True,
    ).first()
    if member is None:
        return response(status=404)
    configured = {str(value) for value in grant.included_member_ids} if isinstance(grant.included_member_ids, list) else set()
    is_owner = member.user_id == grant.created_by_id
    is_selected_dependent = member.role in (Membership.Role.CHILD, Membership.Role.TEEN) and str(member.pk) in configured
    try:
        events = shared_events(grant, member) if (is_owner or is_selected_dependent) else []
        return ics_response(request, grant, events)
    except CalendarCapacityError:
        return response(status=507)
