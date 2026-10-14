# Generated for #617 Premium Fahrtenbuch Professional.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="journey",
            name="business_partner",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="journey",
            name="classified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="journey",
            name="destination",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="journey",
            name="detour_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="journey",
            name="legacy_record",
            field=models.BooleanField(default=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="journey",
            name="legacy_record",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="journey",
            name="note",
            field=models.CharField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="journey",
            name="review_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="journey",
            name="source",
            field=models.CharField(choices=[("tracked", "Tracked"), ("manual", "Manual")], default="tracked", max_length=16),
        ),
        migrations.AddField(
            model_name="journey",
            name="void_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="journey",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="journey",
            name="kind",
            field=models.CharField(choices=[("unclassified", "Unclassified"), ("private", "Private"), ("business", "Business"), ("commute", "Commute")], default="unclassified", max_length=16),
        ),
        migrations.AddIndex(
            model_name="journey",
            index=models.Index(fields=["driver", "kind", "started_at"], name="journey_drv_kind_start_idx"),
        ),
        migrations.AddIndex(
            model_name="journey",
            index=models.Index(fields=["vehicle", "started_at"], name="journey_vehicle_start_idx"),
        ),
        migrations.CreateModel(
            name="JourneyRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence", models.PositiveIntegerField()),
                ("event", models.CharField(choices=[("manual_created", "Manual created"), ("classified", "Classified"), ("corrected", "Corrected"), ("voided", "Voided")], max_length=24)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("before", models.JSONField(default=dict)),
                ("after", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="journey_revisions", to=settings.AUTH_USER_MODEL)),
                ("journey", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="vehicles.journey")),
            ],
            options={
                "ordering": ["journey_id", "sequence"],
                "constraints": [models.UniqueConstraint(fields=("journey", "sequence"), name="journey_revision_sequence_unique")],
            },
        ),
    ]
