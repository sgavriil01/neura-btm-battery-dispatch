# Neura BTM Battery Dispatch

A small Django service for modelling behind-the-meter battery dispatch for a representative Cyprus hotel week.

The app stores 15-minute solar, hotel load, and grid price data in SQLite, runs a greedy dispatch policy for a 400 kWh / 200 kW battery, and exposes a weekly financier-style report at:

```text
/reports/weekly/
```

## What this project does

For one representative summer week, the service:

- imports or generates 15-minute time series data;
- stores the data in the database;
- runs a behind-the-meter battery dispatch policy;
- compares grid cost with and without the battery;
- reports weekly saving, charged/discharged kWh, solar self-consumption, and battery SoC;
- plots the battery SoC curve.

## Scenario

A 4-star hotel in Limassol has:

- 200 kWp rooftop PV;
- 400 kWh / 200 kW LFP battery;
- peak summer demand around 200 kW;
- no grid export;
- stylised 2-rate TOU tariff:
  - day, 09:00-23:00: €0.30/kWh;
  - night, 23:00-09:00: €0.15/kWh.

## Tech stack

- Python 3.11+
- Django
- SQLite
- pandas
- matplotlib
- requests
- python-dotenv

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add a renewables.ninja API token to `.env`:

```env
RENEWABLES_NINJA_TOKEN=your_token_here
```

Then run:

```bash
./run_local.sh
```

Open:

```text
http://127.0.0.1:8000/reports/weekly/
```

## Manual run

```bash
python manage.py migrate
python manage.py seed_week_data
python manage.py run_dispatch
python manage.py runserver
```

For a fully local demo without a renewables.ninja token:

```bash
python manage.py migrate
python manage.py seed_week_data --synthetic-solar
python manage.py run_dispatch
python manage.py runserver
```

## Data

### Solar

The preferred path uses renewables.ninja PV data for Limassol:

| Parameter | Value |
|---|---:|
| Latitude | 34.7071 |
| Longitude | 33.0226 |
| PV capacity | 200 kW |
| Dataset | MERRA-2 |
| Tilt | 25 degrees |
| Azimuth | 180 degrees |
| System loss | 10% |

renewables.ninja returns hourly PV data. The app converts it to 15-minute resolution by aligning the hourly series with the target 15-minute timestamps and applying time interpolation.

If no API token is provided, the app falls back to a synthetic solar curve so the project remains runnable by reviewers. Final reported numbers should be generated with the renewables.ninja path.

### Hotel load

No clean public 15-minute Cyprus hotel load dataset was available, so the hotel load profile is synthetic but defensible.

Assumptions:

- The hotel has a 24/7 base load from refrigeration, pumps, lighting, elevators, standby systems, and common areas.
- Morning activity increases demand around breakfast.
- Afternoon cooling creates the strongest peak in hot Cyprus conditions.
- Evening guest activity creates a second smaller peak.
- Weekends have slightly higher occupancy.
- The generated profile is scaled so the weekly peak is approximately 200 kW.

Because the generated hotel demand remains high relative to the 200 kWp PV system, the representative week has zero curtailment and 100% solar self-consumption.

### Grid price

The service uses the required stylised 2-rate TOU tariff:

| Period | Time | Price |
|---|---:|---:|
| Day | 09:00-23:00 | €0.30/kWh |
| Night | 23:00-09:00 | €0.15/kWh |

## Dispatch policy

The dispatch algorithm is greedy and intentionally simple.

At every 15-minute interval:

1. Solar covers hotel load first.
2. If solar exceeds load, surplus solar charges the battery.
3. If solar cannot cover load and the tariff is day-rate, the battery discharges.
4. Remaining demand is imported from the grid.
5. If surplus solar cannot be used or stored, it is curtailed.
6. Grid export is not allowed.

Battery constraints:

| Constraint | Value |
|---|---:|
| Capacity | 400 kWh |
| Power limit | 200 kW charge/discharge |
| Minimum SoC | 10% = 40 kWh |
| Maximum SoC | 95% = 380 kWh |
| Round-trip efficiency | 88% |

