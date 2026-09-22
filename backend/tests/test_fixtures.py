from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.fixtures import seed_synthetic_history
from app.history import history_summary, list_activities, list_metrics


class SyntheticFixtureTests(unittest.TestCase):
    def test_fixture_is_idempotent_and_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"

            expected = {
                "activities": 3,
                "activity_samples": 4,
                "metric_readings": 14,
            }
            self.assertEqual(seed_synthetic_history(database), expected)
            self.assertEqual(seed_synthetic_history(database), expected)

            summary = history_summary(database)
            self.assertEqual(summary["data_mode"], "synthetic")
            self.assertEqual(summary["activity_count"], 3)
            self.assertEqual(summary["metric_count"], 14)
            self.assertEqual(summary["latest_steps"]["value"], 10421)
            self.assertEqual(
                summary["latest_activity"]["name"], "Morning endurance ride"
            )

            self.assertEqual(len(list_activities(path=database)), 3)
            self.assertEqual(
                len(list_metrics(metric_type="active_calories", path=database)),
                7,
            )


if __name__ == "__main__":
    unittest.main()
