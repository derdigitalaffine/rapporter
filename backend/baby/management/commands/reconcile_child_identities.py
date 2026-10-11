from django.core.management.base import BaseCommand

from baby.child_identity_service import reconcile_orphan_child_identities


class Command(BaseCommand):
    help = "Report or reconcile legacy BabyProfile rows that do not yet have a canonical child identity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create canonical User/Membership/UserProfile identities for unambiguous rows.",
        )

    def handle(self, *args, **options):
        result = reconcile_orphan_child_identities(apply=bool(options["apply"]))
        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(f"{mode}: {len(result['reconciled'])} unambiguous child profile(s)")
        for baby_id in result["reconciled"]:
            self.stdout.write(f"  reconcile {baby_id}")
        if result["review"]:
            self.stdout.write(self.style.WARNING(f"REVIEW REQUIRED: {len(result['review'])} ambiguous profile(s)"))
            for baby_id in result["review"]:
                self.stdout.write(f"  review {baby_id}")
