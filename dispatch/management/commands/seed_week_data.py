from django.core.management.base import BaseCommand

from dispatch.models import DispatchResult, TimeSeriesPoint
from dispatch.services.data_generation import build_representative_week


class Command(BaseCommand):
    help = "Seed one representative week of 15-minute solar/load/price data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--synthetic-solar",
            action="store_true",
            help="Use synthetic solar instead of renewables.ninja.",
        )

    def handle(self, *args, **options):
        use_renewables_ninja = not options["synthetic_solar"]

        self.stdout.write("Clearing existing time series and dispatch results...")
        DispatchResult.objects.all().delete()
        TimeSeriesPoint.objects.all().delete()

        self.stdout.write("Building representative week data...")
        points = build_representative_week(
            use_renewables_ninja=use_renewables_ninja,
        )

        TimeSeriesPoint.objects.bulk_create(
            [
                TimeSeriesPoint(
                    timestamp=point.timestamp,
                    solar_kw=point.solar_kw,
                    load_kw=point.load_kw,
                    grid_price_eur_per_kwh=point.grid_price_eur_per_kwh,
                )
                for point in points
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {len(points)} 15-minute time series points.")
        )