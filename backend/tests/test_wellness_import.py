from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.database import connect, migrate
from app.wellness_import import import_wellness_records, preview_wellness_import


class WellnessImportTests(unittest.TestCase):
    def _archive(self, directory: Path) -> Path:
        archive = directory / "Garmin.zip"
        hydration = {
            "userProfilePK": 123,
            "calendarDate": "2025-01-02",
            "persistedTimestampGMT": "2025-01-02T08:00:00.0",
            "timestampLocal": "2025-01-02T10:00:00.0",
            "hydrationSource": "GARMIN_GCM",
            "valueInML": -250.0,
            "capped": False,
            "uuid": {"uuid": "12345678-1234-5678-1234-567812345678"},
        }
        abnormal = {
            "deviceId": 999,
            "abnormalHrEventGMT": "2025-01-03T06:00:00.0",
            "abnormalHrThresholdValue": 40,
            "abnormalHrValue": 38,
            "calendarDate": "2025-01-03",
        }
        nutrition = {
            "calendarDate": "2025-01-04",
            "mfpCalorie": {"calorie": 1800, "calorieGoal": 2000},
        }
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr(
                "DI_CONNECT/DI-Connect-Aggregator/HydrationLogFile_one.json",
                json.dumps([hydration, hydration]),
            )
            output.writestr(
                "DI_CONNECT/DI-Connect-Wellness/one_AbnormalHrEvents.json",
                json.dumps([abnormal]),
            )
            output.writestr(
                "DI_CONNECT/DI-Connect-Wellness/one_nutritionLogs.json",
                json.dumps([nutrition]),
            )
        return archive

    def test_preview_deduplicates_and_import_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = self._archive(root)
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

            preview = preview_wellness_import(archive)
            self.assertTrue(preview["ready"])
            self.assertEqual(preview["hydration"]["source_records"], 2)
            self.assertEqual(preview["hydration"]["unique_records"], 1)
            self.assertEqual(preview["hydration"]["duplicates"], 1)
            self.assertEqual(preview["abnormal_heart_rate"]["unique_records"], 1)
            self.assertEqual(preview["nutrition"]["unique_records"], 1)

            first = import_wellness_records(archive, database)
            self.assertEqual(first["hydration"]["created"], 1)
            self.assertEqual(first["abnormal_heart_rate"]["created"], 1)
            self.assertEqual(first["nutrition"]["created"], 1)
            second = import_wellness_records(archive, database)
            self.assertEqual(second["imported_files"], 0)
            self.assertEqual(second["resumed_files"], 3)

            with connect(database) as connection:
                hydration = connection.execute(
                    "SELECT value_ml FROM hydration_events"
                ).fetchone()
                abnormal = connection.execute(
                    "SELECT heart_rate_bpm, threshold_bpm FROM abnormal_heart_rate_events"
                ).fetchone()
                nutrition = connection.execute(
                    "SELECT calories_consumed, calorie_goal FROM garmin_nutrition_daily"
                ).fetchone()
                files = connection.execute(
                    "SELECT COUNT(*) FROM wellness_json_import_files"
                ).fetchone()[0]
            self.assertEqual(hydration[0], -250.0)
            self.assertEqual(tuple(abnormal), (38, 40))
            self.assertEqual(tuple(nutrition), (1800, 2000))
            self.assertEqual(files, 3)


if __name__ == "__main__":
    unittest.main()
