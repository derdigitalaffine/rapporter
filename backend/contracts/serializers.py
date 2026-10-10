from .access import can_manage_contract
from .services import contract_documents, derived_dates


def access_payload(entry):
    return {
        "membership": str(entry.membership_id),
        "can_view": entry.can_view,
        "can_manage": entry.can_manage,
    }


def contract_payload(contract, user):
    can_manage = can_manage_contract(user, contract)
    payload = {
        "id": str(contract.id),
        "family": str(contract.family_id),
        "title": contract.title,
        "category": contract.category,
        "provider": contract.provider,
        "contract_number": contract.contract_number,
        "customer_number": contract.customer_number,
        "start_date": contract.start_date.isoformat() if contract.start_date else None,
        "minimum_term_months": contract.minimum_term_months,
        "end_date": contract.end_date.isoformat() if contract.end_date else None,
        "cancellation_period_days": contract.cancellation_period_days,
        "renewal_rule": contract.renewal_rule,
        "amount": str(contract.amount) if contract.amount is not None else None,
        "billing_interval": contract.billing_interval,
        "status": contract.status,
        "notes": contract.notes,
        "visibility": contract.visibility,
        "owner_membership": str(contract.owner_membership_id),
        "archived_at": contract.archived_at.isoformat() if contract.archived_at else None,
        "created_at": contract.created_at.isoformat(),
        "updated_at": contract.updated_at.isoformat(),
        "derived_dates": derived_dates(contract),
        "documents": [
            {
                "id": str(document.id),
                "title": document.title,
                "processing_status": document.processing_status,
                "mime_type": document.mime_type,
                "file_url": f"/api/documents/{document.id}/file/",
            }
            for document in contract_documents(user, contract)
        ],
        "reminders": [
            {
                "id": str(reminder.id),
                "due_on": reminder.due_on.isoformat(),
                "label": reminder.label,
                "status": reminder.status,
                "confirmed_at": reminder.confirmed_at.isoformat(),
            }
            for reminder in contract.reminders.all()
        ],
        "can_manage": can_manage,
    }
    if can_manage:
        payload["access"] = [access_payload(entry) for entry in contract.access_entries.all()]
    return payload
