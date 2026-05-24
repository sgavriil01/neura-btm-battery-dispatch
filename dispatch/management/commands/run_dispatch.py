from django.core.management.base import BaseCommand

from dispatch.models import TimeSeriesPoint
from dispatch.services.dispatch_policy import run_and_save_dispatch


class Command(BaseCommand):
    help = "Run greedy battery dispatch over the seeded weekly data."

    def handle(self, *args, **options):
        if not TimeSeriesPoint.objects.exists():
            self.stdout.write(
                self.style.ERROR(
                    "No time series data found. Run: python manage.py seed_week_data first."
                )
            )
            return

        results = run_and_save_dispatch()

        self.stdout.write(
            self.style.SUCCESS(f"Saved {len(results)} dispatch result points.")
        )