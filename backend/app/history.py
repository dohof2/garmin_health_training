from __future__ import annotations

from pathlib import Path

from .database import connect


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
    }


def list_activities(limit: int = 20, path: Path | None = None) -> list[dict[str, object]]:
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT id, activity_type, name, started_at, ended_at, timezone,
                   duration_seconds, distance_meters, calories_kcal,
                   elevation_gain_meters, source_name
            FROM activities
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


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
