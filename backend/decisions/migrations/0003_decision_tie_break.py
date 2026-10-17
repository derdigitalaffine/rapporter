import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("decisions", "0002_decision_modes_and_vote_values"),
        ("games", "0005_battleshipboard_player_user_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DecisionTieBreak",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("method", models.CharField(choices=[("random", "Random draw"), ("game", "Game duel")], max_length=12)),
                ("resolved_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("challenger_option", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="decisions.decisionoption")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="decision_tie_breaks_created", to=settings.AUTH_USER_MODEL)),
                ("decision", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="tie_break", to="decisions.decision")),
                ("game_match", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="decision_tie_break", to="games.gamematch")),
                ("opponent_option", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="decisions.decisionoption")),
                ("winner_option", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="decisions.decisionoption")),
            ],
        ),
        migrations.AddIndex(
            model_name="decisiontiebreak",
            index=models.Index(fields=["method", "resolved_at"], name="decision_tiebreak_state_idx"),
        ),
    ]
