import json
import os

from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import PushSubscription


def push_configured():
    return bool(os.getenv("VAPID_PUBLIC_KEY", "").strip() and os.getenv("VAPID_PRIVATE_KEY", "").strip())

def public_key():
    return os.getenv("VAPID_PUBLIC_KEY", "").strip()

def _subject():
    value = os.getenv("VAPID_SUBJECT", "").strip()
    if value:return value
    email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com").strip()
    return f"mailto:{email}"

def send_to_subscription(subscription, title, body="", url="/", *, tag="familyos", badge_count=None):
    if not push_configured():raise ValueError("Web Push ist im Setup noch nicht konfiguriert.")
    data={"title":title,"body":body,"url":url or "/","tag":tag}
    if badge_count is not None:data["badge_count"]=max(0,int(badge_count))
    payload=json.dumps(data,ensure_ascii=False)
    try:
        webpush(subscription_info={"endpoint":subscription.endpoint,"keys":{"p256dh":subscription.p256dh,"auth":subscription.auth}},data=payload,vapid_private_key=os.getenv("VAPID_PRIVATE_KEY"),vapid_claims={"sub":_subject()},ttl=3600,timeout=10)
    except WebPushException as exc:
        code=getattr(exc,"status_code",None)
        if code in {404,410}:
            subscription.active=False;subscription.save(update_fields=["active","updated_at"])
        raise
    subscription.last_success_at=timezone.now();subscription.save(update_fields=["last_success_at","updated_at"]);return True

def send_user_push(user,title,body="",url="/",*,tag="familyos",badge_count=None):
    subscriptions=PushSubscription.objects.filter(active=True,user=user);sent,errors=0,0
    for subscription in subscriptions:
        try:send_to_subscription(subscription,title,body,url,tag=tag,badge_count=badge_count);sent+=1
        except Exception:errors+=1
    return {"sent":sent,"errors":errors}

def send_family_push(family,title,body="",url="/",*,tag="familyos",badge_count=None):
    subscriptions=PushSubscription.objects.filter(active=True,user__family_memberships__family=family).distinct();sent,errors=0,0
    for subscription in subscriptions:
        try:send_to_subscription(subscription,title,body,url,tag=tag,badge_count=badge_count);sent+=1
        except Exception:errors+=1
    return {"sent":sent,"errors":errors}
