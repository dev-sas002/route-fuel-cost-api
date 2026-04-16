"""Translate domain errors into HTTP responses.

The domain layer raises plain exceptions and knows nothing about HTTP; this
module is the single adapter that maps them onto status codes, so error
behaviour is defined in one readable table rather than scattered through
``try``/``except`` blocks in views.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from api.domain.errors import (
    DomainError,
    NoFuelStationsAvailable,
    RouteNotFound,
    RoutingProviderError,
    RoutingProviderNotConfigured,
    RoutingProviderTimeout,
    UnreachableDestination,
)

logger = logging.getLogger(__name__)

#: Most specific first — the first matching entry wins.
STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (RoutingProviderNotConfigured, status.HTTP_503_SERVICE_UNAVAILABLE),
    (RoutingProviderTimeout, status.HTTP_504_GATEWAY_TIMEOUT),
    (RoutingProviderError, status.HTTP_502_BAD_GATEWAY),
    (RouteNotFound, status.HTTP_404_NOT_FOUND),
    (UnreachableDestination, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (NoFuelStationsAvailable, status.HTTP_422_UNPROCESSABLE_ENTITY),
)


def status_for(error: DomainError) -> int:
    for error_type, code in STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return code
    return status.HTTP_400_BAD_REQUEST


def domain_exception_handler(exc, context):
    """DRF exception hook (wired via ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``)."""
    if isinstance(exc, DomainError):
        http_status = status_for(exc)
        logger.info("%s -> %s: %s", type(exc).__name__, http_status, exc)
        body = {"error": str(exc), "code": exc.code}
        if isinstance(exc, UnreachableDestination):
            body["detail"] = {
                "from_miles": round(exc.from_miles, 2),
                "to_miles": round(exc.to_miles, 2),
                "gap_miles": round(exc.gap_miles, 2),
                "tank_range_miles": exc.tank_range_miles,
            }
        return Response(body, status=http_status)

    return drf_exception_handler(exc, context)
