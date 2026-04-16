"""Routing providers and the registry that resolves the active one."""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.utils.module_loading import import_string

from .base import RouteProvider

__all__ = ["RouteProvider", "get_route_provider", "reset_route_provider_cache"]


@lru_cache(maxsize=8)
def _build(dotted_path: str) -> RouteProvider:
    provider_class = import_string(dotted_path)
    return provider_class()


def get_route_provider(dotted_path: str | None = None) -> RouteProvider:
    """Instantiate the configured routing provider.

    Providers are stateless and cheap to reuse, so instances are memoised per
    dotted path.
    """
    return _build(dotted_path or settings.ROUTE_PROVIDER)


def reset_route_provider_cache() -> None:
    """Drop memoised providers (used by tests that override settings)."""
    _build.cache_clear()
