def notification_payload(notification):
    return {
        "id": str(notification.id),
        "family": str(notification.family_id),
        "event_type": notification.event_type,
        "title": notification.title,
        "body": notification.body,
        "resource_url": notification.resource_url,
        "priority": notification.priority,
        "read": notification.read_at is not None,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }
