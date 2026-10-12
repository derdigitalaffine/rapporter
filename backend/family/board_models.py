from django.conf import settings
from django.db import models
from .models import Family, Membership, TimestampedModel


class BoardPost(TimestampedModel):
    class Kind(models.TextChoices):
        NOTE = 'note', 'Note'
        PHOTO = 'photo', 'Photo'
        EVENT = 'event', 'Calendar event'
        TASK = 'task', 'Task'
        ROUTINE = 'routine', 'Routine'
        NOTE_REF = 'note_ref', 'Note reference'
        SHOPPING = 'shopping', 'Shopping item'
        SHOPPING_LIST = 'shopping_list', 'Shopping list'
        TRIP = 'trip', 'Trip'
        DOCUMENT = 'document', 'Document'

    class Visibility(models.TextChoices):
        PRIVATE = 'private', 'Private'
        SELECTED = 'selected', 'Selected members'
        FAMILY = 'family', 'Whole family'

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='board_posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='board_posts')
    text = models.TextField(blank=True, max_length=10000)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.NOTE)
    target_id = models.UUIDField(null=True, blank=True)
    adapter_key = models.CharField(max_length=32, blank=True, db_index=True)
    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.FAMILY, db_index=True)
    visible_to_memberships = models.ManyToManyField('Membership', blank=True, related_name='visible_board_posts')
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ['position', '-created_at', '-id']
        indexes = [
            models.Index(fields=['family', 'position'], name='board_family_position'),
            models.Index(fields=['family', '-created_at'], name='board_family_created'),
        ]


class BoardImage(TimestampedModel):
    post = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='images')
    key = models.CharField(max_length=32, editable=False)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()

    class Meta:
        ordering = ['created_at', 'id']


class PinComment(TimestampedModel):
    """Flat, retry-safe family comment attached to a canonical BoardPost."""

    pin = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='comments')
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='pin_comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pin_comments',
    )
    body = models.TextField(max_length=2000)
    client_id = models.UUIDField()
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['pin', 'author', 'client_id'],
                name='pin_comment_retry_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['pin', 'created_at'], name='pin_comment_pin_time'),
            models.Index(fields=['family', 'created_at'], name='pin_comment_family_time'),
        ]


class PinCommentMention(models.Model):
    comment = models.ForeignKey(PinComment, on_delete=models.CASCADE, related_name='mentions')
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='pin_comment_mentions')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['comment', 'membership'],
                name='pin_comment_mention_unique',
            ),
        ]


class PinReaction(TimestampedModel):
    class Key(models.TextChoices):
        THUMBS_UP = 'thumbs_up', 'Passt'
        HEART = 'heart', 'Herz'
        JOY = 'joy', 'Freude'
        CELEBRATE = 'celebrate', 'Feiern'
        SEEN = 'seen', 'Gesehen'

    pin = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='reactions')
    comment = models.ForeignKey(
        PinComment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reactions',
    )
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='pin_reactions')
    key = models.CharField(max_length=16, choices=Key.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['pin', 'membership'],
                condition=models.Q(comment__isnull=True),
                name='pin_reaction_card_member_unique',
            ),
            models.UniqueConstraint(
                fields=['comment', 'membership'],
                condition=models.Q(comment__isnull=False),
                name='pin_reaction_comment_member_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['pin', 'key'], name='pin_reaction_pin_key'),
            models.Index(fields=['comment', 'key'], name='pin_reaction_comment_key'),
        ]


class PinInteractionState(TimestampedModel):
    pin = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='interaction_states')
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='pin_interaction_states')
    last_seen_comment_at = models.DateTimeField(null=True, blank=True)
    muted = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['pin', 'membership'],
                name='pin_interaction_state_unique',
            ),
        ]
        indexes = [models.Index(fields=['membership', 'muted'], name='pin_state_member_muted')]
