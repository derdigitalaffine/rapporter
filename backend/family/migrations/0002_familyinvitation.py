from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FamilyInvitation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token", models.CharField(editable=False, max_length=96, unique=True)),
                ("role", models.CharField(choices=[("owner", "Owner"), ("adult", "Adult"), ("teen", "Teen"), ("child", "Child"), ("guest", "Guest")], default="adult", max_length=16)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("display_name", models.CharField(blank=True, max_length=80)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("accepted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="family_invitations_accepted", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="family.family")),
                ("invited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="family_invitations_created", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
