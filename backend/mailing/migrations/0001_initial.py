# Generated manually for the initial mailing app schema.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TransactionalEmail",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("message_key", models.CharField(max_length=180, unique=True)),
                ("template_key", models.CharField(max_length=80)),
                ("locale", models.CharField(default="de", max_length=8)),
                ("recipient", models.EmailField(blank=True, default="", max_length=254)),
                ("recipient_hash", models.CharField(db_index=True, max_length=64)),
                ("context", models.JSONField(blank=True, default=dict)),
                ("reference_type", models.CharField(blank=True, default="", max_length=80)),
                ("reference_id", models.CharField(blank=True, default="", max_length=120)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("sending", "Sending"), ("sent", "Sent"), ("retry", "Retry"), ("failed", "Failed"), ("canceled", "Canceled")], db_index=True, default="queued", max_length=16)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(db_index=True)),
                ("lease_token", models.UUIDField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_error_code", models.CharField(blank=True, default="", max_length=80)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("payload_cleared_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(
            model_name="transactionalemail",
            index=models.Index(fields=["status", "next_attempt_at"], name="mail_status_due_idx"),
        ),
        migrations.AddIndex(
            model_name="transactionalemail",
            index=models.Index(fields=["status", "lease_expires_at"], name="mail_status_lease_idx"),
        ),
    ]
