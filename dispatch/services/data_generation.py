from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv

from dispatch.services.constants import (
    DAY_PRICE_EUR_PER_KWH,
    NIGHT_PRICE_EUR_PER_KWH,
)


@dataclass(frozen=True)
class WeekDataPoint:
    timestamp: datetime
    solar_kw: float
    load_kw: float
    grid_price_eur_per_kwh: float


LIMASSOL_LAT = 34.7071
LIMASSOL_LON = 33.0226
SYSTEM_CAPACITY_KW = 200.0
TIMEZONE = ZoneInfo("Asia/Nicosia")


def build_representative_week(
    start: datetime | None = None,
    use_renewables_ninja: bool = True,
) -> list[WeekDataPoint]:
    """
    Builds one representative 15-minute week of solar, hotel load and grid price data.

    renewables.ninja returns hourly PV data, so we interpolate it to 15-minute intervals.
    If no API token is available, we fall back to a documented synthetic solar curve so
    the project remains runnable for reviewers.
    """
    load_dotenv()

    if start is None:
        start = datetime(2025, 7, 7, 0, 0, tzinfo=TIMEZONE)

    timestamps = pd.date_range(start=start, periods=7 * 24 * 4, freq="15min")

    solar_series = (
        fetch_renewables_ninja_solar_kw(timestamps)
        if use_renewables_ninja
        else None
    )

    if solar_series is None:
        solar_series = generate_synthetic_solar_kw(timestamps)

    points: list[WeekDataPoint] = []

    raw_load_values = [generate_hotel_load_kw(ts.to_pydatetime()) for ts in timestamps]
    peak_load = max(raw_load_values)
    scale_factor = 200.0 / peak_load

    for ts, raw_load in zip(timestamps, raw_load_values):
        timestamp = ts.to_pydatetime()
        points.append(
            WeekDataPoint(
                timestamp=timestamp,
                solar_kw=max(float(solar_series.loc[ts]), 0.0),
                load_kw=raw_load * scale_factor,
                grid_price_eur_per_kwh=get_tou_price(timestamp),
            )
        )

    return points


def fetch_renewables_ninja_solar_kw(
    target_timestamps: pd.DatetimeIndex,
) -> pd.Series | None:
    """
    Pull hourly PV generation from renewables.ninja and interpolate to 15 minutes.

    Requires RENEWABLES_NINJA_TOKEN in .env.
    """
    token = os.getenv("RENEWABLES_NINJA_TOKEN")

    if not token or token == "your_token_here":
        return None

    start_date = target_timestamps[0].date().isoformat()
    end_date = target_timestamps[-1].date().isoformat()

    url = "https://www.renewables.ninja/api/data/pv"

    params = {
        "lat": LIMASSOL_LAT,
        "lon": LIMASSOL_LON,
        "date_from": start_date,
        "date_to": end_date,
        "dataset": "merra2",
        "capacity": SYSTEM_CAPACITY_KW,
        "system_loss": 0.1,
        "tracking": 0,
        "tilt": 25,
        "azim": 180,
        "format": "json",
    }

    headers = {"Authorization": f"Token {token}"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return None

    payload = response.json()
    raw_data = payload.get("data", {})

    if not raw_data:
        return None

    hourly = pd.DataFrame.from_dict(raw_data, orient="index")
    hourly.index = pd.to_datetime(hourly.index.astype("int64"), unit="ms", utc=True)

    hourly.index = hourly.index.tz_convert(TIMEZONE)

    # renewables.ninja PV result usually uses electricity as the generation column.
    if "electricity" not in hourly.columns:
        return None

    solar_kw = hourly["electricity"].astype(float)

    # Create 15-min series using time interpolation, then align exactly to our target week.
    combined_index = solar_kw.index.union(target_timestamps)
    solar_15min = (
        solar_kw.reindex(combined_index)
        .sort_index()
        .interpolate(method="time")
        .reindex(target_timestamps)
        .fillna(0.0)
    )

    return solar_15min


def generate_synthetic_solar_kw(timestamps: pd.DatetimeIndex) -> pd.Series:
    """
    Fallback solar shape for local runs without an API token.
    This is not the preferred path, but keeps the project runnable.
    """
    values: list[float] = []

    for ts in timestamps:
        hour = ts.hour + ts.minute / 60

        if hour < 6 or hour > 20:
            solar = 0.0
        else:
            daylight_progress = (hour - 6) / 14
            clear_sky_shape = math.sin(math.pi * daylight_progress)
            day_factor = 0.88 + 0.08 * math.sin(ts.dayofweek)
            solar = SYSTEM_CAPACITY_KW * clear_sky_shape * day_factor

        values.append(max(solar, 0.0))

    return pd.Series(values, index=timestamps)


def generate_hotel_load_kw(timestamp: datetime) -> float:
    """
    Synthetic hotel load profile.

    Assumptions:
    - Base load exists 24/7 due to refrigeration, lighting, pumps and always-on systems.
    - Morning and evening activity increase demand.
    - Hot Cyprus afternoons create a cooling peak.
    - Weekend occupancy is slightly higher.
    """
    hour = timestamp.hour + timestamp.minute / 60
    weekday = timestamp.weekday()

    base_load = 75.0

    morning_activity = 22.0 * math.exp(-((hour - 8.5) ** 2) / 5.0)
    afternoon_cooling = 75.0 * math.exp(-((hour - 15.5) ** 2) / 8.0)
    evening_activity = 38.0 * math.exp(-((hour - 20.0) ** 2) / 6.0)

    weekend_multiplier = 1.08 if weekday >= 5 else 1.0
    weekday_variation = 1.0 + 0.03 * math.sin(weekday)

    return (
        base_load + morning_activity + afternoon_cooling + evening_activity
    ) * weekend_multiplier * weekday_variation


def get_tou_price(timestamp: datetime) -> float:
    """
    Stylised 2-rate TOU:
    Day 09:00-23:00: €0.30/kWh
    Night 23:00-09:00: €0.15/kWh
    """
    if 9 <= timestamp.hour < 23:
        return DAY_PRICE_EUR_PER_KWH

    return NIGHT_PRICE_EUR_PER_KWH