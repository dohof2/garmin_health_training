from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.dashboard import dashboard_card_layout, save_dashboard_card_layout
from app.database import migrate


class DashboardLayoutTests(unittest.TestCase):
    def test_default_layout_contains_visible_registered_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)

            layout = dashboard_card_layout(database)

            self.assertEqual(
                [card["id"] for card in layout],
                ["latest_steps", "last_activity", "weekly_calories"],
            )
            self.assertTrue(all(card["is_visible"] for card in layout))

    def test_saved_order_and_visibility_survive_a_new_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)
            requested = [
                {"id": "weekly_calories", "position": 0, "is_visible": True},
                {"id": "latest_steps", "position": 1, "is_visible": False},
                {"id": "last_activity", "position": 2, "is_visible": True},
            ]

            saved = save_dashboard_card_layout(requested, database)
            loaded = dashboard_card_layout(database)

            self.assertEqual(saved, loaded)
            self.assertEqual([card["id"] for card in loaded], [
                "weekly_calories",
                "latest_steps",
                "last_activity",
            ])
            self.assertFalse(loaded[1]["is_visible"])

    def test_rejects_missing_duplicate_and_invalid_positions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)

            with self.assertRaisesRegex(ValueError, "every registered"):
                save_dashboard_card_layout([], database)
            with self.assertRaisesRegex(ValueError, "unique and consecutive"):
                save_dashboard_card_layout(
                    [
                        {"id": "latest_steps", "position": 0, "is_visible": True},
                        {"id": "last_activity", "position": 0, "is_visible": True},
                        {"id": "weekly_calories", "position": 2, "is_visible": True},
                    ],
                    database,
                )


if __name__ == "__main__":
    unittest.main()
