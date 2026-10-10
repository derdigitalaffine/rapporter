from django.urls import path

from .views import document_collection, document_detail, document_file, document_purge, document_restore

urlpatterns = [
    path("documents/", document_collection, name="document-collection"),
    path("documents/<uuid:document_id>/", document_detail, name="document-detail"),
    path("documents/<uuid:document_id>/file/", document_file, name="document-file"),
    path("documents/<uuid:document_id>/restore/", document_restore, name="document-restore"),
    path("documents/<uuid:document_id>/purge/", document_purge, name="document-purge"),
]
