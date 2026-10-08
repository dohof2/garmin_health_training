from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.settings import get_settings, save_goals, save_profile


class SettingsTests(unittest.TestCase):
    def test_profile_defaults_and_validated_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "settings.sqlite3"

            defaults = get_settings(database)["profile"]
            self.assertEqual(defaults["preferred_distance_unit"], "km")
            self.assertEqual(defaults["preferred_weight_unit"], "kg")

            saved = save_profile(
                {
                    "display_name": " Dotan ",
                    "timezone": "Asia/Jerusalem",
                    "preferred_distance_unit": "km",
                    "preferred_weight_unit": "kg",
                    "birth_date": "1990-01-02",
                    "sex": None,
                    "height_cm": 178,
                    "weight_kg": 75,
                },
                database,
            )
            self.assertEqual(saved["display_name"], "Dotan")
            self.assertEqual(saved["timezone"], "Asia/Jerusalem")
            self.assertEqual(saved["height_cm"], 178)

            with self.assertRaisesRegex(ValueError, "valid IANA timezone"):
                save_profile({"timezone": "not/a-zone"}, database)
            with self.assertRaisesRegex(ValueError, "between 50 and 260"):
                save_profile({"height_cm": 300}, database)

    def test_goals_are_upserted_and_omitted_goals_are_archived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "settings.sqlite3"

            first = save_goals(
                [
                    {
                        "goal_type": "cycling",
                        "title": "Improve FTP",
                        "target_value": 250,
                        "target_unit": "W",
                        "target_date": "2027-01-01",
                    },
                    {"goal_type": "running", "title": "Run consistently"},
                ],
                database,
            )
            self.assertEqual(len(first), 2)
            cycling = next(goal for goal in first if goal["goal_type"] == "cycling")

            updated = save_goals(
                [{**cycling, "target_value": 260, "status": "paused"}],
                database,
            )
            self.assertEqual(len(updated), 1)
            self.assertEqual(updated[0]["target_value"], 260)
            self.assertEqual(updated[0]["status"], "paused")

            all_settings = get_settings(database)
            self.assertEqual(len(all_settings["goals"]), 1)

    def test_goal_validation_rejects_missing_title_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "settings.sqlite3"
            with self.assertRaisesRegex(ValueError, "requires a title"):
                save_goals([{"goal_type": "general", "title": " "}], database)
            with self.assertRaisesRegex(ValueError, "IDs must be unique"):
                save_goals(
                    [
                        {"id": "same", "title": "First"},
                        {"id": "same", "title": "Second"},
                    ],
                    database,
                )


if __name__ == "__main__":
    unittest.main()
