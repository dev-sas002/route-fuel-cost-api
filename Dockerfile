# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- build stage
# Wheels are built once here so the runtime image carries no compilers and no
# pip cache.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /wheels
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip wheel --wheel-dir /wheels/dist -r requirements.txt

# -------------------------------------------------------------- runtime stage
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=map_API.settings

# curl is used by the container healthcheck.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder /wheels/dist /wheels/dist
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels/dist -r requirements.txt \
    && rm -rf /wheels

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/health/ || exit 1

# migrate + seed on every boot so the API is never empty on first run.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py load_fuel_data && gunicorn map_API.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 --access-logfile -"]
