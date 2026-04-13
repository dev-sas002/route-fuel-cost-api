"""Measure the two hot paths: station lookup and fuel-stop optimisation.

The numbers quoted in the README's "Design notes" come from this command, so
anyone can reproduce them:

    python manage.py benchmark_planner

It uses synthetic data and the offline routing provider, so it needs no
database, no network and no OpenRouteService key.
"""

from __future__ import annotations

import random
import time

from django.core.management.base import BaseCommand

from api.domain.geo import haversine_miles
from api.domain.types import CandidateStop, GeoPoint, Station
from api.optimizer import plan_fuel_stops
from api.routing.static import StaticRouteProvider
from api.stations.index import StationIndex

LOS_ANGELES = GeoPoint(lat=34.0522, lng=-118.2437)
NEW_YORK = GeoPoint(lat=40.7128, lng=-74.0060)

OPTIMISER_SIZES = (1_000, 10_000, 100_000)
CATALOGUE_SIZES = (1_000, 10_000, 100_000)


def synthetic_stations(count: int, rng: random.Random) -> list[Station]:
    """Stations scattered over the continental United States."""
    return [
        Station(
            id=index,
            name=f"Station {index}",
            location=GeoPoint(
                lat=rng.uniform(25.0, 49.0), lng=rng.uniform(-124.0, -67.0)
            ),
            price_per_gallon=round(rng.uniform(2.50, 5.50), 2),
        )
        for index in range(count)
    ]


def linear_scan(stations, point: GeoPoint, radius_miles: float) -> int:
    return sum(
        1
        for station in stations
        if haversine_miles(point, station.location) <= radius_miles
    )


class Command(BaseCommand):
    help = "Benchmark the station index and the fuel-stop optimiser."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--seed", type=int, default=20260923)
        parser.add_argument("--repeats", type=int, default=5)

    def handle(self, *args, **options) -> None:
        rng = random.Random(options["seed"])
        repeats = options["repeats"]

        self.stdout.write(self.style.MIGRATE_HEADING("Optimiser (plan_fuel_stops)"))
        self.stdout.write(f"{'candidates':>12}  {'best of N (ms)':>15}")
        for size in OPTIMISER_SIZES:
            candidates = [
                CandidateStop(
                    station=Station(
                        id=index,
                        name=f"S{index}",
                        location=GeoPoint(lat=0.0, lng=0.0),
                        price_per_gallon=round(rng.uniform(2.5, 5.5), 2),
                    ),
                    route_miles=index * 2.5,
                    detour_miles=0.0,
                )
                for index in range(size)
            ]
            distance = size * 2.5 + 100
            best = min(
                self._time(
                    plan_fuel_stops,
                    candidates,
                    route_distance_miles=distance,
                    tank_range_miles=500.0,
                    vehicle_mpg=10.0,
                )
                for _ in range(repeats)
            )
            self.stdout.write(f"{size:>12,}  {best * 1000:>15.1f}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Station lookup (50-mile radius)"))
        self.stdout.write(
            f"{'stations':>12}  {'grid (ms)':>11}  {'linear (ms)':>12}  {'speedup':>8}"
        )
        probe = GeoPoint(lat=39.0, lng=-95.0)
        for size in CATALOGUE_SIZES:
            stations = synthetic_stations(size, rng)
            index = StationIndex(stations, cell_degrees=0.5)
            grid = min(self._time(index.near, probe, 50.0) for _ in range(repeats))
            scan = min(
                self._time(linear_scan, stations, probe, 50.0) for _ in range(repeats)
            )
            self.stdout.write(
                f"{size:>12,}  {grid * 1000:>11.3f}  {scan * 1000:>12.3f}  "
                f"{scan / grid if grid else 0:>7.0f}x"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING("End to end (LA to NYC, offline provider)")
        )
        stations = synthetic_stations(100_000, rng)
        index = StationIndex(stations, cell_degrees=0.5)
        route = StaticRouteProvider().get_route(LOS_ANGELES, NEW_YORK)
        build = min(
            self._time(StationIndex, stations, cell_degrees=0.5) for _ in range(repeats)
        )
        match_time, candidates = self._time_result(
            index.candidates_along_route, route, corridor_miles=50.0
        )
        plan_time, plan = self._time_result(
            plan_fuel_stops,
            candidates,
            route_distance_miles=route.distance_miles,
            tank_range_miles=500.0,
            vehicle_mpg=10.0,
        )
        self.stdout.write(f"route distance      : {route.distance_miles:,.1f} miles")
        self.stdout.write(f"catalogue size      : {len(stations):,} stations")
        self.stdout.write(f"index build         : {build * 1000:,.1f} ms")
        self.stdout.write(f"corridor match      : {match_time * 1000:,.1f} ms")
        self.stdout.write(f"candidates found    : {len(candidates):,}")
        self.stdout.write(f"optimise            : {plan_time * 1000:,.1f} ms")
        self.stdout.write(f"fuel stops          : {plan.stop_count}")
        self.stdout.write(f"total fuel cost     : ${plan.total_cost:,.2f}")

    @staticmethod
    def _time(function, *args, **kwargs) -> float:
        start = time.perf_counter()
        function(*args, **kwargs)
        return time.perf_counter() - start

    @staticmethod
    def _time_result(function, *args, **kwargs):
        start = time.perf_counter()
        result = function(*args, **kwargs)
        return time.perf_counter() - start, result
