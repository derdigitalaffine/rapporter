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


class Task(TimestampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=180)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_family_tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_family_tasks")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    recurrence = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=40, default="manual")


class ShoppingList(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_lists")
    name = models.CharField(max_length=120, default="Einkauf")
    store = models.CharField(max_length=120, blank=True)
    archived = models.BooleanField(default=False)


class ShoppingItem(TimestampedModel):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=160)
    quantity = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=80, blank=True)
    checked = models.BooleanField(default=False)
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
        GENERIC = "generic", "Generic"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="integration_sources")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.GENERIC)
    endpoint = models.URLField(blank=True)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)


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
        indexes = [models.Index(fields=["family", "starts_at"]), models.Index(fields=["family", "type"])]


class InboxItem(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="inbox_items")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    source = models.CharField(max_length=40, default="share")
    status = models.CharField(max_length=24, default="new")
    parsed = models.JSONField(default=dict, blank=True)
