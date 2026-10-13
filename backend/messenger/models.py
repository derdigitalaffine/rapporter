import uuid

from django.conf import settings
from django.db import models

from family.models import TimestampedModel


class ChatPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_preferences")
    display_name = models.CharField(max_length=80, blank=True)
    locale = models.CharField(max_length=8, default="de")
    push_enabled = models.BooleanField(default=True)
    read_receipts = models.BooleanField(default=True)
    personal_account = models.BooleanField(default=False)


class Friendship(TimestampedModel):
    low_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_friendships_low")
    high_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_friendships_high")
    active = models.BooleanField(default=True)
    family_derived = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["low_user", "high_user"], name="chat_friend_pair_unique"),
            models.CheckConstraint(condition=models.Q(low_user__lt=models.F("high_user")), name="chat_friend_pair_ordered"),
        ]

    def other_id(self, user_id):
        return self.high_user_id if user_id == self.low_user_id else self.low_user_id


class ChatBlock(TimestampedModel):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_blocks")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_blocked_by")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="chat_block_pair_unique"),
            models.CheckConstraint(condition=~models.Q(blocker=models.F("blocked")), name="chat_block_not_self"),
        ]


class ContactInvitation(TimestampedModel):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_invitations_sent")
    email = models.EmailField(max_length=254)
    generation = models.UUIDField(default=uuid.uuid4)
    request_id = models.UUIDField()
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=16, default="pending")
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="chat_invitations_accepted")
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sender", "request_id"], name="chat_invite_request_unique")]
        indexes = [models.Index(fields=["email", "status", "expires_at"], name="chat_invite_target_idx")]


class Conversation(TimestampedModel):
    kind = models.CharField(max_length=8, choices=[("direct", "Direct"), ("group", "Group")])
    title = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_conversations_created")
    friendship = models.OneToOneField(Friendship, null=True, blank=True, on_delete=models.CASCADE, related_name="conversation")
    revision = models.PositiveBigIntegerField(default=0)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="ConversationMember", through_fields=("conversation", "user"), related_name="chat_conversations")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(kind="direct", friendship__isnull=False) | models.Q(kind="group", friendship__isnull=True), name="chat_conversation_scope")]


class ConversationMember(TimestampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_participations")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_group_invites")
    state = models.CharField(max_length=8, choices=[("invited", "Invited"), ("active", "Active"), ("left", "Left")], default="active")
    label = models.CharField(max_length=80)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    last_read_sequence = models.PositiveBigIntegerField(default=0)
    muted = models.BooleanField(default=False)
    typing_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="chat_member_unique")]
        indexes = [models.Index(fields=["user", "state"], name="chat_member_user_state_idx")]


class ChatMessage(TimestampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages")
    client_id = models.UUIDField()
    sequence = models.PositiveBigIntegerField()
    event_sequence = models.PositiveBigIntegerField()
    payload_digest = models.CharField(max_length=64, blank=True)
    body = models.TextField(blank=True)
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "sender", "client_id"], name="chat_message_retry_unique"),
            models.UniqueConstraint(fields=["conversation", "sequence"], name="chat_message_sequence_unique"),
        ]
        indexes = [models.Index(fields=["conversation", "event_sequence"], name="chat_message_delta_idx")]


class ChatAttachment(TimestampedModel):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=160)
    mime_type = models.CharField(max_length=80)
    kind = models.CharField(max_length=8)
    storage_key = models.CharField(max_length=500)
    size = models.PositiveIntegerField()


class ChatReaction(TimestampedModel):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_reactions")
    emoji = models.CharField(max_length=12)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user"], name="chat_reaction_user_unique")]
