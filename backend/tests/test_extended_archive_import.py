from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.database import connect, migrate
from app.extended_archive_import import (
    import_extended_archive,
    preview_extended_archive_import,
    sanitize_payload,
)


class ExtendedArchiveImportTests(unittest.TestCase):
    def test_sanitizer_removes_identity_keys_recursively(self) -> None:
        sanitized = sanitize_payload(
            {
                "deviceId": 1,
                "value": 42,
                "nested": {"userProfilePK": 2, "calendarDate": "2025-01-01"},
            }
        )
        self.assertEqual(
            sanitized,
            {"value": 42, "nested": {"calendarDate": "2025-01-01"}},
        )

    def test_imports_selected_and_catalogs_every_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "Garmin.zip"
            metric = {
                "userProfilePK": 123,
                "deviceId": 456,
                "calendarDate": 1735776000000,
                "timestamp": "2025-01-02T08:00:00Z",
                "trainingStatus": 3,
            }
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(
                    "DI_CONNECT/DI-Connect-Metrics/TrainingHistory_20250101_20250201_1.json",
                    json.dumps([metric]),
                )
                output.writestr(
                    "DI_CONNECT/DI-Connect-Aggregator/UDSFile_one.json",
                    json.dumps([]),
                )
                output.writestr(
                    "DI_CONNECT/DI-Connect-Social/comments.json",
                    json.dumps([{"comment": "private"}]),
                )

            database = root / "test.sqlite3"
            migrate(database)
            archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO source_files(id, original_name, content_hash, byte_size)
                    VALUES ('archive', 'Garmin.zip', ?, ?)
                    """,
                    (archive_hash, archive.stat().st_size),
                )

            preview = preview_extended_archive_import(archive)
            self.assertTrue(preview["ready"])
            self.assertEqual(preview["selected_files"], 1)
            self.assertEqual(preview["unique_records"], 1)
            self.assertEqual(preview["date_start"], "2025-01-02")
            self.assertEqual(
                preview["catalog"],
                {"excluded": 1, "handled_elsewhere": 1, "imported": 1},
            )

            first = import_extended_archive(archive, database)
            self.assertEqual(first["created_records"], 1)
            second = import_extended_archive(archive, database)
            self.assertEqual(second["imported_files"], 0)
            self.assertEqual(second["resumed_files"], 1)
            with connect(database) as connection:
                payload = connection.execute(
                    "SELECT payload_json FROM garmin_archive_records"
                ).fetchone()[0]
                catalog_count = connection.execute(
                    "SELECT COUNT(*) FROM garmin_archive_file_catalog"
                ).fetchone()[0]
            self.assertNotIn("deviceId", payload)
            self.assertNotIn("userProfilePK", payload)
            self.assertEqual(catalog_count, 3)


if __name__ == "__main__":
    unittest.main()
