from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.database import migrate, schema_status


class DatabaseMigrationTests(unittest.TestCase):
    def test_initial_migration_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"

            self.assertEqual(
                migrate(database),
                [
                    "001_initial.sql",
                    "002_fit_import_tracking.sql",
                    "003_fit_tracking_duplicate_paths.sql",
                    "004_xml_activity_import_tracking.sql",
                    "005_health_fit_samples.sql",
                    "006_wellness_json_events.sql",
                    "007_garmin_nutrition_daily.sql",
                    "008_extended_archive_records.sql",
                    "009_sync_foundation.sql",
                    "010_ai_provider_settings.sql",
                ],
            )
            self.assertEqual(migrate(database), [])

            status = schema_status(database)
            self.assertEqual(status["migrations"], 10)
            self.assertGreaterEqual(status["tables"], 15)

            with closing(sqlite3.connect(database)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertIn("activities", tables)
            self.assertIn("metric_readings", tables)
            self.assertIn("maintenance_events", tables)
            self.assertIn("fit_import_files", tables)
            self.assertIn("xml_activity_import_files", tables)
            self.assertIn("health_samples", tables)
            self.assertIn("monitoring_fit_import_files", tables)
            self.assertIn("hydration_events", tables)
            self.assertIn("abnormal_heart_rate_events", tables)
            self.assertIn("wellness_json_import_files", tables)
            self.assertIn("garmin_nutrition_daily", tables)
            self.assertIn("garmin_archive_records", tables)
            self.assertIn("extended_archive_import_files", tables)
            self.assertIn("garmin_archive_file_catalog", tables)
            self.assertIn("sync_settings", tables)
            self.assertIn("sync_checkpoints", tables)
            self.assertIn("sync_intervals", tables)
            self.assertIn("ai_settings", tables)

    def test_fit_tracking_allows_duplicate_content_at_distinct_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    """
                    INSERT INTO source_files(id, original_name, content_hash, byte_size)
                    VALUES ('archive', 'export.zip', 'archive-hash', 10),
                           ('fit', 'activity.fit', 'same-fit-hash', 5)
                    """
                )
                for identifier, member in (("one", "one.fit"), ("two", "two.fit")):
                    connection.execute(
                        """
                        INSERT INTO fit_import_files(
                            id, archive_source_file_id, fit_source_file_id,
                            nested_archive, member_name, content_hash,
                            file_type, status
                        ) VALUES (?, 'archive', 'fit', 'part.zip', ?,
                                  'same-fit-hash', 'activity', 'completed')
                        """,
                        (identifier, member),
                    )
                count = connection.execute(
                    "SELECT COUNT(*) FROM fit_import_files"
                ).fetchone()[0]
            self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
