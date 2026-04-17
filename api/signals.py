"""Cache invalidation hooks.

The routing provider and the station index are memoised for the life of the
process, which is what makes them cheap. Anything that changes their
configuration must therefore invalidate them; ``setting_changed`` covers
``override_settings`` in tests and ``django-constance``-style runtime changes
alike.
"""

from __future__ import annotations

ROUTING_SETTINGS = frozenset(
    {"ROUTE_PROVIDER", "ORS_API_KEY", "ORS_URL", "ORS_TIMEOUT_SECONDS"}
)
STATION_SETTINGS = frozenset(
    {
        "FUEL_PRICE_SOURCE",
        "FUEL_PRICES_CSV",
        "STATION_GRID_CELL_DEGREES",
        "STATION_INDEX_CACHE_SECONDS",
    }
)


def reset_caches_on_setting_change(sender, setting: str, **kwargs) -> None:
    from api.routing import reset_route_provider_cache
    from api.stations import reset_station_index_cache

    if setting in ROUTING_SETTINGS:
        reset_route_provider_cache()
    if setting in STATION_SETTINGS:
        reset_station_index_cache()
