import uuid

from django.conf import settings
from django.db import models

from family.models import Family, Membership, Task


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
        QUIZ = "quiz", "Quiz duel"
        CONNECT_FOUR = "connect_four", "Connect Four"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    class QuizMode(models.TextChoices):
        MIXED = "mixed", "Mixed knowledge"
        PHYSICS_EXPERT = "physics_expert", "Physics expert"
        CHEMISTRY_EXPERT = "chemistry_expert", "Chemistry expert"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="game_matches", null=True, blank=True)
    challenger = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="games_challenged", null=True, blank=True)
    opponent = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="games_received", null=True, blank=True)
    friendship = models.ForeignKey("messenger.Friendship", null=True, blank=True, on_delete=models.CASCADE, related_name="game_matches")
    challenger_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="personal_games_challenged")
    opponent_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="personal_games_received")
    current_turn_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="personal_games_turn")
    winner_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="personal_games_won")
    locale = models.CharField(max_length=8, default="de")
    game_type = models.CharField(max_length=24, choices=GameType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    rps_round_count = models.PositiveSmallIntegerField(default=3)
    quiz_round_count = models.PositiveSmallIntegerField(default=5)
    quiz_mode = models.CharField(max_length=24, choices=QuizMode.choices, default=QuizMode.MIXED)
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
            models.CheckConstraint(condition=models.Q(family__isnull=False, challenger__isnull=False, opponent__isnull=False, friendship__isnull=True, challenger_user__isnull=True, opponent_user__isnull=True, current_turn_user__isnull=True, winner_user__isnull=True) | models.Q(family__isnull=True, challenger__isnull=True, opponent__isnull=True, current_turn__isnull=True, winner__isnull=True, friendship__isnull=False, challenger_user__isnull=False, opponent_user__isnull=False), name="games_match_scope"),
            models.CheckConstraint(condition=~models.Q(challenger_user=models.F("opponent_user")), name="games_personal_distinct"),
            models.CheckConstraint(
                condition=~models.Q(challenger=models.F("opponent")),
                name="games_distinct_players",
            ),
            models.CheckConstraint(
                condition=models.Q(rps_round_count__gte=1, rps_round_count__lte=5),
                name="games_rps_round_count_1_5",
            ),
            models.CheckConstraint(
                condition=models.Q(quiz_round_count__gte=3, quiz_round_count__lte=7),
                name="games_quiz_round_count_3_7",
            ),
        ]
        indexes = [
            models.Index(fields=["family", "status", "updated_at"], name="games_family_status_idx"),
        ]

    def participant_ids(self):
        from .participants import player_id
        return {player_id(self, "challenger"), player_id(self, "opponent")}

    def opponent_for(self, membership):
        from .participants import player, player_id
        return player(self, "opponent") if membership.id == player_id(self, "challenger") else player(self, "challenger")


class GameTaskAssignment(TimestampedGameModel):
    class Rule(models.TextChoices):
        WINNER = "winner", "Winner takes task"
        LOSER = "loser", "Loser takes task"

    match = models.OneToOneField(GameMatch, on_delete=models.CASCADE, related_name="task_assignment")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="game_assignments")
    rule = models.CharField(max_length=16, choices=Rule.choices)
    expected_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    challenger_confirmed_at = models.DateTimeField()
    opponent_confirmed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidation_reason = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=["task", "created_at"], name="games_task_stake_idx")]


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
    winner_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="personal_rps_rounds_won")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["match", "number"], name="games_rps_round_unique")]


class BattleshipBoard(TimestampedGameModel):
    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="battleship_boards")
    player = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="battleship_boards", null=True, blank=True)
    player_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_battleship_boards", null=True, blank=True)
    ships = models.JSONField(default=list, blank=True)
    confirmed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["match", "player"], name="games_board_player_unique"), models.UniqueConstraint(fields=["match", "player_user"], name="games_board_user_unique"), models.CheckConstraint(condition=models.Q(player__isnull=False, player_user__isnull=True) | models.Q(player__isnull=True, player_user__isnull=False), name="games_board_player_scope")]


class BattleshipShot(TimestampedGameModel):
    class Result(models.TextChoices):
        MISS = "miss", "Miss"
        HIT = "hit", "Hit"
        SUNK = "sunk", "Sunk"

    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="battleship_shots")
    shooter = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="battleship_shots_fired", null=True, blank=True)
    shooter_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_battleship_shots_fired", null=True, blank=True)
    target = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="battleship_shots_received", null=True, blank=True)
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_battleship_shots_received", null=True, blank=True)
    x = models.PositiveSmallIntegerField()
    y = models.PositiveSmallIntegerField()
    result = models.CharField(max_length=8, choices=Result.choices)
    ship_size = models.PositiveSmallIntegerField(null=True, blank=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["match", "target", "x", "y"], name="games_shot_coordinate_unique"),
            models.UniqueConstraint(fields=["match", "target_user", "x", "y"], name="games_shot_user_coordinate"),
            models.CheckConstraint(condition=models.Q(shooter__isnull=False, target__isnull=False, shooter_user__isnull=True, target_user__isnull=True) | models.Q(shooter__isnull=True, target__isnull=True, shooter_user__isnull=False, target_user__isnull=False), name="games_shot_player_scope"),
            models.UniqueConstraint(fields=["match", "sequence"], name="games_shot_sequence_unique"),
            models.CheckConstraint(condition=models.Q(x__lte=9, y__lte=9), name="games_shot_inside_board"),
        ]


class QuizQuestion(TimestampedGameModel):
    mode = models.CharField(max_length=24, choices=GameMatch.QuizMode.choices, db_index=True)
    prompt_de = models.TextField()
    prompt_en = models.TextField()
    options_de = models.JSONField(default=list)
    options_en = models.JSONField(default=list)
    correct_index = models.PositiveSmallIntegerField()
    explanation_de = models.TextField(blank=True)
    explanation_en = models.TextField(blank=True)
    active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["mode", "created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(correct_index__lte=5), name="games_quiz_correct_index_lte_5"),
        ]


class QuizRound(TimestampedGameModel):
    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="quiz_rounds")
    number = models.PositiveSmallIntegerField()
    question = models.ForeignKey(QuizQuestion, on_delete=models.PROTECT, related_name="rounds")
    challenger_answer = models.PositiveSmallIntegerField(null=True, blank=True)
    opponent_answer = models.PositiveSmallIntegerField(null=True, blank=True)
    challenger_correct = models.BooleanField(null=True, blank=True)
    opponent_correct = models.BooleanField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["match", "number"], name="games_quiz_round_unique")]


class ConnectFourMove(TimestampedGameModel):
    match = models.ForeignKey(GameMatch, on_delete=models.CASCADE, related_name="connect_four_moves")
    player = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="connect_four_moves", null=True, blank=True)
    player_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_connect_four_moves", null=True, blank=True)
    column = models.PositiveSmallIntegerField()
    row = models.PositiveSmallIntegerField()
    sequence = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.CheckConstraint(condition=models.Q(player__isnull=False, player_user__isnull=True) | models.Q(player__isnull=True, player_user__isnull=False), name="games_connect4_player_scope"),
            models.UniqueConstraint(fields=["match", "sequence"], name="games_connect4_sequence_unique"),
            models.UniqueConstraint(fields=["match", "column", "row"], name="games_connect4_cell_unique"),
            models.CheckConstraint(condition=models.Q(column__lte=6, row__lte=5), name="games_connect4_inside_board"),
        ]
