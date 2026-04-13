"""An offline routing provider.

This is the reference implementation of the :class:`RouteProvider` seam: it
interpolates a great-circle path between the two points and inflates the
distance by a constant "winding factor" to approximate road distance. It makes
no network calls, which means the API, the browsable DRF interface and the test
suite all work with no OpenRouteService key.

It is not a substitute for real directions — it ignores roads entirely — and
the API response labels the provider so a caller always knows which one
answered. Select it with ``ROUTE_PROVIDER=api.routing.static.StaticRouteProvider``.
"""

from __future__ import annotations

from api.domain.geo import cumulative_miles, haversine_miles, rescale
from api.domain.types import GeoPoint, Route

#: Typical ratio of road distance to great-circle distance for US interstates.
DEFAULT_WINDING_FACTOR = 1.2

#: Interpolated vertices, enough to place stations along a long route.
DEFAULT_SEGMENTS = 200


class StaticRouteProvider:
    """Great-circle "route" between two points; no external service."""

    name = "static"

    def __init__(
        self,
        *,
        winding_factor: float | None = None,
        segments: int | None = None,
    ) -> None:
        self._winding_factor = winding_factor or DEFAULT_WINDING_FACTOR
        self._segments = segments or DEFAULT_SEGMENTS

    def is_configured(self) -> bool:
        return True

    def get_route(self, start: GeoPoint, end: GeoPoint) -> Route:
        segments = max(2, self._segments)
        points = tuple(
            GeoPoint(
                lat=start.lat + (end.lat - start.lat) * (step / segments),
                lng=start.lng + (end.lng - start.lng) * (step / segments),
            )
            for step in range(segments + 1)
        )
        straight_line = haversine_miles(start, end)
        distance_miles = straight_line * self._winding_factor
        running = cumulative_miles(points)
        return Route(
            points=points,
            cumulative_miles=tuple(rescale(running, distance_miles)),
            distance_miles=distance_miles,
            duration_seconds=None,
            provider=self.name,
        )
