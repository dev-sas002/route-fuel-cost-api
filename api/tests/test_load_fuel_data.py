"""The CSV loader management command and the CSV price source."""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from api.models import FuelStation
from api.stations.csv_source import CsvFuelPriceSource

HEADER = (
    "station_name,city,state,zip_code,latitude,longitude,fuel_type,price_per_gallon"
)


def write_csv(rows: list[str], header: str = HEADER) -> Path:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8"
    ) as handle:
        handle.write("\n".join([header, *rows]) + "\n")
    return Path(handle.name)


class CsvSourceTests(SimpleTestCase):
    def test_reads_the_bundled_sample_file(self):
        stations = list(CsvFuelPriceSource(settings.FUEL_PRICES_CSV).stream())
        self.assertEqual(len(stations), 50)
        self.assertTrue(all(station.price_per_gallon > 0 for station in stations))
        self.assertTrue(all(-90 <= station.location.lat <= 90 for station in stations))

    def test_missing_columns_are_reported(self):
        path = write_csv(["Shell,LA"], header="station_name,city")
        self.addCleanup(path.unlink)
        with self.assertRaises(ValueError) as ctx:
            list(CsvFuelPriceSource(path).stream())
        self.assertIn("latitude", str(ctx.exception))

    def test_unparseable_rows_are_skipped_not_fatal(self):
        path = write_csv(
            [
                "Shell,LA,CA,90001,34.05,-118.24,Regular,4.59",
                "Broken,LA,CA,90001,not-a-number,-118.24,Regular,4.59",
                "Nowhere,LA,CA,90001,999.0,-118.24,Regular,4.59",
            ]
        )
        self.addCleanup(path.unlink)
        with self.assertLogs("api.stations.csv_source", "WARNING") as logs:
            stations = list(CsvFuelPriceSource(path).stream())
        self.assertEqual([station.name for station in stations], ["Shell"])
        self.assertEqual(len(logs.output), 2)


class LoadFuelDataCommandTests(TestCase):
    def run_command(self, *args, **kwargs) -> str:
        out = StringIO()
        call_command("load_fuel_data", *args, stdout=out, **kwargs)
        return out.getvalue()

    def test_loads_the_bundled_sample_dataset(self):
        output = self.run_command()
        self.assertEqual(FuelStation.objects.count(), 50)
        self.assertIn("Loaded 50 station(s)", output)

    def test_is_idempotent_and_refreshes_prices(self):
        path = write_csv(["Shell,LA,CA,90001,34.05,-118.24,Regular,4.59"])
        self.addCleanup(path.unlink)
        self.run_command(path=str(path))

        updated = write_csv(["Shell,LA,CA,90001,34.05,-118.24,Regular,3.99"])
        self.addCleanup(updated.unlink)
        self.run_command(path=str(updated))

        # The old loader inserted a second row here instead of updating.
        self.assertEqual(FuelStation.objects.count(), 1)
        self.assertEqual(FuelStation.objects.get().price_per_gallon, 3.99)

    def test_truncate_replaces_the_catalogue(self):
        self.run_command()
        path = write_csv(["Solo,LA,CA,90001,34.05,-118.24,Regular,4.59"])
        self.addCleanup(path.unlink)
        output = self.run_command(path=str(path), truncate=True)
        self.assertEqual(FuelStation.objects.count(), 1)
        self.assertIn("Removed 50 existing station(s)", output)

    def test_missing_file_is_a_command_error(self):
        with self.assertRaises(CommandError):
            self.run_command(path="/nonexistent/prices.csv")

    def test_empty_file_is_a_command_error(self):
        path = write_csv([])
        self.addCleanup(path.unlink)
        with self.assertRaises(CommandError):
            self.run_command(path=str(path))

    def test_malformed_header_is_a_command_error(self):
        path = write_csv(["Shell,LA"], header="station_name,city")
        self.addCleanup(path.unlink)
        with self.assertRaises(CommandError):
            self.run_command(path=str(path))


class DatabaseSourceTests(TestCase):
    def test_maps_rows_onto_domain_stations(self):
        from api.stations.database import DatabaseFuelPriceSource

        FuelStation.objects.create(
            station_name="Shell",
            city="LA",
            state="CA",
            zip_code="90001",
            fuel_type="Regular",
            latitude=34.05,
            longitude=-118.24,
            price_per_gallon=4.59,
        )
        stations = list(DatabaseFuelPriceSource().load())
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].name, "Shell")
        self.assertEqual(stations[0].address, "90001")
        self.assertAlmostEqual(stations[0].location.lat, 34.05)


class FuelStationModelTests(TestCase):
    def test_string_representation(self):
        station = FuelStation(station_name="Shell", city="LA")
        self.assertEqual(str(station), "Shell - LA")
