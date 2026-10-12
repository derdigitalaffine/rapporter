from django.urls import path

from .product_analytics_views import product_analytics_event

urlpatterns = [
    path("analytics/product-event/", product_analytics_event, name="product_analytics_event"),
]
