import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("baby", "0003_pediatricreferencepackage"),
    ]

    operations = [
        migrations.CreateModel(
            name="PediatricPreventiveEventReference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source_key", models.CharField(max_length=64)),
                ("source_version", models.CharField(max_length=96)),
                ("source_checksum", models.CharField(blank=True, max_length=64)),
                ("locale", models.CharField(default="de-DE", max_length=16)),
                ("rule_key", models.CharField(max_length=64)),
                ("start_day", models.PositiveIntegerField()),
                ("end_day", models.PositiveIntegerField()),
                ("target_day", models.PositiveIntegerField()),
                ("baby", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="preventive_event_references", to="baby.babyprofile")),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pediatric_private_reference", to="family.familyevent")),
                ("reference_package", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="preventive_event_references", to="baby.pediatricreferencepackage")),
            ],
            options={
                "ordering": ["baby_id", "target_day", "rule_key"],
                "indexes": [models.Index(fields=["baby", "source_key", "source_version"], name="baby_ped_event_ref_idx")],
            },
        ),
    ]
