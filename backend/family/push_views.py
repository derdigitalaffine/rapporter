from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .badges import badge_count, clear_badge
from .models import PushSubscription
from .push import public_key, push_configured, send_to_subscription


@api_view(["GET"])
def push_config(request):
    configured = push_configured()
    return Response({
        "configured": configured,
        "public_key": public_key() if configured else "",
        "devices": PushSubscription.objects.filter(user=request.user, active=True).count(),
    })


@api_view(["GET", "POST"])
def push_badge(request):
    if request.method == "POST":
        clear_badge(request.user)
        return Response({"unread_count": 0})
    return Response({"unread_count": badge_count(request.user)})


@api_view(["POST"])
def push_subscribe(request):
    if not push_configured():
        return Response({"detail": "Web Push ist im Setup nicht konfiguriert."}, status=status.HTTP_400_BAD_REQUEST)
    endpoint = str(request.data.get("endpoint") or "").strip()
    keys = request.data.get("keys") or {}
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        return Response({"detail": "Ungültige Push-Subscription."}, status=status.HTTP_400_BAD_REQUEST)
    subscription, _ = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "active": True,
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:240],
        },
    )
    return Response({"subscribed": True, "id": str(subscription.id)})


@api_view(["POST"])
def push_unsubscribe(request):
    endpoint = str(request.data.get("endpoint") or "").strip()
    if endpoint:
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).update(active=False)
    else:
        PushSubscription.objects.filter(user=request.user).update(active=False)
    return Response({"subscribed": False})


@api_view(["POST"])
def push_test(request):
    subscription = PushSubscription.objects.filter(user=request.user, active=True).order_by("-updated_at").first()
    if not subscription:
        return Response({"detail": "Auf diesem Konto ist kein aktives Push-Gerät registriert."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        send_to_subscription(subscription, "FamilyOS", "Benachrichtigungen funktionieren 🎉", "/")
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"sent": True})
