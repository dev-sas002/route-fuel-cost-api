"""Cost-optimal fuel-stop planning.

This module is the heart of the service. Everything else — the routing client,
the station index, the views — exists to feed it.

The problem
-----------
Once stations have been projected onto the route (see
:mod:`api.stations.index`), the geography is gone and what remains is a
one-dimensional instance of the classic **gas station problem**:

    Drive from mile 0 to mile *D*. The tank holds *R* miles worth of fuel and
    starts full. At mile ``p_i`` fuel can be bought at ``c_i`` dollars per
    gallon, in any quantity, subject to the tank capacity. Minimise the money
    spent.

Because fuel is divisible (you can buy 3.7 gallons), the problem has an optimal
greedy solution — no dynamic programme is needed.

The algorithm
-------------
Stand at station *i* holding ``f`` miles of range, and let *W* be the set of
stations reachable on a full tank, i.e. those with ``p_j - p_i <= R``.

1. If some station in *W* costs no more than ``c_i``, let *j* be the **first**
   such station. Buy exactly enough to reach it — ``max(0, (p_j - p_i) - f)`` —
   and drive there. Buying more here would mean carrying expensive fuel past an
   equally good or cheaper pump; buying less would strand the vehicle. (Using
   "no more expensive" rather than "strictly cheaper" is what keeps the plan
   from making a pointless stop at the first of several identically priced
   stations.)
2. Otherwise every reachable station is strictly more expensive than ``c_i``, so
   ``c_i`` is the cheapest price available for the whole window. **Fill the
   tank** and drive to the cheapest station in *W* (the farthest one, on a tie,
   which costs nothing extra and yields fewer stops).

The destination is modelled as a sentinel station at mile *D* priced at $0, so
rule 1 naturally handles the final leg: once the destination is in range it is
strictly the cheapest thing in the window, and the vehicle buys exactly enough
fuel to arrive — never a full tank it will not burn. The origin is a sentinel
priced at infinity, which encodes "you cannot buy fuel here"; the starting tank
is free, and rule 1 makes the vehicle coast to the first reachable station and
buy nothing if it does not need to.

Why it is optimal
-----------------
Total fuel burned is fixed at ``D / mpg`` gallons regardless of the plan, so
minimising cost means buying each gallon at the lowest price that can physically
deliver it to the point where it is burned. Rule 1 never carries a gallon past a
cheaper pump; rule 2 fills up only when no cheaper pump is reachable, so every
gallon bought is bought at the cheapest price able to reach its point of use. An
exchange argument on any optimal plan that deviates from these two rules
converts it into the greedy plan without increasing cost.

Complexity
----------
With *n* candidate stops:

* ``next_no_more_expensive`` — the first station after each one that does not
  cost more — is computed once with a monotonic stack in **O(n)**.
* A sparse table over prices answers "cheapest station in ``[l, r]``" in
  **O(1)** after an **O(n log n)** build.
* The window edge is found by binary search, **O(log n)** per step, and each
  step moves strictly forward, so there are at most *n* steps.

Total: **O(n log n)** time, **O(n log n)** memory. The naive alternative —
rescanning the window at every station — is O(n·|W|), quadratic when the tank
range is large relative to station spacing, which is exactly the cross-country
case.

Edge cases
----------
* **Route shorter than one tank** — the destination is in range from mile 0, no
  purchase is made and the trip costs $0 (the starting tank is not charged for).
* **No station within range** — if the next reachable fuelling opportunity is
  farther than *R*, :class:`~api.domain.errors.UnreachableDestination` is raised
  naming the gap, rather than silently returning an infeasible plan.
* **Tank smaller than the gap between stations** — the same check catches it,
  including the gap between the last station and the destination.
* **Equally cheap options** — resolved deterministically to the farthest
  station, so the same request always returns the same plan and no redundant
  stop is made.
* **Duplicate stations at one mile marker** — harmless; ties are broken by
  index.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from math import inf

from api.domain.errors import UnreachableDestination
from api.domain.types import CandidateStop, FuelPlan, FuelPurchase

#: Tolerance in miles for floating-point comparisons of distances.
EPSILON = 1e-9


class _SparseMinTable:
    """Static range-minimum over prices, returning the *farthest* index on ties.

    Build ``O(n log n)``, query ``O(1)``. Ties resolve to the larger index so
    that equally priced options produce the plan with fewer stops.
    """

    __slots__ = ("_log", "_prices", "_table")

    def __init__(self, prices: Sequence[float]) -> None:
        self._prices = prices
        size = len(prices)
        self._log = [0] * (size + 1)
        for i in range(2, size + 1):
            self._log[i] = self._log[i >> 1] + 1
        self._table: list[list[int]] = [list(range(size))]
        level = 1
        while (1 << level) <= size:
            span = 1 << level
            previous = self._table[level - 1]
            current = [0] * (size - span + 1)
            half = span >> 1
            for i in range(size - span + 1):
                current[i] = self._better(previous[i], previous[i + half])
            self._table.append(current)
            level += 1

    def _better(self, left: int, right: int) -> int:
        if self._prices[right] <= self._prices[left]:
            return right
        return left

    def argmin(self, low: int, high: int) -> int:
        """Index of the cheapest price in the inclusive range ``[low, high]``."""
        if low > high:
            raise ValueError("empty range")
        level = self._log[high - low + 1]
        span = 1 << level
        return self._better(
            self._table[level][low], self._table[level][high - span + 1]
        )


def _next_no_more_expensive(prices: Sequence[float]) -> list[int]:
    """For each index, the next index priced at or below it (or ``len``).

    Single monotonic stack pass, ``O(n)``. Equal prices count as "no more
    expensive" so the optimiser defers a purchase to the last of a run of
    identically priced stations instead of stopping at the first.
    """
    size = len(prices)
    result = [size] * size
    stack: list[int] = []
    for index, price in enumerate(prices):
        while stack and prices[stack[-1]] >= price:
            result[stack.pop()] = index
        stack.append(index)
    return result


def plan_fuel_stops(
    candidates: Sequence[CandidateStop],
    *,
    route_distance_miles: float,
    tank_range_miles: float,
    vehicle_mpg: float,
    start_range_miles: float | None = None,
) -> FuelPlan:
    """Return the cheapest sequence of fuel stops for a route.

    Args:
        candidates: Stations already projected onto the route. Order does not
            matter; stops outside ``[0, route_distance_miles]`` are ignored.
        route_distance_miles: Total driving distance.
        tank_range_miles: Miles the vehicle can travel on a full tank.
        vehicle_mpg: Miles per gallon, used to convert range into gallons.
        start_range_miles: Range in the tank at the origin. Defaults to a full
            tank, which is not charged for.

    Raises:
        ValueError: If the vehicle parameters are not positive.
        UnreachableDestination: If some stretch of the route is longer than the
            tank range.
    """
    if tank_range_miles <= 0:
        raise ValueError("tank_range_miles must be positive")
    if vehicle_mpg <= 0:
        raise ValueError("vehicle_mpg must be positive")
    if route_distance_miles < 0:
        raise ValueError("route_distance_miles must not be negative")

    fuel = tank_range_miles if start_range_miles is None else start_range_miles
    fuel = max(0.0, min(fuel, tank_range_miles))

    usable = sorted(
        (
            candidate
            for candidate in candidates
            if -EPSILON <= candidate.route_miles <= route_distance_miles + EPSILON
        ),
        key=lambda candidate: (
            candidate.route_miles,
            candidate.station.price_per_gallon,
        ),
    )

    # Sentinels: origin priced at infinity ("no pump here"), destination priced
    # at zero so the final leg falls out of rule 1.
    positions: list[float] = [0.0]
    prices: list[float] = [inf]
    stops: list[CandidateStop | None] = [None]
    for candidate in usable:
        positions.append(min(route_distance_miles, max(0.0, candidate.route_miles)))
        prices.append(float(candidate.station.price_per_gallon))
        stops.append(candidate)
    positions.append(route_distance_miles)
    prices.append(0.0)
    stops.append(None)

    destination = len(positions) - 1
    next_no_worse = _next_no_more_expensive(prices)
    cheapest_in_range = _SparseMinTable(prices)

    purchases: list[FuelPurchase] = []
    total_cost = 0.0
    total_gallons = 0.0

    index = 0
    while index < destination:
        price = prices[index]
        # At the origin we cannot buy, so our reach is whatever is in the tank.
        reach = fuel if price == inf else tank_range_miles
        window_end = bisect_right(positions, positions[index] + reach + EPSILON) - 1
        if window_end <= index:
            raise UnreachableDestination(
                "No fuel stop is reachable between mile "
                f"{positions[index]:.1f} and mile {positions[index + 1]:.1f}: "
                f"the {positions[index + 1] - positions[index]:.1f} mile gap "
                f"exceeds the {tank_range_miles:.1f} mile tank range.",
                from_miles=positions[index],
                to_miles=positions[index + 1],
                tank_range_miles=tank_range_miles,
            )

        no_worse = next_no_worse[index]
        if no_worse <= window_end:
            # Rule 1: buy the minimum needed to reach the next pump that costs
            # no more than this one.
            target = no_worse
            buy = max(0.0, (positions[target] - positions[index]) - fuel)
        else:
            # Rule 2: everything reachable is dearer, so fill up here.
            target = cheapest_in_range.argmin(index + 1, window_end)
            buy = max(0.0, tank_range_miles - fuel)

        if buy > EPSILON:
            stop = stops[index]
            if stop is None:  # pragma: no cover - guarded by the reach logic
                raise AssertionError("attempted to buy fuel at a sentinel node")
            gallons = buy / vehicle_mpg
            cost = gallons * price
            purchases.append(
                FuelPurchase(
                    stop=stop,
                    gallons=gallons,
                    cost=cost,
                    range_added_miles=buy,
                    arrival_range_miles=fuel,
                )
            )
            total_cost += cost
            total_gallons += gallons
            fuel += buy

        fuel = max(0.0, fuel - (positions[target] - positions[index]))
        index = target

    return FuelPlan(
        purchases=tuple(purchases),
        total_cost=total_cost,
        total_gallons=total_gallons,
        candidates_considered=len(usable),
    )
