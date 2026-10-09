import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0012_family_messages"),
    ]

    operations = [
        migrations.CreateModel(
            name="Expense",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=180)),
                ("merchant", models.CharField(blank=True, max_length=180)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("total_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("currency", models.CharField(default="EUR", max_length=3)),
                ("receipt_content", models.BinaryField(blank=True, editable=False, null=True)),
                ("receipt_mime", models.CharField(blank=True, max_length=64)),
                ("receipt_status", models.CharField(choices=[("none", "None"), ("queued", "Queued"), ("processing", "Processing"), ("review", "Review"), ("ready", "Ready"), ("failed", "Failed")], default="none", max_length=16)),
                ("notes", models.TextField(blank=True)),
                ("source", models.CharField(choices=[("manual", "Manual"), ("receipt", "Receipt")], default="manual", max_length=16)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("posted", "Posted")], db_index=True, default="posted", max_length=16)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="family_expenses_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expenses", to="family.family")),
                ("paid_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="expenses_paid", to="family.membership")),
            ],
            options={"ordering": ["-occurred_at", "-created_at"]},
        ),
        migrations.CreateModel(
            name="ReceiptExtraction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("processing", "Processing"), ("review", "Review"), ("ready", "Ready"), ("failed", "Failed")], db_index=True, default="queued", max_length=16)),
                ("merchant", models.CharField(blank=True, max_length=180)),
                ("date", models.DateField(blank=True, null=True)),
                ("total", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("subtotal", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("tax", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("currency", models.CharField(blank=True, max_length=3)),
                ("raw_text", models.TextField(blank=True)),
                ("structured_data", models.JSONField(blank=True, default=dict)),
                ("field_confidences", models.JSONField(blank=True, default=dict)),
                ("parser_version", models.CharField(default="receipt-v1", max_length=32)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.CharField(blank=True, max_length=500)),
                ("expense", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="extraction", to="expenses.expense")),
            ],
        ),
        migrations.CreateModel(
            name="ExpenseShare",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("split_type", models.CharField(choices=[("equal", "Equal"), ("exact", "Exact"), ("percentage", "Percentage"), ("shares", "Shares")], default="equal", max_length=16)),
                ("expense", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="expenses.expense")),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="expense_shares", to="family.membership")),
            ],
            options={"ordering": ["created_at"], "unique_together": {("expense", "member")}},
        ),
        migrations.CreateModel(
            name="Settlement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="EUR", max_length=3)),
                ("settled_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("voided_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="family_settlements_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expense_settlements", to="family.family")),
                ("from_member", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="settlements_sent", to="family.membership")),
                ("to_member", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="settlements_received", to="family.membership")),
            ],
            options={"ordering": ["-settled_at", "-created_at"]},
        ),
        migrations.AddIndex(model_name="expense", index=models.Index(fields=["family", "currency", "status"], name="exp_family_currency_idx")),
        migrations.AddIndex(model_name="expense", index=models.Index(fields=["family", "occurred_at"], name="exp_family_date_idx")),
        migrations.AddIndex(model_name="settlement", index=models.Index(fields=["family", "currency", "voided_at"], name="settle_family_currency_idx")),
    ]
