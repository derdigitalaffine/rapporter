"""Small domain-consumer registry for the shared document worker.

The document core owns storage/OCR/queueing. Domain consumers may project a
completed or failed run into their canonical domain inside the same DB
transaction, but they must never start another worker or mutate canonical files.
"""

_CONSUMERS = {}


def register_processing_consumer(domain_type, relationship, callback):
    key = (str(domain_type), str(relationship))
    existing = _CONSUMERS.get(key)
    if existing is not None and existing is not callback:
        raise RuntimeError(f"Document processing consumer already registered for {key!r}")
    _CONSUMERS[key] = callback


def dispatch_processing_consumers(run):
    for link in run.document.domain_links.all().order_by("created_at"):
        callback = _CONSUMERS.get((str(link.domain_type), str(link.relationship)))
        if callback is not None:
            callback(run, link)
