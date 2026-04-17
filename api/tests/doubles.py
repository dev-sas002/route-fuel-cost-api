"""Test doubles.

Every collaborator that would otherwise touch the network has a double here.
**No test in this project makes a real OpenRouteService call** — ORS is a keyed,
rate-limited service, and a suite that depends on it is neither hermetic nor
free.
"""

from __future__ import annotations

from api.domain.errors import RoutingProviderError
from api.domain.geo import cumulative_miles, rescale
from api.domain.types import CandidateStop, GeoPoint, Route, Station


def make_route(
    points: list[tuple[float, float]],
    distance_miles: float | None = None,
    *,
    provider: str = "fake",
) -> Route:
    """Build a :class:`Route` from ``(lat, lng)`` pairs."""
    geo_points = tuple(GeoPoint(lat=lat, lng=lng) for lat, lng in points)
    running = cumulative_miles(geo_points)
    total = distance_miles if distance_miles is not None else running[-1]
    return Route(
        points=geo_points,
        cumulative_miles=tuple(rescale(running, total)),
        distance_miles=total,
        duration_seconds=None,
        provider=provider,
    )


def make_station(
    station_id: int,
    price: float,
    *,
    lat: float = 0.0,
    lng: float = 0.0,
    name: str | None = None,
) -> Station:
    return Station(
        id=station_id,
        name=name or f"Station {station_id}",
        location=GeoPoint(lat=lat, lng=lng),
        price_per_gallon=price,
        city="Testville",
        state="TS",
        fuel_type="Regular",
    )


def make_stop(
    route_miles: float, price: float, station_id: int | None = None
) -> CandidateStop:
    """A candidate already projected onto the route, for optimiser tests."""
    identifier = station_id if station_id is not None else int(route_miles * 1000)
    return CandidateStop(
        station=make_station(identifier, price),
        route_miles=float(route_miles),
        detour_miles=0.0,
    )


class FakeRouteProvider:
    """A provider that returns a canned straight-line route.

    Selected in tests via ``ROUTE_PROVIDER=api.tests.doubles.FakeRouteProvider``.
    """

    name = "fake"

    #: Miles reported for any request; kept as a class attribute so tests can
    #: tune it without reaching into the instance the view constructs.
    distance_miles = 900.0
    segments = 90

    def is_configured(self) -> bool:
        return True

    def get_route(self, start: GeoPoint, end: GeoPoint) -> Route:
        points = [
            (
                start.lat + (end.lat - start.lat) * step / self.segments,
                start.lng + (end.lng - start.lng) * step / self.segments,
            )
            for step in range(self.segments + 1)
        ]
        return make_route(points, self.distance_miles, provider=self.name)


class BrokenRouteProvider:
    """A provider that always fails upstream."""

    name = "broken"

    def is_configured(self) -> bool:
        return True

    def get_route(self, start: GeoPoint, end: GeoPoint) -> Route:
        raise RoutingProviderError("upstream exploded")


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload, status_code: int = 200, exc: Exception | None = None):
        self._payload = payload
        self.status_code = status_code
        self._exc = exc

    def raise_for_status(self) -> None:
        if self._exc is not None:
            raise self._exc

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Records calls and replays queued responses."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if not self._responses:
            raise AssertionError("FakeSession ran out of queued responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
