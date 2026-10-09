from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0005_integration_health"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.TextField()),
                ("auth", models.TextField()),
                ("user_agent", models.CharField(blank=True, max_length=240)),
                ("active", models.BooleanField(default=True)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="famuhle_push_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterField(
            model_name="automationrule",
            name="action_type",
            field=models.CharField(choices=[("task_create", "Create task"), ("shopping_add", "Add shopping item"), ("inbox_create", "Create inbox message"), ("home_service", "Call Home Assistant service"), ("push_notify", "Send push notification")], max_length=40),
        ),
    ]
