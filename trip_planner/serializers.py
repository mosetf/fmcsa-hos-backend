from datetime import datetime

from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    """Validate the inputs accepted by the plan-trip endpoint."""
    current_location = serializers.CharField()
    pickup_location = serializers.CharField()
    dropoff_location = serializers.CharField()
    cycle_used_hours = serializers.FloatField(min_value=0, max_value=70)
    departure_datetime = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        """Default the departure time to 06:00 when the client omits it."""
        if "departure_datetime" not in attrs:
            attrs["departure_datetime"] = datetime.now().replace(
                hour=6,
                minute=0,
                second=0,
                microsecond=0,
            )
        return attrs
