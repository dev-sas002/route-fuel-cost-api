"""OpenRouteService implementation of :class:`~api.routing.base.RouteProvider`.

Responses are cached: ORS is rate-limited and a route between two fixed points
does not change minute to minute, so repeated planning requests (the common
case when a caller tweaks MPG or tank range) hit the cache rather than the
network.
"""

from __future__ import annotations

import hashlib
import logging

import polyline
import requests
from django.conf import settings
from django.core.cache import cache

from api.domain.errors import (
    RouteNotFound,
    RoutingProviderError,
    RoutingProviderNotConfigured,
    RoutingProviderTimeout,
)
from api.domain.geo import cumulative_miles, rescale, to_geo_points
from api.domain.types import GeoPoint, Route

logger = logging.getLogger(__name__)

METRES_PER_MILE = 1609.344


class OpenRouteServiceProvider:
    """Driving directions from the OpenRouteService Directions API."""

    name = "openrouteservice"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        url: str | None = None,
        timeout: float | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.ORS_API_KEY
        self._url = url or settings.ORS_URL
        self._timeout = timeout if timeout is not None else settings.ORS_TIMEOUT_SECONDS
        self._session = session or requests

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def get_route(self, start: GeoPoint, end: GeoPoint) -> Route:
        if not self.is_configured():
            raise RoutingProviderNotConfigured(
                "ORS_API_KEY is not set. Set it, or point ROUTE_PROVIDER at "
                "api.routing.static.StaticRouteProvider to run offline."
            )

        cache_key = self._cache_key(start, end)
        payload = cache.get(cache_key)
        if payload is None:
            payload = self._fetch(start, end)
            ttl = settings.ROUTE_CACHE_SECONDS
            if ttl > 0:
                cache.set(cache_key, payload, ttl)
        return self._to_route(payload)

    # -- internals ---------------------------------------------------------

    def _cache_key(self, start: GeoPoint, end: GeoPoint) -> str:
        # Coordinates are rounded to ~11 m before hashing so that jitter in the
        # caller's input still hits the same cached route.
        raw = "|".join(
            (
                self._url,
                f"{start.lat:.4f},{start.lng:.4f}",
                f"{end.lat:.4f},{end.lng:.4f}",
            )
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"ors:route:{digest}"

    def _fetch(self, start: GeoPoint, end: GeoPoint) -> dict:
        try:
            response = self._session.post(
                self._url,
                headers={
                    "Authorization": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "coordinates": [list(start.as_lng_lat()), list(end.as_lng_lat())]
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as exc:
            raise RoutingProviderTimeout(
                f"OpenRouteService did not respond within {self._timeout}s."
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.warning("OpenRouteService request failed: %s", exc)
            raise RoutingProviderError(
                f"OpenRouteService request failed: {exc}"
            ) from exc
        except ValueError as exc:  # malformed JSON
            raise RoutingProviderError(
                "OpenRouteService returned a malformed response."
            ) from exc

    def _to_route(self, payload: dict) -> Route:
        routes = payload.get("routes") or []
        if not routes:
            raise RouteNotFound("OpenRouteService found no drivable route.")

        best = routes[0]
        summary = best.get("summary") or {}
        geometry = best.get("geometry")
        if not geometry:
            raise RouteNotFound("OpenRouteService returned a route with no geometry.")

        decoded = polyline.decode(geometry, settings.ORS_POLYLINE_PRECISION)
        if len(decoded) < 2:
            raise RouteNotFound("OpenRouteService returned a degenerate route.")

        points = to_geo_points(decoded)
        running = cumulative_miles(points)
        distance_miles = float(summary.get("distance", 0.0)) / METRES_PER_MILE
        if distance_miles <= 0:
            distance_miles = running[-1]

        return Route(
            points=points,
            cumulative_miles=tuple(rescale(running, distance_miles)),
            distance_miles=distance_miles,
            duration_seconds=summary.get("duration"),
            provider=self.name,
        )
