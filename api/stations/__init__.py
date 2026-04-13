"""Fuel station catalogue: price sources and the spatial index."""

from __future__ import annotations

import threading
import time

from django.conf import settings
from django.utils.module_loading import import_string

from .base import FuelPriceSource
from .index import StationIndex

__all__ = [
    "FuelPriceSource",
    "StationIndex",
    "get_fuel_price_source",
    "get_station_index",
    "reset_station_index_cache",
]

_lock = threading.Lock()
_cached: tuple[str, float, StationIndex] | None = None


def get_fuel_price_source(dotted_path: str | None = None) -> FuelPriceSource:
    """Instantiate the configured fuel price source."""
    source_class = import_string(dotted_path or settings.FUEL_PRICE_SOURCE)
    return source_class()


def get_station_index(*, force_reload: bool = False) -> StationIndex:
    """Return a process-wide station index, rebuilt when its TTL expires.

    Prices move slowly and the catalogue is small enough to hold in memory, so
    rebuilding it per request would be pure waste. ``STATION_INDEX_CACHE_SECONDS``
    controls the TTL; set it to 0 to disable caching (tests do).
    """
    global _cached

    ttl = settings.STATION_INDEX_CACHE_SECONDS
    fingerprint = f"{settings.FUEL_PRICE_SOURCE}|{settings.STATION_GRID_CELL_DEGREES}"
    now = time.monotonic()

    with _lock:
        if not force_reload and _cached is not None and ttl > 0:
            cached_fingerprint, built_at, index = _cached
            if cached_fingerprint == fingerprint and now - built_at < ttl:
                return index

        index = StationIndex(
            get_fuel_price_source().load(),
            cell_degrees=settings.STATION_GRID_CELL_DEGREES,
        )
        _cached = (fingerprint, now, index)
        return index


def reset_station_index_cache() -> None:
    """Forget the cached index (call after loading new prices, and in tests)."""
    global _cached
    with _lock:
        _cached = None
