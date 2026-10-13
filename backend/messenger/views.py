import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from auth_abuse.service import enforce
from auth_identity.models import EmailIdentity
from auth_identity.service import EmailConflictError
from family.auth_views import set_user_cookies
from . import services
from .access import blocked_ids, eligible, friendship_access, friendship_for, membership, preferences, profile_payload, require_writer, visible_messages
from .invitations import accept_invitation, create_invitation, register_from_invitation, resolve_invitation
from .models import ChatAttachment, ChatBlock, ContactInvitation, ConversationMember, Friendship
from .serializers import conversation_payload, message_payload


def rate(request, scope, identifier=None):
    decision = enforce(scope, request=request, user=request.user if request.user.is_authenticated else None, identifier=identifier)
    if not decision.allowed:
        raise Throttled(wait=decision.retry_after)


def validated(data, **fields):
    class Input(serializers.Serializer):
        pass
    schema = Input(data=data)
    schema.fields.update(fields)
    schema.is_valid(raise_exception=True)
    return schema.validated_data


def invite_payload(invite):
    return {"id": str(invite.pk), "email": invite.email, "status": invite.status if invite.expires_at > timezone.now() else "expired", "expires_at": invite.expires_at.isoformat()}


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def account(request):
    pref = preferences(request.user)
    if request.method == "PATCH":
        require_writer(request.user)
        data = validated(request.data, display_name=serializers.CharField(max_length=80, required=False), locale=serializers.ChoiceField(choices=["de", "en"], required=False), push_enabled=serializers.BooleanField(required=False), read_receipts=serializers.BooleanField(required=False))
        for key, value in data.items():
            setattr(pref, key, value)
        pref.save()
        if "display_name" in data:
            ConversationMember.objects.filter(user=request.user, state="active").update(label=pref.display_name)
    return Response({"user_id": request.user.pk, "display_name": pref.display_name, "locale": pref.locale, "push_enabled": pref.push_enabled, "read_receipts": pref.read_receipts, "can_chat": eligible(request.user)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def contacts(request):
    require_writer(request.user)
    friends = Friendship.objects.filter(active=True).filter(Q(low_user=request.user) | Q(high_user=request.user)).select_related("low_user", "high_user").exclude(low_user_id__in=blocked_ids(request.user)).exclude(high_user_id__in=blocked_ids(request.user))
    email = EmailIdentity.objects.filter(user=request.user, kind="primary", verified_at__isnull=False).values_list("email_normalized", flat=True).first()
    incoming = ContactInvitation.objects.filter(email=email, status="pending", expires_at__gt=timezone.now()).select_related("sender").exclude(sender_id__in=blocked_ids(request.user))[:50]
    return Response({"friends": [{"id": str(f.pk), "user": profile_payload(f.high_user if f.low_user_id == request.user.pk else f.low_user)} for f in friends[:100] if f.low_user.is_active and f.high_user.is_active], "incoming": [{"id": str(i.pk), "sender": profile_payload(i.sender), "expires_at": i.expires_at.isoformat()} for i in incoming if eligible(i.sender)], "outgoing": [invite_payload(i) for i in ContactInvitation.objects.filter(sender=request.user).order_by("-created_at")[:50]], "blocked": [{"user_id": b.blocked_id} for b in ChatBlock.objects.filter(blocker=request.user)[:100]]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invitations(request):
    require_writer(request.user)
    data = validated(request.data, email=serializers.EmailField(max_length=254), request_id=serializers.UUIDField())
    rate(request, "chat.invite")
    invite = create_invitation(request.user, **data)
    # Account existence / blocking is deliberately absent from the response.
    return Response(invite_payload(invite), status=202)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invitation_action(request, invitation_id):
    data = validated(request.data, action=serializers.ChoiceField(choices=["accept", "decline", "revoke"]))
    rate(request, "chat.write")
    with transaction.atomic():
        invite = ContactInvitation.objects.select_for_update().select_related("sender").filter(pk=invitation_id, expires_at__gt=timezone.now(), status__in=["pending", "accepted"]).first()
        if not invite:
            raise Http404
        if data["action"] == "revoke":
            if invite.sender_id != request.user.pk or invite.status != "pending":
                raise Http404
            invite.status = "revoked"
        else:
            email = EmailIdentity.objects.filter(user=request.user, kind="primary", verified_at__isnull=False).values_list("email_normalized", flat=True).first()
            if email != invite.email or not eligible(invite.sender):
                raise Http404
            if data["action"] == "accept":
                friend = accept_invitation(invite, request.user)
                return Response({"friendship_id": str(friend.pk)})
            if invite.status != "pending":
                raise Http404
            invite.status = "declined"
        invite.save(update_fields=["status", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def invitation_preview(request):
    data = validated(request.data, token=serializers.CharField(max_length=1000))
    rate(request, "chat.consume", identifier=data["token"])
    invite = resolve_invitation(data["token"])
    return Response({"sender_name": preferences(invite.sender).display_name, "status": invite.status, "expires_at": invite.expires_at.isoformat()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invitation_accept(request):
    data = validated(request.data, token=serializers.CharField(max_length=1000))
    rate(request, "chat.consume", identifier=data["token"])
    with transaction.atomic():
        friend = accept_invitation(resolve_invitation(data["token"], lock=True), request.user)
    return Response({"friendship_id": str(friend.pk)})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def invitation_register(request):
    data = validated(request.data, token=serializers.CharField(max_length=1000), password=serializers.CharField(min_length=8, max_length=128, trim_whitespace=False), display_name=serializers.CharField(max_length=80))
    rate(request, "chat.consume", identifier=data["token"])
    try:
        user, friend = register_from_invitation(**data)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from None
    except (IntegrityError, EmailConflictError):
        raise ValidationError({"code": "invite_login_required"}) from None
    return set_user_cookies(Response({"user_id": user.pk, "friendship_id": str(friend.pk)}, status=201), user, request)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def contact_action(request, friendship_id):
    data = validated(request.data, action=serializers.ChoiceField(choices=["remove", "block"]))
    rate(request, "chat.write")
    services.change_friendship(request.user, friendship_id, block=data["action"] == "block")
    return Response({"ok": True})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def unblock(request, user_id):
    require_writer(request.user)
    rate(request, "chat.write")
    ChatBlock.objects.filter(blocker=request.user, blocked_id=user_id).delete()
    # Removing a block never restores friendship automatically.
    return Response({"ok": True})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def conversations(request):
    require_writer(request.user)
    if request.method == "POST":
        rate(request, "chat.write")
        data = validated(request.data, kind=serializers.ChoiceField(choices=["direct", "group"]), friendship_id=serializers.UUIDField(required=False), title=serializers.CharField(max_length=100, required=False), friends=serializers.ListField(child=serializers.UUIDField(), max_length=19, required=False))
        if data["kind"] == "direct":
            if not data.get("friendship_id"):
                raise ValidationError({"friendship_id": "required"})
            member = services.direct_conversation(request.user, data["friendship_id"])
        else:
            member = services.create_group(request.user, data.get("title"), data.get("friends"))
        return Response(conversation_payload(member), status=201)
    rows = ConversationMember.objects.filter(user=request.user).select_related("conversation").order_by("-conversation__updated_at")[:100]
    return Response({"results": [conversation_payload(m) for m in rows]})


@api_view(["GET", "PATCH", "POST"])
@permission_classes([IsAuthenticated])
def conversation_detail(request, conversation_id):
    member = membership(request.user, conversation_id)
    if request.method == "POST":
        rate(request, "chat.write")
        data = validated(request.data, action=serializers.ChoiceField(choices=["join", "leave"]))
        member = services.group_action(request.user, conversation_id, data["action"])
    if request.method == "PATCH":
        data = validated(request.data, muted=serializers.BooleanField())
        member.muted = data["muted"]
        member.save(update_fields=["muted", "updated_at"])
    return Response(conversation_payload(member))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def messages(request, conversation_id):
    member = membership(request.user, conversation_id)
    if request.method == "POST":
        rate(request, "chat.write")
        data = validated(request.data, client_id=serializers.UUIDField(), body=serializers.CharField(max_length=4000, allow_blank=True, required=False, default=""), reply_to=serializers.UUIDField(required=False, allow_null=True))
        msg = services.send_message(request.user, conversation_id, files=request.FILES.getlist("files"), **data)
        return Response(message_payload(msg, member), status=201)
    data = validated(request.query_params, after=serializers.IntegerField(min_value=0, required=False), before=serializers.IntegerField(min_value=1, required=False), q=serializers.CharField(max_length=100, required=False))
    if "after" in data and ("before" in data or "q" in data):
        raise ValidationError({"code": "invalid_cursor"})
    rows = visible_messages(member).select_related("reply_to").prefetch_related("attachments", "reactions")
    if data.get("q"):
        rows = rows.filter(body__icontains=data["q"], deleted_at__isnull=True)
    if "before" in data:
        rows = rows.filter(sequence__lt=data["before"])
    if "after" in data:
        rows = list(rows.filter(event_sequence__gt=data["after"]).order_by("event_sequence")[:51])
        more = len(rows) > 50
        rows = rows[:50]
        cursor = rows[-1].event_sequence if more else member.conversation.revision
    else:
        rows = list(rows.order_by("-sequence")[:51])
        more = len(rows) > 50
        rows = list(reversed(rows[:50]))
        cursor = member.conversation.revision
    return Response({"results": [message_payload(m, member) for m in rows], "cursor": cursor, "has_more": more, "before": rows[0].sequence if rows else None, "conversation": conversation_payload(member)})


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def message_detail(request, conversation_id, message_id):
    rate(request, "chat.write")
    data = {} if request.method == "DELETE" else validated(request.data, body=serializers.CharField(max_length=4000, required=False), reaction=serializers.ChoiceField(choices=list(services.REACTIONS) + [""], required=False))
    if request.method == "PATCH" and len(data) != 1:
        raise ValidationError({"code": "one_action_required"})
    msg = services.change_message(request.user, conversation_id, message_id, delete=request.method == "DELETE", **data)
    return Response(message_payload(msg, membership(request.user, conversation_id)))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def typing(request, conversation_id):
    data = validated(request.data, active=serializers.BooleanField())
    rate(request, "chat.typing")
    services.typing(request.user, conversation_id, data["active"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def read(request, conversation_id):
    data = validated(request.data, sequence=serializers.IntegerField(min_value=0))
    rate(request, "chat.write")
    member = services.read_messages(request.user, conversation_id, data["sequence"])
    return Response({"sequence": member.last_read_sequence})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attachment(request, attachment_id):
    from documents.storage import open_canonical
    row = ChatAttachment.objects.select_related("message").filter(pk=attachment_id, message__deleted_at__isnull=True).first()
    if not row or not visible_messages(membership(request.user, row.message.conversation_id)).filter(pk=row.message_id).exists():
        raise Http404
    try:
        response = FileResponse(open_canonical(row.storage_key), content_type=row.mime_type, as_attachment=row.kind == "pdf", filename=row.name)
    except FileNotFoundError:
        raise Http404 from None
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def avatar(request, user_id):
    from family.models import UserProfile
    from family.profile_views import _avatar_path
    if user_id != request.user.pk:
        friend = Friendship.objects.filter(active=True).filter(Q(low_user=request.user, high_user_id=user_id) | Q(high_user=request.user, low_user_id=user_id)).exists()
        group = ConversationMember.objects.filter(user=request.user, state="active", conversation__participants__user_id=user_id, conversation__participants__state="active").exists()
        if user_id in blocked_ids(request.user) or not (friend or group):
            raise Http404
    profile = UserProfile.objects.filter(user_id=user_id, user__is_active=True).first()
    if not profile or not profile.avatar_key:
        raise Http404
    path = _avatar_path(profile.avatar_key, 128)
    if not path.exists():
        raise Http404
    return FileResponse(path.open("rb"), content_type="image/webp")
