from __future__ import annotations

from dataclasses import dataclass

from dispatch.models import DispatchResult, TimeSeriesPoint
from dispatch.services.constants import (
    BATTERY_POWER_LIMIT_KW,
    CHARGE_EFFICIENCY,
    DISCHARGE_EFFICIENCY,
    INTERVAL_HOURS,
    SOC_MAX_KWH,
    SOC_MIN_KWH,
)


@dataclass(frozen=True)
class DispatchStep:
    timestamp: object
    solar_kw: float
    load_kw: float
    grid_price_eur_per_kwh: float
    battery_power_kw: float
    soc_kwh: float
    grid_import_kw: float
    curtailed_solar_kw: float
    charged_kwh: float
    discharged_kwh: float


def run_dispatch(initial_soc_kwh: float = SOC_MIN_KWH) -> list[DispatchStep]:
    """
    Greedy battery policy:
    1. Solar covers load first.
    2. Surplus solar charges the battery.
    3. During day-rate hours, battery discharges to cover remaining load.
    4. Remaining demand comes from the grid.
    5. No grid export is allowed.
    """
    points = list(TimeSeriesPoint.objects.order_by("timestamp"))

    soc_kwh = initial_soc_kwh
    results: list[DispatchStep] = []

    for point in points:
        solar_kw = point.solar_kw
        load_kw = point.load_kw
        price = point.grid_price_eur_per_kwh

        solar_to_load_kw = min(solar_kw, load_kw)
        remaining_load_kw = load_kw - solar_to_load_kw
        surplus_solar_kw = solar_kw - solar_to_load_kw

        battery_power_kw = 0.0
        grid_import_kw = 0.0
        curtailed_solar_kw = 0.0
        charged_kwh = 0.0
        discharged_kwh = 0.0

        # Charge from surplus solar.
        if surplus_solar_kw > 0:
            available_capacity_kwh = SOC_MAX_KWH - soc_kwh
            max_charge_from_capacity_kw = available_capacity_kwh / (
                INTERVAL_HOURS * CHARGE_EFFICIENCY
            )

            charge_kw = min(
                surplus_solar_kw,
                BATTERY_POWER_LIMIT_KW,
                max_charge_from_capacity_kw,
            )

            charged_kwh = charge_kw * INTERVAL_HOURS
            soc_kwh += charged_kwh * CHARGE_EFFICIENCY
            battery_power_kw = -charge_kw

            curtailed_solar_kw = max(surplus_solar_kw - charge_kw, 0.0)

        # Discharge only during expensive/day-rate hours.
        elif remaining_load_kw > 0 and is_day_rate(price):
            available_energy_kwh = soc_kwh - SOC_MIN_KWH
            max_discharge_from_soc_kw = (
                available_energy_kwh * DISCHARGE_EFFICIENCY
            ) / INTERVAL_HOURS

            discharge_kw = min(
                remaining_load_kw,
                BATTERY_POWER_LIMIT_KW,
                max_discharge_from_soc_kw,
            )

            discharged_kwh = discharge_kw * INTERVAL_HOURS
            soc_kwh -= discharged_kwh / DISCHARGE_EFFICIENCY
            battery_power_kw = discharge_kw

            grid_import_kw = max(remaining_load_kw - discharge_kw, 0.0)

        else:
            grid_import_kw = max(remaining_load_kw, 0.0)

        soc_kwh = min(max(soc_kwh, SOC_MIN_KWH), SOC_MAX_KWH)

        results.append(
            DispatchStep(
                timestamp=point.timestamp,
                solar_kw=solar_kw,
                load_kw=load_kw,
                grid_price_eur_per_kwh=price,
                battery_power_kw=battery_power_kw,
                soc_kwh=soc_kwh,
                grid_import_kw=grid_import_kw,
                curtailed_solar_kw=curtailed_solar_kw,
                charged_kwh=charged_kwh,
                discharged_kwh=discharged_kwh,
            )
        )

    return results


def save_dispatch_results(results: list[DispatchStep]) -> None:
    DispatchResult.objects.all().delete()

    DispatchResult.objects.bulk_create(
        [
            DispatchResult(
                timestamp=result.timestamp,
                solar_kw=result.solar_kw,
                load_kw=result.load_kw,
                grid_price_eur_per_kwh=result.grid_price_eur_per_kwh,
                battery_power_kw=result.battery_power_kw,
                soc_kwh=result.soc_kwh,
                grid_import_kw=result.grid_import_kw,
                curtailed_solar_kw=result.curtailed_solar_kw,
                charged_kwh=result.charged_kwh,
                discharged_kwh=result.discharged_kwh,
            )
            for result in results
        ]
    )


def run_and_save_dispatch() -> list[DispatchStep]:
    results = run_dispatch()
    save_dispatch_results(results)
    return results


def is_day_rate(price: float) -> bool:
    return price >= 0.30