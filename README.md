# FMCSA HOS Backend

Django + DRF API for planning truck trips and simulating FMCSA Hours of Service.

## Current Phase Status
- Phase 1: Complete (versioned endpoint, ORS route service, Swagger, pytest endpoint coverage)
- Phase 2: Complete (HOS simulation engine wired to endpoint, trip segment serialization)
- Phase 3+: Pending

## API Versioning
All business endpoints are versioned under `/api/v1/`.

## Endpoints
- `POST /api/v1/plan-trip/`
- `GET /api/schema/` (OpenAPI schema)
- `GET /api/docs/` (Swagger UI)

## Request Contract
`POST /api/v1/plan-trip/`

```json
{
  "current_location": "Chicago, IL",
  "pickup_location": "Indianapolis, IN",
  "dropoff_location": "Nashville, TN",
  "cycle_used_hours": 10,
  "departure_datetime": "2026-04-26T06:00:00"
}
```

`departure_datetime` is optional. If omitted, backend defaults to local date at `06:00`.

## Response Contract (Phase 1)
```json
{
  "route": {
    "legs": [],
    "total_distance_miles": 0,
    "total_duration_hours": 0,
    "full_polyline": [],
    "waypoints": []
  },
  "trip_segments": [
    {
      "type": "ON_DUTY_NOT_DRIVING|DRIVING|OFF_DUTY|SLEEPER_BERTH",
      "label": "string",
      "start": "ISO datetime",
      "end": "ISO datetime",
      "distance_miles": 0,
      "location": "string|null"
    }
  ],
  "log_sheets": []
}
```

Structured errors:
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

Scope:
- Endpoint-first API behavior tests
- Known edge cases per phase
