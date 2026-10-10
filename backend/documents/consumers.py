"""Small registration surface for domain consumers of completed document runs.

The document-processing core stays domain-agnostic. Feature apps register handlers
for their own ``DocumentLink.domain_type`` during AppConfig.ready(); workers then
publish processing state/results to those handlers without importing domain models.
"""

_CONSUMERS = {}


def register_document_consumer(domain_type, handler):
    existing = _CONSUMERS.get(domain_type)
    if existing is not None and existing is not handler:
        raise RuntimeError(f"Document consumer already registered for {domain_type}")
    _CONSUMERS[domain_type] = handler


def dispatch_document_consumers(run):
    """Dispatch one run snapshot to every linked, registered domain consumer."""
    for link in run.document.domain_links.all():
        handler = _CONSUMERS.get(link.domain_type)
        if handler is not None:
            handler(run, link)
