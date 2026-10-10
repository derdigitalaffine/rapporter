import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("baby", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BabyPrivateMedia",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scope", models.CharField(choices=[("pregnancy", "Pregnancy"), ("development", "Development")], max_length=20)),
                ("storage_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("content_type", models.CharField(max_length=64)),
                ("size_bytes", models.PositiveIntegerField()),
                ("baby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="private_media", to="baby.babyprofile")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="baby_private_media", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="baby_private_media", to="family.family")),
                ("pregnancy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="private_media", to="baby.pregnancyjourney")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["family", "scope", "created_at"], name="baby_media_family_scope_idx")],
            },
        ),
    ]
