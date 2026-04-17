"""Request and response schemas for the planning endpoint."""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from api.services import RoutePlan, route_points_for_response


class RouteRequestSerializer(serializers.Serializer):
    """Validates a planning request.

    Bounds are enforced here so the domain layer can assume sane input.
    """

    start_lat = serializers.FloatField(min_value=-90.0, max_value=90.0)
    start_lng = serializers.FloatField(min_value=-180.0, max_value=180.0)
    end_lat = serializers.FloatField(min_value=-90.0, max_value=90.0)
    end_lng = serializers.FloatField(min_value=-180.0, max_value=180.0)
    vehicle_mpg = serializers.FloatField(
        required=False,
        min_value=0.1,
        max_value=200.0,
        help_text="Miles per gallon. Defaults to DEFAULT_VEHICLE_MPG.",
    )
    tank_range_miles = serializers.FloatField(
        required=False,
        min_value=1.0,
        max_value=5000.0,
        help_text="Miles on a full tank. Defaults to DEFAULT_TANK_RANGE_MILES.",
    )
    corridor_miles = serializers.FloatField(
        required=False,
        min_value=1.0,
        max_value=250.0,
        help_text="How far off the route a station may be to count as a stop.",
    )

    def validate(self, attrs: dict) -> dict:
        if (attrs["start_lat"], attrs["start_lng"]) == (
            attrs["end_lat"],
            attrs["end_lng"],
        ):
            raise serializers.ValidationError(
                "Start and end locations must be different."
            )
        attrs.setdefault("vehicle_mpg", settings.DEFAULT_VEHICLE_MPG)
        attrs.setdefault("tank_range_miles", settings.DEFAULT_TANK_RANGE_MILES)
        attrs.setdefault("corridor_miles", settings.FUEL_STOP_CORRIDOR_MILES)
        return attrs


def serialize_route_plan(result: RoutePlan) -> dict:
    """Render a :class:`~api.services.RoutePlan` as the API response body."""
    route = result.route
    plan = result.plan
    points = route_points_for_response(route)

    return {
        "provider": route.provider,
        "total_distance_miles": round(route.distance_miles, 2),
        "estimated_duration_seconds": route.duration_seconds,
        "vehicle_mpg": result.vehicle_mpg,
        "tank_range_miles": result.tank_range_miles,
        "corridor_miles": result.corridor_miles,
        "total_fuel_cost": round(plan.total_cost, 2),
        "total_gallons": round(plan.total_gallons, 2),
        "fuel_stop_count": plan.stop_count,
        "candidate_station_count": plan.candidates_considered,
        "fuel_stops": [
            {
                "station_name": purchase.stop.station.name,
                "city": purchase.stop.station.city,
                "state": purchase.stop.station.state,
                "latitude": purchase.stop.station.location.lat,
                "longitude": purchase.stop.station.location.lng,
                "price_per_gallon": purchase.stop.station.price_per_gallon,
                "route_miles": round(purchase.stop.route_miles, 2),
                "detour_miles": round(purchase.stop.detour_miles, 2),
                "gallons": round(purchase.gallons, 2),
                "cost": round(purchase.cost, 2),
            }
            for purchase in plan.purchases
        ],
        "route": points,
        "route_points_returned": len(points),
        "route_points_total": len(route.points),
    }
