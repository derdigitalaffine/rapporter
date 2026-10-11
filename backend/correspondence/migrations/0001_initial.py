import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0001_initial"),
        ("family", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CorrespondenceReview",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("open", "Open"), ("reviewed", "Reviewed")], db_index=True, default="open", max_length=16)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="correspondence_reviews_created", to=settings.AUTH_USER_MODEL)),
                ("document", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="correspondence_review", to="documents.document")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="correspondence_reviews", to="family.family")),
                ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="correspondence_reviews_updated", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(model_name="correspondencereview", index=models.Index(fields=["family", "status", "updated_at"], name="corr_family_status_idx")),
    ]
