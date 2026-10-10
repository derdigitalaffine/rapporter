from .access import can_manage_document


def access_payload(entry):
    return {
        "membership": str(entry.membership_id),
        "can_view": entry.can_view,
        "can_manage": entry.can_manage,
    }


def link_payload(link):
    return {
        "id": str(link.id),
        "domain_type": link.domain_type,
        "object_id": str(link.object_id),
        "relationship": link.relationship,
    }


def document_payload(document, user):
    payload = {
        "id": str(document.id),
        "family": str(document.family_id),
        "kind": document.kind,
        "title": document.title,
        "document_date": document.document_date.isoformat() if document.document_date else None,
        "correspondent": document.correspondent,
        "visibility": document.visibility,
        "owner_membership": str(document.owner_membership_id),
        "mime_type": document.mime_type,
        "size": document.size,
        "sha256": document.sha256,
        "page_count": document.page_count,
        "processing_status": document.processing_status,
        "pinned": document.pinned,
        "archived_at": document.archived_at.isoformat() if document.archived_at else None,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "file_url": f"/api/documents/{document.id}/file/",
        "links": [link_payload(link) for link in document.domain_links.all()],
        "can_manage": can_manage_document(user, document),
    }
    if payload["can_manage"]:
        payload["access"] = [access_payload(entry) for entry in document.access_entries.all()]
    return payload
