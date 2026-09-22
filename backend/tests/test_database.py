from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database import migrate, schema_status


class DatabaseMigrationTests(unittest.TestCase):
    def test_initial_migration_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"

            self.assertEqual(migrate(database), ["001_initial.sql"])
            self.assertEqual(migrate(database), [])

            status = schema_status(database)
            self.assertEqual(status["migrations"], 1)
            self.assertGreaterEqual(status["tables"], 15)

            with sqlite3.connect(database) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertIn("activities", tables)
            self.assertIn("metric_readings", tables)
            self.assertIn("maintenance_events", tables)


if __name__ == "__main__":
    unittest.main()
