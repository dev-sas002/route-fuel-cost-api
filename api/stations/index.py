"""Spatial index over fuel stations, and projection of stations onto a route.

The original implementation ran one bounding-box query per polyline segment
whenever the tank was low, then scanned the results in Python. On a
cross-country route that is tens of thousands of database round-trips for data
that changes once a day.

This module does the opposite: load the catalogue once, bucket it into a
uniform latitude/longitude grid, and answer neighbourhood queries from memory.

Grid
----
Stations are bucketed by ``(floor(lat / cell), floor(lng / cell))`` with a
half-degree cell (~35 miles) by default. A radius query touches only the cells
overlapping the query's bounding box, so the work is proportional to the
stations actually nearby rather than to the size of the catalogue.

Projecting stations onto a route
--------------------------------
For each vertex sampled along the route (every ``sample_spacing_miles``, not
every vertex — a provider's vertex density is arbitrary), collect stations
within the corridor and keep, per station, the sample where it is closest. That
sample's cumulative distance becomes the station's position along the route.

Cost is ``O(V + S + K·B)``: ``V`` route vertices to sample, ``S`` stations to
bucket, ``K`` samples each touching ``B`` nearby stations — against ``O(V·S)``
for the naive scan.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from api.domain.geo import (
    haversine_miles,
    latitude_degrees_for_miles,
    longitude_degrees_for_miles,
    sample_indices,
)
from api.domain.types import CandidateStop, GeoPoint, Route, Station

DEFAULT_CELL_DEGREES = 0.5


class StationIndex:
    """An in-memory uniform-grid index over a station catalogue."""

    __slots__ = ("_cell", "_grid", "_stations")

    def __init__(
        self,
        stations: Iterable[Station],
        *,
        cell_degrees: float = DEFAULT_CELL_DEGREES,
    ) -> None:
        if cell_degrees <= 0:
            raise ValueError("cell_degrees must be positive")
        self._cell = cell_degrees
        self._stations: list[Station] = list(stations)
        self._grid: dict[tuple[int, int], list[Station]] = {}
        for station in self._stations:
            self._grid.setdefault(self._cell_of(station.location), []).append(station)

    def __len__(self) -> int:
        return len(self._stations)

    @property
    def cell_count(self) -> int:
        """Number of occupied grid cells; useful for tuning ``cell_degrees``."""
        return len(self._grid)

    @property
    def stations(self) -> Sequence[Station]:
        return self._stations

    def _cell_of(self, point: GeoPoint) -> tuple[int, int]:
        return (
            math.floor(point.lat / self._cell),
            math.floor(point.lng / self._cell),
        )

    def near(self, point: GeoPoint, radius_miles: float) -> list[Station]:
        """Stations within ``radius_miles`` of ``point``.

        Cells overlapping the bounding box are gathered first (cheap integer
        arithmetic), then each candidate is checked with haversine.
        """
        if radius_miles <= 0 or not self._grid:
            return []
        lat_span = latitude_degrees_for_miles(radius_miles)
        lng_span = longitude_degrees_for_miles(radius_miles, point.lat)

        lat_lo = math.floor((point.lat - lat_span) / self._cell)
        lat_hi = math.floor((point.lat + lat_span) / self._cell)
        lng_lo = math.floor((point.lng - lng_span) / self._cell)
        lng_hi = math.floor((point.lng + lng_span) / self._cell)

        found: list[Station] = []
        for lat_cell in range(lat_lo, lat_hi + 1):
            for lng_cell in range(lng_lo, lng_hi + 1):
                for station in self._grid.get((lat_cell, lng_cell), ()):
                    if haversine_miles(point, station.location) <= radius_miles:
                        found.append(station)
        return found

    def candidates_along_route(
        self,
        route: Route,
        *,
        corridor_miles: float,
        sample_spacing_miles: float = 5.0,
    ) -> list[CandidateStop]:
        """Project every station within the corridor onto the route.

        Returns stops ordered by distance from the origin, each annotated with
        the detour (straight-line miles from the route to the station).
        """
        if corridor_miles <= 0 or not self._grid:
            return []

        # A station within ``corridor_miles`` of the route lies within
        # ``corridor_miles + spacing/2`` of some sampled vertex, so the search
        # radius is widened to keep the sampling lossless.
        search_radius = corridor_miles + sample_spacing_miles / 2.0

        best: dict[int, tuple[float, float]] = {}
        stations_by_id: dict[int, Station] = {}
        for index in sample_indices(route.cumulative_miles, sample_spacing_miles):
            vertex = route.points[index]
            position = route.cumulative_miles[index]
            for station in self.near(vertex, search_radius):
                detour = haversine_miles(vertex, station.location)
                previous = best.get(station.id)
                if previous is None or detour < previous[0]:
                    best[station.id] = (detour, position)
                    stations_by_id[station.id] = station

        stops = [
            CandidateStop(
                station=stations_by_id[station_id],
                route_miles=position,
                detour_miles=detour,
            )
            for station_id, (detour, position) in best.items()
            if detour <= corridor_miles
        ]
        stops.sort(key=lambda stop: (stop.route_miles, stop.station.price_per_gallon))
        return stops
