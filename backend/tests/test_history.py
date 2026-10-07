from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.database import connect, migrate
from app.history import get_activity, list_activities, weekly_calories_summary


class WeeklyCaloriesSummaryTests(unittest.TestCase):
    def test_empty_database_has_no_weekly_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)

            self.assertIsNone(weekly_calories_summary(database))

    def test_uses_latest_garmin_monday_to_sunday_week_and_reports_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)
            with connect(database) as connection:
                readings = [
                    ("old", "garmin_export", "old", "total_calories", "2026-09-27", 900),
                    ("total-mon", "garmin_export", "total-mon", "total_calories", "2026-09-28", 2400),
                    ("active-mon", "garmin_export", "active-mon", "active_calories", "2026-09-28", 300),
                    ("resting-mon", "garmin_export", "resting-mon", "resting_calories", "2026-09-28", 2100),
                    ("total-wed", "garmin_export", "total-wed", "total_calories", "2026-09-30", 2700),
                    ("active-wed", "garmin_export", "active-wed", "active_calories", "2026-09-30", 650),
                    ("resting-wed", "garmin_export", "resting-wed", "resting_calories", "2026-09-30", 2050),
                    ("other-fri", "other_source", "other-fri", "total_calories", "2026-10-02", 9999),
                ]
                connection.executemany(
                    """
                    INSERT INTO metric_readings(
                        id, source_name, source_record_id, metric_type,
                        recorded_at, value, unit
                    ) VALUES (?, ?, ?, ?, ?, ?, 'kcal')
                    """,
                    readings,
                )

            summary = weekly_calories_summary(database)

            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary["week_start"], "2026-09-28")
            self.assertEqual(summary["week_end"], "2026-10-04")
            self.assertEqual(summary["days_with_data"], 2)
            self.assertFalse(summary["is_complete"])
            self.assertEqual(summary["total_kcal"], 5100)
            self.assertEqual(summary["active_kcal"], 950)
            self.assertEqual(summary["resting_kcal"], 4150)
            self.assertEqual(
                summary["missing_dates"],
                [
                    "2026-09-29",
                    "2026-10-01",
                    "2026-10-02",
                    "2026-10-03",
                    "2026-10-04",
                ],
            )


class ActivityHistoryTests(unittest.TestCase):
    def test_filters_activities_by_inclusive_date_range_and_returns_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)
            with connect(database) as connection:
                connection.executemany(
                    """
                    INSERT INTO activities(
                        id, source_name, source_record_id, activity_type, name,
                        started_at, duration_seconds, distance_meters, calories_kcal
                    ) VALUES (?, 'garmin_export', ?, 'cycling', ?, ?, 3600, 25000, 700)
                    """,
                    [
                        ("older", "older", "Older ride", "2026-08-31T06:00:00Z"),
                        ("first", "first", "First ride", "2026-09-01T06:00:00Z"),
                        ("last", "last", "Last ride", "2026-09-30T06:00:00Z"),
                        ("newer", "newer", "Newer ride", "2026-10-01T06:00:00Z"),
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO activity_samples(
                        activity_id, recorded_at, heart_rate_bpm, power_watts,
                        speed_mps
                    ) VALUES ('last', ?, ?, ?, ?)
                    """,
                    [
                        ("2026-09-30T06:00:00Z", 120, 180, 8.0),
                        ("2026-09-30T06:00:01Z", 160, 220, 10.0),
                    ],
                )

            activities = list_activities(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
                path=database,
            )
            self.assertEqual([item["id"] for item in activities], ["last", "first"])

            detail = get_activity("last", database)
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertEqual(detail["sample_summary"]["sample_count"], 2)
            self.assertEqual(
                detail["sample_summary"]["average_heart_rate_bpm"], 140
            )
            self.assertEqual(detail["sample_summary"]["maximum_power_watts"], 220)
            self.assertIsNone(get_activity("missing", database))

    def test_rejects_reversed_activity_date_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)

            with self.assertRaisesRegex(ValueError, "start_date"):
                list_activities(
                    start_date=date(2026, 10, 1),
                    end_date=date(2026, 9, 1),
                    path=database,
                )


if __name__ == "__main__":
    unittest.main()
