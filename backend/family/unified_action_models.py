"""Additive mirror; legacy domain rows remain authoritative during rollout."""
from django.conf import settings
from django.db import models
from .models import TimestampedModel


class Action(TimestampedModel):
    family = models.ForeignKey('Family', on_delete=models.CASCADE, related_name='unified_actions')
    legacy_task = models.OneToOneField('Task', null=True, blank=True, on_delete=models.SET_NULL, related_name='unified_action')
    legacy_routine = models.OneToOneField('Routine', null=True, blank=True, on_delete=models.SET_NULL, related_name='unified_action')
    legacy_event = models.OneToOneField('FamilyEvent', null=True, blank=True, on_delete=models.SET_NULL, related_name='unified_action')
    title = models.CharField(max_length=180)
    state = models.CharField(max_length=16, default='open')
    kind_hint = models.CharField(max_length=16)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    due_at = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, default='normal')
    estimate_minutes = models.PositiveIntegerField(null=True, blank=True)
    icon = models.CharField(max_length=48, blank=True)
    accent_token = models.CharField(max_length=16, blank=True)
    source = models.CharField(max_length=96, default='manual')
    schedule = models.JSONField(default=dict, blank=True)
    rejected_proposals = models.JSONField(default=list, blank=True)
    learning_cutoff_at = models.DateTimeField(null=True, blank=True)
    migration_phase = models.CharField(max_length=24, default='mirror')

    class Meta:
        constraints = [models.CheckConstraint(condition=~((models.Q(legacy_task__isnull=False) & models.Q(legacy_routine__isnull=False)) | (models.Q(legacy_event__isnull=False) & models.Q(legacy_task__isnull=False)) | (models.Q(legacy_event__isnull=False) & models.Q(legacy_routine__isnull=False))), name='action_one_legacy_kind')]
        indexes = [models.Index(fields=['family', 'state'], name='action_family_state_idx')]


class ActionCompletion(TimestampedModel):
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name='completions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    occurred_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=24, default='ui')
    request_id = models.UUIDField(null=True, blank=True)
    legacy_log = models.OneToOneField('RoutineLog', null=True, blank=True, on_delete=models.SET_NULL, related_name='action_completion')
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['action', 'request_id'], name='action_completion_request_unique')]
        indexes = [models.Index(fields=['action', 'occurred_at'], name='action_completion_time_idx')]


class ActionCommand(TimestampedModel):
    """Receipts survive undo so replaying a request cannot execute it again."""
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name='commands')
    request_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    operation = models.CharField(max_length=16)
    completion = models.ForeignKey(ActionCompletion, null=True, on_delete=models.SET_NULL)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['action', 'request_id'], name='action_command_request_unique')]


class ActionCapture(TimestampedModel):
    family = models.ForeignKey('Family', on_delete=models.CASCADE)
    request_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.ForeignKey(Action, on_delete=models.CASCADE)
    completion = models.ForeignKey(ActionCompletion, on_delete=models.CASCADE)
    original_title = models.CharField(max_length=160)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['family', 'request_id'], name='action_capture_request_unique')]


class ActionDecisionRound(TimestampedModel):
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name='decision_rounds')
    template = models.ForeignKey('decisions.Decision', on_delete=models.PROTECT, related_name='+')
    decision = models.OneToOneField('decisions.Decision', on_delete=models.CASCADE, related_name='action_round')
    request_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['action', 'request_id'], name='action_decision_round_request_unique')]


class ActionPolicy(TimestampedModel):
    family = models.OneToOneField('Family', on_delete=models.CASCADE, related_name='action_policy')
    adaptive_enabled = models.BooleanField(default=True)
    calendar_aware = models.BooleanField(default=False)
    learning_history_days = models.PositiveIntegerField(default=365)


class ActionPersonalSetting(TimestampedModel):
    membership = models.OneToOneField('Membership', on_delete=models.CASCADE)
    capture_suggestions = models.BooleanField(default=True)
    calendar_aware = models.BooleanField(default=False)
