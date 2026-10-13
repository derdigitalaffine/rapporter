from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from family.models import Membership, UserProfile

from .child_identity_service import child_profile, require_child_guardian
from .models import PregnancyBaby
from .views import _serialize_baby


User = get_user_model()


class ChildProfileInput(serializers.Serializer):
    display_name = serializers.CharField(max_length=80, trim_whitespace=True, required=False)
    birth_date = serializers.DateField(required=False)

    def validate_display_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name must not be empty.")
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide display_name or birth_date.")
        return attrs


def _require_child_confirmation(request, baby):
    if request.data.get("confirm") != "DELETE_CHILD":
        raise ValidationError({"confirm": "Send DELETE_CHILD to remove this child from the family."})
    if str(request.data.get("confirm_name") or "").strip() != baby.display_name:
        raise ValidationError({"confirm_name": "Repeat the current child name exactly."})


@api_view(["PATCH", "DELETE"])
def baby_profile_detail(request, baby_id):
    with transaction.atomic():
        baby = child_profile(baby_id, for_update=True)
        require_child_guardian(request.user, baby, manage=True)

        if request.method == "PATCH":
            serializer = ChildProfileInput(data=request.data)
            serializer.is_valid(raise_exception=True)
            display_name = serializer.validated_data.get("display_name")
            birth_date = serializer.validated_data.get("birth_date")
            update_fields = ["updated_at"]
            if display_name is not None:
                baby.display_name = display_name
                update_fields.append("display_name")
                if baby.membership_id:
                    Membership.objects.filter(pk=baby.membership_id).update(display_name=display_name)
                if baby.source_pregnancy_baby_id:
                    PregnancyBaby.objects.filter(pk=baby.source_pregnancy_baby_id).update(display_name=display_name)
            if birth_date is not None:
                baby.birth_date = birth_date
                update_fields.append("birth_date")
                if baby.membership_id:
                    profile, _ = UserProfile.objects.get_or_create(user_id=baby.membership.user_id)
                    profile.birth_year = birth_date.year
                    profile.birth_month = birth_date.month
                    profile.birth_day = birth_date.day
                    profile.save(update_fields=["birth_year", "birth_month", "birth_day", "updated_at"])
            baby.save(update_fields=update_fields)
            baby.refresh_from_db()
            return Response(_serialize_baby(baby))

        _require_child_confirmation(request, baby)
        membership = baby.membership
        child_user = membership.user if membership else None
        baby.delete()
        if membership:
            try:
                membership.delete()
            except ProtectedError as exc:
                raise ValidationError({"detail": "Child cannot be removed while protected family data still references the membership."}) from exc

        # A managed child starts as a technical user with an unusable password. If
        # this was its only family membership, remove that otherwise-orphaned
        # technical identity. Activated or reused user accounts are deliberately
        # retained; deleting Pregnancy/Baby data is never an account deletion.
        if child_user and child_user.username.startswith("child-") and not child_user.has_usable_password():
            if not Membership.objects.filter(user_id=child_user.pk).exists():
                User.objects.filter(pk=child_user.pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)