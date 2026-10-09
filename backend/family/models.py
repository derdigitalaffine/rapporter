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


class UserProfile(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="familyos_profile")
    avatar_key = models.CharField(max_length=64, blank=True)
    avatar_version = models.UUIDField(default=uuid.uuid4, editable=False)
    birth_month = models.PositiveSmallIntegerField(null=True, blank=True)
    birth_day = models.PositiveSmallIntegerField(null=True, blank=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)


class Family(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    locale = models.CharField(max_length=8, default="de")
    timezone = models.CharField(max_length=64, default="Europe/Berlin")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    def __str__(self):
        return self.name


class Membership(TimestampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADULT = "adult", "Adult"
        TEEN = "teen", "Teen"
        CHILD = "child", "Child"
        GUEST = "guest", "Guest"

    class BirthdayVisibility(models.TextChoices):
        HIDDEN = "hidden", "Hidden"
        DAY_MONTH = "day_month", "Day and month"
        FULL_DATE = "full_date", "Full date"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="family_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.ADULT)
    display_name = models.CharField(max_length=80, blank=True)
    avatar = models.CharField(max_length=255, blank=True)
    birthday_visibility = models.CharField(max_length=16, choices=BirthdayVisibility.choices, default=BirthdayVisibility.DAY_MONTH)

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
        return self.family.status == Family.Status.ACTIVE and not self.accepted_at and not self.revoked_at and self.expires_at > timezone.now()


class TaskList(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="task_lists")
    name = models.CharField(max_length=120)
    icon = models.CharField(max_length=48, default="list-check")
    archived = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    workflow_enabled = models.BooleanField(default=False)

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
    source = models.CharField(max_length=96, default="manual")
    estimate_minutes = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    workflow_column = models.ForeignKey("TaskWorkflowColumn", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    workflow_position = models.DecimalField(max_digits=24, decimal_places=10, null=True, blank=True)
    birthday_context = models.UUIDField(null=True, blank=True, editable=False)
    hidden_from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="hidden_gift_tasks", editable=False)

    def save(self, *args, **kwargs):
        # Every writer (API, quick-add, toggle and automation) uses the same invariant.
        from django.db import transaction
        from .task_workflow import prepare_task, record_status
        with transaction.atomic():
            previous = prepare_task(self)
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"workflow_column", "workflow_position", "completed_at"}
            super().save(*args, **kwargs)
            record_status(self, previous)


class TaskWorkflowColumn(TimestampedModel):
    task_list = models.ForeignKey(TaskList, on_delete=models.CASCADE, related_name="workflow_columns")
    name = models.CharField(max_length=80)
    key = models.SlugField(max_length=80)
    position = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=16, choices=[("open", "Open"), ("active", "Active"), ("waiting", "Waiting"), ("done", "Done")], default="open")
    is_terminal = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "created_at"]
        unique_together = ("task_list", "key")


class TaskStatusEvent(TimestampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="status_events")
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    from_column = models.ForeignKey(TaskWorkflowColumn, null=True, on_delete=models.SET_NULL, related_name="departures")
    to_column = models.ForeignKey(TaskWorkflowColumn, null=True, on_delete=models.SET_NULL, related_name="arrivals")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    source = models.CharField(max_length=16, default="api")

    class Meta:
        ordering = ["-created_at"]


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
    birthday_context = models.UUIDField(null=True, blank=True, editable=False)
    hidden_from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="hidden_gift_items", editable=False)


class BirthdayPerson(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="birthday_people")
    name = models.CharField(max_length=120)
    birth_month = models.PositiveSmallIntegerField()
    birth_day = models.PositiveSmallIntegerField()
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    relation = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)


