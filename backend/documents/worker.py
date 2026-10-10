from .consumers import dispatch_processing_consumers
from .extraction import ProcessingError, extract_document
from .processing import ClaimLost, fail_run, finish_run, renew_lease


def _publish(final):
    if final is not None:
        dispatch_processing_consumers(final)
    return final


def process_claimed_run(run):
    """Execute one already-claimed run without ever mutating its canonical file.

    Generic run state commits first. Domain consumers run afterwards and are
    best-effort projections, so an Expense parser bug cannot turn successful OCR
    into a retry or duplicate CPU work. A domain object deleted during OCR is a
    normal form of claim loss and never crashes the long-running worker.
    """

    def heartbeat():
        if not renew_lease(run):
            raise ClaimLost()

    try:
        result = extract_document(run.document, heartbeat=heartbeat)
        heartbeat()
    except ClaimLost:
        return run.__class__.objects.filter(pk=run.pk).first()
    except ProcessingError as exc:
        return _publish(
            fail_run(
                run,
                error_code=exc.code,
                safe_error=exc.safe_message,
                retryable=exc.retryable,
            )
        )
    except Exception:
        # Raw exception strings can contain file contents, paths or library
        # details. Persist only a stable redacted category for operators.
        return _publish(
            fail_run(
                run,
                error_code="processing_failed",
                safe_error="Dokumentverarbeitung ist unerwartet fehlgeschlagen.",
                retryable=True,
            )
        )

    return _publish(finish_run(run, result, needs_review=result.needs_review))
