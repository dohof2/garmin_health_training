from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import date
from pathlib import Path

from app.database import connect, migrate
from app.exports import (
    ExportError,
    create_backup,
    create_original_activity_bundle,
    export_csv,
    export_json,
    original_activity_inventory,
    preview_restore,
    restore_backup,
)
from app.fixtures import seed_synthetic_history


class ExportTests(unittest.TestCase):
    def test_csv_is_date_filtered_and_spreadsheet_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "source.sqlite3"
            output = root / "activities.csv"
            seed_synthetic_history(database)
            with connect(database) as connection:
                connection.execute(
                    "UPDATE activities SET name = '=unsafe' WHERE id = (SELECT id FROM activities ORDER BY started_at LIMIT 1)"
                )

            result = export_csv(
                "activities",
                output,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
                path=database,
            )
            with output.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))

            self.assertEqual(result["records"], 3)
            self.assertEqual(len(rows), 3)
            unsafe = next(row for row in rows if row["name"].endswith("unsafe"))
            self.assertEqual(unsafe["name"], "'=unsafe")

    def test_versioned_json_preserves_dashboard_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "source.sqlite3"
            output = root / "data.json"
            seed_synthetic_history(database)
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO dashboard_cards(id, card_type, position, is_visible)
                    VALUES ('latest_steps', 'metric', 0, 0)
                    """
                )

            export_json(output, path=database)
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["metadata"]["schema_version"], 1)
            self.assertEqual(len(payload["tables"]["activities"]), 3)
            self.assertEqual(payload["tables"]["dashboard_cards"][0]["is_visible"], 0)
            self.assertNotIn("source_files", payload["tables"])

    def test_backup_preview_and_restore_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.sqlite3"
            backup = root / "backup.zip"
            restored = root / "restored.sqlite3"
            seed_synthetic_history(source)
            with connect(source) as connection:
                connection.execute(
                    """
                    INSERT INTO dashboard_cards(id, card_type, position, is_visible)
                    VALUES ('last_activity', 'activity', 0, 1)
                    """
                )

            created = create_backup(backup, source)
            preview = preview_restore(backup)
            restored_result = restore_backup(backup, restored)

            self.assertFalse(created["originals"]["included"])
            self.assertTrue(preview["ready"])
            self.assertFalse(preview["credentials_included"])
            self.assertEqual(preview["table_counts"]["activities"], 3)
            self.assertEqual(restored_result["table_counts"]["activity_samples"], 4)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(
                    connection.execute("SELECT is_visible FROM dashboard_cards WHERE id = 'last_activity'").fetchone()[0],
                    1,
                )

    def test_restore_preview_rejects_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            backup = Path(temporary_directory) / "unsafe.zip"
            with zipfile.ZipFile(backup, "w") as archive:
                archive.writestr("../escape", b"unsafe")
            with self.assertRaisesRegex(ExportError, "unsafe path"):
                preview_restore(backup)

    def test_original_activity_bundle_preserves_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "source.sqlite3"
            outer = root / "garmin.zip"
            bundle = root / "activities.zip"
            fit_content = b"synthetic-fit-source"
            nested_buffer = io.BytesIO()
            with zipfile.ZipFile(nested_buffer, "w") as nested:
                nested.writestr("activity.fit", fit_content)
            with zipfile.ZipFile(outer, "w") as archive:
                archive.writestr("nested.zip", nested_buffer.getvalue())

            migrate(database)
            fit_hash = hashlib.sha256(fit_content).hexdigest()
            archive_hash = hashlib.sha256(outer.read_bytes()).hexdigest()
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO source_files(id, original_name, content_hash, media_type, byte_size, stored_path)
                    VALUES ('archive', 'garmin.zip', ?, 'application/zip', ?, ?),
                           ('fit', 'activity.fit', ?, 'application/vnd.ant.fit', ?, ?)
                    """,
                    (
                        archive_hash,
                        outer.stat().st_size,
                        str(outer),
                        fit_hash,
                        len(fit_content),
                        f"{outer}!/nested.zip!/activity.fit",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO activities(id, source_name, source_record_id, source_file_id, activity_type, started_at)
                    VALUES ('activity', 'test', 'activity', 'archive', 'cycling', '2026-09-01T07:00:00Z')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO fit_import_files(
                        id, archive_source_file_id, fit_source_file_id, nested_archive,
                        member_name, content_hash, file_type, activity_id, status
                    ) VALUES ('fit-import', 'archive', 'fit', 'nested.zip', 'activity.fit', ?, 'activity', 'activity', 'completed')
                    """,
                    (fit_hash,),
                )

            self.assertEqual(original_activity_inventory(database)["files"], 1)
            create_original_activity_bundle(bundle, database)
            with zipfile.ZipFile(bundle) as archive:
                activity_name = next(name for name in archive.namelist() if name.endswith("activity.fit"))
                self.assertEqual(archive.read(activity_name), fit_content)


if __name__ == "__main__":
    unittest.main()
