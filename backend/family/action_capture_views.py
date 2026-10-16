import logging

from django.views.decorators.csrf import csrf_exempt

from .action_capture_context import rank_family_capture_rows
from .models import Family
from .unified_action_views import quick_capture as canonical_quick_capture


logger = logging.getLogger(__name__)


@csrf_exempt
def quick_capture(request):
    """Keep the canonical DRF capture endpoint intact while enriching GET suggestions."""
    response = canonical_quick_capture(request)
    if request.method != "GET" or response.status_code != 200:
        return response
    suggestions = response.data.get("suggestions") or []
    if not suggestions:
        return response

    # This compatibility wrapper receives Django's raw HttpRequest. The canonical
    # DRF endpoint above has already authenticated the actor and verified family
    # membership, so do not call DRF-only helpers (request.query_params) again.
    family_id = request.GET.get("family")
    family = Family.objects.filter(pk=family_id).first() if family_id else None
    if family is None:
        return response
    try:
        response.data["suggestions"] = rank_family_capture_rows(family=family, rows=suggestions)
    except Exception:
        logger.exception("Action Capture context enrichment failed for family %s", family.id)
    return response
