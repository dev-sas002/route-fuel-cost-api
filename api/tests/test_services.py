"""The application service that wires routing, indexing and optimisation."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from api.domain.errors import NoFuelStationsAvailable, RoutingProviderError
from api.domain.types import GeoPoint
from api.services import FuelRoutePlanner, route_points_for_response
from api.stations.index import StationIndex
from api.tests.doubles import (
    BrokenRouteProvider,
    FakeRouteProvider,
    make_route,
    make_station,
)

START = GeoPoint(lat=0.0, lng=0.0)
END = GeoPoint(lat=0.0, lng=10.0)


def planner(stations, *, provider=None):
    return FuelRoutePlanner(
        route_provider=provider or FakeRouteProvider(),
        station_index=StationIndex(stations),
    )


class PlannerTests(SimpleTestCase):
    def test_plans_stops_along_the_route(self):
        stations = [
            make_station(1, 4.00, lat=0.0, lng=3.0),
            make_station(2, 2.00, lat=0.0, lng=6.0),
        ]
        result = planner(stations).plan(
            start=START, end=END, vehicle_mpg=10, tank_range_miles=400
        )
        self.assertEqual(result.route.distance_miles, FakeRouteProvider.distance_miles)
        self.assertEqual(result.plan.candidates_considered, 2)
        self.assertGreater(result.plan.total_cost, 0)

    def test_short_trip_needs_no_stops(self):
        result = planner([make_station(1, 4.00, lat=0.0, lng=3.0)]).plan(
            start=START, end=END, vehicle_mpg=10, tank_range_miles=2000
        )
        self.assertEqual(result.plan.stop_count, 0)
        self.assertEqual(result.plan.total_cost, 0.0)

    def test_no_stations_on_a_long_route_is_reported(self):
        with self.assertRaises(NoFuelStationsAvailable):
            planner([]).plan(start=START, end=END, vehicle_mpg=10, tank_range_miles=100)

    def test_no_stations_on_a_short_route_is_fine(self):
        result = planner([]).plan(
            start=START, end=END, vehicle_mpg=10, tank_range_miles=2000
        )
        self.assertEqual(result.plan.stop_count, 0)

    def test_provider_failures_propagate(self):
        with self.assertRaises(RoutingProviderError):
            planner([], provider=BrokenRouteProvider()).plan(
                start=START, end=END, vehicle_mpg=10, tank_range_miles=400
            )

    @override_settings(FUEL_STOP_CORRIDOR_MILES=5.0)
    def test_corridor_defaults_to_the_setting(self):
        far_station = [make_station(1, 2.00, lat=1.0, lng=5.0)]  # ~69 mi off route
        with self.assertRaises(NoFuelStationsAvailable):
            planner(far_station).plan(
                start=START, end=END, vehicle_mpg=10, tank_range_miles=400
            )

    def test_explicit_corridor_overrides_the_setting(self):
        far_station = [make_station(1, 2.00, lat=1.0, lng=5.0)]
        result = planner(far_station).plan(
            start=START,
            end=END,
            vehicle_mpg=10,
            tank_range_miles=500,
            corridor_miles=100,
        )
        self.assertEqual(result.plan.candidates_considered, 1)
        self.assertGreater(result.plan.purchases[0].stop.detour_miles, 50)


class ResponsePolylineTests(SimpleTestCase):
    @override_settings(MAX_ROUTE_POINTS_RETURNED=50)
    def test_long_polylines_are_thinned_for_the_response(self):
        route = make_route([(0.0, i / 1000) for i in range(5000)], 300.0)
        points = route_points_for_response(route)
        self.assertEqual(len(points), 50)
        self.assertEqual(points[0], [0.0, 0.0])

    @override_settings(MAX_ROUTE_POINTS_RETURNED=5000)
    def test_short_polylines_are_returned_whole(self):
        route = make_route([(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)], 138.0)
        self.assertEqual(len(route_points_for_response(route)), 3)
