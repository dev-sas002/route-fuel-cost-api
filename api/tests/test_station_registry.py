"""The fuel-price-source registry and the memoised station index."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from api.stations import (
    get_fuel_price_source,
    get_station_index,
    reset_station_index_cache,
)
from api.stations.csv_source import CsvFuelPriceSource
from api.stations.index import StationIndex
from api.tests.doubles import make_station


@override_settings(FUEL_PRICE_SOURCE="api.stations.csv_source.CsvFuelPriceSource")
class RegistryTests(SimpleTestCase):
    def setUp(self):
        reset_station_index_cache()
        self.addCleanup(reset_station_index_cache)

    def test_resolves_the_configured_source(self):
        self.assertIsInstance(get_fuel_price_source(), CsvFuelPriceSource)

    def test_explicit_dotted_path_wins(self):
        source = get_fuel_price_source("api.stations.csv_source.CsvFuelPriceSource")
        self.assertEqual(source.name, "csv")

    def test_load_returns_a_concrete_list(self):
        stations = get_fuel_price_source().load()
        self.assertIsInstance(stations, list)
        self.assertEqual(len(stations), 50)

    @override_settings(STATION_INDEX_CACHE_SECONDS=300)
    def test_index_is_memoised_between_calls(self):
        first = get_station_index()
        self.assertIs(get_station_index(), first)

    @override_settings(STATION_INDEX_CACHE_SECONDS=300)
    def test_force_reload_rebuilds_the_index(self):
        first = get_station_index()
        self.assertIsNot(get_station_index(force_reload=True), first)

    @override_settings(STATION_INDEX_CACHE_SECONDS=0)
    def test_caching_can_be_disabled(self):
        self.assertIsNot(get_station_index(), get_station_index())

    @override_settings(STATION_INDEX_CACHE_SECONDS=300)
    def test_changing_the_source_setting_invalidates_the_index(self):
        # api.apps.ApiConfig wires setting_changed to the cache reset, which is
        # what keeps override_settings honest in the rest of the suite.
        first = get_station_index()
        with override_settings(STATION_GRID_CELL_DEGREES=1.0):
            self.assertIsNot(get_station_index(), first)


class IndexAccessorTests(SimpleTestCase):
    def test_exposes_the_stations_it_was_built_from(self):
        stations = [make_station(1, 3.0), make_station(2, 4.0)]
        index = StationIndex(stations)
        self.assertEqual(list(index.stations), stations)
