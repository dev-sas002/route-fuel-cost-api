# Captured API output

Every block below was produced by running the commands shown against a local
server started with:

```
ROUTE_PROVIDER=api.routing.static.StaticRouteProvider \
  MAX_ROUTE_POINTS_RETURNED=6 python manage.py runserver 127.0.0.1:8370
```

`MAX_ROUTE_POINTS_RETURNED=6` is set only so the `route` polyline fits on the
page; the default is 2000. The offline `StaticRouteProvider` is used so the
capture is reproducible without an OpenRouteService key.

## Health check

```console
$ curl -s http://localhost:8370/api/health/ | python -m json.tool
{
    "status": "ok",
    "route_provider": "static",
    "route_provider_configured": true
}

```

## Plan a route: Los Angeles to New York City

```console
$ curl -s -X POST http://localhost:8370/api/route/ \
    -H "Content-Type: application/json" \
    -d @- <<JSON | python -m json.tool
{"start_lat": 34.05233, "start_lng": -118.24356,
 "end_lat": 40.71278, "end_lng": -74.00600,
 "vehicle_mpg": 10, "tank_range_miles": 800, "corridor_miles": 200}
JSON
{
    "provider": "static",
    "total_distance_miles": 2934.66,
    "estimated_duration_seconds": null,
    "vehicle_mpg": 10.0,
    "tank_range_miles": 800.0,
    "corridor_miles": 200.0,
    "total_fuel_cost": 872.73,
    "total_gallons": 213.47,
    "fuel_stop_count": 3,
    "candidate_station_count": 19,
    "fuel_stops": [
        {
            "station_name": "Sam's Club",
            "city": "Albuquerque",
            "state": "NM",
            "latitude": 35.0844,
            "longitude": -106.6504,
            "price_per_gallon": 4.02,
            "route_miles": 786.93,
            "detour_miles": 48.61,
            "gallons": 78.69,
            "cost": 316.35
        },
        {
            "station_name": "QuikTrip",
            "city": "Tulsa",
            "state": "OK",
            "latitude": 36.154,
            "longitude": -95.9928,
            "price_per_gallon": 4.08,
            "route_miles": 1484.11,
            "detour_miles": 84.87,
            "gallons": 69.72,
            "cost": 284.45
        },
        {
            "station_name": "Speedway",
            "city": "Indianapolis",
            "state": "IN",
            "latitude": 39.7684,
            "longitude": -86.1581,
            "price_per_gallon": 4.18,
            "route_miles": 2167.39,
            "detour_miles": 60.04,
            "gallons": 65.06,
            "cost": 271.93
        }
    ],
    "route": [
        [
            34.05233,
            -118.24356
        ],
        [
            35.38442,
            -109.39604800000001
        ],
        [
            36.71651,
            -100.548536
        ],
        [
            38.0486,
            -91.701024
        ],
        [
            39.38069,
            -82.853512
        ],
        [
            40.71278,
            -74.006
        ]
    ],
    "route_points_returned": 6,
    "route_points_total": 201
}
```

## The route fits in one tank: no stops, nothing bought

```console
$ curl -s -X POST http://localhost:8370/api/route/ \
    -H "Content-Type: application/json" \
    -d "{\"start_lat\": 34.05233, \"start_lng\": -118.24356,
         \"end_lat\": 36.16990, \"end_lng\": -115.13980}" | python -m json.tool
{
    "provider": "static",
    "total_distance_miles": 274.09,
    "estimated_duration_seconds": null,
    "vehicle_mpg": 10.0,
    "tank_range_miles": 500.0,
    "corridor_miles": 50.0,
    "total_fuel_cost": 0.0,
    "total_gallons": 0.0,
    "fuel_stop_count": 0,
    "candidate_station_count": 2,
    "fuel_stops": [],
    "route": [
        [
            34.05233,
            -118.24356
        ],
        [
            34.475843999999995,
            -117.622808
        ],
        [
            34.899358,
            -117.002056
        ],
        [
            35.322872,
            -116.381304
        ],
        [
            35.746386,
            -115.76055199999999
        ],
        [
            36.1699,
            -115.1398
        ]
    ],
    "route_points_returned": 6,
    "route_points_total": 201
}
```

## The tank cannot bridge the gap between two stations (HTTP 422)

```console
$ curl -s -X POST http://localhost:8370/api/route/ \
    -H "Content-Type: application/json" \
    -d "{\"start_lat\": 34.05233, \"start_lng\": -118.24356,
         \"end_lat\": 40.71278, \"end_lng\": -74.00600,
         \"tank_range_miles\": 500, \"corridor_miles\": 200}" | python -m json.tool
{
    "error": "No fuel stop is reachable between mile 786.9 and mile 1381.1: the 594.2 mile gap exceeds the 500.0 mile tank range.",
    "code": "unreachable_destination",
    "detail": {
        "from_miles": 786.93,
        "to_miles": 1381.14,
        "gap_miles": 594.21,
        "tank_range_miles": 500.0
    }
}
```

## Invalid input (HTTP 400)

```console
$ curl -s -X POST http://localhost:8370/api/route/ \
    -H "Content-Type: application/json" \
    -d "{\"start_lat\": 34.05, \"start_lng\": -118.24,
         \"end_lat\": 34.05, \"end_lng\": -118.24, \"vehicle_mpg\": 0}" | python -m json.tool
{
    "vehicle_mpg": [
        "Ensure this value is greater than or equal to 0.1."
    ]
}
```

## No OpenRouteService key configured (HTTP 503)

Captured from a second server started with the ORS provider and an empty key:
`ROUTE_PROVIDER=api.routing.openrouteservice.OpenRouteServiceProvider ORS_API_KEY= python manage.py runserver 127.0.0.1:8372`

```console
$ curl -s http://localhost:8372/api/health/ | python -m json.tool
{
    "status": "ok",
    "route_provider": "openrouteservice",
    "route_provider_configured": false
}

$ curl -s -X POST http://localhost:8372/api/route/ \
    -H "Content-Type: application/json" \
    -d "{\"start_lat\": 34.05, \"start_lng\": -118.24,
         \"end_lat\": 40.71, \"end_lng\": -74.00}" | python -m json.tool
{
    "error": "ORS_API_KEY is not set. Set it, or point ROUTE_PROVIDER at api.routing.static.StaticRouteProvider to run offline.",
    "code": "routing_provider_not_configured"
}
```
