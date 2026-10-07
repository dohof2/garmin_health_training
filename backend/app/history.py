from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .database import connect
from .garmin_import import GARMIN_SOURCE_NAME


def history_summary(path: Path | None = None) -> dict[str, object]:
    with connect(path) as connection:
        activity_count = connection.execute(
            "SELECT COUNT(*) FROM activities"
        ).fetchone()[0]
        metric_count = connection.execute(
            "SELECT COUNT(*) FROM metric_readings"
        ).fetchone()[0]
        latest_activity = connection.execute(
            """
            SELECT id, activity_type, name, started_at, duration_seconds,
                   distance_meters, calories_kcal, source_name
            FROM activities
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        latest_steps = connection.execute(
            """
            SELECT value, unit, recorded_at, source_name
            FROM metric_readings
            WHERE metric_type = 'steps'
            ORDER BY recorded_at DESC
            LIMIT 1
            """
        ).fetchone()
        source_names = {
            row[0]
            for row in connection.execute(
                """
                SELECT source_name FROM activities
                UNION
                SELECT source_name FROM metric_readings
                """
            )
        }
        activity_bounds = connection.execute(
            """
            SELECT MIN(substr(started_at, 1, 10)), MAX(substr(started_at, 1, 10))
            FROM activities
            """
        ).fetchone()
        latest_metric_at = connection.execute(
            "SELECT MAX(recorded_at) FROM metric_readings"
        ).fetchone()[0]

    return {
        "data_mode": (
            "empty"
            if not source_names
            else "synthetic"
            if source_names == {"synthetic_fixture"}
            else "mixed"
            if "synthetic_fixture" in source_names
            else "real"
        ),
        "activity_count": activity_count,
        "metric_count": metric_count,
        "latest_activity": dict(latest_activity) if latest_activity else None,
        "latest_steps": dict(latest_steps) if latest_steps else None,
        "activity_date_start": activity_bounds[0],
        "activity_date_end": activity_bounds[1],
        "latest_metric_at": latest_metric_at,
    }


def weekly_calories_summary(path: Path | None = None) -> dict[str, object] | None:
    """Summarize the Monday-Sunday week containing the latest Garmin calorie day."""
    with connect(path) as connection:
        latest_recorded_at = connection.execute(
            """
            SELECT MAX(recorded_at)
            FROM metric_readings
            WHERE source_name = ? AND metric_type = 'total_calories'
            """,
            (GARMIN_SOURCE_NAME,),
        ).fetchone()[0]

        if latest_recorded_at is None:
            return None

        latest_date = date.fromisoformat(str(latest_recorded_at)[:10])
        week_start = latest_date - timedelta(days=latest_date.weekday())
        week_end = week_start + timedelta(days=6)
        rows = connection.execute(
            """
            SELECT metric_type, substr(recorded_at, 1, 10) AS recorded_date,
                   SUM(value) AS value
            FROM metric_readings
            WHERE source_name = ?
              AND metric_type IN (
                  'total_calories', 'active_calories', 'resting_calories'
              )
              AND substr(recorded_at, 1, 10) BETWEEN ? AND ?
            GROUP BY metric_type, substr(recorded_at, 1, 10)
            ORDER BY recorded_date, metric_type
            """,
            (GARMIN_SOURCE_NAME, week_start.isoformat(), week_end.isoformat()),
        ).fetchall()

    totals = {
        "total_calories": 0.0,
        "active_calories": 0.0,
        "resting_calories": 0.0,
    }
    total_dates: set[str] = set()
    for row in rows:
        totals[row["metric_type"]] += float(row["value"])
        if row["metric_type"] == "total_calories":
            total_dates.add(row["recorded_date"])

    expected_dates = [
        (week_start + timedelta(days=offset)).isoformat() for offset in range(7)
    ]
    missing_dates = [item for item in expected_dates if item not in total_dates]

    return {
        "basis": "latest_available_garmin_week",
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "days_expected": 7,
        "days_with_data": len(total_dates),
        "missing_dates": missing_dates,
        "is_complete": not missing_dates,
        "total_kcal": totals["total_calories"],
        "active_kcal": totals["active_calories"],
        "resting_kcal": totals["resting_calories"],
        "source_name": GARMIN_SOURCE_NAME,
    }


def list_activities(
    limit: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
    path: Path | None = None,
) -> list[dict[str, object]]:
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    query = """
        SELECT id, activity_type, name, started_at, ended_at, timezone,
               duration_seconds, distance_meters, calories_kcal,
               elevation_gain_meters, source_name
        FROM activities
    """
    clauses: list[str] = []
    parameters: list[object] = []
    if start_date:
        clauses.append("substr(started_at, 1, 10) >= ?")
        parameters.append(start_date.isoformat())
    if end_date:
        clauses.append("substr(started_at, 1, 10) <= ?")
        parameters.append(end_date.isoformat())
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY started_at DESC LIMIT ?"
    parameters.append(limit)

    with connect(path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_activity(activity_id: str, path: Path | None = None) -> dict[str, object] | None:
    with connect(path) as connection:
        activity = connection.execute(
            """
            SELECT id, activity_type, name, started_at, ended_at, timezone,
                   duration_seconds, distance_meters, calories_kcal,
                   elevation_gain_meters, source_name
            FROM activities
            WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        if activity is None:
            return None

        samples = connection.execute(
            """
            SELECT COUNT(*) AS sample_count,
                   MIN(recorded_at) AS first_sample_at,
                   MAX(recorded_at) AS last_sample_at,
                   AVG(heart_rate_bpm) AS average_heart_rate_bpm,
                   MAX(heart_rate_bpm) AS maximum_heart_rate_bpm,
                   AVG(power_watts) AS average_power_watts,
                   MAX(power_watts) AS maximum_power_watts,
                   MAX(speed_mps) AS maximum_speed_mps
            FROM activity_samples
            WHERE activity_id = ?
            """,
            (activity_id,),
        ).fetchone()

    result = dict(activity)
    result["sample_summary"] = dict(samples)
    return result


def list_metrics(
    metric_type: str | None = None,
    limit: int = 100,
    path: Path | None = None,
) -> list[dict[str, object]]:
    query = """
        SELECT id, metric_type, recorded_at, value, unit, source_name
        FROM metric_readings
    """
    parameters: list[object] = []
    if metric_type:
        query += " WHERE metric_type = ?"
        parameters.append(metric_type)
    query += " ORDER BY recorded_at DESC LIMIT ?"
    parameters.append(limit)

    with connect(path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]
