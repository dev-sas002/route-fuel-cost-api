"""Domain errors.

These are plain exceptions with no DRF dependency; ``api.exception_handlers``
translates them into HTTP responses. Dependencies point inward: the domain does
not know it is being served over HTTP.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error this application raises deliberately."""

    #: Short machine-readable code included in the JSON error body.
    code = "domain_error"


class RoutingProviderError(DomainError):
    """The upstream routing provider failed."""

    code = "routing_provider_error"


class RoutingProviderNotConfigured(RoutingProviderError):
    """The routing provider is missing credentials or configuration."""

    code = "routing_provider_not_configured"


class RoutingProviderTimeout(RoutingProviderError):
    """The routing provider did not answer in time."""

    code = "routing_provider_timeout"


class RouteNotFound(DomainError):
    """The provider answered, but no drivable route connects the two points."""

    code = "route_not_found"


class NoFuelStationsAvailable(DomainError):
    """No known fuel station lies within the search corridor of the route."""

    code = "no_fuel_stations_available"


class UnreachableDestination(DomainError):
    """The vehicle cannot complete the route with the given tank range.

    Raised when the gap between two consecutive reachable fuelling
    opportunities exceeds the tank range.
    """

    code = "unreachable_destination"

    def __init__(
        self,
        message: str,
        *,
        from_miles: float,
        to_miles: float,
        tank_range_miles: float,
    ) -> None:
        super().__init__(message)
        self.from_miles = from_miles
        self.to_miles = to_miles
        self.tank_range_miles = tank_range_miles

    @property
    def gap_miles(self) -> float:
        return self.to_miles - self.from_miles
