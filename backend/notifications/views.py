from urllib.parse import parse_qs, urlsplit

from django.http import Http404
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from family.models import Family, Membership

from .models import Notification
from .serializers import notification_payload
from .services import mark_all_read, set_read, unread_count, sync_launcher_badge


class NotificationCursorPagination(CursorPagination):
    page_size = 25
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = ("-created_at", "-id")


def _membership_or_404(user, family_id):
    if not family_id:
        raise Http404
    membership = Membership.objects.filter(user=user, family_id=family_id, family__status=Family.Status.ACTIVE).select_related("family", "user").first()
    if not membership:
        raise Http404
    return membership


def _cursor_from_link(link):
    if not link:
        return None
    return parse_qs(urlsplit(link).query).get("cursor", [None])[0]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_collection(request):
    family_id = request.query_params.get("family")
    membership = _membership_or_404(request.user, family_id) if family_id else None
    scope = Q(recipient_user=request.user)
    if membership:
        scope |= Q(recipient=membership)
    queryset = Notification.objects.filter(scope).select_related("recipient", "recipient__user", "recipient_user")
    paginator = NotificationCursorPagination()
    page = paginator.paginate_queryset(queryset, request)
    return Response({
        "results": [notification_payload(row) for row in page],
        "unread_count": queryset.filter(read_at__isnull=True).count(),
        "next_cursor": _cursor_from_link(paginator.get_next_link()),
        "previous_cursor": _cursor_from_link(paginator.get_previous_link()),
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_detail(request, notification_id):
    notification = Notification.objects.select_related("recipient", "recipient__user", "recipient_user").filter(
        Q(recipient_user=request.user) | Q(recipient__user=request.user, family__status=Family.Status.ACTIVE),
        id=notification_id,
    ).first()
    if not notification:
        raise Http404
    if "read" not in request.data or not isinstance(request.data.get("read"), bool):
        return Response({"detail": "read muss true oder false sein."}, status=400)
    set_read(notification, read=request.data["read"])
    return Response(notification_payload(notification))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_read_all(request):
    family_id = request.data.get("family")
    membership = _membership_or_404(request.user, family_id) if family_id else None
    scope = Q(recipient_user=request.user)
    if membership:
        scope |= Q(recipient=membership)
    updated = Notification.objects.filter(scope, read_at__isnull=True).update(read_at=timezone.now())
    sync_launcher_badge(request.user)
    return Response({"updated": updated, "unread_count": 0})
