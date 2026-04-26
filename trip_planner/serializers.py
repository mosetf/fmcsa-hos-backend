from datetime import datetime

from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    """Validate the inputs accepted by the plan-trip endpoint."""
    current_location = serializers.CharField()
    pickup_location = serializers.CharField()
    dropoff_location = serializers.CharField()
    cycle_used_hours = serializers.FloatField(min_value=0, max_value=70)
    departure_datetime = serializers.DateTimeField(required=False)
    driver_name = serializers.CharField(required=False, allow_blank=True)
    carrier_name = serializers.CharField(required=False, allow_blank=True)
    truck_number = serializers.CharField(required=False, allow_blank=True)
    trailer_number = serializers.CharField(required=False, allow_blank=True)
    co_driver = serializers.CharField(required=False, allow_blank=True)
    shipping_doc = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        """Default departure to the current server time when the client omits it."""
        if "departure_datetime" not in attrs:
            attrs["departure_datetime"] = datetime.now().replace(second=0, microsecond=0)
        attrs["log_details"] = {
            "driver_name": attrs.get("driver_name") or "N/A",
            "carrier_name": attrs.get("carrier_name") or "Trip Planner Co.",
            "truck_number": attrs.get("truck_number") or "N/A",
            "trailer_number": attrs.get("trailer_number") or "N/A",
            "co_driver": attrs.get("co_driver") or "N/A",
            "shipping_doc": attrs.get("shipping_doc") or "N/A",
        }
        return attrs
