from __future__ import annotations

import time
from typing import Dict, List

import requests
from django.conf import settings


GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"


class GeocodingError(Exception):
    pass


class RoutingError(Exception):
    pass


def _validate_route_output(
    legs: List[Dict[str, object]],
    full_polyline: List[List[float]],
    waypoints: List[Dict[str, object]],
) -> None:
    if len(waypoints) != 3:
        raise RoutingError("Expected exactly three base waypoints")
    if len(legs) != 2:
        raise RoutingError("Expected exactly two route legs")
    if not full_polyline:
        raise RoutingError("Route polyline is empty")
    if any(float(leg.get("distance_miles", 0.0)) <= 0 for leg in legs):
        raise RoutingError("Route contains a leg with non-positive distance")
    if any(float(leg.get("duration_hours", 0.0)) <= 0 for leg in legs):
        raise RoutingError("Route contains a leg with non-positive duration")


def geocode(location: str, api_key: str) -> Dict[str, float | str]:
    params = {"api_key": api_key, "text": location, "size": 1}

    try:
        response = requests.get(GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f"Failed to geocode '{location}'") from exc

    data = response.json()
    if not data.get("features"):
        raise GeocodingError(f"No geocoding results for '{location}'")

    coords = data["features"][0]["geometry"]["coordinates"]
    return {"lat": coords[1], "lng": coords[0], "label": location}


def _request_directions(
    coordinates: List[List[float]],
    api_key: str,
) -> Dict[str, object]:
    payload = {
        "coordinates": coordinates,
        "instructions": False,
        "geometry": True,
        "units": "mi",
    }
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            DIRECTIONS_URL,
            json=payload,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RoutingError("Failed to fetch route from ORS") from exc

    data = response.json()
    features = data.get("features", [])
    if not features:
        raise RoutingError("No route returned by ORS")

    feature = features[0]
    props = feature.get("properties", {})
    summary = props.get("summary", {})
    geometry = feature.get("geometry", {}).get("coordinates", [])

    if not isinstance(geometry, list) or not geometry:
        raise RoutingError("Route geometry format was not recognized")

    return {
        "distance_miles": round(float(summary.get("distance", 0.0)), 2),
        "duration_hours": round(float(summary.get("duration", 0.0)) / 3600, 2),
        "polyline": [[lat, lng] for lng, lat in geometry],
    }


def get_route(current: str, pickup: str, dropoff: str) -> Dict[str, object]:
    api_key = settings.ORS_API_KEY
    if not api_key:
        raise RoutingError("ORS_API_KEY is missing")

    current_geo = geocode(current, api_key)
    time.sleep(0.2)
    pickup_geo = geocode(pickup, api_key)
    time.sleep(0.2)
    dropoff_geo = geocode(dropoff, api_key)

    current_coord = [current_geo["lng"], current_geo["lat"]]
    pickup_coord = [pickup_geo["lng"], pickup_geo["lat"]]
    dropoff_coord = [dropoff_geo["lng"], dropoff_geo["lat"]]

    leg_one = _request_directions([current_coord, pickup_coord], api_key)
    time.sleep(0.2)
    leg_two = _request_directions([pickup_coord, dropoff_coord], api_key)
    time.sleep(0.2)
    full_route = _request_directions([current_coord, pickup_coord, dropoff_coord], api_key)

    legs = [
        {
            "from": current,
            "to": pickup,
            "distance_miles": leg_one["distance_miles"],
            "duration_hours": leg_one["duration_hours"],
            "geometry": leg_one["polyline"],
        },
        {
            "from": pickup,
            "to": dropoff,
            "distance_miles": leg_two["distance_miles"],
            "duration_hours": leg_two["duration_hours"],
            "geometry": leg_two["polyline"],
        },
    ]

    waypoints = [
        {
            "lat": current_geo["lat"],
            "lng": current_geo["lng"],
            "label": "Current Location",
            "type": "current",
        },
        {
            "lat": pickup_geo["lat"],
            "lng": pickup_geo["lng"],
            "label": "Pickup",
            "type": "pickup",
        },
        {
            "lat": dropoff_geo["lat"],
            "lng": dropoff_geo["lng"],
            "label": "Dropoff",
            "type": "dropoff",
        },
    ]

    _validate_route_output(
        legs=legs,
        full_polyline=full_route["polyline"],
        waypoints=waypoints,
    )

    return {
        "legs": legs,
        "total_distance_miles": full_route["distance_miles"],
        "total_duration_hours": full_route["duration_hours"],
        "full_polyline": full_route["polyline"],
        "waypoints": waypoints,
    }
