from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

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
    - departure_datetime (str, optional): ISO datetime; defaults to today 06:00.

    Success response (200):
    {
      "route": {
        "legs": [...],
        "total_distance_miles": 0.0,
        "total_duration_hours": 0.0,
        "full_polyline": [[lat, lng], ...],
        "waypoints": [...]
      },
      "trip_segments": [],
      "log_sheets": []
    }

    Error response:
    {
      "error": {
        "code": "INVALID_INPUT|CYCLE_EXHAUSTED|GEOCODING_FAILED|ROUTING_FAILED",
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

    def post(self, request):
        """POST /api/v1/plan-trip/ returning route data with structured errors."""
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

        return Response(
            {
                "route": route,
                "trip_segments": [],
                "log_sheets": [],
            }
        )
