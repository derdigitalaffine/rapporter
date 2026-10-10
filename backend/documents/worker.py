from django.db import close_old_connections

from .extraction import ProcessingError, extract_document
from .processing import fail_run, finish_run


def process_claimed_run(run):
    """Execute one already-claimed run without ever mutating its canonical file."""
    close_old_connections()
    try:
        try:
            result = extract_document(run.document)
        except ProcessingError as exc:
            return fail_run(
                run,
                error_code=exc.code,
                safe_error=exc.safe_message,
                retryable=exc.retryable,
            )
        except Exception:
            # Raw exception strings can contain file contents, paths or library
            # details. Persist only a stable redacted category for operators.
            return fail_run(
                run,
                error_code="processing_failed",
                safe_error="Dokumentverarbeitung ist unerwartet fehlgeschlagen.",
                retryable=True,
            )
        return finish_run(run, result, needs_review=result.needs_review)
    finally:
        close_old_connections()
