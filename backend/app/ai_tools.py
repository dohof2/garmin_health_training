from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .database import connect, migrate
from .history import get_activity, list_activities
from .route_matching import compare_routes, load_gps_route


MAX_ACTIVITY_RESULTS = 100
MAX_METRIC_TYPES = 20
MAX_QUERY_DAYS = 7_305
MAX_SIMILAR_RIDE_RESULTS = 25
RIDE_ACTIVITY_TYPES = [
    "cycling",
    "gravel_cycling",
    "indoor_cycling",
    "mountain_biking",
    "virtual_ride",
]
AI_METRIC_TYPES = [
    "active_calories", "active_duration", "average_spo2", "average_stress",
    "awake_sleep", "body_battery_at_wake", "body_battery_charged",
    "body_battery_drained", "body_battery_high", "body_battery_latest",
    "body_battery_low", "deep_sleep", "distance", "floors_ascended",
    "floors_descended", "highly_active_duration", "hrv_last_night_5min_high",
    "hrv_last_night_average", "hrv_weekly_average", "intensity_minutes_goal",
    "light_sleep", "lowest_spo2", "maximum_heart_rate", "minimum_heart_rate",
    "moderate_intensity", "rem_sleep", "resting_calories",
    "resting_heart_rate", "sedentary_duration", "sleep_average_heart_rate",
    "sleep_body_battery_change", "sleep_duration", "sleep_hrv_average",
    "sleep_respiration", "sleep_score", "sleep_spo2_average",
    "sleep_spo2_lowest", "sleep_stress", "step_goal", "steps",
    "total_calories", "unmeasurable_sleep", "vigorous_intensity",
    "waking_respiration", "weight",
]
METRIC_TYPE_ALIASES = {
    "calories": "total_calories",
    "heart_rate": "resting_heart_rate",
    "hrv": "hrv_last_night_average",
    "sleep": "sleep_duration",
}
ADDITIVE_METRICS = {
    "active_calories",
    "active_duration",
    "distance",
    "highly_active_duration",
    "moderate_intensity",
    "resting_calories",
    "steps",
    "total_calories",
    "vigorous_intensity",
}
DURATION_METRICS = {
    "active_duration",
    "awake_sleep",
    "deep_sleep",
    "highly_active_duration",
    "light_sleep",
    "moderate_intensity",
    "rem_sleep",
    "sedentary_duration",
    "sleep_duration",
    "unmeasurable_sleep",
    "vigorous_intensity",
}


TOOL_DEFINITIONS: list[dict[str, object]] = [
    {
        "name": "get_health_summary",
        "description": (
            "Return deterministic aggregates and coverage for normalized health "
            "metrics in an inclusive date range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "metric_types": {
                    "type": "array",
                    "description": (
                        "Normalized metric names. Use sleep_duration for total sleep, "
                        "steps for steps, resting_heart_rate for resting heart rate, "
                        "and hrv_last_night_average for overnight HRV."
                    ),
                    "items": {"type": "string", "enum": AI_METRIC_TYPES},
                    "maxItems": MAX_METRIC_TYPES,
                },
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_activities",
        "description": (
            "List stored activities and available sensor summaries for an inclusive "
            "date range, with stable evidence links."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "activity_type": {
                    "type": ["string", "null"],
                    "maxLength": 80,
                    "description": "Normalized type such as running, cycling, or strength_training; null for all types.",
                },
                "timezone": {"type": ["string", "null"], "maxLength": 100},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_ACTIVITY_RESULTS,
                },
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_periods",
        "description": (
            "Compare deterministic activity totals and selected health-metric "
            "averages between two inclusive date ranges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period_a_start": {"type": "string", "format": "date"},
                "period_a_end": {"type": "string", "format": "date"},
                "period_b_start": {"type": "string", "format": "date"},
                "period_b_end": {"type": "string", "format": "date"},
                "activity_type": {
                    "type": ["string", "null"],
                    "maxLength": 80,
                    "description": "Normalized type such as running, cycling, or strength_training; null for all types.",
                },
                "metric_types": {
                    "type": "array",
                    "description": (
                        "Normalized metric names. Use sleep_duration for total sleep, "
                        "steps for steps, resting_heart_rate for resting heart rate, "
                        "and hrv_last_night_average for overnight HRV."
                    ),
                    "items": {"type": "string", "enum": AI_METRIC_TYPES},
                    "maxItems": MAX_METRIC_TYPES,
                },
                "timezone": {"type": ["string", "null"], "maxLength": 100},
            },
            "required": [
                "period_a_start",
                "period_a_end",
                "period_b_start",
                "period_b_end",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_similar_rides",
        "description": (
            "Find rides similar to a reference ride using deterministic, visible, "
            "adjustable activity-type, duration, distance, and elevation criteria. "
            "Omit reference_activity_id to use the latest stored ride."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference_activity_id": {
                    "type": ["string", "null"],
                    "maxLength": 200,
                },
                "candidate_start_date": {"type": ["string", "null"], "format": "date"},
                "candidate_end_date": {"type": ["string", "null"], "format": "date"},
                "candidate_activity_types": {
                    "type": ["array", "null"],
                    "description": (
                        "Ride types to include. Null uses only the reference ride's exact "
                        "type, keeping indoor and outdoor rides separate."
                    ),
                    "items": {"type": "string", "enum": RIDE_ACTIVITY_TYPES},
                    "maxItems": len(RIDE_ACTIVITY_TYPES),
                },
                "duration_tolerance_percent": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Null disables duration matching; omitted defaults to 30%.",
                },
                "distance_tolerance_percent": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Null disables distance matching; omitted defaults to 30%.",
                },
                "elevation_tolerance_percent": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Null disables elevation matching; omitted defaults to 50%.",
                },
                "timezone": {"type": ["string", "null"], "maxLength": 100},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SIMILAR_RIDE_RESULTS,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_same_course_rides",
        "description": (
            "Find repeated attempts on the same outdoor course using local GPS route "
            "overlap, endpoints, distance, and direction. Returns deterministic "
            "earliest-to-latest performance changes without exposing coordinates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference_activity_id": {
                    "type": ["string", "null"],
                    "maxLength": 200,
                },
                "reference_date": {
                    "type": ["string", "null"],
                    "format": "date",
                    "description": "Local calendar date of the reference ride; omit to use the latest GPS ride.",
                },
                "candidate_start_date": {"type": ["string", "null"], "format": "date"},
                "candidate_end_date": {"type": ["string", "null"], "format": "date"},
                "candidate_activity_types": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "enum": RIDE_ACTIVITY_TYPES},
                    "maxItems": len(RIDE_ACTIVITY_TYPES),
                },
                "distance_tolerance_percent": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "maximum": 50,
                    "description": "Null disables distance prefiltering; omitted defaults to 15%.",
                },
                "route_tolerance_meters": {
                    "type": "number",
                    "minimum": 20,
                    "maximum": 500,
                    "description": "Maximum distance from the other route for a GPS point to count as overlapping; defaults to 100 m.",
                },
                "minimum_route_overlap_percent": {
                    "type": "number",
                    "minimum": 50,
                    "maximum": 100,
                    "description": "Required bidirectional route coverage; defaults to 80%.",
                },
                "endpoint_tolerance_meters": {
                    "type": "number",
                    "minimum": 50,
                    "maximum": 2000,
                    "description": "Maximum start/end separation; defaults to 500 m.",
                },
                "allow_reverse_direction": {"type": "boolean"},
                "timezone": {"type": ["string", "null"], "maxLength": 100},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SIMILAR_RIDE_RESULTS,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
]


