from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .database import connect, migrate
from .history import list_activities


MAX_ACTIVITY_RESULTS = 100
MAX_METRIC_TYPES = 20
MAX_QUERY_DAYS = 7_305
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

    sample_summaries: dict[str, dict[str, object]] = {}
    if ids:
        placeholders = ",".join("?" for _ in ids)
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
                ids,
            ).fetchall()
        sample_summaries = {str(row["activity_id"]): dict(row) for row in rows}

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
