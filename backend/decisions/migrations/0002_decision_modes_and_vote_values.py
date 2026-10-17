from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("decisions", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="decision",
            name="mode",
            field=models.CharField(
                choices=[
                    ("single", "Single choice"),
                    ("multiple", "Multiple choice"),
                    ("ranking", "Ranking"),
                    ("rating", "Rating"),
                ],
                default="single",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="decisionvote",
            name="rank",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="decisionvote",
            name="score",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="decisionvote",
            constraint=models.CheckConstraint(
                condition=models.Q(("rank__isnull", True), ("rank__gte", 1), _connector="OR"),
                name="decision_vote_rank_positive_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="decisionvote",
            constraint=models.CheckConstraint(
                condition=models.Q(("score__isnull", True), ("score__range", (1, 5)), _connector="OR"),
                name="decision_vote_score_range_ck",
            ),
        ),
    ]
