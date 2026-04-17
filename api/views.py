"""HTTP layer.

Views do three things and nothing else: validate input, call the application
service, serialise the result. All the domain errors are turned into status
codes by :mod:`api.exception_handlers`.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.domain.types import GeoPoint
from api.serializers import RouteRequestSerializer, serialize_route_plan
from api.services import FuelRoutePlanner


class RouteAPIView(APIView):
    """Plan a driving route and the cheapest sequence of fuel stops along it.

    POST a start and end coordinate. `vehicle_mpg`, `tank_range_miles` and
    `corridor_miles` are optional and fall back to the project defaults.
    """

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = FuelRoutePlanner().plan(
            start=GeoPoint(lat=data["start_lat"], lng=data["start_lng"]),
            end=GeoPoint(lat=data["end_lat"], lng=data["end_lng"]),
            vehicle_mpg=data["vehicle_mpg"],
            tank_range_miles=data["tank_range_miles"],
            corridor_miles=data["corridor_miles"],
        )
        return Response(serialize_route_plan(result))


class HealthAPIView(APIView):
    """Liveness probe. Reports which routing provider is active and configured."""

    def get(self, request):
        from api.routing import get_route_provider

        provider = get_route_provider()
        return Response(
            {
                "status": "ok",
                "route_provider": provider.name,
                "route_provider_configured": provider.is_configured(),
            },
            status=status.HTTP_200_OK,
        )
