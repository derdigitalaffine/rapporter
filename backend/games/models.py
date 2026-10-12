import uuid

from django.db import models

from family.models import Family, Membership


class TimestampedGameModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class GameMatch(TimestampedGameModel):
    class GameType(models.TextChoices):
        RPS = "rps", "Rock paper scissors"
        BATTLESHIP = "battleship", "Battleship"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="game_matches")
    challenger = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="games_challenged")
    opponent = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="games_received")
    game_type = models.CharField(max_length=16, choices=GameType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    rps_round_count = models.PositiveSmallIntegerField(default=3)
    current_round = models.PositiveSmallIntegerField(default=1)
    current_turn = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="games_current_turn",
    )
    winner = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="games_won",
    )
    is_draw = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(challenger=models.F("opponent")),
                name="games_distinct_players",
            ),
            models.CheckConstraint(
                condition=models.Q(rps_round_count__gte=1, rps_round_count__lte=5),
                name="games_rps_round_count_1_5",
            ),
        ]
        indexes = [
            models.Index(fields=["family", "status", "updated_at"], name="games_family_status_idx"),
        ]

    def participant_ids(self):
        return {self.challenger_id, self.opponent_id}

    def opponent_for(self, membership):
        return self.opponent if membership.id == self.challenger_id else self.challenger


class RockPaperScissorsRound(TimestampedGameModel):
    class Choice(models.TextChoices):
        ROCK = "rock", "Rock"
        PAPER = "paper", "Paper"
        SCISSORS = "scissors", "Scissors"

    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="rps_rounds")
    number = models.PositiveSmallIntegerField()
    challenger_choice = models.CharField(max_length=8, choices=Choice.choices, blank=True)
    opponent_choice = models.CharField(max_length=8, choices=Choice.choices, blank=True)
    winner = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rps_rounds_won",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["match", "number"], name="games_rps_round_unique")]


class BattleshipBoard(TimestampedGameModel):
    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="battleship_boards")
    player = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="battleship_boards")
    ships = models.JSONField(default=list, blank=True)
    confirmed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["match", "player"], name="games_board_player_unique")]


class BattleshipShot(TimestampedGameModel):
    class Result(models.TextChoices):
        MISS = "miss", "Miss"
        HIT = "hit", "Hit"
        SUNK = "sunk", "Sunk"

    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="battleship_shots")
    shooter = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="battleship_shots_fired")
    target = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="battleship_shots_received")
    x = models.PositiveSmallIntegerField()
    y = models.PositiveSmallIntegerField()
    result = models.CharField(max_length=8, choices=Result.choices)
    ship_size = models.PositiveSmallIntegerField(null=True, blank=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["match", "target", "x", "y"], name="games_shot_coordinate_unique"),
            models.UniqueConstraint(fields=["match", "sequence"], name="games_shot_sequence_unique"),
            models.CheckConstraint(condition=models.Q(x__lte=9, y__lte=9), name="games_shot_inside_board"),
        ]
