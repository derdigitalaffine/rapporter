from django.urls import path

from .views import entitlement_snapshot


urlpatterns = [
    path("entitlements/", entitlement_snapshot, name="entitlement_snapshot"),
]
