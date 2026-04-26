import pytest
from django.urls import reverse

from trip_planner.route_service import GeocodingError, RoutingError


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def valid_payload():
    return {
        "current_location": "Chicago, IL",
        "pickup_location": "Indianapolis, IN",
        "dropoff_location": "Nashville, TN",
        "cycle_used_hours": 10,
    }


def test_plan_trip_success_returns_expected_shape(monkeypatch, api_client, valid_payload):
    def fake_get_route(current, pickup, dropoff):
        return {
            "legs": [
                {
                    "from": current,
                    "to": pickup,
                    "distance_miles": 181.5,
                    "duration_hours": 2.72,
                    "geometry": [[41.0, -87.0], [40.0, -86.0]],
                },
                {
                    "from": pickup,
                    "to": dropoff,
                    "distance_miles": 287.4,
                    "duration_hours": 4.35,
                    "geometry": [[40.0, -86.0], [36.0, -86.0]],
                },
            ],
            "total_distance_miles": 468.9,
            "total_duration_hours": 7.07,
            "full_polyline": [[41.0, -87.0], [39.0, -86.0], [36.0, -86.0]],
            "waypoints": [
                {"lat": 41.0, "lng": -87.0, "label": "Current Location", "type": "current"},
                {"lat": 39.0, "lng": -86.0, "label": "Pickup", "type": "pickup"},
                {"lat": 36.0, "lng": -86.0, "label": "Dropoff", "type": "dropoff"},
            ],
        }

    monkeypatch.setattr("trip_planner.views.get_route", fake_get_route)

    response = api_client.post("/api/v1/plan-trip/", valid_payload, format="json")

    assert response.status_code == 200
    assert set(response.data.keys()) == {"route", "trip_segments", "log_sheets"}
    assert len(response.data["route"]["legs"]) == 2
    assert response.data["trip_segments"] == []
    assert response.data["log_sheets"] == []


def test_plan_trip_missing_field_returns_invalid_input(api_client, valid_payload):
    payload = {**valid_payload}
    payload.pop("current_location")

    response = api_client.post("/api/v1/plan-trip/", payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "INVALID_INPUT"


def test_plan_trip_cycle_exhausted_returns_400(api_client, valid_payload):
    payload = {**valid_payload, "cycle_used_hours": 70}

    response = api_client.post("/api/v1/plan-trip/", payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "CYCLE_EXHAUSTED"


def test_plan_trip_negative_cycle_returns_invalid_input(api_client, valid_payload):
    payload = {**valid_payload, "cycle_used_hours": -1}

    response = api_client.post("/api/v1/plan-trip/", payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "INVALID_INPUT"


def test_plan_trip_geocoding_error_returns_422(monkeypatch, api_client, valid_payload):
    def fake_get_route(*_args, **_kwargs):
        raise GeocodingError("No geocoding results for input")

    monkeypatch.setattr("trip_planner.views.get_route", fake_get_route)

    response = api_client.post("/api/v1/plan-trip/", valid_payload, format="json")

    assert response.status_code == 422
    assert response.data["error"]["code"] == "GEOCODING_FAILED"


def test_plan_trip_routing_error_returns_422(monkeypatch, api_client, valid_payload):
    def fake_get_route(*_args, **_kwargs):
        raise RoutingError("No route returned by ORS")

    monkeypatch.setattr("trip_planner.views.get_route", fake_get_route)

    response = api_client.post("/api/v1/plan-trip/", valid_payload, format="json")

    assert response.status_code == 422
    assert response.data["error"]["code"] == "ROUTING_FAILED"


def test_unversioned_endpoint_not_exposed(api_client, valid_payload):
    response = api_client.post("/api/plan-trip/", valid_payload, format="json")

    assert response.status_code == 404


def test_plan_trip_get_is_not_allowed(api_client):
    response = api_client.get("/api/v1/plan-trip/")

    assert response.status_code == 405


def test_openapi_schema_endpoint_available(api_client):
    response = api_client.get("/api/schema/")

    assert response.status_code == 200


def test_swagger_ui_endpoint_available(api_client):
    response = api_client.get("/api/docs/")

    assert response.status_code == 200
