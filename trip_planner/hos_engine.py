from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional


EPSILON = 1e-6


@dataclass
class RouteLeg:
    """A routed leg between two named locations."""
    from_location: str
    to_location: str
    distance_miles: float
    duration_hours: float


@dataclass
class TripSegment:
    """A timestamped duty-status segment produced by the HOS engine."""
    type: str
    label: str
    start: datetime
    end: datetime
    distance_miles: float = 0.0
    location: Optional[str] = None


@dataclass
class EngineState:
    """Mutable simulation state used while expanding route legs into trip segments."""
    clock_time: datetime
    shift_start_time: datetime
    driving_hours_today: float = 0.0
    on_duty_hours_today: float = 0.0
    driving_since_break: float = 0.0
    cycle_hours_remaining: float = 70.0
    miles_since_fuel: float = 0.0


def simulate_trip(
    legs: List[RouteLeg],
    departure_datetime: datetime,
    cycle_used_hours: float,
    pickup_location: str,
    dropoff_location: str,
) -> List[TripSegment]:
    """Simulate a trip under FMCSA HOS rules and return chained trip segments."""
    segments: List[TripSegment] = []
    state = EngineState(
        clock_time=departure_datetime,
        shift_start_time=departure_datetime,
        cycle_hours_remaining=max(0.0, 70.0 - cycle_used_hours),
    )

    _drive_route(segments, state, legs[:1])
    _add_pickup(segments, state, pickup_location)
    _drive_route(segments, state, legs[1:])
    _add_dropoff(segments, state, dropoff_location)
    _add_final_rest(segments, state)

    return segments


def _add_pickup(segments: List[TripSegment], state: EngineState, location: str) -> None:
    """Append the fixed one-hour pickup stop at the pickup location."""
    duration = timedelta(hours=1)
    segments.append(
        TripSegment(
            type="ON_DUTY_NOT_DRIVING",
            label="Pickup",
            start=state.clock_time,
            end=state.clock_time + duration,
            location=location,
        )
    )
    state.clock_time += duration
    state.on_duty_hours_today += 1.0
    state.cycle_hours_remaining = max(0.0, state.cycle_hours_remaining - 1.0)
    state.shift_start_time = state.clock_time


def _add_dropoff(segments: List[TripSegment], state: EngineState, location: str) -> None:
    """Append the fixed one-hour dropoff stop at the dropoff location."""
    duration = timedelta(hours=1)
    segments.append(
        TripSegment(
            type="ON_DUTY_NOT_DRIVING",
            label="Dropoff",
            start=state.clock_time,
            end=state.clock_time + duration,
            location=location,
        )
    )
    state.clock_time += duration
    state.on_duty_hours_today += 1.0
    state.cycle_hours_remaining = max(0.0, state.cycle_hours_remaining - 1.0)


def _add_rest(segments: List[TripSegment], state: EngineState, hours: float, label: str) -> None:
    """Append an off-duty break or reset and update the driver's duty clocks."""
    duration = timedelta(hours=hours)
    segments.append(
        TripSegment(
            type="OFF_DUTY",
            label=label,
            start=state.clock_time,
            end=state.clock_time + duration,
        )
    )
    state.clock_time += duration
    state.driving_since_break = 0.0

    if hours >= 10.0:
        state.driving_hours_today = 0.0
        state.on_duty_hours_today = 0.0
        state.shift_start_time = state.clock_time


def _add_fuel_stop(segments: List[TripSegment], state: EngineState) -> None:
    """Append a fuel stop and reset the miles-since-fuel counter."""
    duration = timedelta(hours=0.5)
    segments.append(
        TripSegment(
            type="ON_DUTY_NOT_DRIVING",
            label="Fuel stop",
            start=state.clock_time,
            end=state.clock_time + duration,
        )
    )
    state.clock_time += duration
    state.on_duty_hours_today += 0.5
    state.cycle_hours_remaining = max(0.0, state.cycle_hours_remaining - 0.5)
    state.miles_since_fuel = 0.0


def _hours_in_window(state: EngineState) -> float:
    """Return elapsed hours since the current 14-hour shift window began."""
    return (state.clock_time - state.shift_start_time).total_seconds() / 3600


def _drive_route(segments: List[TripSegment], state: EngineState, legs: List[RouteLeg]) -> None:
    """Expand route legs into driving, break, fuel, and reset segments."""
    for leg in legs:
        if leg.duration_hours <= 0:
            raise ValueError("Invalid leg duration")

        remaining_miles = float(leg.distance_miles)
        speed = leg.distance_miles / leg.duration_hours

        iteration_guard = 0
        while remaining_miles > EPSILON:
            iteration_guard += 1
            if iteration_guard > 10000:
                raise RuntimeError("Infinite loop detected in HOS engine")

            if state.cycle_hours_remaining <= EPSILON:
                raise ValueError("Cycle hours exhausted mid-trip. Cannot continue.")

            if _hours_in_window(state) >= 14.0 - EPSILON:
                _add_rest(segments, state, hours=10.0, label="10-hr reset (14-hr window)")
                continue

            if state.driving_since_break >= 8.0 - EPSILON:
                _add_rest(segments, state, hours=0.5, label="30-min break")
                continue

            if state.driving_hours_today >= 11.0 - EPSILON:
                _add_rest(segments, state, hours=10.0, label="10-hr reset (11-hr limit)")
                continue

            if state.miles_since_fuel >= 1000.0 - EPSILON:
                _add_fuel_stop(segments, state)
                continue

            max_hours = min(
                8.0 - state.driving_since_break,
                11.0 - state.driving_hours_today,
                14.0 - _hours_in_window(state),
                state.cycle_hours_remaining,
            )
            miles_to_fuel = 1000.0 - state.miles_since_fuel
            drive_miles = min(max_hours * speed, miles_to_fuel, remaining_miles)

            if drive_miles <= EPSILON:
                if miles_to_fuel <= EPSILON:
                    _add_fuel_stop(segments, state)
                    continue
                raise RuntimeError("Infinite loop detected in HOS engine")

            drive_hours = drive_miles / speed
            drive_start = state.clock_time

            state.clock_time += timedelta(hours=drive_hours)
            state.driving_hours_today += drive_hours
            state.on_duty_hours_today += drive_hours
            state.driving_since_break += drive_hours
            state.cycle_hours_remaining = max(0.0, state.cycle_hours_remaining - drive_hours)
            state.miles_since_fuel += drive_miles
            remaining_miles -= drive_miles

            segments.append(
                TripSegment(
                    type="DRIVING",
                    label=f"Drive: {leg.from_location} -> {leg.to_location}",
                    start=drive_start,
                    end=state.clock_time,
                    distance_miles=drive_miles,
                )
            )


def _add_final_rest(segments: List[TripSegment], state: EngineState) -> None:
    """Append the trailing off-duty segment after trip completion."""
    segments.append(
        TripSegment(
            type="OFF_DUTY",
            label="Trip complete - off duty",
            start=state.clock_time,
            end=state.clock_time + timedelta(hours=10),
        )
    )
