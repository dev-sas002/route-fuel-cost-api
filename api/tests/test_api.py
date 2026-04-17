"""End-to-end tests for the HTTP layer.

These run against the real URLconf, serializers, service and optimiser; only
the routing provider is replaced with a double, so no network call is made.
"""

from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from api.models import FuelStation
from api.stations import reset_station_index_cache
from api.tests.doubles import FakeRouteProvider

ROUTE_URL = reverse("api:route")
HEALTH_URL = reverse("api:health")

VALID_BODY = {
    "start_lat": 0.0,
    "start_lng": 0.0,
    "end_lat": 0.0,
    "end_lng": 10.0,
    "vehicle_mpg": 10,
    "tank_range_miles": 400,
}


@override_settings(
    ROUTE_PROVIDER="api.tests.doubles.FakeRouteProvider",
    STATION_INDEX_CACHE_SECONDS=0,
    FUEL_PRICE_SOURCE="api.stations.database.DatabaseFuelPriceSource",
)
class RouteEndpointTests(TestCase):
    """The FakeRouteProvider returns a 900-mile route due east along the equator."""

    @classmethod
    def setUpTestData(cls):
        FuelStation.objects.bulk_create(
            [
                FuelStation(
                    station_name=f"Station {index}",
                    city="Testville",
                    state="TS",
                    zip_code=f"{10000 + index}",
                    fuel_type="Regular",
                    latitude=0.0,
                    longitude=float(longitude),
                    price_per_gallon=price,
                )
                for index, (longitude, price) in enumerate(
                    [(3.0, 4.50), (5.0, 2.50), (7.0, 5.00)], start=1
                )
            ]
        )

    def setUp(self):
        reset_station_index_cache()
        self.addCleanup(reset_station_index_cache)

    def post(self, **overrides):
        body = {**VALID_BODY, **overrides}
        return self.client.post(ROUTE_URL, body, content_type="application/json")

    # -- happy path --------------------------------------------------------

    def test_returns_a_plan(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["provider"], "fake")
        self.assertAlmostEqual(payload["total_distance_miles"], 900.0, places=2)
        self.assertEqual(payload["candidate_station_count"], 3)
        self.assertGreaterEqual(payload["fuel_stop_count"], 1)
        self.assertGreater(payload["total_fuel_cost"], 0)
        self.assertEqual(
            payload["route_points_returned"], payload["route_points_total"]
        )

    def test_fuel_stop_shape(self):
        stop = self.post().json()["fuel_stops"][0]
        self.assertEqual(
            set(stop),
            {
                "station_name",
                "city",
                "state",
                "latitude",
                "longitude",
                "price_per_gallon",
                "route_miles",
                "detour_miles",
                "gallons",
                "cost",
            },
        )

    def test_picks_the_cheapest_reachable_station(self):
        # Station 2 at mile ~450 is the cheapest of the three and is reachable
        # on the starting tank, so the plan buys there.
        names = [stop["station_name"] for stop in self.post().json()["fuel_stops"]]
        self.assertIn("Station 2", names)

    def test_reported_cost_matches_the_sum_of_the_stops(self):
        payload = self.post().json()
        self.assertAlmostEqual(
            payload["total_fuel_cost"],
            round(sum(stop["cost"] for stop in payload["fuel_stops"]), 2),
            places=1,
        )

    def test_short_trip_costs_nothing(self):
        payload = self.post(tank_range_miles=1000).json()
        self.assertEqual(payload["fuel_stop_count"], 0)
        self.assertEqual(payload["total_fuel_cost"], 0.0)

    def test_defaults_are_applied(self):
        response = self.client.post(
            ROUTE_URL,
            {"start_lat": 0.0, "start_lng": 0.0, "end_lat": 0.0, "end_lng": 10.0},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["vehicle_mpg"], 10.0)
        self.assertEqual(payload["tank_range_miles"], 500.0)

    @override_settings(MAX_ROUTE_POINTS_RETURNED=10)
    def test_route_polyline_is_bounded(self):
        payload = self.post().json()
        self.assertEqual(payload["route_points_returned"], 10)
        self.assertEqual(payload["route_points_total"], FakeRouteProvider.segments + 1)

    # -- validation --------------------------------------------------------

    def test_missing_fields_are_rejected(self):
        response = self.client.post(ROUTE_URL, {}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("start_lat", response.json())

    def test_identical_endpoints_are_rejected(self):
        response = self.post(end_lat=0.0, end_lng=0.0)
        self.assertEqual(response.status_code, 400)

    def test_out_of_range_latitude_is_rejected(self):
        response = self.post(start_lat=120.0)
        self.assertEqual(response.status_code, 400)

    def test_non_positive_mpg_is_rejected(self):
        response = self.post(vehicle_mpg=0)
        self.assertEqual(response.status_code, 400)

    def test_non_numeric_input_is_rejected(self):
        response = self.post(vehicle_mpg="not-a-number")
        self.assertEqual(response.status_code, 400)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(ROUTE_URL).status_code, 405)

    # -- domain errors -> status codes -------------------------------------

    def test_unreachable_destination_returns_422_with_the_gap(self):
        response = self.post(tank_range_miles=50)
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["code"], "unreachable_destination")
        self.assertGreater(payload["detail"]["gap_miles"], 50)

    def test_no_stations_returns_422(self):
        FuelStation.objects.all().delete()
        reset_station_index_cache()
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "no_fuel_stations_available")

    @override_settings(ROUTE_PROVIDER="api.tests.doubles.BrokenRouteProvider")
    def test_provider_failure_returns_502(self):
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "routing_provider_error")

    @override_settings(
        ROUTE_PROVIDER="api.routing.openrouteservice.OpenRouteServiceProvider",
        ORS_API_KEY="",
    )
    def test_missing_ors_key_returns_503_rather_than_crashing(self):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "routing_provider_not_configured")


class HealthEndpointTests(TestCase):
    @override_settings(ROUTE_PROVIDER="api.routing.static.StaticRouteProvider")
    def test_reports_the_active_provider(self):
        response = self.client.get(HEALTH_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "route_provider": "static",
                "route_provider_configured": True,
            },
        )

    @override_settings(
        ROUTE_PROVIDER="api.routing.openrouteservice.OpenRouteServiceProvider",
        ORS_API_KEY="",
    )
    def test_reports_an_unconfigured_provider_without_failing(self):
        response = self.client.get(HEALTH_URL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["route_provider_configured"])
