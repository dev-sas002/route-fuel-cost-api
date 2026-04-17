"""The routing-provider seam.

A provider turns two coordinates into a :class:`~api.domain.types.Route`. That
is the entire contract, and it is the one place the application touches a
third-party service. Implementations live beside this module; the active one is
chosen by the ``ROUTE_PROVIDER`` setting (a dotted path), so swapping
OpenRouteService for Mapbox, Valhalla or an in-house engine is a configuration
change and a new class — no caller changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from api.domain.types import GeoPoint, Route


@runtime_checkable
class RouteProvider(Protocol):
    """Computes a drivable route between two points."""

    #: Stable short name, echoed in the API response and used in cache keys.
    name: str

    def is_configured(self) -> bool:
        """Whether the provider has everything it needs to answer a request."""
        ...

    def get_route(self, start: GeoPoint, end: GeoPoint) -> Route:
        """Return the driving route from ``start`` to ``end``.

        Raises:
            RoutingProviderNotConfigured: Credentials or configuration missing.
            RoutingProviderTimeout: The upstream service did not respond in time.
            RoutingProviderError: Any other upstream failure.
            RouteNotFound: The service answered but found no drivable route.
        """
        ...
