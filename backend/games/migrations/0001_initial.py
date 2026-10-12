import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [("family", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="GameMatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("game_type", models.CharField(choices=[("rps", "Rock paper scissors"), ("battleship", "Battleship")], max_length=16)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("active", "Active"), ("finished", "Finished"), ("declined", "Declined"), ("cancelled", "Cancelled")], db_index=True, default="pending", max_length=16)),
                ("rps_round_count", models.PositiveSmallIntegerField(default=3)),
                ("current_round", models.PositiveSmallIntegerField(default=1)),
                ("is_draw", models.BooleanField(default=False)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("challenger", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="games_challenged", to="family.membership")),
                ("current_turn", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="games_current_turn", to="family.membership")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="game_matches", to="family.family")),
                ("opponent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="games_received", to="family.membership")),
                ("winner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="games_won", to="family.membership")),
            ],
            options={
                "ordering": ["-updated_at", "-created_at"],
                "indexes": [models.Index(fields=["family", "status", "updated_at"], name="games_family_status_idx")],
                "constraints": [
                    models.CheckConstraint(condition=~models.Q(challenger=models.F("opponent")), name="games_distinct_players"),
                    models.CheckConstraint(condition=models.Q(("rps_round_count__gte", 1), ("rps_round_count__lte", 5)), name="games_rps_round_count_1_5"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BattleshipBoard",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ships", models.JSONField(blank=True, default=list)),
                ("confirmed", models.BooleanField(default=False)),
                ("match", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="battleship_boards", to="games.gamematch")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="battleship_boards", to="family.membership")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("match", "player"), name="games_board_player_unique")]},
        ),
        migrations.CreateModel(
            name="RockPaperScissorsRound",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.PositiveSmallIntegerField()),
                ("challenger_choice", models.CharField(blank=True, choices=[("rock", "Rock"), ("paper", "Paper"), ("scissors", "Scissors")], max_length=8)),
                ("opponent_choice", models.CharField(blank=True, choices=[("rock", "Rock"), ("paper", "Paper"), ("scissors", "Scissors")], max_length=8)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("match", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rps_rounds", to="games.gamematch")),
                ("winner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rps_rounds_won", to="family.membership")),
            ],
            options={"ordering": ["number"], "constraints": [models.UniqueConstraint(fields=("match", "number"), name="games_rps_round_unique")]},
        ),
        migrations.CreateModel(
            name="BattleshipShot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("x", models.PositiveSmallIntegerField()),
                ("y", models.PositiveSmallIntegerField()),
                ("result", models.CharField(choices=[("miss", "Miss"), ("hit", "Hit"), ("sunk", "Sunk")], max_length=8)),
                ("ship_size", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sequence", models.PositiveIntegerField()),
                ("match", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="battleship_shots", to="games.gamematch")),
                ("shooter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="battleship_shots_fired", to="family.membership")),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="battleship_shots_received", to="family.membership")),
            ],
            options={
                "ordering": ["sequence"],
                "constraints": [
                    models.UniqueConstraint(fields=("match", "target", "x", "y"), name="games_shot_coordinate_unique"),
                    models.UniqueConstraint(fields=("match", "sequence"), name="games_shot_sequence_unique"),
                    models.CheckConstraint(condition=models.Q(("x__lte", 9), ("y__lte", 9)), name="games_shot_inside_board"),
                ],
            },
        ),
    ]
