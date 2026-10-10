from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from family.models import Family

from .media_models import BabyPrivateMedia
from .media_service import delete_private_media, get_private_media_for_user, save_private_media
from .models import BabyProfile, PregnancyJourney


def _family(request):
    value=request.data.get("family") or request.query_params.get("family")
    try:
        family=Family.objects.filter(pk=value,status=Family.Status.ACTIVE,memberships__user=request.user).distinct().first()
    except (ValueError,DjangoValidationError):
        family=None
    if not family:
        raise NotFound("Family not found.")
    return family


@api_view(["POST"])
def private_media_upload(request):
    family=_family(request)
    upload=request.FILES.get("file")
    if not upload:
        raise ValidationError({"file":"Choose a file."})
    scope=request.data.get("scope")
    pregnancy=None;baby=None
    if scope==BabyPrivateMedia.Scope.PREGNANCY:
        pregnancy=PregnancyJourney.objects.filter(pk=request.data.get("pregnancy"),family=family).first()
        if not pregnancy:
            raise ValidationError({"pregnancy":"Pregnancy not found."})
    elif scope==BabyPrivateMedia.Scope.DEVELOPMENT:
        baby=BabyProfile.objects.filter(pk=request.data.get("baby"),family=family,active=True).first()
        if not baby:
            raise ValidationError({"baby":"Baby profile not found."})
    row=save_private_media(user=request.user,family=family,upload=upload,scope=scope,pregnancy=pregnancy,baby=baby)
    return Response({
        "id":str(row.id),"scope":row.scope,"content_type":row.content_type,"size_bytes":row.size_bytes,
        "url":f"/api/baby/media/{row.id}/","metadata_stripped":row.content_type=="image/webp",
    },status=201)


@api_view(["GET","DELETE"])
def private_media_detail(request,media_id):
    if request.method=="DELETE":
        delete_private_media(user=request.user,media_id=media_id)
        return Response(status=204)
    row,path=get_private_media_for_user(user=request.user,media_id=media_id)
    response=FileResponse(path.open("rb"),content_type=row.content_type)
    response["Content-Disposition"]="inline"
    response["X-Content-Type-Options"]="nosniff"
    return response
