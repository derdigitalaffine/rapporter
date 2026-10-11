import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .matomo_product import ProductAnalyticsError, ProductAnalyticsSchemaError, dispatch_product_event

logger = logging.getLogger("telemetry")


@api_view(["POST"])
def product_analytics_event(request):
    try:
        sent = dispatch_product_event(request.data)
    except ProductAnalyticsSchemaError as exc:
        return Response({"code": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except ProductAnalyticsError as exc:
        logger.warning("matomo_product_event_failed error_class=%s", exc.__class__.__name__)
        # Analytics is optional. A remote outage or deployment mistake must not
        # become a product failure or expose Matomo details to the browser.
        return Response({"accepted": False}, status=status.HTTP_202_ACCEPTED)

    if not sent:
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response({"accepted": True}, status=status.HTTP_202_ACCEPTED)
