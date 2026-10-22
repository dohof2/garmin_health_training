from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .database import connect
from .garmin_import import GARMIN_SOURCE_NAME
from .time_utils import (
    calendar_date,
    monday_sunday_week,
    select_timezone,
    timezone_info,
)


def history_summary(
    path: Path | None = None,
    timezone_name: str | None = None,
) -> dict[str, object]:
    timezone_info(timezone_name)
    with connect(path) as connection:
        activity_count = connection.execute(
            "SELECT COUNT(*) FROM activities WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture'"
        ).fetchone()[0]
        metric_count = connection.execute(
            "SELECT COUNT(*) FROM metric_readings WHERE source_name != 'synthetic_fixture'"
        ).fetchone()[0]
        latest_activity = connection.execute(
            """
            SELECT id, activity_type, name, started_at, duration_seconds,
                   distance_meters, calories_kcal, source_name, timezone
            FROM activities
            WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture'
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        latest_steps = connection.execute(
            """
            SELECT value, unit, recorded_at, source_name
            FROM metric_readings
            WHERE metric_type = 'steps' AND source_name != 'synthetic_fixture'
            ORDER BY recorded_at DESC
            LIMIT 1
            """
        ).fetchone()
        source_names = {
            row[0]
            for row in connection.execute(
                """
                SELECT source_name FROM activities WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture'
                UNION
                SELECT source_name FROM metric_readings WHERE source_name != 'synthetic_fixture'
                """
            )
        }
        activity_times = connection.execute(
            """
            SELECT started_at, timezone
            FROM activities
            WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture'
            """
        ).fetchall()
        latest_metric_at = connection.execute(
            "SELECT MAX(recorded_at) FROM metric_readings WHERE source_name != 'synthetic_fixture'"
        ).fetchone()[0]

    latest_activity_data = dict(latest_activity) if latest_activity else None
    if latest_activity_data:
        timezone_used = select_timezone(
            latest_activity_data.get("timezone"), timezone_name
        )
        latest_activity_data["local_date"] = calendar_date(
            str(latest_activity_data["started_at"]),
            str(timezone_used) if timezone_used else None,
        ).isoformat()
        latest_activity_data["timezone_used"] = timezone_used

    activity_dates = [
        calendar_date(
            str(row["started_at"]),
            select_timezone(row["timezone"], timezone_name),
        )
        for row in activity_times
    ]

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
        "latest_activity": latest_activity_data,
        "latest_steps": dict(latest_steps) if latest_steps else None,
        "activity_date_start": min(activity_dates).isoformat() if activity_dates else None,
        "activity_date_end": max(activity_dates).isoformat() if activity_dates else None,
        "latest_metric_at": latest_metric_at,
    }


def weekly_calories_summary(path: Path | None = None, timezone_name='UTC', now=None) -> dict[str, object] | None:
    """Latest Garmin week, one corrected daily observation per metric/source day."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    timezone_info(timezone_name)
    today=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo(timezone_name)).date()
    with connect(path) as connection:
        latest=connection.execute("""SELECT MAX(substr(recorded_at,1,10)) FROM metric_readings
            WHERE source_name IN ('garmin_export','garmin_connect') AND metric_type='total_calories'
            AND unit='kcal' AND value>=0 AND value<1e308 AND substr(recorded_at,1,10)<=?""",(today.isoformat(),)).fetchone()[0]
        if latest is None:return None
        week_start,week_end=monday_sunday_week(date.fromisoformat(latest))
        rows=connection.execute("""SELECT * FROM (
            SELECT metric_type,substr(recorded_at,1,10) AS recorded_date,value,source_name,
                ROW_NUMBER() OVER (PARTITION BY metric_type,substr(recorded_at,1,10)
                    ORDER BY (source_name='garmin_connect') DESC,COALESCE(source_updated_at,'') DESC,recorded_at DESC,id DESC) AS rank
            FROM metric_readings WHERE source_name IN ('garmin_export','garmin_connect')
                AND metric_type IN ('total_calories','active_calories','resting_calories')
                AND unit='kcal' AND value>=0 AND value<1e308
                AND substr(recorded_at,1,10) BETWEEN ? AND ?
            ) WHERE rank=1 ORDER BY recorded_date,metric_type""",(week_start.isoformat(),min(week_end,today).isoformat())).fetchall()
    totals={key:0.0 for key in ('total_calories','active_calories','resting_calories')}
    dates={key:set() for key in totals};sources=set()
    for row in rows:
        totals[row['metric_type']]+=float(row['value']);dates[row['metric_type']].add(row['recorded_date']);sources.add(row['source_name'])
    expected=[(week_start+timedelta(days=i)).isoformat() for i in range(7) if week_start+timedelta(days=i)<=today]
    missing=[day for day in expected if day not in dates['total_calories']]
    ongoing=week_start<=today<=week_end
    return {'basis':'latest_available_garmin_week','week_start':week_start.isoformat(),'week_end':week_end.isoformat(),
        'days_expected':7,'days_elapsed':len(expected),'days_with_data':len(dates['total_calories']),
        'missing_dates':missing,'is_complete':len(dates['total_calories'])==7,
        'period_status':'week_to_date' if ongoing and not missing else 'partial' if missing else 'complete',
        'today_in_progress':ongoing and today.isoformat() in dates['total_calories'],
        'missing_by_metric':{key:[day for day in expected if day not in observed] for key,observed in dates.items()},
        'total_kcal':totals['total_calories'],'active_kcal':totals['active_calories'],'resting_kcal':totals['resting_calories'],
        'source_name':next(iter(sources)) if len(sources)==1 else 'Garmin Connect + export','sources':sorted(sources)}


