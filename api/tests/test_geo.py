"""Geometry helpers."""

from __future__ import annotations

from itertools import pairwise

from django.test import SimpleTestCase

from api.domain.geo import (
    cumulative_miles,
    downsample,
    haversine_miles,
    latitude_degrees_for_miles,
    longitude_degrees_for_miles,
    rescale,
    sample_indices,
)
from api.domain.types import GeoPoint

LOS_ANGELES = GeoPoint(lat=34.0522, lng=-118.2437)
NEW_YORK = GeoPoint(lat=40.7128, lng=-74.0060)


class HaversineTests(SimpleTestCase):
    def test_zero_distance_between_identical_points(self):
        self.assertEqual(haversine_miles(LOS_ANGELES, LOS_ANGELES), 0.0)

    def test_known_city_pair(self):
        # LA to NYC great-circle distance is ~2445 miles.
        miles = haversine_miles(LOS_ANGELES, NEW_YORK)
        self.assertAlmostEqual(miles, 2445, delta=10)

    def test_symmetric(self):
        self.assertAlmostEqual(
            haversine_miles(LOS_ANGELES, NEW_YORK),
            haversine_miles(NEW_YORK, LOS_ANGELES),
            places=9,
        )

    def test_antipodal_points_do_not_overflow_the_arcsine(self):
        # sqrt(h) can exceed 1.0 by a float ulp; the formula clamps it.
        north = GeoPoint(lat=0.0, lng=0.0)
        south = GeoPoint(lat=0.0, lng=180.0)
        self.assertAlmostEqual(haversine_miles(north, south), 12436, delta=20)


class DegreeConversionTests(SimpleTestCase):
    def test_latitude_degrees_are_constant(self):
        self.assertAlmostEqual(latitude_degrees_for_miles(69.0547), 1.0, places=6)

    def test_longitude_degrees_widen_towards_the_poles(self):
        equator = longitude_degrees_for_miles(50, latitude=0.0)
        high = longitude_degrees_for_miles(50, latitude=60.0)
        self.assertGreater(high, equator)

    def test_longitude_degrees_do_not_divide_by_zero_at_the_pole(self):
        self.assertGreater(longitude_degrees_for_miles(50, latitude=90.0), 0.0)


class CumulativeTests(SimpleTestCase):
    def test_starts_at_zero_and_increases(self):
        points = [GeoPoint(lat=0.0, lng=x) for x in (0.0, 1.0, 2.0, 3.0)]
        running = cumulative_miles(points)
        self.assertEqual(running[0], 0.0)
        self.assertEqual(len(running), len(points))
        self.assertTrue(all(b >= a for a, b in pairwise(running)))

    def test_rescale_matches_the_target_total(self):
        rescaled = rescale([0.0, 1.0, 3.0, 4.0], 8.0)
        self.assertEqual(rescaled, [0.0, 2.0, 6.0, 8.0])

    def test_rescale_handles_a_degenerate_polyline(self):
        self.assertEqual(rescale([0.0, 0.0], 10.0), [0.0, 0.0])
        self.assertEqual(rescale([], 10.0), [])


class SampleIndicesTests(SimpleTestCase):
    def test_keeps_first_and_last(self):
        distances = [float(i) for i in range(100)]
        chosen = sample_indices(distances, spacing_miles=10)
        self.assertEqual(chosen[0], 0)
        self.assertEqual(chosen[-1], 99)

    def test_respects_spacing(self):
        distances = [float(i) for i in range(100)]
        chosen = sample_indices(distances, spacing_miles=10)
        gaps = [distances[b] - distances[a] for a, b in pairwise(chosen[:-1])]
        self.assertTrue(all(gap >= 10 for gap in gaps))
        self.assertLess(len(chosen), 100)

    def test_zero_spacing_keeps_everything(self):
        distances = [0.0, 1.0, 2.0]
        self.assertEqual(sample_indices(distances, 0), [0, 1, 2])


class DownsampleTests(SimpleTestCase):
    def test_short_polyline_is_untouched(self):
        points = [GeoPoint(lat=0.0, lng=float(i)) for i in range(5)]
        self.assertEqual(downsample(points, 10), points)

    def test_long_polyline_is_capped_and_keeps_endpoints(self):
        points = [GeoPoint(lat=0.0, lng=i / 100) for i in range(10_000)]
        thinned = downsample(points, 100)
        self.assertEqual(len(thinned), 100)
        self.assertEqual(thinned[0], points[0])
        self.assertEqual(thinned[-1], points[-1])
