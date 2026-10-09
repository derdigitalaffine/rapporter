import secrets
import uuid
from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Family(TimestampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    locale = models.CharField(max_length=8, default="de")
    timezone = models.CharField(max_length=64, default="Europe/Berlin")

    def __str__(self):
        return self.name


class Membership(TimestampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADULT = "adult", "Adult"
        TEEN = "teen", "Teen"
        CHILD = "child", "Child"
        GUEST = "guest", "Guest"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="family_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.ADULT)
    display_name = models.CharField(max_length=80, blank=True)
    avatar = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("family", "user")


class FamilyInvitation(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="invitations")
    token = models.CharField(max_length=96, unique=True, editable=False)
    role = models.CharField(max_length=16, choices=Membership.Role.choices, default=Membership.Role.ADULT)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="family_invitations_created")
    email = models.EmailField(blank=True)
    display_name = models.CharField(max_length=80, blank=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="family_invitations_accepted")
    revoked_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(36)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        from django.utils import timezone
        return not self.accepted_at and not self.revoked_at and self.expires_at > timezone.now()


class TaskList(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="task_lists")
    name = models.CharField(max_length=120)
    icon = models.CharField(max_length=48, default="list-check")
    archived = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]
        unique_together = ("family", "name")


class Task(TimestampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="tasks")
    task_list = models.ForeignKey(TaskList, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    title = models.CharField(max_length=180)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_family_tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_family_tasks")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    recurrence = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=40, default="manual")
    estimate_minutes = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)


class ShoppingList(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_lists")
    name = models.CharField(max_length=120, default="Einkauf")
    store = models.CharField(max_length=120, blank=True)
    icon = models.CharField(max_length=48, default="cart-shopping")
    archived = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)


class ShoppingItem(TimestampedModel):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=160)
    quantity = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=240, blank=True)
    aisle = models.CharField(max_length=80, blank=True)
    favorite = models.BooleanField(default=False)
    checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class Routine(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="routines")
    name = models.CharField(max_length=160)
    suggested_interval_days = models.PositiveIntegerField(null=True, blank=True)
    icon = models.CharField(max_length=40, default="sparkles")
    active = models.BooleanField(default=True)


class RoutineLog(TimestampedModel):
    routine = models.ForeignKey(Routine, on_delete=models.CASCADE, related_name="logs")
    done_at = models.DateTimeField()
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=240, blank=True)


class IntegrationSource(TimestampedModel):
    class Kind(models.TextChoices):
        ICS = "ics", "ICS/iCal"
        WASTE = "waste", "Waste calendar"
        WEATHER = "weather", "Weather"
        WARNING = "warning", "Public warning"
        MESSENGER = "messenger", "Messenger"
        HOME = "home", "Home automation"
        TRANSIT = "transit", "Public transit"
        SCHOOL = "school", "School"
        GENERIC = "generic", "Generic"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="integration_sources")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.GENERIC)
    endpoint = models.URLField(blank=True)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=16, default="never")
    last_sync_error = models.TextField(blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_sync_at = models.DateTimeField(null=True, blank=True)


class FamilyEvent(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="events")
    source = models.ForeignKey(IntegrationSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    type = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    actionable = models.BooleanField(default=False)
    payload = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=180, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["family", "starts_at"], name="fam_evt_family_start_idx"),
            models.Index(fields=["family", "type"], name="fam_evt_family_type_idx"),
        ]


class InboxItem(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="inbox_items")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    source = models.CharField(max_length=40, default="share")
    status = models.CharField(max_length=24, default="new")
    parsed = models.JSONField(default=dict, blank=True)


class PushSubscription(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="famuhle_push_subscriptions")
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=240, blank=True)
    active = models.BooleanField(default=True)
    last_success_at = models.DateTimeField(null=True, blank=True)


class AutomationRule(TimestampedModel):
    class Trigger(models.TextChoices):
        WASTE_TOMORROW = "waste_tomorrow", "Waste collection tomorrow"
        WEATHER_FROST = "weather_frost", "Frost forecast"
        WEATHER_RAIN = "weather_rain", "Rain forecast"
        WARNING_ACTIVE = "warning_active", "Official warning active"
        EVENT_UPCOMING = "event_upcoming", "Upcoming event"
        DAILY = "daily", "Daily at time"
        HOME_STATE = "home_state", "Home Assistant entity state"
        TRANSIT_DELAY = "transit_delay", "Transit delay"
        TASK_COMPLETED = "task_completed", "Task completed"

    class Action(models.TextChoices):
        TASK_CREATE = "task_create", "Create task"
        SHOPPING_ADD = "shopping_add", "Add shopping item"
        INBOX_CREATE = "inbox_create", "Create inbox message"
        HOME_SERVICE = "home_service", "Call Home Assistant service"
        PUSH_NOTIFY = "push_notify", "Send push notification"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="automation_rules")
    name = models.CharField(max_length=160)
    icon = models.CharField(max_length=48, default="wand-magic-sparkles")
    enabled = models.BooleanField(default=True)
    trigger_type = models.CharField(max_length=40, choices=Trigger.choices)
    trigger_config = models.JSONField(default=dict, blank=True)
    action_type = models.CharField(max_length=40, choices=Action.choices)
    action_config = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="automation_rules_created")
    last_run_at = models.DateTimeField(null=True, blank=True)


class AutomationExecution(TimestampedModel):
    rule = models.ForeignKey(AutomationRule, on_delete=models.CASCADE, related_name="executions")
    fingerprint = models.CharField(max_length=220)
    status = models.CharField(max_length=20, default="success")
    message = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = ("rule", "fingerprint")
        ordering = ["-created_at"]
