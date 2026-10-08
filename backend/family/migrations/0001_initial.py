import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Family",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("locale", models.CharField(default="de", max_length=8)),
                ("timezone", models.CharField(default="Europe/Berlin", max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name="IntegrationSource",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("kind", models.CharField(choices=[("ics", "ICS/iCal"), ("waste", "Waste calendar"), ("weather", "Weather"), ("warning", "Public warning"), ("messenger", "Messenger"), ("generic", "Generic")], default="generic", max_length=32)),
                ("endpoint", models.URLField(blank=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("enabled", models.BooleanField(default=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="integration_sources", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="ShoppingList",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(default="Einkauf", max_length=120)),
                ("store", models.CharField(blank=True, max_length=120)),
                ("archived", models.BooleanField(default=False)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_lists", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="Routine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("suggested_interval_days", models.PositiveIntegerField(blank=True, null=True)),
                ("icon", models.CharField(default="sparkles", max_length=40)),
                ("active", models.BooleanField(default=True)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="routines", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("owner", "Owner"), ("adult", "Adult"), ("teen", "Teen"), ("child", "Child"), ("guest", "Guest")], default="adult", max_length=16)),
                ("display_name", models.CharField(blank=True, max_length=80)),
                ("avatar", models.CharField(blank=True, max_length=255)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="family.family")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="family_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("family", "user")}},
        ),
        migrations.CreateModel(
            name="InboxItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True)),
                ("source", models.CharField(default="share", max_length=40)),
                ("status", models.CharField(default="new", max_length=24)),
                ("parsed", models.JSONField(blank=True, default=dict)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inbox_items", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="FamilyEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("type", models.CharField(max_length=80)),
                ("title", models.CharField(max_length=200)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("actionable", models.BooleanField(default=False)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("external_id", models.CharField(blank=True, max_length=180)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="family.family")),
                ("source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events", to="family.integrationsource")),
            ],
            options={"indexes": [models.Index(fields=["family", "starts_at"], name="fam_evt_family_start_idx"), models.Index(fields=["family", "type"], name="fam_evt_family_type_idx")]},
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=180)),
                ("notes", models.TextField(blank=True)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("priority", models.CharField(choices=[("low", "Low"), ("normal", "Normal"), ("high", "High")], default="normal", max_length=10)),
                ("recurrence", models.CharField(blank=True, max_length=120)),
                ("source", models.CharField(default="manual", max_length=40)),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_family_tasks", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_family_tasks", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="ShoppingItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("quantity", models.CharField(blank=True, max_length=40)),
                ("category", models.CharField(blank=True, max_length=80)),
                ("checked", models.BooleanField(default=False)),
                ("added_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("shopping_list", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="family.shoppinglist")),
            ],
        ),
        migrations.CreateModel(
            name="RoutineLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("done_at", models.DateTimeField()),
                ("note", models.CharField(blank=True, max_length=240)),
                ("done_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("routine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="family.routine")),
            ],
        ),
    ]
