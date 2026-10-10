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
                    ("ride-near", "ride-near", "cycling", "Similar ride", "2026-10-04T06:00:00Z", 3900, 31500, 725, 220),
                    ("ride-far", "ride-far", "cycling", "Long ride", "2026-10-07T06:00:00Z", 7200, 60000, 1300, 600),
                    ("ride-indoor", "ride-indoor", "indoor_cycling", "Indoor ride", "2026-10-06T06:00:00Z", 3700, 30500, 680, 0),
                    ("run-b", "run-b", "running", "Long run", "2026-10-08T06:00:00Z", 5400, 15000, 900, 60),
                ],
            )
            route_samples = []
            for activity_id, latitude_offset in (("ride-a", 0.0), ("ride-near", 0.0001)):
                route_samples.extend(
                    (
                        activity_id,
                        f"2026-10-03T06:00:{index:02d}Z",
                        32.0 + latitude_offset + index * 0.001,
                        34.8 + index * 0.001,
                    )
                    for index in range(12)
                )
            connection.executemany(
                """
                INSERT INTO activity_samples(
                    activity_id, recorded_at, latitude, longitude
                ) VALUES (?, ?, ?, ?)
                """,
                route_samples,
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

    def test_course_progress_includes_sensors_from_matches_outside_display_limit(self) -> None:
        with connect(self.database) as connection:
            connection.execute("""INSERT INTO activities(id, source_name, activity_type, started_at, duration_seconds, distance_meters)
                VALUES ('old-ride', 'synthetic', 'cycling', '2024-01-01T06:00:00Z', 4000, 31000)""")
            connection.executemany("INSERT INTO activity_samples(activity_id, recorded_at, latitude, longitude, power_watts) VALUES ('old-ride', ?, ?, ?, 100)",
                [(f"2024-01-01T06:00:{index:02d}Z", 32.0003 + index * .001, 34.8 + index * .001) for index in range(12)])
            connection.execute("UPDATE activity_samples SET power_watts = 200 WHERE activity_id = 'ride-near'")
        result = execute_tool('find_same_course_rides', {'reference_activity_id': 'ride-near', 'limit': 1}, self.database)
        self.assertEqual(result['total_matches'], 2)
        self.assertNotEqual(result['rides'][0]['id'], 'old-ride')
        power_change = next(change for change in result['course_progress']['changes_latest_minus_earliest'] if change['metric'] == 'average power')
        self.assertEqual(power_change['earliest'], 100)
        self.assertEqual(power_change['latest'], 200)
        self.assertEqual(power_change['percent'], 100)

    def test_catalog_exposes_only_scoped_read_only_tools(self) -> None:
        definitions = tool_definitions()
        self.assertEqual(
            [item["name"] for item in definitions],
            [
                "get_health_summary",
                "list_activities",
                "compare_periods",
                "find_similar_rides",
                "find_same_course_rides",
                "assess_ride",
                "running_volume_trend",
                "get_training_context",
                "propose_settings_change",
                "log_maintenance",
                "list_maintenance",
                "update_maintenance",
                "undo_maintenance",
                "export_maintenance",
            ],
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

    def test_similar_rides_exposes_adjustable_criteria_sample_and_links(self) -> None:
        result = execute_tool(
            "find_similar_rides",
            {
                "reference_activity_id": "ride-a",
                "duration_tolerance_percent": 20,
                "distance_tolerance_percent": 20,
                "elevation_tolerance_percent": 30,
                "timezone": "UTC",
                "limit": 5,
            },
            self.database,
        )

        self.assertEqual(result["reference_ride"]["id"], "ride-a")
        self.assertEqual(result["candidate_pool_count"], 2)
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["rides"][0]["id"], "ride-near")
        self.assertEqual(result["rides"][0]["evidence_url"], "/api/activities/ride-near")
        self.assertGreater(result["rides"][0]["similarity_score"], 0)
        distance = next(
            item for item in result["criteria"] if item["field"] == "distance_meters"
        )
        self.assertEqual(distance["unit"], "kilometers")
        self.assertEqual(distance["minimum"], 24)
        self.assertEqual(distance["maximum"], 36)
        self.assertEqual(result["reference_ride"]["duration_hours"], 1)
        self.assertIn("intended intensity", result["unavailable_criteria"])

        broadened = execute_tool(
            "find_similar_rides",
            {
                "reference_activity_id": "ride-a",
                "candidate_activity_types": ["cycling", "indoor_cycling"],
                "elevation_tolerance_percent": None,
            },
            self.database,
        )
        self.assertEqual(broadened["candidate_pool_count"], 3)
        self.assertEqual(
            {item["id"] for item in broadened["rides"]},
            {"ride-near", "ride-indoor"},
        )

    def test_same_course_rides_match_gps_locally_and_report_progress(self) -> None:
        result = execute_tool(
            "find_same_course_rides",
            {
                "reference_activity_id": "ride-a",
                "candidate_activity_types": ["cycling", "indoor_cycling"],
                "route_tolerance_meters": 100,
                "minimum_route_overlap_percent": 80,
                "endpoint_tolerance_meters": 500,
                "distance_tolerance_percent": 15,
                "timezone": "UTC",
            },
            self.database,
        )

        self.assertEqual(result["reference_ride"]["id"], "ride-a")
        self.assertEqual(result["candidate_pool_count"], 2)
        self.assertEqual(result["gps_candidates_evaluated"], 1)
        self.assertEqual(result["excluded_without_gps"], 1)
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["rides"][0]["id"], "ride-near")
        self.assertGreaterEqual(
            result["rides"][0]["route_match"]["route_overlap_percent"], 80
        )
        self.assertEqual(result["course_progress"]["attempt_count"], 2)
        self.assertNotIn("latitude", str(result))
        self.assertIn("not included", result["privacy"])

        by_date = execute_tool(
            "find_same_course_rides",
            {"reference_date": "2026-10-03", "timezone": "UTC"},
            self.database,
        )
        self.assertEqual(by_date["reference_ride"]["id"], "ride-a")

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
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            execute_tool(
                "find_similar_rides",
                {
                    "reference_activity_id": "ride-a",
                    "distance_tolerance_percent": -1,
                },
                self.database,
            )


if __name__ == "__main__":
    unittest.main()
