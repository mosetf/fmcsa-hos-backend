from datetime import datetime, timezone

from trip_planner.hos_engine import TripSegment
from trip_planner.log_builder import build_log_sheets


def test_log_builder_single_day_has_four_rows_and_total_24():
    segments = [
        TripSegment(
            type="ON_DUTY_NOT_DRIVING",
            label="Pickup",
            start=datetime(2024, 4, 26, 6, 0, 0),
            end=datetime(2024, 4, 26, 7, 0, 0),
            location="Yard",
        ),
        TripSegment(
            type="DRIVING",
            label="Drive A -> B",
            start=datetime(2024, 4, 26, 7, 0, 0),
            end=datetime(2024, 4, 26, 11, 0, 0),
            distance_miles=240.0,
        ),
        TripSegment(
            type="OFF_DUTY",
            label="30-min break",
            start=datetime(2024, 4, 26, 11, 0, 0),
            end=datetime(2024, 4, 26, 11, 30, 0),
        ),
        TripSegment(
            type="DRIVING",
            label="Drive B -> C",
            start=datetime(2024, 4, 26, 11, 30, 0),
            end=datetime(2024, 4, 26, 14, 0, 0),
            distance_miles=150.0,
        ),
    ]

    sheets = build_log_sheets(segments)

    assert len(sheets) == 1
    sheet = sheets[0]
    assert len(sheet["grid"]) == 4
    assert [row["status"] for row in sheet["grid"]] == [
        "OFF_DUTY",
        "SLEEPER_BERTH",
        "DRIVING",
        "ON_DUTY_NOT_DRIVING",
    ]
    assert sheet["total_check"] == 24.0


def test_log_builder_splits_midnight_and_preserves_total_miles():
    segments = [
        TripSegment(
            type="DRIVING",
            label="Drive overnight",
            start=datetime(2024, 4, 26, 22, 0, 0),
            end=datetime(2024, 4, 27, 2, 0, 0),
            distance_miles=200.0,
        )
    ]

    sheets = build_log_sheets(segments)

    assert len(sheets) == 2
    assert sheets[0]["date"] == "2024-04-26"
    assert sheets[1]["date"] == "2024-04-27"
    assert sheets[0]["total_check"] == 24.0
    assert sheets[1]["total_check"] == 24.0
    assert round(sheets[0]["total_miles"] + sheets[1]["total_miles"], 1) == 200.0


def test_log_builder_remarks_are_chronological():
    segments = [
        TripSegment(
            type="DRIVING",
            label="Second",
            start=datetime(2024, 4, 26, 9, 0, 0),
            end=datetime(2024, 4, 26, 10, 0, 0),
            distance_miles=50.0,
        ),
        TripSegment(
            type="ON_DUTY_NOT_DRIVING",
            label="First",
            start=datetime(2024, 4, 26, 6, 0, 0),
            end=datetime(2024, 4, 26, 7, 0, 0),
            location="Dock",
        ),
    ]

    sheets = build_log_sheets(segments)

    remarks = sheets[0]["remarks"]
    times = [item["time"] for item in remarks]
    assert times == sorted(times)


def test_log_builder_no_segment_crosses_days_after_split():
    segments = [
        TripSegment(
            type="OFF_DUTY",
            label="Reset",
            start=datetime(2024, 4, 26, 20, 0, 0),
            end=datetime(2024, 4, 27, 8, 0, 0),
        )
    ]

    sheets = build_log_sheets(segments)

    for sheet in sheets:
        for row in sheet["grid"]:
            for segment in row["segments"]:
                assert 0.0 <= segment["start_hour"] <= 24.0
                assert 0.0 <= segment["end_hour"] <= 24.0
                assert segment["start_hour"] <= segment["end_hour"]


def test_log_builder_handles_timezone_aware_segments():
    segments = [
        TripSegment(
            type="DRIVING",
            label="Aware overnight drive",
            start=datetime(2024, 4, 26, 22, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 4, 27, 2, 0, 0, tzinfo=timezone.utc),
            distance_miles=200.0,
        )
    ]

    sheets = build_log_sheets(segments)

    assert len(sheets) == 2
    assert sheets[0]["total_check"] == 24.0
    assert sheets[1]["total_check"] == 24.0
