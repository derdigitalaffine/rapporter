from collections import Counter

from django.test import TestCase

from .category_models import QUIZ_CATEGORY_LABELS, QuizQuestionCategory
from .models import GameMatch, QuizQuestion
from .quiz_bank_v1 import build_questions


class QuizCategoryBankTests(TestCase):
    def test_source_bank_is_exactly_500_original_categorized_questions(self):
        source = build_questions(QUIZ_CATEGORY_LABELS)
        self.assertEqual(len(source), 500)
        self.assertEqual({row["category"] for row in source}, set(QUIZ_CATEGORY_LABELS))
        counts = Counter(row["category"] for row in source)
        self.assertEqual(len(counts), 19)
        self.assertGreaterEqual(min(counts.values()), 24)
        self.assertLessEqual(max(counts.values()), 28)
        self.assertEqual(len({row["prompt_de"] for row in source}), 500)
        for row in source:
            self.assertEqual(len(row["options_de"]), 4)
            self.assertEqual(len(set(row["options_de"])), 4)
            self.assertEqual(len(row["options_en"]), 4)
            self.assertEqual(len(set(row["options_en"])), 4)
            self.assertIn(row["correct_index"], range(4))
            self.assertTrue(row["explanation_de"])
            self.assertTrue(row["explanation_en"])

    def test_database_uses_only_the_500_categorized_rows_for_new_mixed_quizzes(self):
        active = QuizQuestion.objects.filter(mode=GameMatch.QuizMode.MIXED, active=True)
        self.assertEqual(active.count(), 500)
        self.assertEqual(QuizQuestionCategory.objects.filter(question__in=active).count(), 500)
        self.assertEqual(set(QuizQuestionCategory.objects.filter(question__in=active).values_list("category", flat=True)), set(QUIZ_CATEGORY_LABELS))
        for question in active[:25]:
            meta = question.category_meta
            self.assertTrue(question.prompt_de.startswith(f"{QUIZ_CATEGORY_LABELS[meta.category]['de']} · "))
            self.assertTrue(question.prompt_en.startswith(f"{QUIZ_CATEGORY_LABELS[meta.category]['en']} · "))