I model charge and discharge efficiency symmetrically as:

```python
charge_efficiency = discharge_efficiency = sqrt(0.88)
```

The dispatch logic lives in `dispatch/services/dispatch_policy.py`, not in the Django view.

## Weekly report

The report at `/reports/weekly/` shows:

- grid spend without battery;
- grid spend with battery;
- weekly saving;
- total kWh charged;
- total kWh discharged;
- solar self-consumption percentage;
- battery SoC curve.

Example output from a renewables.ninja run:

| Metric | Value |
|---|---:|
| Grid spend without battery | €3222.27 |
| Grid spend with battery | €3121.05 |
| Weekly saving | €101.22 |
| Total charged energy | 383.41 kWh |
| Total discharged energy | 337.40 kWh |
| Solar self-consumption | 100.00% |

## Tests

Run:

```bash
python manage.py test
```

Tests cover:

- SoC never goes below minimum;
- SoC never goes above maximum;
- charge power limit is respected;
- discharge power limit is respected;
- surplus solar charges the battery before curtailment;
- grid export does not occur;
- the battery discharges during day-rate;
- the battery does not discharge during night-rate.

## Project structure

```text
dispatch/
├── management/
│   └── commands/
│       ├── seed_week_data.py
│       └── run_dispatch.py
├── services/
│   ├── constants.py
│   ├── data_generation.py
│   ├── dispatch_policy.py
│   └── report_service.py
├── templates/
│   └── dispatch/
│       └── weekly_report.html
├── models.py
├── tests.py
├── urls.py
└── views.py
```

The Django view only calls the report service. Data generation, dispatch logic, and report calculations are separated into service modules.

## Design choices

### Why a greedy dispatch?

The task only needs a small internal tool slice, so I used a readable greedy policy rather than an LP/optimisation solver. This keeps the behaviour explainable:

- use free solar first;
- store surplus solar when possible;
- discharge during expensive day-rate periods;
- import the remainder from the grid.

### Why no grid charging?

I assumed the battery only charges from surplus solar. With more time, I would add optional night-rate grid charging and compare whether the day/night spread still creates value after efficiency losses.

### Why SQLite?

SQLite is enough for a local take-home service and keeps setup simple. The schema could move to PostgreSQL without changing the service layer much.

## Assumptions and uncertainty

- The hotel load profile is synthetic because no suitable public 15-minute Cyprus hotel dataset was available.
- The generated load is scaled to a 200 kW peak, matching the scenario.
- The dispatch policy is greedy, not globally optimal.
- The model assumes no grid charging.
- The model assumes no grid export.
- The representative week is a July week to reflect summer cooling demand.
- The solar interpolation from hourly to 15-minute data is simple time interpolation. This is acceptable for the slice, but a production model could use measured inverter data or a higher-resolution irradiance model.

## What I would build next

With another day, I would add:

1. A what-if form for PV size, battery capacity, and battery power.
2. Real EAC commercial tariff support.
3. Optional night-rate grid charging when financially attractive.
4. CSV export for the weekly report.
5. Additional charts for load, solar, grid import, battery power, and curtailment.
6. A comparison between this greedy policy and an LP-based optimal dispatch.
7. Basic authentication if the report was meant for real customer/financier access.

## AI usage

I used AI coding assistance to speed up scaffolding, implementation, and review. I used it as a junior developer rather than as an autopilot: I asked it for structure, tested the code locally, inspected failures, and adjusted the implementation.

Specific examples:

- AI helped propose a clean Django architecture where data generation, dispatch policy, and report calculations live in separate service modules instead of `views.py`.
- AI helped design the dispatch test cases around the real constraints: SoC bounds, power limits, no export, day-rate discharge, and night-rate idle behaviour.
- AI helped debug renewables.ninja timestamp parsing. The API returned timestamps in milliseconds, so the code needed `pd.to_datetime(..., unit="ms", utc=True)` instead of ordinary string parsing.
- AI also helped decide to keep a synthetic solar fallback. That makes the app runnable for reviewers without a private API token while still supporting the required renewables.ninja path.

## Time spent

Approximate time spent: 2-3 hours.