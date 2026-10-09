from django.conf import settings
from django.db import models
from .models import Family, TimestampedModel

class Note(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='private_notes')
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(blank=True)
    drawing = models.JSONField(default=list, blank=True)
    pinned = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    class Meta:
        ordering = ['-pinned', '-updated_at']
        indexes = [models.Index(fields=['family', 'author', '-updated_at'], name='notes_family_author_date')]

class NoteShare(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    permission = models.CharField(max_length=8, choices=[('read','Read'), ('edit','Edit')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['note','user'], name='unique_note_share')]

class NoteRevision(TimestampedModel):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='revisions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(blank=True)
    drawing = models.JSONField(default=list)
    class Meta:
        ordering = ['-version']
