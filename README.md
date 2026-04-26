# FMCSA HOS Backend

Django + DRF API for planning truck trips and simulating FMCSA Hours of Service.

## Scope (from `plan.md` / `phases.md`)
- Phase 1: Django project setup + OpenRouteService integration
- Phase 2: Input serializer + structured API errors
- Phase 3: HOS simulation engine
- Phase 4: Build final API response with map/rest/fuel/log data
- Phase 5: Backend testing + deployment

## Quick start
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# then scaffold Django project:
# django-admin startproject core .
# python manage.py startapp trip_planner
```

## Environment
Copy `.env.example` to `.env` and set values.
