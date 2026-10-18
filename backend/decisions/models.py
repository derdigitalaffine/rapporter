from django.conf import settings
from django.db import models
from django.utils import timezone

from family.models import Family, Membership, TimestampedModel


class Decision(TimestampedModel):
    class Mode(models.TextChoices):
        SINGLE = "single", "Single choice"
        MULTIPLE = "multiple", "Multiple choice"
        RANKING = "ranking", "Ranking"
        RATING = "rating", "Rating"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="decisions")
    question = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="family_decisions_created",
    )
    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.SINGLE)
    anonymous = models.BooleanField(default=False)
    closes_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    context_bound = models.BooleanField(default=False, editable=False, db_index=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["family", "closed_at", "created_at"], name="decision_family_state_idx")]

    @property
    def is_open(self):
        if self.closed_at is not None:
            return False
        return self.closes_at is None or self.closes_at > timezone.now()


class DecisionOption(TimestampedModel):
    decision = models.ForeignKey(Decision, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=240)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["decision", "position"], name="decision_option_position_uq"),
        ]


class DecisionVote(TimestampedModel):
    decision = models.ForeignKey(Decision, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(DecisionOption, on_delete=models.CASCADE, related_name="votes")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="decision_votes")
    rank = models.PositiveSmallIntegerField(null=True, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["decision", "option", "member"],
                name="decision_vote_member_option_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(rank__isnull=True) | models.Q(rank__gte=1),
                name="decision_vote_rank_positive_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(score__isnull=True) | models.Q(score__range=(1, 5)),
                name="decision_vote_score_range_ck",
            ),
        ]
        indexes = [models.Index(fields=["decision", "member"], name="decision_vote_member_idx")]


class DecisionTieBreak(TimestampedModel):
    class Method(models.TextChoices):
        RANDOM = "random", "Random draw"
        GAME = "game", "Game duel"

    decision = models.OneToOneField(Decision, on_delete=models.CASCADE, related_name="tie_break")
    method = models.CharField(max_length=12, choices=Method.choices)
    winner_option = models.ForeignKey(
        DecisionOption,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    game_match = models.OneToOneField(
        "games.GameMatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decision_tie_break",
    )
    challenger_option = models.ForeignKey(
        DecisionOption,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    opponent_option = models.ForeignKey(
        DecisionOption,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decision_tie_breaks_created",
    )
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["method", "resolved_at"], name="decision_tiebreak_state_idx")]
