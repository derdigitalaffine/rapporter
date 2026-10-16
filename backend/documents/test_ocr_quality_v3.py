from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image

from .extraction import _candidate_score, _ocr_image, _tsv_page
from .quality import MAX_OCR_WORKING_DIMENSION, prepare_for_ocr


class DocumentOcrQualityV3Tests(SimpleTestCase):
    def _tsv(self, count, confidence, *, lines=1):
        return {
            "text": [f"W{i}" for i in range(count)],
            "conf": [str(confidence)] * count,
            "left": [i * 10 for i in range(count)],
            "top": [(i % max(1, lines)) * 20 for i in range(count)],
            "width": [8] * count,
            "height": [12] * count,
            "block_num": [1] * count,
            "par_num": [1] * count,
            "line_num": [(i % max(1, lines)) + 1 for i in range(count)],
        }

    def test_candidate_score_prefers_supported_dense_output_over_sparse_confidence(self):
        sparse = _tsv_page(self._tsv(2, 96, lines=1), 1, psm=6, language="deu+eng", width=900, height=1200)
        dense = _tsv_page(self._tsv(18, 88, lines=6), 1, psm=4, language="deu+eng", width=900, height=1200)
        self.assertGreater(_candidate_score(dense), _candidate_score(sparse))
        self.assertEqual(sparse["high_confidence_ratio"], 1.0)
        self.assertEqual(dense["line_count"], 6)

    def test_low_resolution_is_upscaled_only_on_bounded_ocr_working_copy(self):
        source = Image.new("RGB", (400, 800), "white")
        prepared, quality = prepare_for_ocr(source)
        self.assertEqual(source.size, (400, 800))
        self.assertGreater(prepared.width, source.width)
        self.assertGreater(prepared.height, source.height)
        self.assertLessEqual(max(prepared.size), MAX_OCR_WORKING_DIMENSION)
        metadata = quality["preprocessing"]
        self.assertGreater(metadata["upscale_factor"], 1.0)
        self.assertTrue(metadata["canonical_unchanged"])
        self.assertFalse(metadata["destructive_thresholding"])

    def test_weak_sparse_psm_uses_fallback_and_records_selected_workflow(self):
        prepared = Image.new("L", (900, 1200), 255)
        weak = self._tsv(2, 96, lines=1)
        strong = self._tsv(18, 88, lines=6)
        with patch(
            "documents.extraction.prepare_for_ocr",
            return_value=(prepared, {"preprocessing": {"workflow_version": 2}}),
        ), patch(
            "documents.extraction._run_tesseract",
            side_effect=[(weak, "deu+eng"), (strong, "deu+eng")],
        ):
            page = _ocr_image(Image.new("RGB", (900, 1200), "white"), 1, heartbeat=lambda: None)

        workflow = page["ocr_workflow"]
        self.assertTrue(workflow["fallback_used"])
        self.assertEqual(workflow["candidate_count"], 2)
        self.assertEqual(workflow["selected_psm"], 4)
        self.assertGreater(workflow["selected_score"], 0.72)
