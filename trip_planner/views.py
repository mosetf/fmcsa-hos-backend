from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .hos_engine import RouteLeg, simulate_trip
from .log_builder import build_log_sheets
from .route_service import GeocodingError, RoutingError, get_route
from .serializers import TripRequestSerializer


class PlanTripView(APIView):
    """
    Plan a trip from current location to pickup and dropoff.

    Accepted JSON params:
    - current_location (str): Origin text for geocoding.
    - pickup_location (str): Pickup text for geocoding.
    - dropoff_location (str): Dropoff text for geocoding.
    - cycle_used_hours (float): Current 70-hour cycle usage in [0, 70].
    - departure_datetime (str, optional): ISO datetime; defaults to current server time.
    - driver_name/carrier_name/truck_number/trailer_number/co_driver/shipping_doc (str, optional): Log header details.
    Query params:
    - detail (compact|full, optional): Response detail mode. Default compact.
    - debug (true|false, optional): When true, includes raw polyline arrays.

    Success response (200):
    {
      "route": {
        "legs": [...],
        "total_distance_miles": 0.0,
        "total_duration_hours": 0.0,
        "polyline_encoded": "....",
        "waypoints": [...]
      },
      "trip_segments": [...],
      "log_sheets": [...]
    }

    Error response:
    {
      "error": {
        "code": "INVALID_INPUT|CYCLE_EXHAUSTED|GEOCODING_FAILED|ROUTING_FAILED|HOS_SIMULATION_FAILED",
        "message": "details"
      }
    }
    """

    @staticmethod
    def _error_response(code: str, message, status_code: int) -> Response:
        return Response(
            {"error": {"code": code, "message": message}},
            status=status_code,
        )

    @staticmethod
    def _parse_debug_flag(value: str | None) -> bool:
        return (value or "").strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _build_route_response(route: dict, detail: str, debug: bool) -> dict:
        response = {
            "legs": route["legs"],
            "total_distance_miles": route["total_distance_miles"],
            "total_duration_hours": route["total_duration_hours"],
            "waypoints": route.get("waypoints", []),
            "polyline_encoded": route["polyline_encoded"],
        }
        if detail == "full":
            response["polyline_point_count"] = route.get(
                "polyline_point_count",
                len(route.get("full_polyline", [])),
            )
        if debug:
            response["full_polyline"] = route["full_polyline"]
        return response

    def post(self, request):
        """POST /api/v1/plan-trip/ returning route data with structured errors."""
        detail = (request.query_params.get("detail") or "compact").strip().lower()
        if detail not in {"compact", "full"}:
            return self._error_response(
                code="INVALID_INPUT",
                message="Query param 'detail' must be one of: compact, full.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        debug = self._parse_debug_flag(request.query_params.get("debug"))

        serializer = TripRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return self._error_response(
                code="INVALID_INPUT",
                message=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        if data["cycle_used_hours"] >= 70:
            return self._error_response(
                code="CYCLE_EXHAUSTED",
                message="Driver has no remaining cycle hours.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            route = get_route(
                data["current_location"],
                data["pickup_location"],
                data["dropoff_location"],
            )
        except GeocodingError as exc:
            return self._error_response(
                code="GEOCODING_FAILED",
                message=str(exc),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RoutingError as exc:
            return self._error_response(
                code="ROUTING_FAILED",
                message=str(exc),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        legs = [
            RouteLeg(
                from_location=leg["from"],
                to_location=leg["to"],
                distance_miles=leg["distance_miles"],
                duration_hours=leg["duration_hours"],
            )
            for leg in route["legs"]
        ]

        try:
            trip_segments = simulate_trip(
                legs=legs,
                departure_datetime=data["departure_datetime"],
                cycle_used_hours=data["cycle_used_hours"],
                pickup_location=data["pickup_location"],
                dropoff_location=data["dropoff_location"],
            )
        except (ValueError, RuntimeError) as exc:
            return self._error_response(
                code="HOS_SIMULATION_FAILED",
                message=str(exc),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serialized_segments = [
            {
                "type": segment.type,
                "label": segment.label,
                "start": segment.start.isoformat(),
                "end": segment.end.isoformat(),
                "distance_miles": round(segment.distance_miles, 2),
                "location": segment.location,
            }
            for segment in trip_segments
        ]
        log_sheets = build_log_sheets(trip_segments)

        return Response(
            {
                "route": self._build_route_response(route=route, detail=detail, debug=debug),
                "log_details": data["log_details"],
                "trip_segments": serialized_segments,
                "log_sheets": log_sheets,
            }
        )
