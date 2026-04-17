"""Application service: the one place the three pieces are wired together.

Views stay thin because this object owns the orchestration — fetch a route,
project stations onto it, optimise the stops — and each collaborator is
injectable, so the service can be tested without a network, a database, or an
HTTP request.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from api.domain.errors import NoFuelStationsAvailable
from api.domain.geo import downsample
from api.domain.types import FuelPlan, GeoPoint, Route
from api.optimizer import plan_fuel_stops
from api.routing import RouteProvider, get_route_provider
from api.stations import StationIndex, get_station_index


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """Everything the API needs to answer one planning request."""

    route: Route
    plan: FuelPlan
    corridor_miles: float
    vehicle_mpg: float
    tank_range_miles: float


class FuelRoutePlanner:
    """Plans a route and the cheapest fuel stops along it."""

    def __init__(
        self,
        *,
        route_provider: RouteProvider | None = None,
        station_index: StationIndex | None = None,
    ) -> None:
        self._route_provider = route_provider
        self._station_index = station_index

    @property
    def route_provider(self) -> RouteProvider:
        return (
            get_route_provider()
            if self._route_provider is None
            else self._route_provider
        )

    @property
    def station_index(self) -> StationIndex:
        return (
            get_station_index() if self._station_index is None else self._station_index
        )

    def plan(
        self,
        *,
        start: GeoPoint,
        end: GeoPoint,
        vehicle_mpg: float,
        tank_range_miles: float,
        corridor_miles: float | None = None,
    ) -> RoutePlan:
        """Compute the route and its optimal fuel stops.

        Raises:
            RoutingProviderError / RouteNotFound: propagated from the provider.
            NoFuelStationsAvailable: the route needs at least one stop but no
                station lies within the corridor.
            UnreachableDestination: some stretch is longer than the tank range.
        """
        corridor = (
            corridor_miles
            if corridor_miles is not None
            else settings.FUEL_STOP_CORRIDOR_MILES
        )
        route = self.route_provider.get_route(start, end)
        candidates = self.station_index.candidates_along_route(
            route,
            corridor_miles=corridor,
            sample_spacing_miles=settings.ROUTE_SAMPLE_SPACING_MILES,
        )
        if not candidates and route.distance_miles > tank_range_miles:
            raise NoFuelStationsAvailable(
                f"The route is {route.distance_miles:.1f} miles but no fuel "
                f"station is known within {corridor:.0f} miles of it."
            )

        plan = plan_fuel_stops(
            candidates,
            route_distance_miles=route.distance_miles,
            tank_range_miles=tank_range_miles,
            vehicle_mpg=vehicle_mpg,
        )
        return RoutePlan(
            route=route,
            plan=plan,
            corridor_miles=corridor,
            vehicle_mpg=vehicle_mpg,
            tank_range_miles=tank_range_miles,
        )


def route_points_for_response(route: Route) -> list[list[float]]:
    """Thin the polyline to a bounded number of ``[lat, lng]`` pairs."""
    points = downsample(route.points, settings.MAX_ROUTE_POINTS_RETURNED)
    return [[point.lat, point.lng] for point in points]
