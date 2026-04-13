"""The fuel-stop optimiser.

Two kinds of test live here: hand-written cases that pin down the documented
behaviour and the edge cases, and a randomised cross-check against an
exhaustive dynamic programme that proves the greedy really is optimal.
"""

from __future__ import annotations

import random
from functools import cache

from django.test import SimpleTestCase

from api.domain.errors import UnreachableDestination
from api.optimizer import plan_fuel_stops
from api.optimizer.fuel import _next_no_more_expensive, _SparseMinTable
from api.tests.doubles import make_stop


def plan(stops, distance, tank, mpg=10.0):
    return plan_fuel_stops(
        stops,
        route_distance_miles=distance,
        tank_range_miles=tank,
        vehicle_mpg=mpg,
    )


class ValidationTests(SimpleTestCase):
    def test_rejects_non_positive_tank_range(self):
        with self.assertRaises(ValueError):
            plan([], distance=10, tank=0)

    def test_rejects_non_positive_mpg(self):
        with self.assertRaises(ValueError):
            plan([], distance=10, tank=100, mpg=0)

    def test_rejects_negative_distance(self):
        with self.assertRaises(ValueError):
            plan([], distance=-1, tank=100)


class ShortRouteTests(SimpleTestCase):
    def test_route_shorter_than_one_tank_needs_no_stops(self):
        result = plan([make_stop(100, 3.00)], distance=400, tank=500)
        self.assertEqual(result.stop_count, 0)
        self.assertEqual(result.total_cost, 0.0)
        self.assertEqual(result.total_gallons, 0.0)

    def test_route_exactly_one_tank_long_needs_no_stops(self):
        result = plan([make_stop(100, 3.00)], distance=500, tank=500)
        self.assertEqual(result.stop_count, 0)

    def test_route_with_no_stations_and_no_stops_needed(self):
        result = plan([], distance=100, tank=500)
        self.assertEqual(result.stop_count, 0)


class GreedyRuleTests(SimpleTestCase):
    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        # Full tank of 100 covers mile 0-100. At mile 100 ($5) the cheaper pump
        # at mile 150 ($2) is in range, so buy exactly 50 miles of range there.
        stops = [make_stop(100, 5.00), make_stop(150, 2.00)]
        result = plan(stops, distance=250, tank=100, mpg=10)

        self.assertEqual(result.stop_count, 2)
        first, second = result.purchases
        self.assertEqual(first.stop.route_miles, 100)
        self.assertAlmostEqual(first.range_added_miles, 50.0)
        self.assertAlmostEqual(first.cost, 50 / 10 * 5.00)
        # At the cheap pump only the remaining 100 miles are bought, not a full tank.
        self.assertAlmostEqual(second.range_added_miles, 100.0)
        self.assertAlmostEqual(result.total_cost, 25.0 + 20.0)

    def test_fills_up_when_nothing_cheaper_is_reachable(self):
        # At mile 100 ($2) everything in range costs more, so fill the tank.
        stops = [make_stop(100, 2.00), make_stop(150, 5.00), make_stop(190, 4.00)]
        result = plan(stops, distance=280, tank=100, mpg=10)

        first = result.purchases[0]
        self.assertEqual(first.stop.route_miles, 100)
        self.assertAlmostEqual(first.range_added_miles, 100.0)

    def test_skips_an_expensive_station_it_does_not_need(self):
        stops = [make_stop(50, 9.99), make_stop(450, 1.00)]
        result = plan(stops, distance=800, tank=500, mpg=10)
        self.assertEqual([p.stop.route_miles for p in result.purchases], [450])

    def test_never_buys_more_than_the_tank_holds(self):
        stops = [make_stop(mile, 3.00) for mile in (90, 180, 270)]
        result = plan(stops, distance=350, tank=100, mpg=10)
        for purchase in result.purchases:
            self.assertLessEqual(
                purchase.arrival_range_miles + purchase.range_added_miles, 100 + 1e-9
            )

    def test_buys_no_more_than_needed_to_finish(self):
        # Arriving at mile 400 with an empty tank, only 100 miles are left.
        stops = [make_stop(400, 3.00)]
        result = plan(stops, distance=500, tank=400, mpg=10)
        self.assertEqual(result.stop_count, 1)
        self.assertAlmostEqual(result.purchases[0].range_added_miles, 100.0)
        self.assertAlmostEqual(result.total_gallons, 10.0)


