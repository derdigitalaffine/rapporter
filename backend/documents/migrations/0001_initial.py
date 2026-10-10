import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("family", "0207_shopping_templates_stores"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(default="generic", max_length=64)),
                ("title", models.CharField(max_length=240)),
                ("document_date", models.DateField(blank=True, null=True)),
                ("correspondent", models.CharField(blank=True, max_length=180)),
                ("visibility", models.CharField(choices=[("private", "Private"), ("family", "Family"), ("selected", "Selected")], db_index=True, default="private", max_length=16)),
                ("canonical_file", models.CharField(editable=False, max_length=500)),
                ("mime_type", models.CharField(editable=False, max_length=96)),
                ("size", models.PositiveBigIntegerField(editable=False)),
                ("sha256", models.CharField(db_index=True, editable=False, max_length=64)),
                ("page_count", models.PositiveIntegerField(default=1, editable=False)),
                ("processing_status", models.CharField(choices=[("stored", "Stored"), ("queued", "Queued"), ("processing", "Processing"), ("review", "Review"), ("ready", "Ready"), ("failed", "Failed")], db_index=True, default="stored", max_length=16)),
                ("pinned", models.BooleanField(default=False)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="family.family")),
                ("owner_membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_documents", to="family.membership")),
            ],
            options={"ordering": ["-document_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="DocumentAccess",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("can_view", models.BooleanField(default=True)),
                ("can_manage", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_entries", to="documents.document")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="document_access_entries", to="family.membership")),
            ],
        ),
        migrations.CreateModel(
            name="DocumentLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("domain_type", models.CharField(choices=[("expense", "Expense"), ("pet", "Pet"), ("school", "School"), ("contract", "Contract"), ("event", "Event"), ("task", "Task"), ("other", "Other")], max_length=32)),
                ("object_id", models.UUIDField()),
                ("relationship", models.CharField(default="source", max_length=48)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="domain_links", to="documents.document")),
            ],
        ),
        migrations.AddIndex(model_name="document", index=models.Index(fields=["family", "sha256", "archived_at"], name="doc_family_hash_arch_idx")),
        migrations.AddIndex(model_name="document", index=models.Index(fields=["family", "visibility", "archived_at"], name="doc_family_vis_arch_idx")),
        migrations.AddConstraint(model_name="documentaccess", constraint=models.UniqueConstraint(fields=("document", "membership"), name="document_access_member_uniq")),
        migrations.AddConstraint(model_name="documentlink", constraint=models.UniqueConstraint(fields=("document", "domain_type", "object_id", "relationship"), name="document_domain_link_uniq")),
        migrations.AddIndex(model_name="documentlink", index=models.Index(fields=["domain_type", "object_id"], name="document_domain_obj_idx")),
    ]
