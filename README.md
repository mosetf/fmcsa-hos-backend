# FMCSA HOS Backend

This repository contains the Django REST API that powers the FMCSA Hours of Service trip planner.
It accepts a trip request, resolves locations, builds a route, simulates Hours of Service compliance, and returns structured trip segments and daily log sheets.

## What This Backend Does

- Geocodes the current location, pickup, and dropoff points
- Requests truck-safe routing from OpenRouteService
- Simulates Hours of Service rules across the full trip
- Builds duty-status segments for driving, on-duty, off-duty, and sleeper berth time
- Generates FMCSA-style daily log sheets from the simulated segments
- Returns route metadata, summary totals, and log details for the frontend

## Technology Stack

- Python 3.14
- Django
- Django REST Framework
- drf-spectacular for OpenAPI schema and Swagger UI
- django-cors-headers for browser access from the frontend
- gunicorn for production serving
- pytest and pytest-django for testing

## External APIs

- OpenRouteService Geocoding API
- OpenRouteService Directions API

OpenRouteService is used to resolve locations and build the route polyline and leg summaries. The backend keeps the HOS logic local so the compliance simulation is deterministic and testable.

## API Surface

All business endpoints are versioned under `/api/v1/`.

- `POST /api/v1/plan-trip/?detail=compact|full`
- `GET /api/schema/`
- `GET /api/docs/`

### Request Contract

`POST /api/v1/plan-trip/?detail=compact|full`

```json
{
  "current_location": "Chicago, IL",
  "pickup_location": "Indianapolis, IN",
  "dropoff_location": "Nashville, TN",
  "cycle_used_hours": 10,
  "departure_datetime": "2026-04-26T06:00:00"
}
```

`departure_datetime` is optional. If omitted, the backend defaults to the current local server date and time.

`detail=compact` is the default.

`detail=full` includes additional route and log metadata for diagnostics.

`debug=true` can include raw polyline arrays for troubleshooting.

### Response Shape

The response includes:

- `route`
- `trip_segments`
- `log_sheets`
- `log_details`

The route contains total distance, total duration, waypoints, and the encoded polyline. Trip segments describe each duty-status block with start/end timestamps, labels, distances, and locations.

## HOS Engine

The HOS engine is the rule layer that turns a route into duty-status time blocks.

### Core logic

- Driving time is allocated across route legs.
- On-duty non-driving time is inserted for operational actions such as pickup or staging where needed.
- Off-duty breaks are inserted when the driving window requires them.
- Sleeper berth and reset behavior are represented as separate segments where applicable.
- The engine tracks cycle hours and emits `CYCLE_EXHAUSTED` when the request cannot be completed within the available hours.

### Why this is done in code

The compliance logic is implemented in Python instead of relying on a third-party HOS service so that:

- the behavior is deterministic
- edge cases can be tested directly
- the frontend only renders the result instead of re-deriving rules

## Log Builder

The log builder converts the HOS segments into FMCSA-style daily log sheets.

It is responsible for:

- laying out the 24-hour graph grid
- mapping each segment onto the correct duty-status row
- generating the remarks section from segment changes
- calculating per-status totals
- producing paper-style sheets that resemble the FMCSA driver daily log format

The rendered sheet is intentionally close to the paper reference:

- continuous horizontal duty lines
- vertical transitions at status changes
- labeled totals on the right side
- remarks and shipping document fields below the grid

## Error Handling

Structured errors returned by the API:

- `INVALID_INPUT` -> `400`
- `CYCLE_EXHAUSTED` -> `400`
- `GEOCODING_FAILED` -> `422`
- `ROUTING_FAILED` -> `422`
- `HOS_SIMULATION_FAILED` -> `422`

## Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Render Deploy

- Root directory: `fmcsa-hos-backend`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --timeout 120`
- Or use the bundled `Procfile`

## Environment Variables

Copy `.env.example` to `.env`.

- `ORS_API_KEY`
- `CORS_ALLOWED_ORIGINS`
- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS` (optional, comma-separated)

## Testing

Tests are run with `pytest`.

```bash
pytest -q
```

Coverage focus:

- endpoint behavior
- route planning
- HOS simulation
- log sheet generation
- settings and environment validation
