import uuid
from datetime import timedelta
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from auth_identity.models import EmailIdentity
from auth_identity.service import create_primary_identity, generate_internal_username, normalize_email
from mailing.service import enqueue_transactional_email
from .access import eligible, is_blocked, preferences, require_writer
from .models import ChatPreference, ContactInvitation, Friendship

SALT = "familyos.chat-invitation.v1"


def invitation_token(invite):
    return signing.dumps({"id": str(invite.pk), "generation": str(invite.generation)}, salt=SALT)


def resolve_invitation(token, *, lock=False):
    try:
        if not isinstance(token, str) or len(token) > 1000:
            raise ValueError
        data = signing.loads(token, salt=SALT, max_age=7 * 86400)
        invite_id, generation = uuid.UUID(data["id"]), uuid.UUID(data["generation"])
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        raise Http404 from None
    rows = ContactInvitation.objects.select_related("sender")
    if lock:
        rows = rows.select_for_update(of=("self",))
    invite = rows.filter(pk=invite_id, generation=generation, status__in=("pending", "accepted"), expires_at__gt=timezone.now()).first()
    if not invite or not eligible(invite.sender):
        raise Http404
    return invite


def invitation_path(reference_id):
    try:
        invite_id, generation = str(reference_id).split(":", 1)
        invite = ContactInvitation.objects.filter(pk=uuid.UUID(invite_id), generation=uuid.UUID(generation), status="pending", expires_at__gt=timezone.now()).select_related("sender").first()
    except (ValueError, TypeError):
        return ""
    if not invite or not eligible(invite.sender):
        return ""
    target = EmailIdentity.objects.filter(email_normalized=invite.email, kind="primary").values_list("user_id", flat=True).first()
    if target:
        low, high = sorted((invite.sender_id, target))
        removed = Friendship.objects.filter(low_user_id=low, high_user_id=high, active=False, updated_at__gte=invite.created_at).exists()
        if removed or is_blocked(invite.sender_id, target):
            return ""
    return f"/?page=inbox#chat-invite={quote(invitation_token(invite), safe='')}"


def create_invitation(sender, email, request_id):
    require_writer(sender)
    email = normalize_email(email)
    own = EmailIdentity.objects.filter(user=sender, kind="primary").first()
    if own and email == own.email_normalized:
        raise ValidationError({"email": "Du kannst dich nicht selbst einladen."})
    with transaction.atomic():
        get_user_model().objects.select_for_update(no_key=True).get(pk=sender.pk)
        previous = ContactInvitation.objects.filter(sender=sender, request_id=request_id).first()
        if previous:
            if previous.email != email:
                raise ValidationError({"code": "request_conflict"})
            return previous
        invite = ContactInvitation.objects.create(sender=sender, email=email, request_id=request_id, expires_at=timezone.now() + timedelta(days=7))
        pref = preferences(sender)
        if not pref.personal_account:
            pref.personal_account = True
            pref.save(update_fields=["personal_account"])
        target = EmailIdentity.objects.filter(email_normalized=email, kind="primary").values_list("user_id", flat=True).first()
        # The sender receives the same response regardless of registration or block status.
        if not target or not is_blocked(sender.pk, target):
            enqueue_transactional_email(message_key=f"chat-invite:{invite.pk}:{invite.generation}", template_key="chat.invitation", recipient=email, locale=preferences(sender).locale, context={"details": preferences(sender).display_name, "action_label": "Einladung öffnen" if preferences(sender).locale == "de" else "Open invitation"}, reference_type="chat.invitation", reference_id=f"{invite.pk}:{invite.generation}")
        return invite


def accept_invitation(invite, user):
    # Keep FK key-share locks compatible with chat/game inserts while serializing consent.
    users = {row.pk: row for row in get_user_model().objects.select_for_update(no_key=True).filter(pk__in=(user.pk, invite.sender_id)).order_by("pk")}
    user, sender = users.get(user.pk), users.get(invite.sender_id)
    if not user or not sender or not user.is_active or (getattr(user, "is_superadmin", False) or user.is_superuser) or not eligible(sender) or user.pk == sender.pk or is_blocked(user.pk, sender.pk):
        raise Http404
    identity = EmailIdentity.objects.filter(user=user, kind="primary", verified_at__isnull=False, email_normalized=invite.email).first()
    if not identity:
        raise Http404
    if user.family_memberships.exists():
        require_writer(user)
    else:
        pref = preferences(user)
        pref.personal_account = True
        pref.save(update_fields=["personal_account"])
    if invite.status == "accepted" and invite.accepted_by_id != user.pk:
        raise Http404
    low, high = sorted((user.pk, sender.pk))
    friend, _ = Friendship.objects.get_or_create(low_user_id=low, high_user_id=high)
    if not friend.active:
        if invite.status == "accepted" or invite.created_at <= friend.updated_at:
            raise PermissionDenied({"code": "friendship_removed"})
        friend.active = True
        friend.save(update_fields=["active", "updated_at"])
    for participant in (user, sender):
        pref = preferences(participant)
        if not pref.personal_account:
            pref.personal_account = True
            pref.save(update_fields=["personal_account"])
    invite.status, invite.accepted_by, invite.accepted_at = "accepted", user, timezone.now()
    invite.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])
    return friend


def register_from_invitation(token, password, display_name):
    # The mailbox-delivered invitation proves the recipient address; it never grants a family role.
    with transaction.atomic():
        invite = resolve_invitation(token, lock=True)
        if invite.status != "pending":
            raise Http404
        if EmailIdentity.objects.filter(email_normalized=invite.email).exists():
            raise ValidationError({"code": "invite_login_required", "detail": "Melde dich mit dem eingeladenen Konto an."})
        user = get_user_model()(username=generate_internal_username(), email=invite.email, first_name=display_name[:80])
        validate_password(password, user=user)
        user.set_password(password)
        user.save()
        create_primary_identity(user, invite.email, verified=True)
        ChatPreference.objects.create(user=user, display_name=display_name[:80], personal_account=True)
        friend = accept_invitation(invite, user)
        return user, friend
