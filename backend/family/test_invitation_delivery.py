from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from mailing.models import TransactionalEmail

from .invitation_delivery import invitation_delivery_summary
from .invitation_service import issue_invitation
from .models import Family, Membership


class InvitationDeliveryProjectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="delivery-owner",
            email="delivery-owner@example.test",
            password="test-password-123",
        )
        self.family = Family.objects.create(name="Delivery Family", slug="delivery-family")
        Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )

    def test_resend_keeps_previous_success_as_last_sent_at(self):
        invite, _token = issue_invitation(
            family=self.family,
            invited_by=self.owner,
            role=Membership.Role.GUEST,
            email="guest@example.test",
        )
        first_mail = TransactionalEmail.objects.get(
            reference_type="family.invitation",
            reference_id__startswith=f"{invite.pk}:",
        )
        sent_at = timezone.now()
        first_mail.status = TransactionalEmail.Status.SENT
        first_mail.sent_at = sent_at
        first_mail.save(update_fields=["status", "sent_at", "updated_at"])

        resent, _new_token = issue_invitation(
            family=self.family,
            invited_by=self.owner,
            role=Membership.Role.GUEST,
            email="guest@example.test",
        )
        summary = invitation_delivery_summary(resent)

        self.assertEqual(summary["delivery_status"], "preparing")
        self.assertEqual(summary["last_sent_at"], sent_at)
        self.assertEqual(
            TransactionalEmail.objects.filter(
                reference_type="family.invitation",
                reference_id__startswith=f"{invite.pk}:",
            ).count(),
            2,
        )
