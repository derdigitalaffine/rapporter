from django.http import Http404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .access import active_membership
from .search import search_documents, search_result_payload


@api_view(["GET"])
def document_search(request):
    family_id = request.query_params.get("family")
    if not family_id:
        return Response({"detail": "family is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not active_membership(request.user, family_id):
        raise Http404
    documents, query_text = search_documents(request.user, family_id, request.query_params)
    results = [search_result_payload(document, request.user, query_text) for document in documents]
    return Response({"count": len(results), "results": results})
