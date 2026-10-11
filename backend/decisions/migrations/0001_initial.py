import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0216_trip_participants"),
    ]

    operations = [
        migrations.CreateModel(
            name="Decision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("question", models.CharField(max_length=500)),
                ("mode", models.CharField(choices=[("single", "Single choice"), ("multiple", "Multiple choice")], default="single", max_length=12)),
                ("anonymous", models.BooleanField(default=False)),
                ("closes_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("context_bound", models.BooleanField(db_index=True, default=False, editable=False)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="family_decisions_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="decisions", to="family.family")),
            ],
            options={"ordering": ["-created_at", "id"]},
        ),
        migrations.CreateModel(
            name="DecisionOption",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=240)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("decision", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="decisions.decision")),
            ],
            options={"ordering": ["position", "created_at", "id"]},
        ),
        migrations.CreateModel(
            name="DecisionVote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("decision", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="votes", to="decisions.decision")),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="decision_votes", to="family.membership")),
                ("option", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="votes", to="decisions.decisionoption")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="decision",
            index=models.Index(fields=["family", "closed_at", "created_at"], name="decision_family_state_idx"),
        ),
        migrations.AddConstraint(
            model_name="decisionoption",
            constraint=models.UniqueConstraint(fields=("decision", "position"), name="decision_option_position_uq"),
        ),
        migrations.AddConstraint(
            model_name="decisionvote",
            constraint=models.UniqueConstraint(fields=("decision", "option", "member"), name="decision_vote_member_option_uq"),
        ),
        migrations.AddIndex(
            model_name="decisionvote",
            index=models.Index(fields=["decision", "member"], name="decision_vote_member_idx"),
        ),
    ]
