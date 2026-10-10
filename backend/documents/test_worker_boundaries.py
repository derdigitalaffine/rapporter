from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .extraction import ExtractionResult
from .worker import process_claimed_run


class DocumentWorkerBoundaryTests(SimpleTestCase):
    def test_generic_finish_failure_still_uses_durable_retry_policy(self):
        run = SimpleNamespace(document=object())
        result = ExtractionResult(text="ok", extractor="fixture", needs_review=False)
        retry = SimpleNamespace(status="retry")

        with (
            patch("documents.worker.renew_lease", return_value=True),
            patch("documents.worker.extract_document", return_value=result),
            patch("documents.worker.finish_run", side_effect=RuntimeError("db write failed")),
            patch("documents.worker.fail_run", return_value=retry) as fail,
            patch("documents.worker.dispatch_processing_consumers") as dispatch,
        ):
            final = process_claimed_run(run)

        self.assertIs(final, retry)
        fail.assert_called_once_with(
            run,
            error_code="processing_failed",
            safe_error="Dokumentverarbeitung ist unerwartet fehlgeschlagen.",
            retryable=True,
        )
        dispatch.assert_called_once_with(retry)

    def test_successful_generic_finish_is_published_after_finish_returns(self):
        run = SimpleNamespace(document=object())
        result = ExtractionResult(text="ok", extractor="fixture", needs_review=False)
        finished = SimpleNamespace(status="ready")
        calls = []

        def finish(*args, **kwargs):
            calls.append("finish")
            return finished

        def dispatch(final):
            calls.append("dispatch")
            self.assertIs(final, finished)

        with (
            patch("documents.worker.renew_lease", return_value=True),
            patch("documents.worker.extract_document", return_value=result),
            patch("documents.worker.finish_run", side_effect=finish),
            patch("documents.worker.dispatch_processing_consumers", side_effect=dispatch),
            patch("documents.worker.fail_run") as fail,
        ):
            final = process_claimed_run(run)

        self.assertIs(final, finished)
        self.assertEqual(calls, ["finish", "dispatch"])
        fail.assert_not_called()
