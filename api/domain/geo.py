"""Great-circle geometry helpers.

Distances are in statute miles throughout the project. We use the spherical
haversine formula rather than an ellipsoidal one: the error is under 0.5% and
the input data (station coordinates rounded to four decimals, a routing
provider's simplified polyline) is far coarser than that.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt

from .types import GeoPoint

#: Mean Earth radius in statute miles (IUGG mean radius, 6371.0088 km).
EARTH_RADIUS_MILES = 3958.7613

#: Miles per degree of latitude (constant); used for cheap bounding boxes.
MILES_PER_DEGREE_LATITUDE = 69.0547


def haversine_miles(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points, in miles."""
    lat1, lng1, lat2, lng2 = map(radians, (a.lat, a.lng, b.lat, b.lng))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(min(1.0, h)))


def longitude_degrees_for_miles(miles: float, latitude: float) -> float:
    """Degrees of longitude spanning ``miles`` at the given latitude.

    Clamped near the poles, where a degree of longitude collapses to zero and
    the naive formula divides by (almost) zero.
    """
    shrink = max(cos(radians(max(-89.5, min(89.5, latitude)))), 1e-6)
    return miles / (MILES_PER_DEGREE_LATITUDE * shrink)


def latitude_degrees_for_miles(miles: float) -> float:
    return miles / MILES_PER_DEGREE_LATITUDE


def cumulative_miles(points: Sequence[GeoPoint]) -> list[float]:
    """Running great-circle distance along a polyline, starting at 0."""
    running = [0.0]
    total = 0.0
    for previous, current in pairwise(points):
        total += haversine_miles(previous, current)
        running.append(total)
    return running


def rescale(values: Sequence[float], target_total: float) -> list[float]:
    """Scale a monotonic distance list so its last element equals ``target_total``.

    A provider reports an authoritative road distance that will not match the
    haversine sum over its own simplified polyline (the polyline cuts corners).
    Rescaling keeps every station's position along the route consistent with the
    distance we report to the caller.
    """
    if not values:
        return []
    last = values[-1]
    if last <= 0:
        return [0.0 for _ in values]
    factor = target_total / last
    return [value * factor for value in values]


def sample_indices(distances: Sequence[float], spacing_miles: float) -> list[int]:
    """Indices of polyline vertices spaced at least ``spacing_miles`` apart.

    Always includes the first and last vertex. Used to keep station matching
    proportional to route *length* rather than to the vertex count, which a
    provider is free to inflate.
    """
    if not distances:
        return []
    if spacing_miles <= 0 or len(distances) <= 2:
        return list(range(len(distances)))
    chosen = [0]
    last_distance = distances[0]
    for index in range(1, len(distances) - 1):
        if distances[index] - last_distance >= spacing_miles:
            chosen.append(index)
            last_distance = distances[index]
    chosen.append(len(distances) - 1)
    return chosen


def downsample(points: Sequence[GeoPoint], max_points: int) -> list[GeoPoint]:
    """Evenly thin a polyline to at most ``max_points``, keeping both endpoints.

    Cross-country ORS polylines run to tens of thousands of vertices; returning
    all of them makes the JSON response the largest cost in the request.
    """
    count = len(points)
    if max_points <= 0 or count <= max_points:
        return list(points)
    if max_points == 1:
        return [points[0]]
    step = (count - 1) / (max_points - 1)
    picked = [points[round(i * step)] for i in range(max_points)]
    picked[-1] = points[-1]
    return picked


def to_geo_points(pairs: Iterable[tuple[float, float]]) -> tuple[GeoPoint, ...]:
    """Build points from ``(lat, lng)`` pairs."""
    return tuple(GeoPoint(lat=float(lat), lng=float(lng)) for lat, lng in pairs)
