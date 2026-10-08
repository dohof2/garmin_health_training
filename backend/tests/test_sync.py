from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app.database import connect, migrate
from app.history import list_activities
from app.sync import (
    SimulatedGarminProvider,
    SyncAlreadyRunning,
    SyncConnectionRequired,
    SyncInterrupted,
    recover_interrupted_sync_jobs,
    run_sync,
    scheduled_sync_decision,
    set_sync_schedule,
    sync_plan,
    sync_status,
)


def _seed(database: Path, coverage_date: str = "2026-01-01") -> None:
    migrate(database)
    with connect(database) as connection:
        connection.execute(
            """
            INSERT INTO activities(
                id, source_name, source_record_id, activity_type, name, started_at, raw_json
            ) VALUES ('imported-activity', 'garmin_export', 'activity-1',
                      'cycling', 'Imported ride', ?, '{}')
            """,
            (f"{coverage_date}T07:00:00Z",),
        )
        connection.execute(
            """
            INSERT INTO metric_readings(
                id, source_name, source_record_id, metric_type, recorded_at,
                value, unit, raw_json
            ) VALUES ('imported-steps', 'garmin_export', ?, 'steps', ?, 1000, 'count', '{}')
            """,
            (f"daily:{coverage_date}", coverage_date),
        )


