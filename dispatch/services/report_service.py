from __future__ import annotations

import base64
from io import BytesIO

import matplotlib.pyplot as plt

from dispatch.models import DispatchResult, TimeSeriesPoint
from dispatch.services.constants import INTERVAL_HOURS


def build_weekly_report() -> dict:
    dispatch_results = list(DispatchResult.objects.order_by("timestamp"))
    time_series = list(TimeSeriesPoint.objects.order_by("timestamp"))

    if not dispatch_results:
        raise ValueError("No dispatch results found. Run python manage.py run_dispatch first.")

    if not time_series:
        raise ValueError("No time series data found. Run python manage.py seed_week_data first.")

    grid_spend_with_battery = sum(
        result.grid_import_kw * INTERVAL_HOURS * result.grid_price_eur_per_kwh
        for result in dispatch_results
    )

    grid_spend_without_battery = sum(
        max(point.load_kw - point.solar_kw, 0.0)
        * INTERVAL_HOURS
        * point.grid_price_eur_per_kwh
        for point in time_series
    )

    total_charged_kwh = sum(result.charged_kwh for result in dispatch_results)
    total_discharged_kwh = sum(result.discharged_kwh for result in dispatch_results)

    total_solar_kwh = sum(result.solar_kw * INTERVAL_HOURS for result in dispatch_results)
    curtailed_solar_kwh = sum(
        result.curtailed_solar_kw * INTERVAL_HOURS for result in dispatch_results
    )

    used_solar_kwh = total_solar_kwh - curtailed_solar_kwh

    solar_self_consumption_percent = (
        used_solar_kwh / total_solar_kwh * 100 if total_solar_kwh > 0 else 0.0
    )

    return {
        "grid_spend_with_battery": grid_spend_with_battery,
        "grid_spend_without_battery": grid_spend_without_battery,
        "saving": grid_spend_without_battery - grid_spend_with_battery,
        "total_charged_kwh": total_charged_kwh,
        "total_discharged_kwh": total_discharged_kwh,
        "solar_self_consumption_percent": solar_self_consumption_percent,
        "soc_chart_base64": build_soc_chart(dispatch_results),
    }


def build_soc_chart(dispatch_results: list[DispatchResult]) -> str:
    timestamps = [result.timestamp for result in dispatch_results]
    soc_values = [result.soc_kwh for result in dispatch_results]

    plt.figure(figsize=(12, 4))
    plt.plot(timestamps, soc_values)
    plt.title("Battery State of Charge Over Representative Week")
    plt.xlabel("Time")
    plt.ylabel("SoC (kWh)")
    plt.xticks(rotation=30)
    plt.tight_layout()

    buffer = BytesIO()
    plt.savefig(buffer, format="png")
    plt.close()

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")