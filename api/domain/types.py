"""Immutable value objects shared by every layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A WGS-84 coordinate in decimal degrees."""

    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"latitude out of range: {self.lat}")
        if not -180.0 <= self.lng <= 180.0:
            raise ValueError(f"longitude out of range: {self.lng}")

    def as_lat_lng(self) -> tuple[float, float]:
        return (self.lat, self.lng)

    def as_lng_lat(self) -> tuple[float, float]:
        """GeoJSON / OpenRouteService coordinate order."""
        return (self.lng, self.lat)


@dataclass(frozen=True, slots=True)
class Route:
    """A drivable route returned by a :class:`~api.routing.base.RouteProvider`.

    ``cumulative_miles[i]`` is the driving distance from the origin to
    ``points[i]``, rescaled so that ``cumulative_miles[-1]`` equals
    ``distance_miles`` (the authoritative figure reported by the provider).
    """

    points: tuple[GeoPoint, ...]
    cumulative_miles: tuple[float, ...]
    distance_miles: float
    duration_seconds: float | None = None
    provider: str = "unknown"

    def __post_init__(self) -> None:
        if len(self.points) != len(self.cumulative_miles):
            raise ValueError("points and cumulative_miles must be the same length")
        if len(self.points) < 2:
            raise ValueError("a route needs at least two points")


@dataclass(frozen=True, slots=True)
class Station:
    """A fuel station with a posted price."""

    id: int
    name: str
    location: GeoPoint
    price_per_gallon: float
    city: str = ""
    state: str = ""
    fuel_type: str = ""
    address: str = ""


@dataclass(frozen=True, slots=True)
class CandidateStop:
    """A station projected onto the route.

    ``route_miles`` is how far along the route the station sits; ``detour_miles``
    is the straight-line distance from the route to the station itself.
    """

    station: Station
    route_miles: float
    detour_miles: float


@dataclass(frozen=True, slots=True)
class FuelPurchase:
    """Fuel bought at one stop."""

    stop: CandidateStop
    gallons: float
    cost: float
    range_added_miles: float
    arrival_range_miles: float


@dataclass(frozen=True, slots=True)
class FuelPlan:
    """The result of the optimiser."""

    purchases: tuple[FuelPurchase, ...] = field(default_factory=tuple)
    total_cost: float = 0.0
    total_gallons: float = 0.0
    candidates_considered: int = 0

    @property
    def stop_count(self) -> int:
        return len(self.purchases)