class SyncTests(unittest.TestCase):
    def test_expired_or_missing_connection_stops_before_creating_a_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            provider = SimulatedGarminProvider(records={})
            provider.connection_status = "reconnect_required"

            with self.assertRaises(SyncConnectionRequired):
                run_sync(provider, date(2026, 1, 2), database, overlap_days=0)
            with connect(database) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                    0,
                )

    def test_catches_up_two_ten_and_thirty_day_gaps_including_empty_days(self) -> None:
        for gap_days in (2, 10, 30):
            with self.subTest(gap_days=gap_days), tempfile.TemporaryDirectory() as temporary:
                database = Path(temporary) / "sync.sqlite3"
                _seed(database)
                provider = SimulatedGarminProvider(records={})
                through = date(2026, 1, 1) + timedelta(days=gap_days)

                plan = sync_plan(through, database, overlap_days=0)
                result = run_sync(provider, through, database, overlap_days=0)
                status = sync_status(database)

                self.assertEqual(plan["total_intervals"], gap_days * 2 + 3)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(status["verified_empty_intervals"], gap_days * 2 + 3)
                self.assertTrue(
                    all(item["coverage_end"] == through.isoformat() for item in status["checkpoints"])
                )

    def test_partial_failure_does_not_advance_the_failed_data_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            provider = SimulatedGarminProvider(
                records={}, failed_intervals={("daily_metrics", "2026-01-02")}
            )

            result = run_sync(provider, date(2026, 1, 3), database, overlap_days=0)
            checkpoints = {item["data_type"]: item for item in sync_status(database)["checkpoints"]}

            self.assertEqual(result["status"], "failed")
            self.assertEqual(checkpoints["activities"]["coverage_end"], "2026-01-03")
            self.assertEqual(checkpoints["daily_metrics"]["coverage_end"], "2026-01-01")
            self.assertEqual(checkpoints["daily_metrics"]["status"], "failed")

    def test_interrupted_job_resumes_after_its_last_committed_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            provider = SimulatedGarminProvider(records={})

            with self.assertRaises(SyncInterrupted):
                run_sync(
                    provider,
                    date(2026, 1, 4),
                    database,
                    overlap_days=0,
                    interrupt_after=1,
                )
            first_status = {item["data_type"]: item for item in sync_status(database)["checkpoints"]}
            self.assertEqual(first_status["activities"]["coverage_end"], "2026-01-02")
            self.assertEqual(first_status["daily_metrics"]["coverage_end"], "2026-01-01")

            result = run_sync(provider, date(2026, 1, 4), database, overlap_days=0)
            self.assertEqual(result["status"], "completed")
            self.assertTrue(
                all(item["coverage_end"] == "2026-01-04" for item in sync_status(database)["checkpoints"])
            )

    def test_reconciliation_finds_late_records_and_old_corrections_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database, "2026-01-10")
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO activities(
                        id, source_name, source_record_id, activity_type, name,
                        started_at, raw_json
                    ) VALUES ('older-import', 'garmin_export', 'activity-old',
                              'cycling', 'Older imported ride', '2026-01-02T07:00:00Z', '{}')
                    """
                )
            corrected = {
                "source_record_id": "activity-old",
                "activity_type": "cycling",
                "name": "Corrected ride",
                "started_at": "2026-01-02T07:00:00Z",
                "distance_meters": 25000.0,
                "source_updated_at": "2026-01-12T10:00:00Z",
            }
            late = {
                "source_record_id": "late-activity",
                "activity_type": "running",
                "name": "Late upload",
                "started_at": "2026-01-02T06:00:00Z",
                "source_updated_at": "2026-01-12T09:00:00Z",
            }
            provider = SimulatedGarminProvider(records={"activities": [corrected, late]})

            normal = run_sync(provider, date(2026, 1, 12), database, overlap_days=1)
            self.assertEqual(normal["totals"]["created"], 0)
            self.assertEqual(normal["totals"]["updated"], 0)

            reconciled = run_sync(
                provider,
                date(2026, 1, 12),
                database,
                overlap_days=0,
                reconcile_from=date(2026, 1, 1),
            )
            repeated = run_sync(
                provider,
                date(2026, 1, 12),
                database,
                overlap_days=0,
                reconcile_from=date(2026, 1, 1),
            )
            with connect(database) as connection:
                activities = connection.execute(
                    "SELECT source_record_id, name FROM activities ORDER BY source_record_id"
                ).fetchall()
                reconciled_ranges = connection.execute(
                    """
                    SELECT last_reconciled_start, last_reconciled_end
                    FROM sync_checkpoints
                    """
                ).fetchall()

            self.assertEqual(reconciled["totals"]["created"], 1)
            self.assertEqual(reconciled["totals"]["updated"], 1)
            self.assertEqual(repeated["totals"]["created"], 0)
            self.assertEqual(repeated["totals"]["updated"], 0)
            self.assertEqual([(row[0], row[1]) for row in activities], [
                ("activity-1", "Imported ride"),
                ("activity-old", "Corrected ride"),
                ("late-activity", "Late upload"),
            ])
            self.assertTrue(
                all(tuple(row) == ("2026-01-01", "2026-01-12") for row in reconciled_ranges)
            )

    def test_explicit_source_deletion_is_hidden_but_not_erased(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            deletion = {
                "source_record_id": "activity-1",
                "deleted": True,
                "source_updated_at": "2026-01-02T12:00:00Z",
                "started_at": "2026-01-01T07:00:00Z",
            }
            provider = SimulatedGarminProvider(records={"activities": [deletion]})

            run_sync(
                provider,
                date(2026, 1, 2),
                database,
                overlap_days=0,
                reconcile_from=date(2026, 1, 1),
            )
            with connect(database) as connection:
                stored = connection.execute(
                    "SELECT deleted_at FROM activities WHERE source_record_id = 'activity-1'"
                ).fetchone()[0]

            self.assertIsNotNone(stored)
            self.assertEqual(list_activities(path=database), [])

    def test_live_activity_id_reconciles_an_archive_only_fit_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO activities(
                        id, source_name, source_record_id, activity_type, name,
                        started_at, duration_seconds, distance_meters, raw_json
                    ) VALUES ('fit-only', 'garmin_export', 'fit:hash', 'cycling',
                              'FIT profile', '2026-01-02T07:00:00Z', 3600, 24000, '{}')
                    """
                )
            live = {
                "source_record_id": "garmin-activity-42",
                "activity_type": "cycling",
                "name": "Garmin title",
                "started_at": "2026-01-02T07:00:00Z",
                "duration_seconds": 3600.1,
                "distance_meters": 24000.5,
            }

            result = run_sync(
                SimulatedGarminProvider(records={"activities": [live]}),
                date(2026, 1, 2),
                database,
                overlap_days=0,
                reconcile_from=date(2026, 1, 2),
            )
            with connect(database) as connection:
                matches = connection.execute(
                    """
                    SELECT id, source_name, source_record_id, name
                    FROM activities WHERE substr(started_at, 1, 10) = '2026-01-02'
                    """
                ).fetchall()

            self.assertEqual(result["totals"]["created"], 0)
            self.assertEqual(result["totals"]["updated"], 1)
            self.assertEqual(
                [tuple(row) for row in matches],
                [("fit-only", "garmin_export", "garmin-activity-42", "Garmin title")],
            )

    def test_live_daily_metric_reconciles_archive_and_old_live_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO metric_readings(
                        id, source_name, source_record_id, metric_type,
                        recorded_at, value, unit, raw_json
                    ) VALUES ('old-live', 'garmin_connect', '2026-01-01:totalSteps',
                              'steps', '2026-01-01', 900, 'count', '{}')
                    """
                )
            provider = SimulatedGarminProvider(
                records={
                    "daily_metrics": [
                        {
                            "source_record_id": "daily:2026-01-01",
                            "metric_type": "steps",
                            "recorded_at": "2026-01-01",
                            "value": 1200,
                            "unit": "count",
                        }
                    ]
                }
            )

            run_sync(
                provider,
                date(2026, 1, 1),
                database,
                overlap_days=1,
                reconcile_from=date(2026, 1, 1),
            )
            with connect(database) as connection:
                rows = connection.execute(
                    """
                    SELECT source_name, source_record_id, value
                    FROM metric_readings
                    WHERE metric_type = 'steps' AND recorded_at = '2026-01-01'
                    """
                ).fetchall()

            self.assertEqual(
                [tuple(row) for row in rows],
                [("garmin_export", "daily:2026-01-01", 1200.0)],
            )

    def test_live_activity_detail_imports_sensor_samples_once(self) -> None:
        class DetailProvider(SimulatedGarminProvider):
            detail_requests = 0

            def fetch_activity_detail(self, source_record_id: str) -> bytes:
                self.detail_requests += 1
                return b"test-fit-content"

        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            activity = {
                "source_record_id": "activity-2",
                "activity_type": "cycling",
                "name": "Sensor ride",
                "started_at": "2026-01-02T07:00:00Z",
                "duration_seconds": 60,
                "distance_meters": 500,
            }
            provider = DetailProvider(records={"activities": [activity]})

            def sample_rows(activity_id, _records):
                return [
                    (
                        activity_id,
                        "2026-01-02T07:00:01Z",
                        None,
                        None,
                        100.0,
                        145,
                        82.0,
                        210.0,
                        8.0,
                    )
                ]

            with (
                patch("app.sync._decode_fit", return_value=({"record_mesgs": [{}]}, [])),
                patch("app.sync._sample_rows", side_effect=sample_rows),
            ):
                first = run_sync(provider, date(2026, 1, 2), database, overlap_days=0)
                repeated = run_sync(provider, date(2026, 1, 2), database, overlap_days=1)

            with connect(database) as connection:
                sample = connection.execute(
                    "SELECT heart_rate_bpm, power_watts FROM activity_samples"
                ).fetchone()

            self.assertEqual(first["totals"]["detail_samples"], 1)
            self.assertEqual(repeated["totals"]["detail_samples"], 0)
            self.assertEqual(provider.detail_requests, 1)
            self.assertEqual(tuple(sample), (145, 210.0))

    def test_single_job_lock_and_recovery_use_the_same_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO jobs(id, job_type, status, progress_total, checkpoint_json)
                    VALUES ('stale', 'garmin_sync', 'running', 1, ?)
                    """,
                    (json.dumps({"trigger": "scheduled"}),),
                )
            provider = SimulatedGarminProvider(records={})

            with self.assertRaises(SyncAlreadyRunning):
                run_sync(provider, date(2026, 1, 2), database, overlap_days=0)
            self.assertEqual(recover_interrupted_sync_jobs(database), 1)
            result = run_sync(
                provider,
                date(2026, 1, 2),
                database,
                overlap_days=0,
                trigger="scheduled",
            )

            self.assertEqual(result["trigger"], "scheduled")
            self.assertEqual(result["status"], "completed")

    def test_open_session_schedule_runs_only_when_due(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "sync.sqlite3"
            _seed(database)
            provider = SimulatedGarminProvider(records={})

            enabled = set_sync_schedule(True, database)
            self.assertTrue(enabled["schedule_enabled"])
            self.assertEqual(
                scheduled_sync_decision(date(2026, 1, 2), database)["reason"],
                "connection_required",
            )

            run_sync(provider, date(2026, 1, 2), database, overlap_days=0)
            current = sync_status(database)
            self.assertTrue(current["live_sync_ready"])
            self.assertEqual(
                scheduled_sync_decision(date(2026, 1, 2), database)["reason"],
                "up_to_date",
            )
            self.assertEqual(
                scheduled_sync_decision(date(2026, 1, 9), database)["reason"],
                "catch_up_required",
            )

            disabled = set_sync_schedule(False, database)
            self.assertFalse(disabled["schedule_enabled"])
            self.assertEqual(
                scheduled_sync_decision(date(2026, 1, 9), database)["reason"],
                "disabled",
            )


if __name__ == "__main__":
    unittest.main()
