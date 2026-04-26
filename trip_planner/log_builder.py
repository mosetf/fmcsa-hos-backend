from collections import defaultdict
from dataclasses import replace
from datetime import datetime, time, timedelta

from .hos_engine import TripSegment


STATUSES = [
    "OFF_DUTY",
    "SLEEPER_BERTH",
    "DRIVING",
    "ON_DUTY_NOT_DRIVING",
]


def build_log_sheets(segments: list[TripSegment]) -> list[dict]:
    """Build FMCSA-style daily log sheets from trip segments."""
    if not segments:
        return []

    split_segments = _split_segments_by_day(segments)
    grouped: dict[str, list[TripSegment]] = defaultdict(list)
    for segment in split_segments:
        grouped[segment.start.date().isoformat()].append(segment)

    sheets: list[dict] = []
    for day in sorted(grouped.keys()):
        day_segments = sorted(grouped[day], key=lambda item: item.start)
        sheets.append(_build_day_sheet(day=day, day_segments=day_segments))
    return sheets


def _split_segments_by_day(segments: list[TripSegment]) -> list[TripSegment]:
    """Split all segments so each returned segment belongs to a single calendar day."""
    split: list[TripSegment] = []
    for segment in sorted(segments, key=lambda item: item.start):
        split.extend(_split_one_segment(segment))
    return split


def _split_one_segment(segment: TripSegment) -> list[TripSegment]:
    """Split one segment at midnight boundaries while preserving proportional distance."""
    if segment.end <= segment.start:
        return []

    parts: list[TripSegment] = []
    current = segment.start
    total_seconds = (segment.end - segment.start).total_seconds()

    while current.date() < segment.end.date():
        midnight = _day_boundary(current.date() + timedelta(days=1), current.tzinfo)
        part_seconds = (midnight - current).total_seconds()
        ratio = part_seconds / total_seconds
        distance = round(segment.distance_miles * ratio, 4)
        parts.append(replace(segment, start=current, end=midnight, distance_miles=distance))
        current = midnight

    consumed_distance = sum(item.distance_miles for item in parts)
    remaining_distance = round(max(0.0, segment.distance_miles - consumed_distance), 4)
    parts.append(replace(segment, start=current, end=segment.end, distance_miles=remaining_distance))
    return parts


def _build_day_sheet(day: str, day_segments: list[TripSegment]) -> dict:
    """Build one daily log sheet with fixed FMCSA rows, totals, and remarks."""
    day_date = datetime.fromisoformat(day).date()
    tzinfo = day_segments[0].start.tzinfo if day_segments else None
    day_start = _day_boundary(day_date, tzinfo)
    day_end = day_start + timedelta(days=1)

    normalized_segments = _fill_day_gaps(day_segments=day_segments, day_start=day_start, day_end=day_end)
    status_segments: dict[str, list[dict]] = {status: [] for status in STATUSES}
    totals: dict[str, float] = {status: 0.0 for status in STATUSES}
    remarks: list[dict] = []

    for segment in normalized_segments:
        duration_hours = round((segment.end - segment.start).total_seconds() / 3600, 4)
        totals.setdefault(segment.type, 0.0)
        totals[segment.type] = round(totals[segment.type] + duration_hours, 4)

        status_segments.setdefault(segment.type, [])
        status_segments[segment.type].append(
            {
                "start_hour": round((segment.start - day_start).total_seconds() / 3600, 4),
                "end_hour": round((segment.end - day_start).total_seconds() / 3600, 4),
                "label": segment.label,
                "distance_miles": round(segment.distance_miles, 2),
                "location": segment.location,
            }
        )

        if segment.label != "Off duty (auto-fill)":
            remarks.append(
                {
                    "time": segment.start.strftime("%H:%M"),
                    "status": segment.type,
                    "label": segment.label,
                    "location": segment.location,
                }
            )

    remarks = sorted(remarks, key=lambda item: item["time"])
    rounded_totals = {status: round(totals.get(status, 0.0), 2) for status in STATUSES}
    total_check = round(sum(rounded_totals.values()), 2)
    if abs(total_check - 24.0) <= 0.05 and total_check != 24.0:
        rounded_totals["OFF_DUTY"] = round(rounded_totals["OFF_DUTY"] + (24.0 - total_check), 2)
        total_check = round(sum(rounded_totals.values()), 2)

    grid = [{"status": status, "segments": status_segments.get(status, [])} for status in STATUSES]
    total_miles = round(sum(item.distance_miles for item in normalized_segments), 2)

    return {
        "date": day,
        "grid": grid,
        "totals": rounded_totals,
        "total_miles": total_miles,
        "total_check": total_check,
        "remarks": remarks,
    }


def _fill_day_gaps(day_segments: list[TripSegment], day_start: datetime, day_end: datetime) -> list[TripSegment]:
    """Fill uncovered portions of a day with synthetic off-duty segments."""
    normalized: list[TripSegment] = []
    cursor = day_start

    for segment in day_segments:
        clipped = _clip_to_day(segment=segment, day_start=day_start, day_end=day_end)
        if clipped is None:
            continue

        if clipped.start > cursor:
            normalized.append(
                TripSegment(
                    type="OFF_DUTY",
                    label="Off duty (auto-fill)",
                    start=cursor,
                    end=clipped.start,
                )
            )

        if clipped.start < cursor:
            clipped = _trim_segment_start(segment=clipped, new_start=cursor)
            if clipped is None:
                continue

        normalized.append(clipped)
        cursor = max(cursor, clipped.end)

    if cursor < day_end:
        normalized.append(
            TripSegment(
                type="OFF_DUTY",
                label="Off duty (auto-fill)",
                start=cursor,
                end=day_end,
            )
        )

    return normalized


def _clip_to_day(segment: TripSegment, day_start: datetime, day_end: datetime) -> TripSegment | None:
    """Clip one segment to the active day boundaries and rescale its distance."""
    start = max(segment.start, day_start)
    end = min(segment.end, day_end)
    if end <= start:
        return None

    original_seconds = (segment.end - segment.start).total_seconds()
    clipped_seconds = (end - start).total_seconds()
    if original_seconds <= 0:
        distance = 0.0
    else:
        distance = round(segment.distance_miles * (clipped_seconds / original_seconds), 4)
    return replace(segment, start=start, end=end, distance_miles=distance)


def _trim_segment_start(segment: TripSegment, new_start: datetime) -> TripSegment | None:
    """Trim a segment start forward and rescale distance for the remaining duration."""
    if new_start >= segment.end:
        return None

    original_seconds = (segment.end - segment.start).total_seconds()
    trimmed_seconds = (segment.end - new_start).total_seconds()
    if original_seconds <= 0:
        distance = 0.0
    else:
        distance = round(segment.distance_miles * (trimmed_seconds / original_seconds), 4)
    return replace(segment, start=new_start, distance_miles=distance)


def _day_boundary(day_date, tzinfo):
    """Return the midnight boundary for a date while preserving timezone awareness."""
    return datetime.combine(day_date, time.min, tzinfo=tzinfo)
