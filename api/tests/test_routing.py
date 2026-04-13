"""Routing providers.

The OpenRouteService client is exercised entirely against a fake session: no
test in this file touches the network.
"""

from __future__ import annotations

import polyline
import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from api.domain.errors import (
    RouteNotFound,
    RoutingProviderError,
    RoutingProviderNotConfigured,
    RoutingProviderTimeout,
)
from api.domain.types import GeoPoint
from api.routing import get_route_provider, reset_route_provider_cache
from api.routing.openrouteservice import OpenRouteServiceProvider
from api.routing.static import StaticRouteProvider
from api.tests.doubles import FakeResponse, FakeSession

LA = GeoPoint(lat=34.0522, lng=-118.2437)
VEGAS = GeoPoint(lat=36.1699, lng=-115.1398)

SAMPLE_GEOMETRY = polyline.encode(
    [(34.0522, -118.2437), (35.0, -117.0), (36.1699, -115.1398)], 5
)


def ors_payload(distance_metres=430_000.0, duration=14_400.0, geometry=SAMPLE_GEOMETRY):
    return {
        "routes": [
            {
                "summary": {"distance": distance_metres, "duration": duration},
                "geometry": geometry,
            }
        ]
    }


@override_settings(ROUTE_CACHE_SECONDS=0)
class OpenRouteServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def provider(self, *responses, **kwargs):
        kwargs.setdefault("api_key", "test-key")
        return OpenRouteServiceProvider(session=FakeSession(*responses), **kwargs)

    def test_requires_an_api_key(self):
        provider = OpenRouteServiceProvider(api_key="", session=FakeSession())
        self.assertFalse(provider.is_configured())
        with self.assertRaises(RoutingProviderNotConfigured):
            provider.get_route(LA, VEGAS)

    def test_parses_a_successful_response(self):
        provider = self.provider(FakeResponse(ors_payload()))
        route = provider.get_route(LA, VEGAS)

        self.assertEqual(route.provider, "openrouteservice")
        self.assertAlmostEqual(route.distance_miles, 430_000 / 1609.344, places=6)
        self.assertEqual(route.duration_seconds, 14_400.0)
        self.assertEqual(len(route.points), 3)
        self.assertEqual(route.cumulative_miles[0], 0.0)
        self.assertAlmostEqual(
            route.cumulative_miles[-1], route.distance_miles, places=6
        )

    def test_sends_coordinates_in_lng_lat_order(self):
        session = FakeSession(FakeResponse(ors_payload()))
        provider = OpenRouteServiceProvider(api_key="test-key", session=session)
        provider.get_route(LA, VEGAS)
        self.assertEqual(
            session.calls[0]["json"]["coordinates"],
            [[LA.lng, LA.lat], [VEGAS.lng, VEGAS.lat]],
        )
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "test-key")

    def test_timeout_is_translated(self):
        provider = self.provider(requests.exceptions.Timeout("slow"))
        with self.assertRaises(RoutingProviderTimeout):
            provider.get_route(LA, VEGAS)

    def test_http_error_is_translated(self):
        failure = FakeResponse(
            {}, status_code=429, exc=requests.exceptions.HTTPError("429")
        )
        provider = self.provider(failure)
        with (
            self.assertLogs("api.routing.openrouteservice", "WARNING"),
            self.assertRaises(RoutingProviderError),
        ):
            provider.get_route(LA, VEGAS)

    def test_malformed_json_is_translated(self):
        provider = self.provider(FakeResponse(ValueError("not json")))
        with self.assertRaises(RoutingProviderError):
            provider.get_route(LA, VEGAS)

    def test_empty_route_list_raises_route_not_found(self):
        provider = self.provider(FakeResponse({"routes": []}))
        with self.assertRaises(RouteNotFound):
            provider.get_route(LA, VEGAS)

    def test_missing_geometry_raises_route_not_found(self):
        provider = self.provider(FakeResponse({"routes": [{"summary": {}}]}))
        with self.assertRaises(RouteNotFound):
            provider.get_route(LA, VEGAS)

    def test_degenerate_geometry_raises_route_not_found(self):
        payload = ors_payload(geometry=polyline.encode([(34.0, -118.0)], 5))
        provider = self.provider(FakeResponse(payload))
        with self.assertRaises(RouteNotFound):
            provider.get_route(LA, VEGAS)

    def test_zero_distance_falls_back_to_the_polyline_length(self):
        provider = self.provider(FakeResponse(ors_payload(distance_metres=0.0)))
        route = provider.get_route(LA, VEGAS)
        self.assertGreater(route.distance_miles, 100)


class OpenRouteServiceCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(ROUTE_CACHE_SECONDS=60)
    def test_identical_requests_hit_the_cache(self):
        session = FakeSession(FakeResponse(ors_payload()))
        provider = OpenRouteServiceProvider(api_key="k", session=session)
        first = provider.get_route(LA, VEGAS)
        second = provider.get_route(LA, VEGAS)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(first.distance_miles, second.distance_miles)

    @override_settings(ROUTE_CACHE_SECONDS=60)
    def test_different_endpoints_do_not_share_a_cache_entry(self):
        session = FakeSession(FakeResponse(ors_payload()), FakeResponse(ors_payload()))
        provider = OpenRouteServiceProvider(api_key="k", session=session)
        provider.get_route(LA, VEGAS)
        provider.get_route(VEGAS, LA)
        self.assertEqual(len(session.calls), 2)


class StaticProviderTests(SimpleTestCase):
    def test_is_always_configured(self):
        self.assertTrue(StaticRouteProvider().is_configured())

    def test_produces_a_usable_route_without_a_network(self):
        route = StaticRouteProvider(segments=20).get_route(LA, VEGAS)
        self.assertEqual(route.provider, "static")
        self.assertEqual(len(route.points), 21)
        self.assertAlmostEqual(
            route.cumulative_miles[-1], route.distance_miles, places=6
        )
        # ~228 mi great-circle, inflated by the 1.2 winding factor.
        self.assertAlmostEqual(route.distance_miles, 274, delta=10)

    def test_endpoints_are_exact(self):
        route = StaticRouteProvider(segments=10).get_route(LA, VEGAS)
        self.assertAlmostEqual(route.points[0].lat, LA.lat, places=6)
        self.assertAlmostEqual(route.points[-1].lng, VEGAS.lng, places=6)


class RegistryTests(SimpleTestCase):
    def setUp(self):
        reset_route_provider_cache()
        self.addCleanup(reset_route_provider_cache)

    @override_settings(ROUTE_PROVIDER="api.routing.static.StaticRouteProvider")
    def test_resolves_the_configured_provider(self):
        self.assertIsInstance(get_route_provider(), StaticRouteProvider)

    def test_explicit_dotted_path_wins(self):
        provider = get_route_provider("api.routing.static.StaticRouteProvider")
        self.assertEqual(provider.name, "static")

    @override_settings(ROUTE_PROVIDER="api.routing.does_not_exist.Nope")
    def test_an_unknown_provider_fails_loudly(self):
        with self.assertRaises(ImportError):
            get_route_provider()
