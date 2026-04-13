"""Load the fuel station catalogue from a CSV file into the database.

Idempotent: rows are matched on the station's identity columns and their price
is updated, so re-running with a fresher price file refreshes prices instead of
duplicating stations. Writes are batched, so a large file is a handful of
queries rather than one per row.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import FuelStation
from api.stations import reset_station_index_cache
from api.stations.csv_source import CsvFuelPriceSource

BATCH_SIZE = 1000

IDENTITY_FIELDS = ("station_name", "city", "state", "zip_code", "fuel_type")


class Command(BaseCommand):
    help = "Load fuel station prices from a CSV file."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path",
            default=None,
            help="CSV file to load (defaults to the FUEL_PRICES_CSV setting).",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete existing stations before loading.",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"] or settings.FUEL_PRICES_CSV)
        if not path.exists():
            raise CommandError(f"CSV file not found: {path}")

        source = CsvFuelPriceSource(path)
        try:
            stations = list(source.stream())
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not stations:
            raise CommandError(f"No usable rows in {path}")

        rows = [
            FuelStation(
                station_name=station.name,
                city=station.city,
                state=station.state,
                zip_code=station.address,
                fuel_type=station.fuel_type,
                latitude=station.location.lat,
                longitude=station.location.lng,
                price_per_gallon=station.price_per_gallon,
            )
            for station in stations
        ]

        with transaction.atomic():
            if options["truncate"]:
                deleted, _ = FuelStation.objects.all().delete()
                self.stdout.write(f"Removed {deleted} existing station(s).")
            FuelStation.objects.bulk_create(
                rows,
                batch_size=BATCH_SIZE,
                update_conflicts=True,
                update_fields=["latitude", "longitude", "price_per_gallon"],
                unique_fields=list(IDENTITY_FIELDS),
            )

        reset_station_index_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(rows)} station(s) from {path}; "
                f"{FuelStation.objects.count()} in the catalogue."
            )
        )
