"""Fuel prices from the local :class:`~api.models.FuelStation` table."""

from __future__ import annotations

from collections.abc import Iterable

from api.domain.types import GeoPoint, Station
from api.models import FuelStation


class DatabaseFuelPriceSource:
    """Reads the station catalogue from PostgreSQL/SQLite."""

    name = "database"

    def load(self) -> Iterable[Station]:
        # ``.only()`` keeps the row payload to the eight columns the index
        # needs; ``.iterator()`` streams rather than materialising the whole
        # table in a Django queryset cache.
        rows = FuelStation.objects.only(
            "id",
            "station_name",
            "city",
            "state",
            "zip_code",
            "fuel_type",
            "latitude",
            "longitude",
            "price_per_gallon",
        ).iterator(chunk_size=2000)
        for row in rows:
            yield Station(
                id=row.id,
                name=row.station_name,
                location=GeoPoint(lat=row.latitude, lng=row.longitude),
                price_per_gallon=row.price_per_gallon,
                city=row.city,
                state=row.state,
                fuel_type=row.fuel_type,
                address=row.zip_code,
            )
