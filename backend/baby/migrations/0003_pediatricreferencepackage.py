import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("baby", "0002_babyprivatemedia"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PediatricReferencePackage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_key", models.CharField(max_length=64)),
                ("source_title", models.CharField(max_length=200)),
                ("source_version", models.CharField(max_length=96)),
                ("locale", models.CharField(default="de-DE", max_length=16)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("superseded", "Superseded")], db_index=True, default="draft", max_length=16)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("imported_at", models.DateTimeField()),
                ("checksum", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("reason", models.CharField(blank=True, max_length=240)),
                ("notes", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pediatric_reference_packages_created", to=settings.AUTH_USER_MODEL)),
                ("published_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pediatric_reference_packages_published", to=settings.AUTH_USER_MODEL)),
                ("superseded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supersedes", to="baby.pediatricreferencepackage")),
            ],
            options={
                "ordering": ["source_key", "locale", "-created_at"],
                "indexes": [models.Index(fields=["source_key", "locale", "status", "effective_from"], name="baby_ped_ref_lookup_idx")],
                "constraints": [models.UniqueConstraint(fields=("source_key", "source_version", "locale"), name="baby_ped_ref_source_version_unique")],
            },
        ),
    ]
