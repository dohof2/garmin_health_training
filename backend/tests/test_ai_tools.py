from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.ai_tools import execute_tool, tool_definitions
from app.database import connect, migrate


class AIToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "tools.sqlite3"
        migrate(self.database)
        with connect(self.database) as connection:
            connection.executemany(
                """
                INSERT INTO activities(
                    id, source_name, source_record_id, activity_type, name,
                    started_at, duration_seconds, distance_meters,
                    calories_kcal, elevation_gain_meters
                ) VALUES (?, 'garmin_export', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("run-a1", "run-a1", "running", "Easy run", "2026-10-01T06:00:00Z", 1800, 5000, 350, 20),
                    ("run-a2", "run-a2", "running", "Steady run", "2026-10-02T06:00:00Z", 2000, 5000, 375, 25),
                    ("ride-a", "ride-a", "cycling", "Ride", "2026-10-03T06:00:00Z", 3600, 30000, 700, 200),
                    ("run-b", "run-b", "running", "Long run", "2026-10-08T06:00:00Z", 5400, 15000, 900, 60),
                ],
            )
            connection.executemany(
                """
                INSERT INTO activity_samples(
                    activity_id, recorded_at, heart_rate_bpm, cadence_rpm,
                    power_watts, speed_mps
                ) VALUES ('run-b', ?, ?, ?, ?, ?)
                """,
                [
                    ("2026-10-08T06:00:00Z", 130, 80, 210, 3.0),
                    ("2026-10-08T06:00:01Z", 150, 84, 230, 4.0),
                ],
            )
            connection.executemany(
                """
                INSERT INTO metric_readings(
                    id, source_name, source_record_id, metric_type,
                    recorded_at, value, unit
                ) VALUES (?, 'garmin_export', ?, ?, ?, ?, ?)
                """,
                [
                    ("steps-a1", "steps-a1", "steps", "2026-10-01", 1000, "count"),
                    ("steps-a2", "steps-a2", "steps", "2026-10-02", 2000, "count"),
                    ("sleep-a1", "sleep-a1", "sleep_duration", "2026-10-01", 25200, "s"),
                    ("steps-b", "steps-b", "steps", "2026-10-08", 3000, "count"),
                ],
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_catalog_exposes_only_scoped_read_only_tools(self) -> None:
        definitions = tool_definitions()
        self.assertEqual(
            [item["name"] for item in definitions],
            ["get_health_summary", "list_activities", "compare_periods"],
        )
        self.assertTrue(
            all(item["input_schema"]["additionalProperties"] is False for item in definitions)
        )

    def test_health_summary_calculates_values_coverage_and_freshness(self) -> None:
        result = execute_tool(
            "get_health_summary",
            {
                "start_date": "2026-10-01",
                "end_date": "2026-10-03",
                "metric_types": ["steps", "sleep_duration", "missing_metric"],
            },
            self.database,
        )

        steps = next(item for item in result["metrics"] if item["metric_type"] == "steps")
        self.assertEqual(steps["sum"], 3000)
        self.assertEqual(steps["average"], 1500)
        self.assertEqual(steps["coverage"]["days_with_data"], 2)
        self.assertEqual(steps["coverage"]["missing_dates"], ["2026-10-03"])
        self.assertEqual(result["missing_metric_types"], ["missing_metric"])
        self.assertEqual(result["freshness"]["latest_recorded_at"], "2026-10-02")
        self.assertEqual(result["evidence"]["record_count"], 3)

        aliased = execute_tool(
            "get_health_summary",
            {
                "start_date": "2026-10-01",
                "end_date": "2026-10-03",
                "metric_types": ["sleep"],
            },
            self.database,
        )
        self.assertEqual(aliased["requested_metric_types"], ["sleep_duration"])
        self.assertEqual(aliased["metrics"][0]["metric_type"], "sleep_duration")
        self.assertEqual(aliased["metrics"][0]["unit"], "hours")
        self.assertEqual(aliased["metrics"][0]["source_unit"], "s")
        self.assertEqual(aliased["metrics"][0]["average"], 7)

    def test_activity_list_filters_and_includes_sensor_evidence(self) -> None:
        result = execute_tool(
            "list_activities",
            {
                "start_date": "2026-10-01",
                "end_date": "2026-10-09",
                "activity_type": "running",
                "timezone": "UTC",
                "limit": 1,
            },
            self.database,
        )

        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["returned_count"], 1)
        self.assertTrue(result["truncated"])
        activity = result["activities"][0]
        self.assertEqual(activity["id"], "run-b")
        self.assertEqual(activity["sample_summary"]["sample_count"], 2)
        self.assertEqual(activity["sample_summary"]["average_heart_rate_bpm"], 140)
        self.assertEqual(activity["sample_summary"]["average_power_watts"], 220)
        self.assertEqual(activity["evidence_url"], "/api/activities/run-b")
        self.assertNotIn("raw_json", activity)

    def test_period_comparison_reports_direction_and_zero_safe_deltas(self) -> None:
        result = execute_tool(
            "compare_periods",
            {
                "period_a_start": "2026-10-01",
                "period_a_end": "2026-10-03",
                "period_b_start": "2026-10-08",
                "period_b_end": "2026-10-09",
                "activity_type": "running",
                "metric_types": ["steps"],
                "timezone": "UTC",
            },
            self.database,
        )

        self.assertEqual(result["direction"], "period_b_minus_period_a")
        activity_deltas = result["deltas"]["activities"]
        self.assertEqual(activity_deltas["activity_count"]["absolute"], -1)
        self.assertEqual(activity_deltas["activity_count"]["percent"], -50)
        self.assertEqual(activity_deltas["distance_meters"]["absolute"], 5000)
        metric_delta = result["deltas"]["metric_averages"][0]
        self.assertEqual(metric_delta["period_a_average"], 1500)
        self.assertEqual(metric_delta["period_b_average"], 3000)
        self.assertEqual(metric_delta["average"]["percent"], 100)

    def test_rejects_unknown_tools_unexpected_arguments_and_invalid_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown AI tool"):
            execute_tool("run_sql", {}, self.database)
        with self.assertRaisesRegex(ValueError, "Unexpected tool arguments"):
            execute_tool(
                "get_health_summary",
                {"start_date": "2026-10-01", "end_date": "2026-10-02", "sql": "DROP TABLE activities"},
                self.database,
            )
        with self.assertRaisesRegex(ValueError, "on or before"):
            execute_tool(
                "list_activities",
                {"start_date": "2026-10-03", "end_date": "2026-10-01"},
                self.database,
            )


if __name__ == "__main__":
    unittest.main()
