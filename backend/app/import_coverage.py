from __future__ import annotations

from pathlib import Path

from .database import connect
from .garmin_import import GARMIN_SOURCE_NAME


def _status(records: int, failed: int = 0, unmatched: int = 0) -> str:
    if failed or unmatched:
        return "attention"
    return "complete" if records else "empty"


def _range_row(connection, query: str, parameters: tuple[object, ...] = ()):
    return connection.execute(query, parameters).fetchone()


def import_coverage(path: Path | None = None) -> dict[str, object]:
    """Summarize durable Garmin import coverage and checkpoint failures."""
    with connect(path) as connection:
        archive = connection.execute(
            """
            SELECT imported_at
            FROM source_files
            WHERE id LIKE 'garmin-export-%'
            ORDER BY imported_at DESC
            LIMIT 1
            """
        ).fetchone()

        activities = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(started_at) AS date_start,
                   MAX(started_at) AS date_end
            FROM activities WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        )
        daily = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(recorded_at) AS date_start,
                   MAX(recorded_at) AS date_end
            FROM metric_readings
            WHERE source_name = ? AND source_record_id LIKE 'daily:%'
            """,
            (GARMIN_SOURCE_NAME,),
        )
        sleep = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(recorded_at) AS date_start,
                   MAX(recorded_at) AS date_end
            FROM metric_readings
            WHERE source_name = ? AND source_record_id LIKE 'sleep:%'
            """,
            (GARMIN_SOURCE_NAME,),
        )

        fit = _range_row(
            connection,
            """
            SELECT
                COALESCE(SUM(imported_samples), 0) AS records,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'unmatched' THEN 1 ELSE 0 END) AS unmatched,
                MIN(a.started_at) AS date_start,
                MAX(a.started_at) AS date_end
            FROM fit_import_files f
            LEFT JOIN activities a ON a.id = f.activity_id
            """,
        )
        xml = _range_row(
            connection,
            """
            SELECT
                COALESCE(SUM(imported_samples), 0) AS records,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'unmatched' THEN 1 ELSE 0 END) AS unmatched,
                MIN(a.started_at) AS date_start,
                MAX(a.started_at) AS date_end
            FROM xml_activity_import_files x
            LEFT JOIN activities a ON a.id = x.activity_id
            """,
        )
        health = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(recorded_at) AS date_start,
                   MAX(recorded_at) AS date_end,
                   COUNT(heart_rate_bpm) AS heart_rate,
                   COUNT(stress_level) AS stress,
                   COUNT(respiration_rate) AS respiration
            FROM health_samples WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        )
        monitoring = _range_row(
            connection,
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM monitoring_fit_import_files
            """,
        )
        hydration = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(calendar_date) AS date_start,
                   MAX(calendar_date) AS date_end,
                   SUM(CASE WHEN value_ml > 0 THEN 1 ELSE 0 END) AS additions,
                   SUM(CASE WHEN value_ml < 0 THEN 1 ELSE 0 END) AS corrections,
                   COUNT(estimated_sweat_loss_ml) AS estimated_sweat
            FROM hydration_events WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        )
        hydration_files = _range_row(
            connection,
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM wellness_json_import_files WHERE category = 'hydration'
            """,
        )
        abnormal_hr = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(calendar_date) AS date_start,
                   MAX(calendar_date) AS date_end,
                   SUM(CASE WHEN heart_rate_bpm < threshold_bpm THEN 1 ELSE 0 END)
                       AS low_events,
                   SUM(CASE WHEN heart_rate_bpm > threshold_bpm THEN 1 ELSE 0 END)
                       AS high_events,
                   SUM(CASE WHEN heart_rate_bpm = threshold_bpm THEN 1 ELSE 0 END)
                       AS threshold_events
            FROM abnormal_heart_rate_events WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        )
        abnormal_hr_files = _range_row(
            connection,
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM wellness_json_import_files WHERE category = 'abnormal_hr'
            """,
        )
        nutrition = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(calendar_date) AS date_start,
                   MAX(calendar_date) AS date_end,
                   COUNT(calories_consumed) AS consumed_days,
                   COUNT(calorie_goal) AS goal_days
            FROM garmin_nutrition_daily WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        )
        nutrition_files = _range_row(
            connection,
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM wellness_json_import_files WHERE category = 'nutrition'
            """,
        )
        extended = _range_row(
            connection,
            """
            SELECT COUNT(*) AS records, MIN(record_date) AS date_start,
                   MAX(record_date) AS date_end,
                   COUNT(DISTINCT category) AS categories
            FROM garmin_archive_records WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        )
        extended_files = _range_row(
            connection,
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM extended_archive_import_files
            """,
        )
        archive_catalog = {
            row["classification"]: int(row["count"])
            for row in connection.execute(
                """
                SELECT classification, COUNT(*) AS count
                FROM garmin_archive_file_catalog GROUP BY classification
                """
            )
        }

        failures = [
            dict(row)
            for row in connection.execute(
                """
                SELECT 'activity_fit' AS category, member_name, status,
                       error_message
                FROM fit_import_files WHERE status != 'completed'
                UNION ALL
                SELECT 'gpx_tcx', member_name, status, error_message
                FROM xml_activity_import_files WHERE status != 'completed'
                UNION ALL
                SELECT 'health_fit', member_name, status, error_message
                FROM monitoring_fit_import_files WHERE status != 'completed'
                UNION ALL
                SELECT category, member_name, status, error_message
                FROM wellness_json_import_files WHERE status != 'completed'
                UNION ALL
                SELECT category, member_name, status, error_message
                FROM extended_archive_import_files WHERE status != 'completed'
                LIMIT 50
                """
            )
        ]

    def base_category(identifier: str, label: str, row, note: str):
        records = int(row["records"] or 0)
        return {
            "id": identifier,
            "label": label,
            "status": _status(records),
            "records": records,
            "files": None,
            "date_start": row["date_start"],
            "date_end": row["date_end"],
            "note": note,
        }

    def tracked_category(identifier: str, label: str, row, note: str):
        records = int(row["records"] or 0)
        completed = int(row["completed"] or 0)
        failed = int(row["failed"] or 0)
        unmatched = int(row["unmatched"] or 0)
        return {
            "id": identifier,
            "label": label,
            "status": _status(records, failed, unmatched),
            "records": records,
            "files": {
                "completed": completed,
                "failed": failed,
                "unmatched": unmatched,
            },
            "date_start": row["date_start"],
            "date_end": row["date_end"],
            "note": note,
        }

    categories = [
        base_category(
            "activity_summaries",
            "Activity summaries",
            activities,
            "Normalized Garmin activity records",
        ),
        base_category(
            "daily_metrics",
            "Daily metrics",
            daily,
            "Steps, distance, calories, heart rate, intensity, and SpO₂",
        ),
        base_category(
            "sleep_metrics",
            "Sleep metrics",
            sleep,
            "Sleep stages, score, stress, respiration, heart rate, and SpO₂",
        ),
        tracked_category(
            "activity_fit",
            "Activity FIT details",
            fit,
            "Official Garmin FIT SDK samples matched to activities",
        ),
        tracked_category(
            "gpx_tcx",
            "GPX and TCX details",
            xml,
            "Track points reconciled with existing activities",
        ),
        {
            "id": "health_fit",
            "label": "Monitoring FIT health",
            "status": _status(
                int(health["records"] or 0),
                int(monitoring["failed"] or 0),
            ),
            "records": int(health["records"] or 0),
            "files": {
                "completed": int(monitoring["completed"] or 0),
                "failed": int(monitoring["failed"] or 0),
                "unmatched": 0,
            },
            "date_start": health["date_start"],
            "date_end": health["date_end"],
            "note": (
                f"{int(health['heart_rate'] or 0):,} heart-rate · "
                f"{int(health['stress'] or 0):,} stress · "
                f"{int(health['respiration'] or 0):,} respiration values"
            ),
        },
        {
            "id": "hydration",
            "label": "Hydration history",
            "status": _status(
                int(hydration["records"] or 0),
                int(hydration_files["failed"] or 0),
            ),
            "records": int(hydration["records"] or 0),
            "files": {
                "completed": int(hydration_files["completed"] or 0),
                "failed": int(hydration_files["failed"] or 0),
                "unmatched": 0,
            },
            "date_start": hydration["date_start"],
            "date_end": hydration["date_end"],
            "note": (
                f"{int(hydration['additions'] or 0):,} intake additions · "
                f"{int(hydration['corrections'] or 0):,} corrections · "
                f"{int(hydration['estimated_sweat'] or 0):,} sweat estimates"
            ),
        },
        {
            "id": "abnormal_heart_rate",
            "label": "Abnormal heart-rate events",
            "status": _status(
                int(abnormal_hr["records"] or 0),
                int(abnormal_hr_files["failed"] or 0),
            ),
            "records": int(abnormal_hr["records"] or 0),
            "files": {
                "completed": int(abnormal_hr_files["completed"] or 0),
                "failed": int(abnormal_hr_files["failed"] or 0),
                "unmatched": 0,
            },
            "date_start": abnormal_hr["date_start"],
            "date_end": abnormal_hr["date_end"],
            "note": (
                f"{int(abnormal_hr['low_events'] or 0):,} low-rate · "
                f"{int(abnormal_hr['high_events'] or 0):,} high-rate · "
                f"{int(abnormal_hr['threshold_events'] or 0):,} at-threshold alerts"
            ),
        },
        {
            "id": "garmin_nutrition",
            "label": "Garmin nutrition summaries",
            "status": _status(
                int(nutrition["records"] or 0),
                int(nutrition_files["failed"] or 0),
            ),
            "records": int(nutrition["records"] or 0),
            "files": {
                "completed": int(nutrition_files["completed"] or 0),
                "failed": int(nutrition_files["failed"] or 0),
                "unmatched": 0,
            },
            "date_start": nutrition["date_start"],
            "date_end": nutrition["date_end"],
            "note": (
                f"{int(nutrition['consumed_days'] or 0):,} calorie-value days · "
                f"{int(nutrition['goal_days'] or 0):,} goal days; no meal or macro detail"
            ),
        },
        {
            "id": "extended_training_archive",
            "label": "Extended training archive",
            "status": _status(
                int(extended["records"] or 0),
                int(extended_files["failed"] or 0),
                int(archive_catalog.get("unsupported", 0)),
            ),
            "records": int(extended["records"] or 0),
            "files": {
                "completed": int(extended_files["completed"] or 0),
                "failed": int(extended_files["failed"] or 0),
                "unmatched": int(archive_catalog.get("unsupported", 0)),
            },
            "date_start": extended["date_start"],
            "date_end": extended["date_end"],
            "note": (
                f"{int(extended['categories'] or 0):,} training/biometric categories · "
                f"{archive_catalog.get('excluded', 0):,} private administrative files excluded"
            ),
        },
    ]
    complete_categories = sum(item["status"] == "complete" for item in categories)
    tracked_files = sum(
        item["files"]["completed"]
        for item in categories
        if item["files"] is not None
    )
    failed_files = sum(
        item["files"]["failed"]
        for item in categories
        if item["files"] is not None
    )
    unmatched_files = sum(
        item["files"]["unmatched"]
        for item in categories
        if item["files"] is not None
    )
    return {
        "archive_imported_at": archive["imported_at"] if archive else None,
        "summary": {
            "categories": len(categories),
            "complete_categories": complete_categories,
            "attention_categories": len(categories) - complete_categories,
            "tracked_files": tracked_files,
            "failed_files": failed_files,
            "unmatched_files": unmatched_files,
        },
        "categories": categories,
        "failures": failures,
        "archive_catalog": {
            "total_files": sum(archive_catalog.values()),
            "imported": archive_catalog.get("imported", 0),
            "handled_elsewhere": archive_catalog.get("handled_elsewhere", 0),
            "excluded": archive_catalog.get("excluded", 0),
            "unsupported": archive_catalog.get("unsupported", 0),
        },
    }
