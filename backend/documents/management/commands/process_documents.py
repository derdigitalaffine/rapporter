import time

from django.core.management.base import BaseCommand

from documents.processing import claim_next_run
from documents.worker import process_claimed_run


class Command(BaseCommand):
    help = "Process durable local document extraction/OCR jobs."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep polling for due document jobs.")
        parser.add_argument("--sleep", type=float, default=2.0, help="Idle polling interval with --loop.")
        parser.add_argument("--max-jobs", type=int, default=0, help="Stop after N jobs (0 means unlimited).")

    def handle(self, *args, **options):
        processed = 0
        max_jobs = max(0, options["max_jobs"])
        while True:
            run = claim_next_run()
            if run is None:
                if not options["loop"]:
                    break
                time.sleep(max(0.25, options["sleep"]))
                continue

            process_claimed_run(run)
            processed += 1
            if max_jobs and processed >= max_jobs:
                break

        self.stdout.write(f"Processed {processed} document job(s).")
