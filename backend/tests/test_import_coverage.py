from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database import connect, migrate
from app.import_coverage import import_coverage


class ImportCoverageTests(unittest.TestCase):
    def test_empty_database_reports_empty_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)
            coverage = import_coverage(database)
            self.assertEqual(coverage["summary"]["complete_categories"], 0)
            self.assertEqual(coverage["summary"]["failed_files"], 0)
            self.assertTrue(
                all(item["status"] == "empty" for item in coverage["categories"])
            )

    def test_reports_completed_and_failed_file_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "test.sqlite3"
            migrate(database)
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO source_files(id, original_name, content_hash, byte_size)
                    VALUES ('archive', 'Garmin.zip', 'archive-hash', 10),
                           ('fit-source', 'ride.fit', 'fit-hash', 5)
                    """
                )
                connection.execute(
                    """
                    INSERT INTO activities(
                        id, source_name, source_record_id, activity_type, started_at
                    ) VALUES ('activity', 'garmin_export', 'one', 'cycling',
                              '2026-01-01T10:00:00Z')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO fit_import_files(
                        id, archive_source_file_id, fit_source_file_id,
                        nested_archive, member_name, content_hash, file_type,
                        activity_id, status, imported_samples
                    ) VALUES (
                        'fit-one', 'archive', 'fit-source', 'part.zip', 'ride.fit',
                        'fit-hash', 'activity', 'activity', 'completed', 12
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO monitoring_fit_import_files(
                        id, archive_source_file_id, nested_archive, member_name,
                        content_hash, status, error_message
                    ) VALUES ('health-one', 'archive', 'part.zip', 'health.fit',
                              'health-hash', 'failed', 'decoder error')
                    """
                )

            coverage = import_coverage(database)
            categories = {item["id"]: item for item in coverage["categories"]}
            self.assertEqual(categories["activity_fit"]["records"], 12)
            self.assertEqual(categories["activity_fit"]["status"], "complete")
            self.assertEqual(categories["health_fit"]["status"], "attention")
            self.assertEqual(coverage["summary"]["failed_files"], 1)
            self.assertEqual(coverage["failures"][0]["member_name"], "health.fit")


if __name__ == "__main__":
    unittest.main()
