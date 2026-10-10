"""Small domain-consumer registry for the shared document worker.

The document core owns storage/OCR/queueing. Domain consumers may project run
state into their canonical domain, but they must never start another worker,
mutate canonical files, or make generic document processing fail. Each domain is
responsible for its own review/fallback state when projection logic breaks.
"""

_CONSUMERS = {}


def register_processing_consumer(domain_type, relationship, callback):
    key = (str(domain_type), str(relationship))
    existing = _CONSUMERS.get(key)
    if existing is not None and existing is not callback:
        raise RuntimeError(f"Document processing consumer already registered for {key!r}")
    _CONSUMERS[key] = callback


def dispatch_processing_consumers(run):
    """Best-effort domain projection that cannot invalidate a generic run.

    Raw callback exceptions are deliberately not logged here: an exception may
    contain domain/file data. The domain callback should persist a redacted
    fallback state if it needs operator/user visibility. Returning failed keys
    keeps the boundary observable to callers/tests without coupling retry policy.
    """
    if run is None:
        return []
    failed = []
    for link in run.document.domain_links.all().order_by("created_at"):
        key = (str(link.domain_type), str(link.relationship))
        callback = _CONSUMERS.get(key)
        if callback is None:
            continue
        try:
            callback(run, link)
        except Exception:
            failed.append(key)
    return failed
