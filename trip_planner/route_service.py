from __future__ import annotations

from typing import Dict, List

import requests
from django.conf import settings


GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv"


class GeocodingError(Exception):
    pass


class RoutingError(Exception):
    pass


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
    # ORS returns [lng, lat]
    return {"lat": coords[1], "lng": coords[0], "label": location}


def _extract_legs(
    route_data: Dict,
    locations: List[str],
    full_polyline: List[List[float]],
) -> List[Dict[str, object]]:
    legs = []
    raw_legs = route_data.get("segments", [])

    for index, leg in enumerate(raw_legs):
        way_points = leg.get("way_points")
        if isinstance(way_points, list) and len(way_points) == 2:
            start_index, end_index = way_points
        else:
            # Fallback: derive the leg range from step waypoint spans.
            starts = []
            ends = []
            for step in leg.get("steps", []):
                step_points = step.get("way_points")
                if isinstance(step_points, list) and len(step_points) == 2:
                    starts.append(step_points[0])
                    ends.append(step_points[1])
            if starts and ends:
                start_index, end_index = min(starts), max(ends)
            else:
                start_index, end_index = 0, 0

        geometry = full_polyline[start_index : end_index + 1]

        legs.append(
            {
                "from": locations[index],
                "to": locations[index + 1],
                "distance_miles": round(float(leg.get("distance", 0.0)), 2),
                "duration_hours": round(float(leg.get("duration", 0.0)) / 3600, 2),
                "geometry": geometry,
            }
        )

    return legs


def get_route(current: str, pickup: str, dropoff: str) -> Dict[str, object]:
    api_key = settings.ORS_API_KEY
    if not api_key:
        raise RoutingError("ORS_API_KEY is missing")

    current_geo = geocode(current, api_key)
    pickup_geo = geocode(pickup, api_key)
    dropoff_geo = geocode(dropoff, api_key)

    coordinates = [
        [current_geo["lng"], current_geo["lat"]],
        [pickup_geo["lng"], pickup_geo["lat"]],
        [dropoff_geo["lng"], dropoff_geo["lat"]],
    ]

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
    routes = data.get("routes", [])
    if not routes:
        raise RoutingError("No route returned by ORS")

    route = routes[0]
    summary = route.get("summary", {})
    route_geometry = route.get("geometry", {}).get("coordinates", [])

    full_polyline = [[lat, lng] for lng, lat in route_geometry]

    locations = [current, pickup, dropoff]
    legs = _extract_legs(route, locations, full_polyline)

    return {
        "legs": legs,
        "total_distance_miles": round(float(summary.get("distance", 0.0)), 2),
        "total_duration_hours": round(float(summary.get("duration", 0.0)) / 3600, 2),
        "full_polyline": full_polyline,
        "waypoints": [
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
        ],
    }
