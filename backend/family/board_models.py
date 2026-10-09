from django.conf import settings
from django.db import models

from .models import Family, TimestampedModel


class BoardPost(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='board_posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='board_posts')
    text = models.TextField(blank=True, max_length=10000)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['family', '-created_at'], name='board_family_created')]


class BoardImage(TimestampedModel):
    post = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='images')
    key = models.CharField(max_length=32, editable=False)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()

    class Meta:
        ordering = ['created_at', 'id']
