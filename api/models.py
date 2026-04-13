"""Persistence for the fuel station catalogue.

The model is intentionally thin: it is a storage detail behind
:class:`~api.stations.database.DatabaseFuelPriceSource`, and no business logic
lives here.
"""

from __future__ import annotations

from django.db import models


class FuelStation(models.Model):
    """One fuel station with a posted price for one fuel type."""

    station_name = models.CharField(max_length=100)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    fuel_type = models.CharField(max_length=50, blank=True)
    price_per_gallon = models.FloatField()

    class Meta:
        constraints = [
            # A station sells one price per fuel type; without this the loader
            # silently accumulated a duplicate row on every price change.
            models.UniqueConstraint(
                fields=["station_name", "city", "state", "zip_code", "fuel_type"],
                name="uniq_fuel_station_identity",
            ),
        ]
        indexes = [
            # Bounding-box lookups filter on both coordinates; the composite
            # index lets the database answer them without a sequential scan.
            models.Index(fields=["latitude", "longitude"], name="idx_station_lat_lng"),
            models.Index(fields=["price_per_gallon"], name="idx_station_price"),
        ]
        ordering = ["station_name", "city"]

    def __str__(self) -> str:
        return f"{self.station_name} - {self.city}"
