from datetime import datetime

import pytest

from trip_planner.hos_engine import RouteLeg, simulate_trip


BASE_TIME = datetime(2026, 4, 26, 6, 0, 0)


def _legs(miles: float, hours: float):
    return [RouteLeg(from_location="A", to_location="B", distance_miles=miles, duration_hours=hours)]


def test_short_trip_no_break_segment():
    segments = simulate_trip(
        legs=_legs(miles=300, hours=5.0),
        departure_datetime=BASE_TIME,
        cycle_used_hours=0,
        pickup_location="A",
        dropoff_location="B",
    )
    middle = segments[1:-1]
    assert not any(seg.type == "OFF_DUTY" and "break" in seg.label.lower() for seg in middle)


def test_break_inserted_before_exceeding_8_hours_driving():
    segments = simulate_trip(
        legs=_legs(miles=600, hours=9.0),
        departure_datetime=BASE_TIME,
        cycle_used_hours=0,
        pickup_location="A",
        dropoff_location="B",
    )
    break_segments = [seg for seg in segments if seg.type == "OFF_DUTY" and "break" in seg.label.lower()]
    assert break_segments


def test_fuel_stop_inserted_for_trip_over_1000_miles():
    segments = simulate_trip(
        legs=_legs(miles=1200, hours=20.0),
        departure_datetime=BASE_TIME,
        cycle_used_hours=0,
        pickup_location="A",
        dropoff_location="B",
    )
    assert any(seg.label == "Fuel stop" for seg in segments)


def test_cycle_used_can_exhaust_mid_trip():
    with pytest.raises(ValueError, match="Cycle hours exhausted"):
        simulate_trip(
            legs=_legs(miles=300, hours=5.0),
            departure_datetime=BASE_TIME,
            cycle_used_hours=69.9,
            pickup_location="A",
            dropoff_location="B",
        )


def test_invalid_leg_duration_raises_value_error():
    with pytest.raises(ValueError, match="Invalid leg duration"):
        simulate_trip(
            legs=_legs(miles=100, hours=0),
            departure_datetime=BASE_TIME,
            cycle_used_hours=0,
            pickup_location="A",
            dropoff_location="B",
        )

