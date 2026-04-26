from django.test import override_settings

from trip_planner import route_service


@override_settings(ORS_API_KEY="dummy-key")
def test_get_route_excludes_per_leg_geometry(monkeypatch):
    def fake_geocode(location, _api_key):
        mapping = {
            "Chicago, IL": {"lat": 41.8781, "lng": -87.6298, "label": "Chicago, IL"},
            "Indianapolis, IN": {"lat": 39.7684, "lng": -86.1581, "label": "Indianapolis, IN"},
            "Nashville, TN": {"lat": 36.1627, "lng": -86.7816, "label": "Nashville, TN"},
        }
        return mapping[location]

    calls = []

    def fake_request_directions(coordinates, _api_key):
        calls.append(coordinates)
        if len(coordinates) == 2 and coordinates[0] == [-87.6298, 41.8781]:
            return {
                "distance_miles": 181.5,
                "duration_hours": 2.72,
                "polyline": [[41.8781, -87.6298], [39.7684, -86.1581]],
            }
        if len(coordinates) == 2 and coordinates[0] == [-86.1581, 39.7684]:
            return {
                "distance_miles": 287.4,
                "duration_hours": 4.35,
                "polyline": [[39.7684, -86.1581], [36.1627, -86.7816]],
            }
        return {
            "distance_miles": 468.9,
            "duration_hours": 7.07,
            "polyline": [[41.8781, -87.6298], [39.7684, -86.1581], [36.1627, -86.7816]],
        }

    monkeypatch.setattr(route_service, "geocode", fake_geocode)
    monkeypatch.setattr(route_service, "_request_directions", fake_request_directions)
    monkeypatch.setattr(route_service.time, "sleep", lambda *_args, **_kwargs: None)

    result = route_service.get_route("Chicago, IL", "Indianapolis, IN", "Nashville, TN")

    assert len(calls) == 3
    assert len(result["legs"]) == 2
    assert set(result["legs"][0].keys()) == {"from", "to", "distance_miles", "duration_hours"}
    assert set(result["legs"][1].keys()) == {"from", "to", "distance_miles", "duration_hours"}
