"""Django settings for the fuel-optimised route planner.

Every environment-specific value is read from the environment (optionally via a
``.env`` file) so the same image runs in development, CI and production.
Defaults are chosen so that ``python manage.py test`` works on a clean checkout
with no database server and no OpenRouteService key.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


# --------------------------------------------------------------------------- core

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-key-do-not-use-in-production",
)
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "map_API.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "map_API.wsgi.application"
ASGI_APPLICATION = "map_API.asgi.application"

# --------------------------------------------------------------------------- database
#
# Defaults to SQLite so the project runs with zero infrastructure. Set
# DB_ENGINE=postgres (and the DB_* vars) to use PostgreSQL, which is what
# docker-compose.yml does.

if os.getenv("DB_ENGINE", "sqlite").lower().startswith("post"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "fuel_routes"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- cache

CACHES = {
    "default": {
        "BACKEND": os.getenv(
            "CACHE_BACKEND",
            "django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": os.getenv("CACHE_LOCATION", "fuel-routes"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        )
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "api.exception_handlers.domain_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# ------------------------------------------------------------------ routing provider
#
# The routing provider is resolved by dotted path, which is the extension seam:
# swap in Mapbox/Valhalla/Google by pointing ROUTE_PROVIDER at another class
# implementing api.routing.base.RouteProvider.

ROUTE_PROVIDER = os.getenv(
    "ROUTE_PROVIDER",
    "api.routing.openrouteservice.OpenRouteServiceProvider",
)
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_URL = os.getenv(
    "ORS_URL", "https://api.openrouteservice.org/v2/directions/driving-car"
)
ORS_TIMEOUT_SECONDS = env_float("ORS_TIMEOUT_SECONDS", 10.0)
ORS_POLYLINE_PRECISION = env_int("ORS_POLYLINE_PRECISION", 5)

ROUTE_CACHE_SECONDS = env_int("ROUTE_CACHE_SECONDS", 3600)

# --------------------------------------------------------------------------- fuel data

FUEL_PRICE_SOURCE = os.getenv(
    "FUEL_PRICE_SOURCE", "api.stations.database.DatabaseFuelPriceSource"
)
FUEL_PRICES_CSV = os.getenv("FUEL_PRICES_CSV", str(BASE_DIR / "fuel_prices_sample.csv"))
STATION_INDEX_CACHE_SECONDS = env_int("STATION_INDEX_CACHE_SECONDS", 300)
STATION_GRID_CELL_DEGREES = env_float("STATION_GRID_CELL_DEGREES", 0.5)

# ------------------------------------------------------------------ planner defaults

DEFAULT_VEHICLE_MPG = env_float("DEFAULT_VEHICLE_MPG", 10.0)
DEFAULT_TANK_RANGE_MILES = env_float("DEFAULT_TANK_RANGE_MILES", 500.0)
FUEL_STOP_CORRIDOR_MILES = env_float("FUEL_STOP_CORRIDOR_MILES", 50.0)
ROUTE_SAMPLE_SPACING_MILES = env_float("ROUTE_SAMPLE_SPACING_MILES", 5.0)
MAX_ROUTE_POINTS_RETURNED = env_int("MAX_ROUTE_POINTS_RETURNED", 2000)