def _parse_period(start_value: object, end_value: object) -> tuple[date, date]:
    try:
        start = date.fromisoformat(str(start_value))
        end = date.fromisoformat(str(end_value))
    except ValueError as error:
        raise ValueError("date values must use YYYY-MM-DD") from error
    if start > end:
        raise ValueError("start date must be on or before end date")
    if (end - start).days + 1 > MAX_QUERY_DAYS:
        raise ValueError(f"date range cannot exceed {MAX_QUERY_DAYS} days")
    return start, end


def _metric_types(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("metric_types must be a list")
    if not value or len(value) > MAX_METRIC_TYPES:
        raise ValueError(f"metric_types must contain 1 to {MAX_METRIC_TYPES} values")
    if any(not isinstance(item, str) for item in value):
        raise ValueError("every metric type must be a string")
    normalized = [
        METRIC_TYPE_ALIASES.get(item.strip().lower(), item.strip().lower())
        for item in value
    ]
    if any(not item or len(item) > 80 for item in normalized):
        raise ValueError("metric types must be 1 to 80 characters")
    if len(set(normalized)) != len(normalized):
        raise ValueError("metric_types must not contain duplicates")
    return normalized


def _optional_activity_type(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("activity_type must be a string")
    activity_type = value.strip().lower()
    if not activity_type:
        return None
    if len(activity_type) > 80:
        raise ValueError("activity_type must be 80 characters or fewer")
    return activity_type


def _optional_timezone(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timezone must be a string")
    timezone_name = value.strip()
    if not timezone_name:
        return None
    if len(timezone_name) > 100:
        raise ValueError("timezone must be 100 characters or fewer")
    return timezone_name


def _optional_identifier(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    identifier = value.strip()
    if not identifier:
        return None
    if len(identifier) > 200:
        raise ValueError(f"{label} must be 200 characters or fewer")
    return identifier


def _optional_tolerance(arguments: dict[str, object], name: str, default: float) -> float | None:
    if name not in arguments:
        return default
    value = arguments[name]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or null")
    tolerance = float(value)
    if not 0 <= tolerance <= 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return tolerance


def _bounded_number(
    arguments: dict[str, object],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def _boolean_argument(
    arguments: dict[str, object], name: str, default: bool
) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _candidate_activity_types(value: object, reference_type: str) -> list[str]:
    if value is None:
        return [reference_type]
    if not isinstance(value, list) or not value:
        raise ValueError("candidate_activity_types must be null or a non-empty list")
    if len(value) > len(RIDE_ACTIVITY_TYPES) or any(
        not isinstance(item, str) or item not in RIDE_ACTIVITY_TYPES for item in value
    ):
        raise ValueError("candidate_activity_types contains an unsupported ride type")
    if len(set(value)) != len(value):
        raise ValueError("candidate_activity_types must not contain duplicates")
    return list(value)


def _optional_candidate_period(arguments: dict[str, object]) -> tuple[date | None, date | None]:
    start_value = arguments.get("candidate_start_date")
    end_value = arguments.get("candidate_end_date")
    if start_value is None and end_value is None:
        return None, None
    if start_value is None or end_value is None:
        raise ValueError("candidate_start_date and candidate_end_date must be used together")
    return _parse_period(start_value, end_value)


def _coverage(start: date, end: date, recorded_dates: set[str]) -> dict[str, object]:
    days_expected = (end - start).days + 1
    missing_count = days_expected - len(recorded_dates)
    missing_dates: list[str] = []
    if days_expected <= 366:
        missing_dates = [
            (start + timedelta(days=offset)).isoformat()
            for offset in range(days_expected)
            if (start + timedelta(days=offset)).isoformat() not in recorded_dates
        ]
    return {
        "days_expected": days_expected,
        "days_with_data": len(recorded_dates),
        "missing_day_count": missing_count,
        "missing_dates": missing_dates,
        "missing_dates_omitted": days_expected > 366,
        "has_record_for_every_date": missing_count == 0,
        "coverage_note": (
            "Dates without records are reported as gaps, not as zero values. "
            "Some metrics are recorded only when measured and are not expected daily."
        ),
    }


def _health_summary(
    start: date,
    end: date,
    metric_types: list[str] | None,
    path: Path | None,
) -> dict[str, object]:
    migrate(path)
    query = """
        SELECT metric_type, unit, substr(recorded_at, 1, 10) AS recorded_date,
               value, source_name, recorded_at
        FROM metric_readings
        WHERE substr(recorded_at, 1, 10) BETWEEN ? AND ?
    """
    parameters: list[object] = [start.isoformat(), end.isoformat()]
    if metric_types:
        placeholders = ",".join("?" for _ in metric_types)
        query += f" AND metric_type IN ({placeholders})"
        parameters.extend(metric_types)
    query += " ORDER BY metric_type, recorded_at"

    with connect(path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    source_names: set[str] = set()
    latest_recorded_at: str | None = None
    for row in rows:
        key = (str(row["metric_type"]), str(row["unit"]))
        group = grouped.setdefault(
            key,
            {
                "metric_type": key[0],
                "unit": key[1],
                "values": [],
                "recorded_dates": set(),
                "sources": set(),
            },
        )
        group["values"].append(float(row["value"]))
        group["recorded_dates"].add(str(row["recorded_date"]))
        group["sources"].add(str(row["source_name"]))
        source_names.add(str(row["source_name"]))
        latest_recorded_at = max(latest_recorded_at or "", str(row["recorded_at"]))

    metrics: list[dict[str, object]] = []
    for group in grouped.values():
        values = group.pop("values")
        recorded_dates = group.pop("recorded_dates")
        sources = sorted(group.pop("sources"))
        source_unit = str(group["unit"])
        if group["metric_type"] in DURATION_METRICS and source_unit == "s":
            values = [value / 3_600 for value in values]
            group["unit"] = "hours"
        metrics.append(
            {
                **group,
                "source_unit": source_unit,
                "count": len(values),
                "sum": sum(values),
                "average": sum(values) / len(values),
                "minimum": min(values),
                "maximum": max(values),
                "recommended_aggregation": (
                    "sum" if group["metric_type"] in ADDITIVE_METRICS else "average"
                ),
                "sources": sources,
                "coverage": _coverage(start, end, recorded_dates),
            }
        )

    found_types = {str(item["metric_type"]) for item in metrics}
    return {
        "tool": "get_health_summary",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "metrics": metrics,
        "requested_metric_types": metric_types,
        "missing_metric_types": (
            [item for item in metric_types if item not in found_types]
            if metric_types
            else []
        ),
        "freshness": {
            "latest_recorded_at": latest_recorded_at,
            "sources": sorted(source_names),
        },
        "evidence": {
            "record_count": len(rows),
            "record_endpoint": "/api/metrics",
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
    }


def get_health_summary_tool(
    arguments: dict[str, object], path: Path | None = None
) -> dict[str, object]:
    start, end = _parse_period(arguments.get("start_date"), arguments.get("end_date"))
    return _health_summary(start, end, _metric_types(arguments.get("metric_types")), path)


def list_activities_tool(
    arguments: dict[str, object], path: Path | None = None
) -> dict[str, object]:
    start, end = _parse_period(arguments.get("start_date"), arguments.get("end_date"))
    activity_type = _optional_activity_type(arguments.get("activity_type"))
    timezone_name = _optional_timezone(arguments.get("timezone"))
    limit_value = arguments.get("limit", 20)
    if isinstance(limit_value, bool) or not isinstance(limit_value, int):
        raise ValueError("limit must be an integer")
    limit = limit_value
    if not 1 <= limit <= MAX_ACTIVITY_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_ACTIVITY_RESULTS}")

    activities = list_activities(
        limit=10_000,
        start_date=start,
        end_date=end,
        timezone_name=timezone_name,
        path=path,
    )
    if activity_type:
        activities = [
            item for item in activities if item["activity_type"] == activity_type
        ]
    total_matches = len(activities)
    selected = activities[:limit]
    ids = [str(item["id"]) for item in selected]
    sample_summaries = _sample_summaries(ids, path)

    source_names: set[str] = set()
    for activity in selected:
        activity["sample_summary"] = sample_summaries.get(
            str(activity["id"]),
            {
                "sample_count": 0,
                "average_heart_rate_bpm": None,
                "maximum_heart_rate_bpm": None,
                "average_power_watts": None,
                "maximum_power_watts": None,
                "average_cadence_rpm": None,
                "average_speed_mps": None,
            },
        )
        activity["evidence_url"] = f"/api/activities/{activity['id']}"
        source_names.add(str(activity["source_name"]))

    return {
        "tool": "list_activities",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "filters": {"activity_type": activity_type, "timezone": timezone_name},
        "total_matches": total_matches,
        "returned_count": len(selected),
        "truncated": total_matches > len(selected),
        "activities": selected,
        "freshness": {
            "latest_started_at": selected[0]["started_at"] if selected else None,
            "sources": sorted(source_names),
        },
    }


def _sample_summaries(
    activity_ids: list[str], path: Path | None
) -> dict[str, dict[str, object]]:
    if not activity_ids:
        return {}
    placeholders = ",".join("?" for _ in activity_ids)
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT activity_id, COUNT(*) AS sample_count,
                   AVG(heart_rate_bpm) AS average_heart_rate_bpm,
                   MAX(heart_rate_bpm) AS maximum_heart_rate_bpm,
                   AVG(power_watts) AS average_power_watts,
                   MAX(power_watts) AS maximum_power_watts,
                   AVG(cadence_rpm) AS average_cadence_rpm,
                   AVG(speed_mps) AS average_speed_mps
            FROM activity_samples
            WHERE activity_id IN ({placeholders})
            GROUP BY activity_id
            """,
            activity_ids,
        ).fetchall()
    return {str(row["activity_id"]): dict(row) for row in rows}


def _empty_sample_summary() -> dict[str, object]:
    return {
        "sample_count": 0,
        "average_heart_rate_bpm": None,
        "maximum_heart_rate_bpm": None,
        "average_power_watts": None,
        "maximum_power_watts": None,
        "average_cadence_rpm": None,
        "average_speed_mps": None,
    }


def _similarity_criterion(
    field: str,
    label: str,
    unit: str,
    reference_value: object,
    tolerance_percent: float | None,
    scale: float = 1.0,
) -> dict[str, object]:
    if tolerance_percent is None:
        return {
            "field": field,
            "label": label,
            "unit": unit,
            "applied": False,
            "reason": "Disabled by the selected filters.",
        }
    if reference_value is None:
        return {
            "field": field,
            "label": label,
            "unit": unit,
            "applied": False,
            "reason": "The reference ride does not contain this value.",
        }
    reference = float(reference_value) / scale
    fraction = tolerance_percent / 100
    return {
        "field": field,
        "label": label,
        "unit": unit,
        "applied": True,
        "reference_value": reference,
        "tolerance_percent": tolerance_percent,
        "minimum": max(0.0, reference * (1 - fraction)),
        "maximum": reference * (1 + fraction),
        "source_scale": scale,
    }


def _ride_result(
    activity: dict[str, object],
    sample_summary: dict[str, object],
    *,
    evidence_url: str,
    similarity_score: float | None = None,
    differences: dict[str, dict[str, float | None]] | None = None,
) -> dict[str, object]:
    comparison_metrics = {
        "sample_count": sample_summary.get("sample_count", 0),
        "average_heart_rate_bpm": sample_summary.get("average_heart_rate_bpm"),
        "maximum_heart_rate_bpm": sample_summary.get("maximum_heart_rate_bpm"),
        "average_power_watts": sample_summary.get("average_power_watts"),
        "maximum_power_watts": sample_summary.get("maximum_power_watts"),
        "average_cadence_rpm": sample_summary.get("average_cadence_rpm"),
        "average_speed_kilometers_per_hour": (
            float(sample_summary["average_speed_mps"]) * 3.6
            if sample_summary.get("average_speed_mps") is not None
            else None
        ),
    }
    result = {
        "id": activity["id"],
        "name": activity["name"],
        "activity_type": activity["activity_type"],
        "started_at": activity["started_at"],
        "local_date": activity["local_date"],
        "duration_hours": (
            float(activity["duration_seconds"]) / 3_600
            if activity.get("duration_seconds") is not None
            else None
        ),
        "distance_kilometers": (
            float(activity["distance_meters"]) / 1_000
            if activity.get("distance_meters") is not None
            else None
        ),
        "calories_kcal": activity.get("calories_kcal"),
        "elevation_gain_meters": activity.get("elevation_gain_meters"),
        "source_name": activity["source_name"],
        "comparison_metrics": comparison_metrics,
        "evidence_url": evidence_url,
    }
    if similarity_score is not None:
        result["similarity_score"] = similarity_score
    if differences is not None:
        result["differences_from_reference"] = differences
    return result


def find_similar_rides_tool(
    arguments: dict[str, object], path: Path | None = None
) -> dict[str, object]:
    migrate(path)
    timezone_name = _optional_timezone(arguments.get("timezone"))
    reference_id = _optional_identifier(
        arguments.get("reference_activity_id"), "reference_activity_id"
    )
    if reference_id:
        reference = get_activity(reference_id, path, timezone_name)
        if reference is None:
            raise ValueError("reference ride was not found")
    else:
        reference = next(
            (
                item
                for item in list_activities(
                    limit=10_000, timezone_name=timezone_name, path=path
                )
                if item["activity_type"] in RIDE_ACTIVITY_TYPES
            ),
            None,
        )
        if reference is None:
            raise ValueError("no stored ride is available as a reference")
        reference = get_activity(str(reference["id"]), path, timezone_name)
        if reference is None:
            raise ValueError("reference ride was not found")

    reference_type = str(reference["activity_type"])
    if reference_type not in RIDE_ACTIVITY_TYPES:
        raise ValueError("reference activity is not a supported ride type")
    candidate_types = _candidate_activity_types(
        arguments.get("candidate_activity_types"), reference_type
    )
    start, end = _optional_candidate_period(arguments)
    duration_tolerance = _optional_tolerance(
        arguments, "duration_tolerance_percent", 30
    )
    distance_tolerance = _optional_tolerance(
        arguments, "distance_tolerance_percent", 30
    )
    elevation_tolerance = _optional_tolerance(
        arguments, "elevation_tolerance_percent", 50
    )
    limit_value = arguments.get("limit", 10)
    if isinstance(limit_value, bool) or not isinstance(limit_value, int):
        raise ValueError("limit must be an integer")
    if not 1 <= limit_value <= MAX_SIMILAR_RIDE_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_SIMILAR_RIDE_RESULTS}")

    criteria = [
        {
            "field": "activity_type",
            "label": "Ride type / indoor-outdoor category",
            "applied": True,
            "reference_value": reference_type,
            "accepted_values": candidate_types,
            "match": "exact normalized type",
        },
        _similarity_criterion(
            "duration_seconds",
            "Duration",
            "hours",
            reference.get("duration_seconds"),
            duration_tolerance,
            3_600,
        ),
        _similarity_criterion(
            "distance_meters",
            "Distance",
            "kilometers",
            reference.get("distance_meters"),
            distance_tolerance,
            1_000,
        ),
        _similarity_criterion(
            "elevation_gain_meters",
            "Elevation gain",
            "meters",
            reference.get("elevation_gain_meters"),
            elevation_tolerance,
        ),
    ]
    numeric_criteria = [
        item for item in criteria if item["field"] != "activity_type" and item["applied"]
    ]
    if not numeric_criteria:
        raise ValueError("no numeric similarity criterion is available or enabled")

    candidates = [
        item
        for item in list_activities(
            limit=10_000,
            start_date=start,
            end_date=end,
            timezone_name=timezone_name,
            path=path,
        )
        if str(item["id"]) != str(reference["id"])
        and str(item["activity_type"]) in candidate_types
    ]
    excluded_missing = {str(item["field"]): 0 for item in numeric_criteria}
    matched: list[dict[str, object]] = []
    for candidate in candidates:
        differences: dict[str, dict[str, float | None]] = {}
        normalized_differences: list[float] = []
        accepted = True
        for criterion in numeric_criteria:
            field = str(criterion["field"])
            candidate_value = candidate.get(field)
            if candidate_value is None:
                excluded_missing[field] += 1
                accepted = False
                break
            scale = float(criterion.get("source_scale", 1.0))
            reference_value = float(criterion["reference_value"])
            value = float(candidate_value) / scale
            absolute = value - reference_value
            percent = (
                absolute / reference_value * 100
                if reference_value
                else 0.0 if value == 0 else None
            )
            if not float(criterion["minimum"]) <= value <= float(criterion["maximum"]):
                accepted = False
                break
            tolerance = float(criterion["tolerance_percent"])
            normalized_differences.append(
                0.0
                if tolerance == 0
                else min(1.0, abs(percent or 0.0) / tolerance)
            )
            differences[field] = {"absolute": absolute, "percent": percent}
        if accepted:
            matched.append(
                {
                    "activity": candidate,
                    "similarity_score": round(
                        100 * (1 - sum(normalized_differences) / len(normalized_differences)),
                        1,
                    ),
                    "differences": differences,
                }
            )

    matched.sort(
        key=lambda item: (
            -float(item["similarity_score"]),
            str(item["activity"]["started_at"]),
        ),
    )
    total_matches = len(matched)
    selected = matched[:limit_value]
    summary_ids = [
        str(reference["id"]),
        *[str(item["activity"]["id"]) for item in matched],
    ]
    summaries = _sample_summaries(summary_ids, path)
    reference_summary = summaries.get(
        str(reference["id"]), reference.get("sample_summary") or _empty_sample_summary()
    )
    reference_result = _ride_result(
        reference,
        reference_summary,
        evidence_url=f"/api/activities/{reference['id']}",
    )
    ride_results = [
        _ride_result(
            item["activity"],
            summaries.get(str(item["activity"]["id"]), _empty_sample_summary()),
            evidence_url=f"/api/activities/{item['activity']['id']}",
            similarity_score=float(item["similarity_score"]),
            differences=item["differences"],
        )
        for item in selected
    ]
    public_criteria = [
        {key: value for key, value in item.items() if key != "source_scale"}
        for item in criteria
    ]

    return {
        "tool": "find_similar_rides",
        "reference_ride": reference_result,
        "candidate_period": (
            {"start": start.isoformat(), "end": end.isoformat()}
            if start and end
            else None
        ),
        "criteria": public_criteria,
        "unavailable_criteria": [
            "route identity",
            "intended intensity",
            "equipment",
            "weather",
        ],
        "candidate_pool_count": len(candidates),
        "evaluated_count": len(candidates) - sum(excluded_missing.values()),
        "excluded_for_missing_values": excluded_missing,
        "total_matches": total_matches,
        "returned_count": len(selected),
        "truncated": total_matches > len(selected),
        "rides": ride_results,
        "freshness": {
            "latest_started_at": candidates[0]["started_at"] if candidates else None,
            "sources": sorted(
                {str(reference["source_name"])}
                | {str(item["activity"]["source_name"]) for item in selected}
            ),
        },
        "limitations": [
            "Similarity means the ride passed the displayed filters; it does not imply the same route, conditions, equipment, or purpose.",
            "Heart rate, power, cadence, and speed are returned only when recorded and are comparison evidence, not matching criteria.",
        ],
    }


def _course_progress(attempts: list[dict[str, object]]) -> dict[str, object] | None:
    if len(attempts) < 2:
        return None
    ordered = sorted(attempts, key=lambda item: str(item["started_at"]))
    earliest = ordered[0]
    latest = ordered[-1]

    def change(
        label: str, earliest_value: object, latest_value: object, unit: str
    ) -> dict[str, object] | None:
        if earliest_value is None or latest_value is None:
            return None
        delta = _delta(float(latest_value), float(earliest_value))
        return {
            "metric": label,
            "unit": unit,
            "earliest": float(earliest_value),
            "latest": float(latest_value),
            **delta,
        }

    earliest_metrics = earliest["comparison_metrics"]
    latest_metrics = latest["comparison_metrics"]
    changes = [
        change(
            "duration",
            earliest.get("duration_hours"),
            latest.get("duration_hours"),
            "hours",
        ),
        change(
            "average speed",
            earliest_metrics.get("average_speed_kilometers_per_hour"),
            latest_metrics.get("average_speed_kilometers_per_hour"),
            "kilometers_per_hour",
        ),
        change(
            "average heart rate",
            earliest_metrics.get("average_heart_rate_bpm"),
            latest_metrics.get("average_heart_rate_bpm"),
            "bpm",
        ),
        change(
            "average power",
            earliest_metrics.get("average_power_watts"),
            latest_metrics.get("average_power_watts"),
            "watts",
        ),
        change(
            "average cadence",
            earliest_metrics.get("average_cadence_rpm"),
            latest_metrics.get("average_cadence_rpm"),
            "rpm",
        ),
    ]
    return {
        "attempt_count": len(ordered),
        "earliest": {
            "id": earliest["id"],
            "local_date": earliest["local_date"],
            "evidence_url": earliest["evidence_url"],
        },
        "latest": {
            "id": latest["id"],
            "local_date": latest["local_date"],
            "evidence_url": latest["evidence_url"],
        },
        "changes_latest_minus_earliest": [item for item in changes if item],
        "interpretation_notes": [
            "A negative duration change means the latest attempt was faster over the matched course.",
            "Heart-rate, power, and cadence changes are observations, not proof of improved fitness or efficiency.",
            "Conditions, stops, equipment, surface, and weather may differ because they are not normalized for matching.",
        ],
    }


def find_same_course_rides_tool(
    arguments: dict[str, object], path: Path | None = None
) -> dict[str, object]:
    migrate(path)
    timezone_name = _optional_timezone(arguments.get("timezone"))
    reference_id = _optional_identifier(
        arguments.get("reference_activity_id"), "reference_activity_id"
    )
    reference_date_value = arguments.get("reference_date")
    reference_date = None
    if reference_date_value is not None:
        try:
            reference_date = date.fromisoformat(str(reference_date_value))
        except ValueError as error:
            raise ValueError("reference_date must use YYYY-MM-DD") from error
    if reference_id and reference_date:
        raise ValueError("use reference_activity_id or reference_date, not both")
    reference_points: list[tuple[float, float]] = []
    if reference_id:
        reference = get_activity(reference_id, path, timezone_name)
        if reference is None:
            raise ValueError("reference ride was not found")
        reference_points = load_gps_route(reference_id, path)
    elif reference_date:
        reference = next(
            (
                item
                for item in list_activities(
                    limit=100,
                    start_date=reference_date,
                    end_date=reference_date,
                    timezone_name=timezone_name,
                    path=path,
                )
                if item["activity_type"] in RIDE_ACTIVITY_TYPES
            ),
            None,
        )
        if reference is None:
            raise ValueError("no stored ride was found on reference_date")
        reference = get_activity(str(reference["id"]), path, timezone_name)
        reference_points = load_gps_route(str(reference["id"]), path)
    else:
        reference = None
        for item in list_activities(
            limit=10_000, timezone_name=timezone_name, path=path
        ):
            if item["activity_type"] not in RIDE_ACTIVITY_TYPES:
                continue
            points = load_gps_route(str(item["id"]), path)
            if len(points) >= 10:
                reference = get_activity(str(item["id"]), path, timezone_name)
                reference_points = points
                break
        if reference is None:
            raise ValueError("no stored GPS ride is available as a reference")

    reference_type = str(reference["activity_type"])
    if reference_type not in RIDE_ACTIVITY_TYPES:
        raise ValueError("reference activity is not a supported ride type")
    if len(reference_points) < 10:
        raise ValueError("reference ride does not contain enough GPS points")

    candidate_types = _candidate_activity_types(
        arguments.get("candidate_activity_types"), reference_type
    )
    start, end = _optional_candidate_period(arguments)
    distance_tolerance = _optional_tolerance(
        arguments, "distance_tolerance_percent", 15
    )
    if distance_tolerance is not None and distance_tolerance > 50:
        raise ValueError("distance_tolerance_percent must be between 0 and 50")
    route_tolerance = _bounded_number(
        arguments, "route_tolerance_meters", 100, 20, 500
    )
    minimum_overlap = _bounded_number(
        arguments, "minimum_route_overlap_percent", 80, 50, 100
    )
    endpoint_tolerance = _bounded_number(
        arguments, "endpoint_tolerance_meters", 500, 50, 2_000
    )
    allow_reverse = _boolean_argument(
        arguments, "allow_reverse_direction", True
    )
    limit_value = arguments.get("limit", 10)
    if isinstance(limit_value, bool) or not isinstance(limit_value, int):
        raise ValueError("limit must be an integer")
    if not 1 <= limit_value <= MAX_SIMILAR_RIDE_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_SIMILAR_RIDE_RESULTS}")

    distance_criterion = _similarity_criterion(
        "distance_meters",
        "Distance prefilter",
        "kilometers",
        reference.get("distance_meters"),
        distance_tolerance,
        1_000,
    )
    criteria = [
        {
            "field": "activity_type",
            "label": "Ride type / indoor-outdoor category",
            "applied": True,
            "reference_value": reference_type,
            "accepted_values": candidate_types,
            "match": "exact normalized type",
        },
        {key: value for key, value in distance_criterion.items() if key != "source_scale"},
        {
            "field": "route_overlap",
            "label": "GPS route overlap",
            "applied": True,
            "description": f"At least {minimum_overlap:g}% bidirectional coverage with points within {route_tolerance:g} m.",
        },
        {
            "field": "endpoints",
            "label": "Start and finish",
            "applied": True,
            "description": f"Both endpoints must be within {endpoint_tolerance:g} m.",
        },
        {
            "field": "direction",
            "label": "Direction",
            "applied": True,
            "description": "Same or reverse direction is allowed." if allow_reverse else "Only the same direction is allowed.",
        },
    ]

    candidates = []
    for item in list_activities(
        limit=10_000,
        start_date=start,
        end_date=end,
        timezone_name=timezone_name,
        path=path,
    ):
        if str(item["id"]) == str(reference["id"]):
            continue
        if str(item["activity_type"]) not in candidate_types:
            continue
        if distance_criterion["applied"]:
            candidate_distance = item.get("distance_meters")
            if candidate_distance is None:
                continue
            candidate_kilometers = float(candidate_distance) / 1_000
            if not float(distance_criterion["minimum"]) <= candidate_kilometers <= float(
                distance_criterion["maximum"]
            ):
                continue
        candidates.append(item)

    matched: list[dict[str, object]] = []
    excluded_without_gps = 0
    for candidate in candidates:
        candidate_points = load_gps_route(str(candidate["id"]), path)
        if len(candidate_points) < 10:
            excluded_without_gps += 1
            continue
        route_match = compare_routes(
            reference_points,
            candidate_points,
            route_tolerance_meters=route_tolerance,
            endpoint_tolerance_meters=endpoint_tolerance,
            allow_reverse_direction=allow_reverse,
        )
        if not route_match["usable"]:
            excluded_without_gps += 1
            continue
        if float(route_match["endpoint_distance_meters"]) > endpoint_tolerance:
            continue
        if float(route_match["route_overlap_percent"]) < minimum_overlap:
            continue
        if not route_match["direction_allowed"]:
            continue
        matched.append({"activity": candidate, "route_match": route_match})

    matched.sort(
        key=lambda item: (
            -float(item["route_match"]["route_overlap_percent"]),
            float(item["route_match"]["endpoint_distance_meters"]),
        )
    )
    total_matches = len(matched)
    selected = matched[:limit_value]
    summary_ids = [
        str(reference["id"]),
        *[str(item["activity"]["id"]) for item in selected],
    ]
    summaries = _sample_summaries(summary_ids, path)
    reference_result = _ride_result(
        reference,
        summaries.get(
            str(reference["id"]),
            reference.get("sample_summary") or _empty_sample_summary(),
        ),
        evidence_url=f"/api/activities/{reference['id']}",
    )
    reference_result["gps_point_count"] = len(reference_points)
    all_ride_results = []
    for item in matched:
        activity = item["activity"]
        ride = _ride_result(
            activity,
            summaries.get(str(activity["id"]), _empty_sample_summary()),
            evidence_url=f"/api/activities/{activity['id']}",
        )
        ride["route_match"] = item["route_match"]
        all_ride_results.append(ride)

    ride_results = all_ride_results[:limit_value]
    attempts = [reference_result, *all_ride_results]
    return {
        "tool": "find_same_course_rides",
        "reference_ride": reference_result,
        "candidate_period": (
            {"start": start.isoformat(), "end": end.isoformat()}
            if start and end
            else None
        ),
        "criteria": criteria,
        "candidate_pool_count": len(candidates),
        "gps_candidates_evaluated": len(candidates) - excluded_without_gps,
        "excluded_without_gps": excluded_without_gps,
        "total_matches": total_matches,
        "returned_count": len(ride_results),
        "truncated": total_matches > len(ride_results),
        "rides": ride_results,
        "course_progress": _course_progress(attempts),
        "unavailable_criteria": [
            "weather",
            "surface condition",
            "stops",
            "equipment",
            "intended effort",
        ],
        "freshness": {
            "latest_started_at": max(
                [str(reference["started_at"])]
                + [str(item["started_at"]) for item in ride_results]
            ),
            "sources": sorted(
                {str(reference["source_name"])}
                | {str(item["source_name"]) for item in ride_results}
            ),
        },
        "privacy": "Raw GPS coordinates were processed locally and are not included in this result.",
        "limitations": [
            "Course matching measures recorded track proximity and endpoints; GPS noise or reroutes can change overlap.",
            "Weather, surface condition, stops, equipment, and intended effort are not normalized.",
            "Performance changes are observations and do not alone establish improved fitness.",
        ],
    }


def _activity_totals(
    start: date,
    end: date,
    activity_type: str | None,
    timezone_name: str | None,
    path: Path | None,
) -> dict[str, object]:
    activities = list_activities(
        limit=10_000,
        start_date=start,
        end_date=end,
        timezone_name=timezone_name,
        path=path,
    )
    if activity_type:
        activities = [
            item for item in activities if item["activity_type"] == activity_type
        ]

    def total(field: str) -> float:
        return sum(float(item[field]) for item in activities if item[field] is not None)

    return {
        "activity_count": len(activities),
        "duration_seconds": total("duration_seconds"),
        "distance_meters": total("distance_meters"),
        "calories_kcal": total("calories_kcal"),
        "elevation_gain_meters": total("elevation_gain_meters"),
        "activity_ids": [str(item["id"]) for item in activities],
        "sources": sorted({str(item["source_name"]) for item in activities}),
        "latest_started_at": activities[0]["started_at"] if activities else None,
    }


def _delta(current: float | int, baseline: float | int) -> dict[str, float | None]:
    absolute = float(current) - float(baseline)
    return {
        "absolute": absolute,
        "percent": (absolute / float(baseline) * 100) if baseline else None,
    }


def compare_periods_tool(
    arguments: dict[str, object], path: Path | None = None
) -> dict[str, object]:
    a_start, a_end = _parse_period(
        arguments.get("period_a_start"), arguments.get("period_a_end")
    )
    b_start, b_end = _parse_period(
        arguments.get("period_b_start"), arguments.get("period_b_end")
    )
    activity_type = _optional_activity_type(arguments.get("activity_type"))
    metric_types = _metric_types(arguments.get("metric_types"))
    timezone_name = _optional_timezone(arguments.get("timezone"))

    period_a_activities = _activity_totals(
        a_start, a_end, activity_type, timezone_name, path
    )
    period_b_activities = _activity_totals(
        b_start, b_end, activity_type, timezone_name, path
    )
    period_a_health = _health_summary(a_start, a_end, metric_types, path)
    period_b_health = _health_summary(b_start, b_end, metric_types, path)

    activity_deltas = {
        field: _delta(period_b_activities[field], period_a_activities[field])
        for field in (
            "activity_count",
            "duration_seconds",
            "distance_meters",
            "calories_kcal",
            "elevation_gain_meters",
        )
    }
    a_metrics = {
        (str(item["metric_type"]), str(item["unit"])): item
        for item in period_a_health["metrics"]
    }
    b_metrics = {
        (str(item["metric_type"]), str(item["unit"])): item
        for item in period_b_health["metrics"]
    }
    metric_deltas = [
        {
            "metric_type": key[0],
            "unit": key[1],
            "average": _delta(b_metrics[key]["average"], a_metrics[key]["average"]),
            "period_a_average": a_metrics[key]["average"],
            "period_b_average": b_metrics[key]["average"],
        }
        for key in sorted(a_metrics.keys() & b_metrics.keys())
    ]

    return {
        "tool": "compare_periods",
        "direction": "period_b_minus_period_a",
        "filters": {"activity_type": activity_type, "timezone": timezone_name},
        "period_a": {
            "period": {"start": a_start.isoformat(), "end": a_end.isoformat()},
            "activities": period_a_activities,
            "health": period_a_health,
        },
        "period_b": {
            "period": {"start": b_start.isoformat(), "end": b_end.isoformat()},
            "activities": period_b_activities,
            "health": period_b_health,
        },
        "deltas": {"activities": activity_deltas, "metric_averages": metric_deltas},
        "limitations": [
            "Percent change is omitted when the period A value is zero.",
            "A comparison describes recorded differences and does not establish causation.",
        ],
    }


ToolHandler = Callable[[dict[str, object], Path | None], dict[str, object]]
TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_health_summary": get_health_summary_tool,
    "list_activities": list_activities_tool,
    "compare_periods": compare_periods_tool,
    "find_similar_rides": find_similar_rides_tool,
    "find_same_course_rides": find_same_course_rides_tool,
}
TOOL_DEFINITIONS_BY_NAME = {
    str(definition["name"]): definition for definition in TOOL_DEFINITIONS
}


def tool_definitions() -> list[dict[str, object]]:
    return TOOL_DEFINITIONS


def execute_tool(
    name: str,
    arguments: dict[str, object],
    path: Path | None = None,
) -> dict[str, object]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown AI tool: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    definition = TOOL_DEFINITIONS_BY_NAME[name]
    allowed = set(definition["input_schema"]["properties"])
    unexpected = sorted(set(arguments) - allowed)
    if unexpected:
        raise ValueError(f"Unexpected tool arguments: {', '.join(unexpected)}")
    return handler(arguments, path)
