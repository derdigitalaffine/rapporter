import logging

from .action_capture_context import rank_family_capture_rows
from .action_views import _family_membership
from .unified_action_views import quick_capture as canonical_quick_capture


logger = logging.getLogger(__name__)


def quick_capture(request):
    """Keep canonical capture available even when optional GET ranking fails."""
    response = canonical_quick_capture(request)
    if request.method != "GET" or response.status_code != 200:
        return response
    suggestions = response.data.get("suggestions") or []
    if not suggestions:
        return response

    family, _, error = _family_membership(request)
    if error is not None:
        return response
    try:
        response.data["suggestions"] = rank_family_capture_rows(family=family, rows=suggestions)
    except Exception:
        logger.exception("Action Capture context enrichment failed for family %s", family.id)
    return response
