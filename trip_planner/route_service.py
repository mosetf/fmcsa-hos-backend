from __future__ import annotations

import time
from typing import Dict, List

import requests
from django.conf import settings


GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"


class GeocodingError(Exception):
    """Raised when a location string cannot be resolved by ORS."""
    pass


class RoutingError(Exception):
    """Raised when ORS routing fails or returns unusable route data."""
    pass


def _rdp(points: List[List[float]], epsilon: float) -> List[List[float]]:
    """Simplify a polyline with the Ramer-Douglas-Peucker algorithm."""
    if len(points) <= 2:
        return points

    start = points[0]
    end = points[-1]
    max_distance = -1.0
    max_index = 0

    sx, sy = start[1], start[0]
    ex, ey = end[1], end[0]
    dx = ex - sx
    dy = ey - sy

    for idx in range(1, len(points) - 1):
        px, py = points[idx][1], points[idx][0]
        if dx == 0 and dy == 0:
            distance = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
        else:
            numerator = abs(dy * px - dx * py + ex * sy - ey * sx)
            denominator = (dx ** 2 + dy ** 2) ** 0.5
            distance = numerator / denominator
        if distance > max_distance:
            max_distance = distance
            max_index = idx

    if max_distance > epsilon:
        left = _rdp(points[: max_index + 1], epsilon)
        right = _rdp(points[max_index:], epsilon)
        return left[:-1] + right
    return [start, end]


def _simplify_polyline(polyline: List[List[float]], epsilon: float = 0.0001) -> List[List[float]]:
    """Reduce route geometry density before encoding it for API responses."""
    if not polyline:
        return []
    return _rdp(polyline, epsilon)


def _encode_polyline(polyline: List[List[float]]) -> str:
    """Encode `[lat, lng]` points into a Google-style polyline string."""
    result = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in polyline:
        lat_i = int(round(lat * 1e5))
        lng_i = int(round(lng * 1e5))
        for value in (lat_i - prev_lat, lng_i - prev_lng):
            shifted = value << 1
            if value < 0:
                shifted = ~shifted
            while shifted >= 0x20:
                result.append(chr((0x20 | (shifted & 0x1F)) + 63))
                shifted >>= 5
            result.append(chr(shifted + 63))
        prev_lat = lat_i
        prev_lng = lng_i

    return "".join(result)


def _validate_route_output(
    legs: List[Dict[str, object]],
    full_polyline: List[List[float]],
    polyline_encoded: str,
    polyline_point_count: int,
    waypoints: List[Dict[str, object]],
) -> None:
    """Validate the assembled route payload before returning it to the API layer."""
    if len(waypoints) != 3:
        raise RoutingError("Expected exactly three base waypoints")
    if len(legs) != 2:
        raise RoutingError("Expected exactly two route legs")
    if not full_polyline:
        raise RoutingError("Route polyline is empty")
    if not polyline_encoded:
        raise RoutingError("Encoded polyline is empty")
    if polyline_point_count <= 0:
        raise RoutingError("Polyline point count is invalid")
    if any(float(leg.get("distance_miles", 0.0)) <= 0 for leg in legs):
        raise RoutingError("Route contains a leg with non-positive distance")
    if any(float(leg.get("duration_hours", 0.0)) <= 0 for leg in legs):
        raise RoutingError("Route contains a leg with non-positive duration")


def geocode(location: str, api_key: str) -> Dict[str, float | str]:
    """Geocode one location string into a normalized `{lat, lng, label}` mapping."""
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
    """Request ORS directions and normalize distance, duration, and geometry."""
    payload = {
        "coordinates": coordinates,
        "instructions": False,
        "geometry": True,
        "units": "mi",
        "radiuses": [2000] * len(coordinates),
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
    except requests.RequestException as exc:
        raise RoutingError("Failed to fetch route from ORS") from exc

    if response.status_code >= 400:
        try:
            error_payload = response.json()
            error_message = error_payload.get("error", {}).get("message", response.text)
            error_code = error_payload.get("error", {}).get("code")
            if error_code:
                raise RoutingError(f"ORS error {error_code}: {error_message}")
            raise RoutingError(f"ORS error: {error_message}")
        except ValueError:
            raise RoutingError(f"ORS error: HTTP {response.status_code}") from None

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
    """Build the route payload for the current, pickup, and dropoff locations."""
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
        },
        {
            "from": pickup,
            "to": dropoff,
            "distance_miles": leg_two["distance_miles"],
            "duration_hours": leg_two["duration_hours"],
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

    simplified_polyline = _simplify_polyline(full_route["polyline"])
    polyline_encoded = _encode_polyline(simplified_polyline)

    _validate_route_output(
        legs=legs,
        full_polyline=full_route["polyline"],
        polyline_encoded=polyline_encoded,
        polyline_point_count=len(simplified_polyline),
        waypoints=waypoints,
    )

    return {
        "legs": legs,
        "total_distance_miles": full_route["distance_miles"],
        "total_duration_hours": full_route["duration_hours"],
        "full_polyline": full_route["polyline"],
        "polyline_encoded": polyline_encoded,
        "polyline_point_count": len(simplified_polyline),
        "waypoints": waypoints,
    }
