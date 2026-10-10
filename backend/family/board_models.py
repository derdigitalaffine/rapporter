from django.conf import settings
from django.db import models
from .models import Family, TimestampedModel


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

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='board_posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='board_posts')
    text = models.TextField(blank=True, max_length=10000)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.NOTE)
    target_id = models.UUIDField(null=True, blank=True)
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