class TieBreakingTests(SimpleTestCase):
    def test_equal_prices_resolve_to_the_farthest_station(self):
        stops = [make_stop(60, 3.00), make_stop(80, 3.00), make_stop(100, 3.00)]
        result = plan(stops, distance=200, tank=100, mpg=10)
        self.assertEqual([p.stop.route_miles for p in result.purchases], [100])

    def test_result_is_deterministic_regardless_of_input_order(self):
        stops = [make_stop(60, 3.00), make_stop(80, 3.00), make_stop(100, 3.00)]
        forward = plan(stops, distance=200, tank=100)
        backward = plan(list(reversed(stops)), distance=200, tank=100)
        self.assertEqual(
            [p.stop.station.id for p in forward.purchases],
            [p.stop.station.id for p in backward.purchases],
        )


class UnreachableTests(SimpleTestCase):
    def test_gap_between_stations_wider_than_the_tank(self):
        stops = [make_stop(100, 3.00), make_stop(400, 3.00)]
        with self.assertRaises(UnreachableDestination) as ctx:
            plan(stops, distance=500, tank=200)
        error = ctx.exception
        self.assertAlmostEqual(error.from_miles, 100)
        self.assertAlmostEqual(error.to_miles, 400)
        self.assertAlmostEqual(error.gap_miles, 300)
        self.assertEqual(error.tank_range_miles, 200)

    def test_final_leg_longer_than_the_tank(self):
        stops = [make_stop(100, 3.00)]
        with self.assertRaises(UnreachableDestination) as ctx:
            plan(stops, distance=1000, tank=200)
        self.assertAlmostEqual(ctx.exception.from_miles, 100)
        self.assertAlmostEqual(ctx.exception.to_miles, 1000)

    def test_first_station_out_of_reach_of_the_starting_tank(self):
        stops = [make_stop(300, 3.00)]
        with self.assertRaises(UnreachableDestination):
            plan(stops, distance=400, tank=200)

    def test_no_stations_at_all_on_a_long_route(self):
        with self.assertRaises(UnreachableDestination):
            plan([], distance=900, tank=500)

    def test_exactly_at_range_is_reachable(self):
        stops = [make_stop(200, 3.00)]
        result = plan(stops, distance=400, tank=200)
        self.assertEqual(result.stop_count, 1)


class FilteringTests(SimpleTestCase):
    def test_stops_beyond_the_destination_are_ignored(self):
        stops = [make_stop(100, 1.00), make_stop(900, 0.01)]
        result = plan(stops, distance=200, tank=100)
        self.assertEqual(result.candidates_considered, 1)
        self.assertEqual([p.stop.route_miles for p in result.purchases], [100])

    def test_duplicate_positions_are_handled(self):
        stops = [make_stop(100, 4.00, 1), make_stop(100, 2.00, 2)]
        result = plan(stops, distance=200, tank=100)
        self.assertEqual(result.stop_count, 1)
        self.assertEqual(result.purchases[0].stop.station.id, 2)


class HelperTests(SimpleTestCase):
    def test_next_no_more_expensive(self):
        self.assertEqual(_next_no_more_expensive([4, 3, 5, 2, 6]), [1, 3, 3, 5, 5])

    def test_next_no_more_expensive_treats_equal_prices_as_targets(self):
        self.assertEqual(_next_no_more_expensive([3, 3, 3]), [1, 2, 3])

    def test_sparse_table_returns_the_farthest_minimum(self):
        table = _SparseMinTable([5, 1, 3, 1, 9])
        self.assertEqual(table.argmin(0, 4), 3)
        self.assertEqual(table.argmin(0, 2), 1)
        self.assertEqual(table.argmin(2, 2), 2)

    def test_sparse_table_rejects_an_empty_range(self):
        with self.assertRaises(ValueError):
            _SparseMinTable([1.0, 2.0]).argmin(1, 0)