class BirthdayGiftPlan(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="birthday_gift_plans")
    membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.CASCADE, related_name="birthday_gift_plans")
    person = models.ForeignKey(BirthdayPerson, null=True, blank=True, on_delete=models.CASCADE, related_name="gift_plans")
    occurrence_year = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=[(x,x) for x in ["none", "idea", "planned", "ordered", "ready", "given"]], default="none")
    idea_text = models.TextField(blank=True)
    linked_task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL, related_name="birthday_gift_plans")
    linked_shopping_item = models.ForeignKey(ShoppingItem, null=True, blank=True, on_delete=models.SET_NULL)
    hidden_from_birthday_person = models.BooleanField(default=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(models.Q(membership__isnull=False, person__isnull=True) | models.Q(membership__isnull=True, person__isnull=False)), name="gift_exactly_one_person"),
            models.UniqueConstraint(fields=["membership", "occurrence_year"], name="gift_member_year_unique"),
            models.UniqueConstraint(fields=["person", "occurrence_year"], name="gift_person_year_unique"),
        ]


class BirthdayReminder(TimestampedModel):
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE)
    target_key = models.CharField(max_length=64)
    occurrence_year = models.PositiveSmallIntegerField()
    stage = models.PositiveSmallIntegerField()
    delivered_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "target_key", "occurrence_year", "stage"], name="birthday_reminder_once")]


class ShoppingPurchaseEvent(TimestampedModel):
    """Immutable purchase signal retained independently from active shopping rows."""

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_purchase_events")
    shopping_list = models.ForeignKey(ShoppingList, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_events")
    source_item_id = models.UUIDField(null=True, blank=True)
    normalized_name = models.CharField(max_length=180)
    display_name = models.CharField(max_length=160)
    quantity = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=80, blank=True)
    aisle = models.CharField(max_length=80, blank=True)
    store = models.CharField(max_length=120, blank=True)
    purchased_at = models.DateTimeField(db_index=True)
    purchased_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_purchase_events")

    class Meta:
        ordering = ["purchased_at"]
        indexes = [
            models.Index(fields=["family", "normalized_name", "purchased_at"], name="fam_purchase_name_time_idx"),
            models.Index(fields=["family", "purchased_at"], name="fam_purchase_time_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["source_item_id", "purchased_at"], name="fam_purchase_item_time_uniq"),
        ]


class ShoppingPredictionFeedback(TimestampedModel):
    class Action(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        SNOOZED = "snoozed", "Snoozed"
        DISMISSED = "dismissed", "Dismissed"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_prediction_feedback")
    normalized_name = models.CharField(max_length=180)
    action = models.CharField(max_length=16, choices=Action.choices, default=Action.ACCEPTED)
    suppress_until = models.DateTimeField(null=True, blank=True)
    dismiss_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["family", "normalized_name"], name="fam_prediction_feedback_uniq")]
        indexes = [models.Index(fields=["family", "suppress_until"], name="fam_prediction_suppress_idx")]


class EntryMemory(TimestampedModel):
    class Kind(models.TextChoices):
        TASK = "task", "Task"
        SHOPPING = "shopping", "Shopping"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="entry_memories")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    normalized_name = models.CharField(max_length=180)
    name = models.CharField(max_length=180)
    data = models.JSONField(default=dict, blank=True)
    use_count = models.PositiveIntegerField(default=1)
    last_used_at = models.DateTimeField()

    class Meta:
        unique_together = ("family", "kind", "normalized_name")
        indexes = [models.Index(fields=["family", "kind", "last_used_at"], name="fam_mem_family_kind_idx")]


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
    class Audience(models.TextChoices):
        FAMILY = "family", "Whole family"
        SELECTED = "selected", "Selected members"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="inbox_items")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    source = models.CharField(max_length=40, default="share")
    status = models.CharField(max_length=24, default="new")
    parsed = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_family_messages")
    audience = models.CharField(max_length=16, choices=Audience.choices, default=Audience.FAMILY)
    important = models.BooleanField(default=False)
    context = models.JSONField(default=dict, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)


class InboxReceipt(TimestampedModel):
    item = models.ForeignKey(InboxItem, on_delete=models.CASCADE, related_name="receipts")
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="inbox_receipts")
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("item", "membership")
        indexes = [models.Index(fields=["membership", "read_at"], name="fam_inbox_receipt_idx")]


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
