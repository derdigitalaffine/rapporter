from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def seed_receipts(apps, schema_editor):
    InboxItem = apps.get_model("family", "InboxItem")
    InboxReceipt = apps.get_model("family", "InboxReceipt")
    Membership = apps.get_model("family", "Membership")
    rows = []
    for item in InboxItem.objects.all().iterator():
        read_at = None if item.status == "new" else item.updated_at
        for membership_id in Membership.objects.filter(family_id=item.family_id).values_list("id", flat=True):
            rows.append(InboxReceipt(item_id=item.id, membership_id=membership_id, read_at=read_at))
            if len(rows) >= 1000:
                InboxReceipt.objects.bulk_create(rows, ignore_conflicts=True)
                rows = []
    if rows:
        InboxReceipt.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("family", "0011_familyos_brand_data")]

    operations = [
        migrations.AddField(
            model_name="inboxitem",
            name="audience",
            field=models.CharField(choices=[("family", "Whole family"), ("selected", "Selected members")], default="family", max_length=16),
        ),
        migrations.AddField(
            model_name="inboxitem",
            name="context",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="inboxitem",
            name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_family_messages", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="inboxitem",
            name="important",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="inboxitem",
            name="withdrawn_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="InboxReceipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="receipts", to="family.inboxitem")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inbox_receipts", to="family.membership")),
            ],
            options={"unique_together": {("item", "membership")}},
        ),
        migrations.AddIndex(
            model_name="inboxreceipt",
            index=models.Index(fields=["membership", "read_at"], name="fam_inbox_receipt_idx"),
        ),
        migrations.RunPython(seed_receipts, migrations.RunPython.noop),
    ]
