from django.db import models


class TimeSeriesPoint(models.Model):
    timestamp = models.DateTimeField(unique=True)
    solar_kw = models.FloatField()
    load_kw = models.FloatField()
    grid_price_eur_per_kwh = models.FloatField()

    class Meta:
        ordering = ["timestamp"]

    def __str__(self) -> str:
        return f"{self.timestamp} | solar={self.solar_kw:.2f} kW | load={self.load_kw:.2f} kW"


class DispatchResult(models.Model):
    timestamp = models.DateTimeField(unique=True)

    solar_kw = models.FloatField()
    load_kw = models.FloatField()
    grid_price_eur_per_kwh = models.FloatField()

    battery_power_kw = models.FloatField(
        help_text="Positive = discharging, negative = charging, zero = idle"
    )
    soc_kwh = models.FloatField()
    grid_import_kw = models.FloatField()
    curtailed_solar_kw = models.FloatField()

    charged_kwh = models.FloatField()
    discharged_kwh = models.FloatField()

    class Meta:
        ordering = ["timestamp"]

    def __str__(self) -> str:
        return f"{self.timestamp} | battery={self.battery_power_kw:.2f} kW | soc={self.soc_kwh:.2f} kWh"