def list_activities(
    limit: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone_name: str | None = None,
    path: Path | None = None,
    offset: int = 0,
) -> list[dict[str, object]]:
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    timezone_info(timezone_name)
    query = """
        SELECT id, activity_type, name, started_at, ended_at, timezone,
               duration_seconds, distance_meters, calories_kcal,
               elevation_gain_meters, source_name
        FROM activities
        WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture'
    """
    query += " ORDER BY started_at DESC"

    with connect(path) as connection:
        rows = connection.execute(query).fetchall()

    activities: list[dict[str, object]] = []
    if offset < 0: raise ValueError("offset must be nonnegative")
    skipped = 0
    for row in rows:
        activity = dict(row)
        timezone_used = select_timezone(activity.get("timezone"), timezone_name)
        local_date = calendar_date(
            str(activity["started_at"]),
            str(timezone_used) if timezone_used else None,
        )
        if start_date and local_date < start_date:
            continue
        if end_date and local_date > end_date:
            continue
        if skipped < offset:
            skipped += 1
            continue
        activity["local_date"] = local_date.isoformat()
        activity["timezone_used"] = timezone_used
        activities.append(activity)
        if len(activities) == limit:
            break
    return activities


def get_activity(
    activity_id: str,
    path: Path | None = None,
    timezone_name: str | None = None,
) -> dict[str, object] | None:
    timezone_info(timezone_name)
    with connect(path) as connection:
        activity = connection.execute(
            """
            SELECT id, activity_type, name, started_at, ended_at, timezone,
                   duration_seconds, distance_meters, calories_kcal,
                   elevation_gain_meters, source_name
            FROM activities
            WHERE id = ? AND deleted_at IS NULL AND source_name != 'synthetic_fixture'
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
                   AVG(speed_mps) AS average_speed_mps,
                   AVG(cadence_rpm) AS average_cadence_rpm,
                   MAX(cadence_rpm) AS maximum_cadence_rpm,
                   MIN(elevation_meters) AS minimum_elevation_meters,
                   MAX(elevation_meters) AS maximum_elevation_meters,
                   MAX(speed_mps) AS maximum_speed_mps
            FROM activity_samples
            WHERE activity_id = ?
            """,
            (activity_id,),
        ).fetchone()
        metrics = connection.execute('SELECT metric_type, value, unit, source_method, source_field FROM activity_metrics WHERE activity_id=? ORDER BY metric_type', (activity_id,)).fetchall()

    result = dict(activity)
    timezone_used = select_timezone(result.get("timezone"), timezone_name)
    result["local_date"] = calendar_date(
        str(result["started_at"]),
        str(timezone_used) if timezone_used else None,
    ).isoformat()
    result["timezone_used"] = timezone_used
    result["sample_summary"] = dict(samples)
    result['activity_metrics'] = [dict(row) for row in metrics]
    return result


def list_metrics(
    metric_type: str | None = None,
    limit: int = 100,
    path: Path | None = None,
) -> list[dict[str, object]]:
    query = """
        SELECT id, metric_type, recorded_at, value, unit, source_name
        FROM metric_readings
        WHERE source_name != 'synthetic_fixture'
    """
    parameters: list[object] = []
    if metric_type:
        query += " AND metric_type = ?"
        parameters.append(metric_type)
    query += " ORDER BY recorded_at DESC LIMIT ?"
    parameters.append(limit)

    with connect(path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]
