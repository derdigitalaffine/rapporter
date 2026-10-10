from .extraction import ProcessingError, extract_document
from .processing import ClaimLost, fail_run, finish_run, renew_lease


def process_claimed_run(run):
    """Execute one already-claimed run without ever mutating its canonical file.

    Database connection lifecycle belongs to the long-running management loop,
    not this unit of work. Keeping this helper connection-neutral also makes it
    safe to call from an existing transaction. Long-running extraction renews
    the durable lease at page/OCR boundaries; a lost fencing token aborts
    publication immediately.

    Domain-consumer projection is part of ``finish_run``'s transaction. Keeping
    that call inside this try block means a consumer failure rolls the finish
    transaction back and follows the same durable retry policy instead of
    leaving a completed generic run with an unprojected domain object.
    """

    def heartbeat():
        if not renew_lease(run):
            raise ClaimLost()

    try:
        result = extract_document(run.document, heartbeat=heartbeat)
        heartbeat()
        return finish_run(run, result, needs_review=result.needs_review)
    except ClaimLost:
        return run.__class__.objects.get(pk=run.pk)
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
