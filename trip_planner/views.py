from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .route_service import GeocodingError, RoutingError, get_route
from .serializers import TripRequestSerializer


class PlanTripView(APIView):
    def post(self, request):
        serializer = TripRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": {"code": "INVALID_INPUT", "message": serializer.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        if data["cycle_used_hours"] >= 70:
            return Response(
                {
                    "error": {
                        "code": "CYCLE_EXHAUSTED",
                        "message": "Driver has no remaining cycle hours.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            route = get_route(
                data["current_location"],
                data["pickup_location"],
                data["dropoff_location"],
            )
        except GeocodingError as exc:
            return Response(
                {"error": {"code": "GEOCODING_FAILED", "message": str(exc)}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RoutingError as exc:
            return Response(
                {"error": {"code": "ROUTING_FAILED", "message": str(exc)}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(
            {
                "route": route,
                "trip_segments": [],
                "log_sheets": [],
            }
        )
