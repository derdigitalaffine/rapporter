from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0236_shopping_list_access"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ShoppingSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="active", max_length=16)),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_activity_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("activity_seq", models.PositiveBigIntegerField(default=0)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completed_shopping_sessions", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_sessions", to="family.family")),
                ("shopping_list", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_sessions", to="family.shoppinglist")),
                ("started_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="started_shopping_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="ShoppingSessionParticipant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="family.shoppingsession")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_session_participations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["joined_at"]},
        ),
        migrations.CreateModel(
            name="ShoppingSessionActivity",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sequence", models.PositiveBigIntegerField()),
                ("kind", models.CharField(choices=[("item_added", "Item added"), ("item_checked", "Item checked"), ("item_reopened", "Item reopened")], max_length=24)),
                ("item_id", models.UUIDField(blank=True, null=True)),
                ("item_name", models.CharField(blank=True, max_length=160)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shopping_session_activities", to=settings.AUTH_USER_MODEL)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="family.shoppingsession")),
            ],
            options={"ordering": ["sequence"]},
        ),
        migrations.AddConstraint(
            model_name="shoppingsession",
            constraint=models.UniqueConstraint(condition=models.Q(status="active"), fields=("shopping_list",), name="shop_one_active_session"),
        ),
        migrations.AddIndex(
            model_name="shoppingsession",
            index=models.Index(fields=["family", "status", "last_activity_at"], name="shop_session_family_idx"),
        ),
        migrations.AddConstraint(
            model_name="shoppingsessionparticipant",
            constraint=models.UniqueConstraint(fields=("session", "user"), name="shop_session_participant_uniq"),
        ),
        migrations.AddConstraint(
            model_name="shoppingsessionactivity",
            constraint=models.UniqueConstraint(fields=("session", "sequence"), name="shop_session_activity_seq_uniq"),
        ),
        migrations.AddIndex(
            model_name="shoppingsessionactivity",
            index=models.Index(fields=["session", "sequence"], name="shop_session_cursor_idx"),
        ),
    ]