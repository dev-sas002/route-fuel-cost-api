"""The spatial index and the projection of stations onto a route."""

from __future__ import annotations

from django.test import SimpleTestCase

from api.domain.geo import haversine_miles
from api.domain.types import GeoPoint
from api.stations.index import StationIndex
from api.tests.doubles import make_route, make_station


class GridTests(SimpleTestCase):
    def setUp(self):
        self.stations = [
            make_station(1, 3.00, lat=34.05, lng=-118.24),  # Los Angeles
            make_station(2, 3.10, lat=34.10, lng=-118.30),  # ~5 mi away
            make_station(3, 2.90, lat=40.71, lng=-74.00),  # New York
        ]
        self.index = StationIndex(self.stations, cell_degrees=0.5)

    def test_reports_its_size(self):
        self.assertEqual(len(self.index), 3)
        self.assertEqual(self.index.cell_count, 2)

    def test_rejects_a_non_positive_cell_size(self):
        with self.assertRaises(ValueError):
            StationIndex([], cell_degrees=0)

    def test_finds_only_stations_inside_the_radius(self):
        found = self.index.near(GeoPoint(lat=34.05, lng=-118.24), radius_miles=20)
        self.assertEqual({station.id for station in found}, {1, 2})

    def test_tight_radius_excludes_the_neighbour(self):
        found = self.index.near(GeoPoint(lat=34.05, lng=-118.24), radius_miles=1)
        self.assertEqual({station.id for station in found}, {1})

    def test_empty_index_returns_nothing(self):
        self.assertEqual(StationIndex([]).near(GeoPoint(lat=0, lng=0), 500), [])

    def test_non_positive_radius_returns_nothing(self):
        self.assertEqual(self.index.near(GeoPoint(lat=34.05, lng=-118.24), 0), [])

    def test_matches_a_brute_force_scan(self):
        # The grid is an optimisation, not a different answer.
        point = GeoPoint(lat=34.2, lng=-118.5)
        radius = 40.0
        expected = {
            station.id
            for station in self.stations
            if haversine_miles(point, station.location) <= radius
        }
        self.assertEqual({s.id for s in self.index.near(point, radius)}, expected)

    def test_query_spanning_a_cell_boundary(self):
        index = StationIndex(
            [
                make_station(10, 3.0, lat=0.49, lng=0.0),
                make_station(11, 3.0, lat=0.51, lng=0.0),
            ],
            cell_degrees=0.5,
        )
        found = index.near(GeoPoint(lat=0.50, lng=0.0), radius_miles=10)
        self.assertEqual({station.id for station in found}, {10, 11})


class ProjectionTests(SimpleTestCase):
    def setUp(self):
        # A due-east route along the equator: 1 degree of longitude ~= 69 miles.
        self.route = make_route([(0.0, float(x)) for x in range(0, 11)], 690.0)

    def test_stations_on_the_route_are_ordered_by_distance_travelled(self):
        index = StationIndex(
            [
                make_station(1, 3.0, lat=0.0, lng=8.0),
                make_station(2, 3.0, lat=0.0, lng=2.0),
                make_station(3, 3.0, lat=0.0, lng=5.0),
            ]
        )
        stops = index.candidates_along_route(self.route, corridor_miles=25)
        self.assertEqual([stop.station.id for stop in stops], [2, 3, 1])
        self.assertTrue(all(stop.detour_miles < 1.0 for stop in stops))

    def test_positions_line_up_with_the_route(self):
        index = StationIndex([make_station(1, 3.0, lat=0.0, lng=5.0)])
        stop = index.candidates_along_route(self.route, corridor_miles=25)[0]
        self.assertAlmostEqual(stop.route_miles, 345.0, delta=5.0)

    def test_stations_outside_the_corridor_are_dropped(self):
        index = StationIndex([make_station(1, 3.0, lat=2.0, lng=5.0)])  # ~138 mi north
        self.assertEqual(
            index.candidates_along_route(self.route, corridor_miles=50), []
        )
        self.assertEqual(
            len(index.candidates_along_route(self.route, corridor_miles=200)), 1
        )

    def test_a_station_appears_at_most_once(self):
        index = StationIndex([make_station(1, 3.0, lat=0.0, lng=5.0)])
        stops = index.candidates_along_route(
            self.route, corridor_miles=200, sample_spacing_miles=1
        )
        self.assertEqual(len(stops), 1)

    def test_empty_corridor_is_rejected(self):
        index = StationIndex([make_station(1, 3.0, lat=0.0, lng=5.0)])
        self.assertEqual(index.candidates_along_route(self.route, corridor_miles=0), [])

    def test_sampling_does_not_lose_stations(self):
        # A coarse sample must still find every station inside the corridor,
        # which is why the search radius is widened by half the spacing.
        stations = [make_station(i, 3.0, lat=0.0, lng=i / 10.0) for i in range(1, 100)]
        index = StationIndex(stations)
        dense = index.candidates_along_route(
            self.route, corridor_miles=30, sample_spacing_miles=1
        )
        coarse = index.candidates_along_route(
            self.route, corridor_miles=30, sample_spacing_miles=40
        )
        self.assertEqual(
            {stop.station.id for stop in dense},
            {stop.station.id for stop in coarse},
        )
