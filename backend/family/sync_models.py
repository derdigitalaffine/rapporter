from django.conf import settings
from django.db import models


class SyncSequence(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    cursor = models.PositiveBigIntegerField(default=0)
    retained_after = models.PositiveBigIntegerField(default=0)


class SyncJournal(models.Model):
    cursor = models.PositiveBigIntegerField(primary_key=True)
    family = models.ForeignKey('family.Family', on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=24)
    entity_id = models.UUIDField()
    operation = models.CharField(max_length=12)
    version = models.PositiveBigIntegerField()
    changed_fields = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['family', 'cursor'], name='sync_family_cursor'),
                   models.Index(fields=['family', 'entity_type', 'entity_id', 'version'], name='sync_entity_versions')]


class ProcessedMutation(models.Model):
    family = models.ForeignKey('family.Family', on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mutation_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['family', 'actor', 'mutation_id'], name='sync_mutation_once')]