# --------------------------------------------------------------------------- optimality


def brute_force_cost(positions, prices, distance, tank, mpg):
    """Exhaustive DP reference implementation.

    States are ``(station index, integer miles of range in the tank)``. With
    integer positions and an integer tank range the LP has an integral optimum,
    so enumerating integer fuel levels finds the true minimum. Exponential in
    nothing but deliberately naive — it exists only to check the greedy.
    """
    nodes = [
        (0.0, None),
        *zip(positions, prices, strict=True),
        (float(distance), 0.0),
    ]
    last = len(nodes) - 1

    @cache
    def best(index, fuel):
        if index == last:
            return 0.0
        position, price = nodes[index]
        options = []
        max_buy = 0 if price is None else tank - fuel
        for buy in range(0, int(max_buy) + 1):
            available = fuel + buy
            spend = 0.0 if price is None else (buy / mpg) * price
            for target in range(index + 1, last + 1):
                leg = nodes[target][0] - position
                if leg > available:
                    break
                options.append(spend + best(target, int(available - leg)))
        return min(options) if options else float("inf")

    return best(0, tank)


class OptimalityTests(SimpleTestCase):
    """Randomised cross-check of the greedy against the exhaustive DP."""

    def test_greedy_matches_brute_force_on_random_instances(self):
        rng = random.Random(20260923)
        checked = 0
        for _ in range(150):
            distance = rng.randrange(20, 50)
            tank = rng.randrange(10, 22)
            count = rng.randrange(3, 9)
            positions = sorted(rng.sample(range(1, distance), min(count, distance - 1)))
            prices = [float(rng.randrange(1, 9)) for _ in positions]
            mpg = 1.0

            reference = brute_force_cost(positions, prices, distance, tank, mpg)
            stops = [
                make_stop(position, price, station_id=index)
                for index, (position, price) in enumerate(
                    zip(positions, prices, strict=True)
                )
            ]
            try:
                result = plan_fuel_stops(
                    stops,
                    route_distance_miles=float(distance),
                    tank_range_miles=float(tank),
                    vehicle_mpg=mpg,
                )
            except UnreachableDestination:
                self.assertEqual(
                    reference,
                    float("inf"),
                    f"greedy called it infeasible but the DP found a plan: "
                    f"{positions} {prices} d={distance} tank={tank}",
                )
                continue

            self.assertNotEqual(
                reference,
                float("inf"),
                f"greedy produced a plan the DP thinks is infeasible: "
                f"{positions} {prices} d={distance} tank={tank}",
            )
            self.assertAlmostEqual(
                result.total_cost,
                reference,
                places=6,
                msg=(
                    f"greedy {result.total_cost} != optimal {reference} for "
                    f"positions={positions} prices={prices} "
                    f"distance={distance} tank={tank}"
                ),
            )
            checked += 1
        self.assertGreater(checked, 100, "too few feasible instances were compared")

    def test_never_buys_more_fuel_than_the_trip_can_burn(self):
        # The free starting tank covers the first 200 miles, so at most
        # (950 - 200) / 10 gallons are ever purchased.
        stops = [make_stop(mile, 2.0 + (mile % 7) / 10) for mile in range(90, 900, 90)]
        result = plan(stops, distance=950, tank=200, mpg=10)
        self.assertLessEqual(result.total_gallons, (950 - 200) / 10 + 1e-9)
        self.assertGreater(result.total_gallons, 0.0)
        self.assertAlmostEqual(
            result.total_cost,
            sum(purchase.cost for purchase in result.purchases),
            places=9,
        )
