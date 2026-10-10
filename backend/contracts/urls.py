from django.urls import path

from .views import (
    contract_action,
    contract_collection,
    contract_detail,
    contract_document_collection,
    contract_document_detail,
    contract_prefill,
)

urlpatterns = [
    path("contracts/", contract_collection, name="contract-collection"),
    path("contracts/prefill/", contract_prefill, name="contract-prefill"),
    path("contracts/<uuid:contract_id>/", contract_detail, name="contract-detail"),
    path("contracts/<uuid:contract_id>/documents/", contract_document_collection, name="contract-document-collection"),
    path("contracts/<uuid:contract_id>/documents/<uuid:document_id>/", contract_document_detail, name="contract-document-detail"),
    path("contracts/<uuid:contract_id>/actions/", contract_action, name="contract-action"),
]
