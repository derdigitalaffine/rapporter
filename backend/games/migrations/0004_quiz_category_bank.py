import uuid

from django.db import migrations, models
import django.db.models.deletion

from games.quiz_bank_v1 import build_questions


CATEGORY_LABELS = {
    "books_words": {"de": "Bücher & Wörter", "en": "Books & Words"},
    "comics": {"de": "Comics", "en": "Comics"},
    "video_games": {"de": "Computerspiele", "en": "Video Games"},
    "the_2000s": {"de": "Die 2000er", "en": "The 2000s"},
    "outdoors": {"de": "Draußen im Grünen", "en": "Outdoors"},
    "food_drink": {"de": "Essen & Trinken", "en": "Food & Drink"},
    "faith_religion": {"de": "Glaube & Religion", "en": "Faith & Religion"},
    "lab": {"de": "Im Labor", "en": "In the Lab"},
    "movies": {"de": "Kinofilme", "en": "Movies"},
    "body_mind": {"de": "Körper & Geist", "en": "Body & Mind"},
    "art_culture": {"de": "Kunst & Kultur", "en": "Art & Culture"},
    "power_money": {"de": "Macht & Geld", "en": "Power & Money"},
    "media_entertainment": {"de": "Medien & Unterhaltung", "en": "Media & Entertainment"},
    "music_hits": {"de": "Musik & Hits", "en": "Music & Hits"},
    "world": {"de": "Rund um die Welt", "en": "Around the World"},
    "sports_leisure": {"de": "Sport & Freizeit", "en": "Sports & Leisure"},
    "tv_series": {"de": "TV-Serien", "en": "TV Series"},
    "technology": {"de": "Wunder der Technik", "en": "Technology"},
    "history": {"de": "Zeugen der Zeit", "en": "History"},
}


def seed_questions(apps, schema_editor):
    QuizQuestion = apps.get_model("games", "QuizQuestion")
    QuizQuestionCategory = apps.get_model("games", "QuizQuestionCategory")

    # Existing mixed seed rows remain available to historical rounds but are no
    # longer selected for new mixed matches. The categorized 500-question bank
    # becomes the canonical normal quiz pool.
    QuizQuestion.objects.filter(mode="mixed", active=True).update(active=False)

    questions = build_questions(CATEGORY_LABELS)
    created = []
    for payload in questions:
        category = payload.pop("category")
        question = QuizQuestion.objects.create(mode="mixed", active=True, **payload)
        created.append(QuizQuestionCategory(question_id=question.id, category=category))
    QuizQuestionCategory.objects.bulk_create(created, batch_size=100)


def unseed_questions(apps, schema_editor):
    QuizQuestion = apps.get_model("games", "QuizQuestion")
    QuizQuestionCategory = apps.get_model("games", "QuizQuestionCategory")
    ids = list(QuizQuestionCategory.objects.values_list("question_id", flat=True))
    QuizQuestion.objects.filter(id__in=ids).delete()
    QuizQuestion.objects.filter(mode="mixed").update(active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("games", "0003_quiz_connect_four"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuizQuestionCategory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.CharField(db_index=True, max_length=40)),
                ("question", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="category_meta", to="games.quizquestion")),
            ],
            options={"ordering": ["category", "question_id"]},
        ),
        migrations.RunPython(seed_questions, unseed_questions),
    ]
