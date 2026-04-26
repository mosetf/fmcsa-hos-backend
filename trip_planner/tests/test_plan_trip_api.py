import pytest

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
                },
                {
                    "from": pickup,
                    "to": dropoff,
                    "distance_miles": 287.4,
                    "duration_hours": 4.35,
                },
            ],
            "total_distance_miles": 468.9,
            "total_duration_hours": 7.07,
            "polyline_encoded": "encoded_polyline_value",
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
    assert response.data["route"]["polyline_encoded"] == "encoded_polyline_value"
    assert "full_polyline" not in response.data["route"]
    assert all("geometry" not in leg for leg in response.data["route"]["legs"])
    assert len(response.data["trip_segments"]) > 0
    first_segment = response.data["trip_segments"][0]
    assert set(first_segment.keys()) == {"type", "label", "start", "end", "distance_miles", "location"}
    assert len(response.data["log_sheets"]) >= 1
    first_sheet = response.data["log_sheets"][0]
    assert set(first_sheet.keys()) == {"date", "grid", "totals", "total_miles", "total_check", "remarks"}


def test_plan_trip_log_sheets_have_required_rows_and_24_hour_total(monkeypatch, api_client, valid_payload):
    def fake_get_route(current, pickup, dropoff):
        return {
            "legs": [
                {
                    "from": current,
                    "to": pickup,
                    "distance_miles": 181.5,
                    "duration_hours": 2.72,
                },
                {
                    "from": pickup,
                    "to": dropoff,
                    "distance_miles": 287.4,
                    "duration_hours": 4.35,
                },
            ],
            "total_distance_miles": 468.9,
            "total_duration_hours": 7.07,
            "polyline_encoded": "encoded_polyline_value",
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
    assert len(response.data["log_sheets"]) >= 1
    first_sheet = response.data["log_sheets"][0]
    assert [row["status"] for row in first_sheet["grid"]] == [
        "OFF_DUTY",
        "SLEEPER_BERTH",
        "DRIVING",
        "ON_DUTY_NOT_DRIVING",
    ]
    assert first_sheet["total_check"] == 24.0


def test_plan_trip_segments_are_time_chained(monkeypatch, api_client, valid_payload):
    def fake_get_route(current, pickup, dropoff):
        return {
            "legs": [
                {
                    "from": current,
                    "to": pickup,
                    "distance_miles": 300,
                    "duration_hours": 5.0,
                },
                {
                    "from": pickup,
                    "to": dropoff,
                    "distance_miles": 100,
                    "duration_hours": 2.0,
                },
            ],
            "total_distance_miles": 400.0,
            "total_duration_hours": 7.0,
            "polyline_encoded": "encoded_polyline_value",
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

    segments = response.data["trip_segments"]
    assert len(segments) >= 4
    for idx in range(1, len(segments)):
        assert segments[idx - 1]["end"] == segments[idx]["start"]


def test_plan_trip_long_drive_includes_break_segment(monkeypatch, api_client, valid_payload):
    def fake_get_route(current, pickup, dropoff):
        return {
            "legs": [
                {
                    "from": current,
                    "to": pickup,
                    "distance_miles": 600,
                    "duration_hours": 9.0,
                },
                {
                    "from": pickup,
                    "to": dropoff,
                    "distance_miles": 100,
                    "duration_hours": 2.0,
                },
            ],
            "total_distance_miles": 700.0,
            "total_duration_hours": 11.0,
            "polyline_encoded": "encoded_polyline_value",
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

    break_segments = [
        seg for seg in response.data["trip_segments"]
        if seg["type"] == "OFF_DUTY" and "break" in seg["label"].lower()
    ]
    assert break_segments


def test_plan_trip_detail_full_adds_point_count_without_raw_polyline(monkeypatch, api_client, valid_payload):
    def fake_get_route(current, pickup, dropoff):
        return {
            "legs": [
                {"from": current, "to": pickup, "distance_miles": 120.0, "duration_hours": 2.0},
                {"from": pickup, "to": dropoff, "distance_miles": 80.0, "duration_hours": 1.5},
            ],
            "total_distance_miles": 200.0,
            "total_duration_hours": 3.5,
            "polyline_encoded": "encoded_polyline_value",
            "full_polyline": [[41.0, -87.0], [40.0, -86.0], [39.0, -85.0]],
            "waypoints": [
                {"lat": 41.0, "lng": -87.0, "label": "Current Location", "type": "current"},
                {"lat": 40.0, "lng": -86.0, "label": "Pickup", "type": "pickup"},
                {"lat": 39.0, "lng": -85.0, "label": "Dropoff", "type": "dropoff"},
            ],
        }

    monkeypatch.setattr("trip_planner.views.get_route", fake_get_route)

    response = api_client.post("/api/v1/plan-trip/?detail=full", valid_payload, format="json")
    assert response.status_code == 200
    assert response.data["route"]["polyline_encoded"] == "encoded_polyline_value"
    assert response.data["route"]["polyline_point_count"] == 3
    assert "full_polyline" not in response.data["route"]


def test_plan_trip_debug_mode_can_include_raw_polyline(monkeypatch, api_client, valid_payload):
    def fake_get_route(current, pickup, dropoff):
        return {
            "legs": [
                {"from": current, "to": pickup, "distance_miles": 120.0, "duration_hours": 2.0},
                {"from": pickup, "to": dropoff, "distance_miles": 80.0, "duration_hours": 1.5},
            ],
            "total_distance_miles": 200.0,
            "total_duration_hours": 3.5,
            "polyline_encoded": "encoded_polyline_value",
            "full_polyline": [[41.0, -87.0], [40.0, -86.0], [39.0, -85.0]],
            "waypoints": [
                {"lat": 41.0, "lng": -87.0, "label": "Current Location", "type": "current"},
                {"lat": 40.0, "lng": -86.0, "label": "Pickup", "type": "pickup"},
                {"lat": 39.0, "lng": -85.0, "label": "Dropoff", "type": "dropoff"},
            ],
        }

    monkeypatch.setattr("trip_planner.views.get_route", fake_get_route)

    response = api_client.post("/api/v1/plan-trip/?detail=full&debug=true", valid_payload, format="json")
    assert response.status_code == 200
    assert "full_polyline" in response.data["route"]
    assert len(response.data["route"]["full_polyline"]) == 3


def test_plan_trip_invalid_detail_returns_400(api_client, valid_payload):
    response = api_client.post("/api/v1/plan-trip/?detail=verbose", valid_payload, format="json")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "INVALID_INPUT"


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
