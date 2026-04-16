"""Framework-free domain layer: value objects, geometry helpers and errors.

Nothing in this package imports Django. That is deliberate — the routing
client, the station index and the optimiser are all expressed in terms of these
types, which keeps them unit-testable without a database or an HTTP request.
"""

from .errors import (
    DomainError,
    NoFuelStationsAvailable,
    RouteNotFound,
    RoutingProviderError,
    RoutingProviderNotConfigured,
    RoutingProviderTimeout,
    UnreachableDestination,
)
from .types import (
    CandidateStop,
    FuelPlan,
    FuelPurchase,
    GeoPoint,
    Route,
    Station,
)

__all__ = [
    "CandidateStop",
    "DomainError",
    "FuelPlan",
    "FuelPurchase",
    "GeoPoint",
    "NoFuelStationsAvailable",
    "Route",
    "RouteNotFound",
    "RoutingProviderError",
    "RoutingProviderNotConfigured",
    "RoutingProviderTimeout",
    "Station",
    "UnreachableDestination",
]
