from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from dispatch.models import TimeSeriesPoint
from dispatch.services.constants import (
    BATTERY_POWER_LIMIT_KW,
    SOC_MAX_KWH,
    SOC_MIN_KWH,
)
from dispatch.services.dispatch_policy import run_dispatch


class DispatchPolicyTests(TestCase):
    def setUp(self):
        self.tz = ZoneInfo("Asia/Nicosia")

    def create_point(
        self,
        hour: int,
        solar_kw: float,
        load_kw: float,
        price: float = 0.30,
    ) -> TimeSeriesPoint:
        return TimeSeriesPoint.objects.create(
            timestamp=datetime(2025, 7, 7, hour, 0, tzinfo=self.tz),
            solar_kw=solar_kw,
            load_kw=load_kw,
            grid_price_eur_per_kwh=price,
        )

    def test_soc_never_goes_below_minimum(self):
        self.create_point(hour=12, solar_kw=0.0, load_kw=300.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MIN_KWH)

        self.assertGreaterEqual(results[0].soc_kwh, SOC_MIN_KWH)

    def test_soc_never_goes_above_maximum(self):
        self.create_point(hour=12, solar_kw=500.0, load_kw=0.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MAX_KWH)

        self.assertLessEqual(results[0].soc_kwh, SOC_MAX_KWH)

    def test_battery_power_limit_is_respected_when_charging(self):
        self.create_point(hour=12, solar_kw=500.0, load_kw=0.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MIN_KWH)

        self.assertLessEqual(abs(results[0].battery_power_kw), BATTERY_POWER_LIMIT_KW)

    def test_battery_power_limit_is_respected_when_discharging(self):
        self.create_point(hour=12, solar_kw=0.0, load_kw=500.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MAX_KWH)

        self.assertLessEqual(abs(results[0].battery_power_kw), BATTERY_POWER_LIMIT_KW)

    def test_surplus_solar_charges_battery_before_curtailment(self):
        self.create_point(hour=12, solar_kw=150.0, load_kw=50.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MIN_KWH)

        self.assertLess(results[0].battery_power_kw, 0.0)
        self.assertGreater(results[0].charged_kwh, 0.0)

    def test_no_grid_export_occurs(self):
        self.create_point(hour=12, solar_kw=500.0, load_kw=0.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MAX_KWH)

        self.assertGreaterEqual(results[0].grid_import_kw, 0.0)
        self.assertGreaterEqual(results[0].curtailed_solar_kw, 0.0)

    def test_battery_discharges_during_day_rate(self):
        self.create_point(hour=14, solar_kw=0.0, load_kw=100.0, price=0.30)

        results = run_dispatch(initial_soc_kwh=SOC_MAX_KWH)

        self.assertGreater(results[0].battery_power_kw, 0.0)
        self.assertGreater(results[0].discharged_kwh, 0.0)

    def test_battery_does_not_discharge_during_night_rate(self):
        self.create_point(hour=2, solar_kw=0.0, load_kw=100.0, price=0.15)

        results = run_dispatch(initial_soc_kwh=SOC_MAX_KWH)

        self.assertEqual(results[0].battery_power_kw, 0.0)
        self.assertEqual(results[0].discharged_kwh, 0.0)
        self.assertGreater(results[0].grid_import_kw, 0.0)