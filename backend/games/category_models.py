from django.db import models

from .models import QuizQuestion, TimestampedGameModel


QUIZ_CATEGORY_LABELS = {
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


class QuizQuestionCategory(TimestampedGameModel):
    question = models.OneToOneField(QuizQuestion, on_delete=models.CASCADE, related_name="category_meta")
    category = models.CharField(max_length=40, db_index=True)

    class Meta:
        ordering = ["category", "question_id"]
