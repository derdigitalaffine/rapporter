import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def keep_contract_document_links(apps, schema_editor):
    # Runtime creates links only after a Contract exists. No forward backfill is needed.
    pass


def remove_contract_document_links(apps, schema_editor):
    # DocumentLink is intentionally generic and has no FK to Contract. Delete the
    # contract-domain references before dropping Contract rows during rollback.
    DocumentLink = apps.get_model("documents", "DocumentLink")
    DocumentLink.objects.filter(domain_type="contract").delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0001_initial"),
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Contract",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=240)),
                ("category", models.CharField(blank=True, max_length=96)),
                ("provider", models.CharField(blank=True, max_length=180)),
                ("contract_number", models.CharField(blank=True, max_length=120)),
                ("customer_number", models.CharField(blank=True, max_length=120)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("minimum_term_months", models.PositiveIntegerField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("cancellation_period_days", models.PositiveIntegerField(blank=True, null=True)),
                ("renewal_rule", models.CharField(blank=True, max_length=240)),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("billing_interval", models.CharField(blank=True, choices=[("monthly", "Monthly"), ("quarterly", "Quarterly"), ("half_year", "Half year"), ("yearly", "Yearly"), ("one_time", "One time"), ("other", "Other")], max_length=24)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("ending", "Ending"), ("ended", "Ended"), ("cancelled", "Cancelled")], db_index=True, default="active", max_length=16)),
                ("notes", models.TextField(blank=True)),
                ("visibility", models.CharField(choices=[("private", "Private"), ("family", "Family"), ("selected", "Selected")], db_index=True, default="private", max_length=16)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contracts_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contracts", to="family.family")),
                ("owner_membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_contracts", to="family.membership")),
            ],
            options={"ordering": ["title", "created_at"]},
        ),
        migrations.CreateModel(
            name="ContractAccess",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("can_view", models.BooleanField(default=True)),
                ("can_manage", models.BooleanField(default=False)),
                ("contract", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_entries", to="contracts.contract")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contract_access_entries", to="family.membership")),
            ],
        ),
        migrations.CreateModel(
            name="ContractReminder",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("due_on", models.DateField()),
                ("label", models.CharField(blank=True, max_length=240)),
                ("status", models.CharField(choices=[("active", "Active"), ("done", "Done"), ("cancelled", "Cancelled")], db_index=True, default="active", max_length=16)),
                ("confirmed_at", models.DateTimeField()),
                ("contract", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reminders", to="contracts.contract")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contract_reminders_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["due_on", "created_at"]},
        ),
        migrations.AddIndex(model_name="contract", index=models.Index(fields=["family", "visibility", "archived_at"], name="contract_family_vis_idx")),
        migrations.AddIndex(model_name="contract", index=models.Index(fields=["family", "status", "end_date"], name="contract_family_end_idx")),
        migrations.AddConstraint(model_name="contractaccess", constraint=models.UniqueConstraint(fields=("contract", "membership"), name="contract_access_member_uniq")),
        migrations.AddIndex(model_name="contractreminder", index=models.Index(fields=["status", "due_on"], name="contract_reminder_due_idx")),
        migrations.RunPython(keep_contract_document_links, remove_contract_document_links),
    ]
