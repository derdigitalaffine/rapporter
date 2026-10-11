from urllib.parse import parse_qs, urlsplit

from django.http import Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from family.models import Membership

from .models import Notification
from .serializers import notification_payload
from .services import mark_all_read, set_read, unread_count


class NotificationCursorPagination(CursorPagination):
    page_size = 25
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = ("-created_at", "-id")


def _membership_or_404(user, family_id):
    if not family_id:
        raise Http404
    membership = Membership.objects.filter(user=user, family_id=family_id).select_related("family", "user").first()
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
    membership = _membership_or_404(request.user, request.query_params.get("family"))
    queryset = Notification.objects.filter(recipient=membership).select_related("recipient", "recipient__user")
    paginator = NotificationCursorPagination()
    page = paginator.paginate_queryset(queryset, request)
    return Response({
        "results": [notification_payload(row) for row in page],
        "unread_count": unread_count(request.user, family=membership.family),
        "next_cursor": _cursor_from_link(paginator.get_next_link()),
        "previous_cursor": _cursor_from_link(paginator.get_previous_link()),
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_detail(request, notification_id):
    notification = Notification.objects.select_related("recipient", "recipient__user").filter(
        id=notification_id,
        recipient__user=request.user,
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
    membership = _membership_or_404(request.user, request.data.get("family"))
    updated, _ = mark_all_read(membership=membership)
    return Response({"updated": updated, "unread_count": 0})
