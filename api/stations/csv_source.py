"""Fuel prices read straight from a CSV file.

Used by the loader management command and available as a database-free
deployment mode (``FUEL_PRICE_SOURCE=api.stations.csv_source.CsvFuelPriceSource``).
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path

from django.conf import settings

from api.domain.types import GeoPoint, Station

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = frozenset(
    {"station_name", "latitude", "longitude", "price_per_gallon"}
)


class CsvFuelPriceSource:
    """Streams stations from a CSV file with the sample dataset's columns."""

    name = "csv"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or settings.FUEL_PRICES_CSV)

    def load(self) -> Iterable[Station]:
        return list(self.stream())

    def stream(self) -> Iterator[Station]:
        """Yield stations one row at a time; the file is never held in memory."""
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(
                    f"{self.path} is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )
            for line_number, row in enumerate(reader, start=2):
                station = self._to_station(row, line_number)
                if station is not None:
                    yield station

    def _to_station(self, row: dict[str, str], line_number: int) -> Station | None:
        try:
            return Station(
                id=line_number,
                name=(row.get("station_name") or "").strip(),
                location=GeoPoint(
                    lat=float(row["latitude"]), lng=float(row["longitude"])
                ),
                price_per_gallon=float(row["price_per_gallon"]),
                city=(row.get("city") or "").strip(),
                state=(row.get("state") or "").strip(),
                fuel_type=(row.get("fuel_type") or "").strip(),
                address=(row.get("address") or row.get("zip_code") or "").strip(),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping %s line %s: %s", self.path, line_number, exc)
            return None
