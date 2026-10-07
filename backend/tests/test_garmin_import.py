from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
import zipfile
from pathlib import Path

from app.garmin_import import (
    GarminImportError,
    import_garmin_export,
    inspect_archive,
    preview_garmin_export,
)


def _write_test_export(path: Path) -> None:
    activities = [
        {
            "summarizedActivitiesExport": [
                {
                    "activityId": 123,
                    "activityType": "cycling",
                    "name": "Test ride",
                    "beginTimestamp": 1_735_689_600_000,
                    "duration": 3_600_000,
                    "distance": 2_500_000,
                    "calories": 2_092,
                    "elevationGain": 25_000,
                    "timeZoneId": 473,
                }
            ]
        }
    ]
    daily = [
        {
            "calendarDate": "2025-01-01",
            "totalSteps": 10_000,
            "totalDistanceMeters": 8_100,
            "activeKilocalories": 700,
            "currentDayRestingHeartRate": 55,
        },
        {
            "calendarDate": "2025-01-02",
            "totalSteps": 11_000,
        },
    ]
    sleep = [
        {
            "calendarDate": "2025-01-02",
            "sleepStartTimestampGMT": "2025-01-01T22:00:00.0",
            "sleepEndTimestampGMT": "2025-01-02T06:00:00.0",
            "deepSleepSeconds": 3_600,
            "lightSleepSeconds": 7_200,
            "remSleepSeconds": 1_800,
            "awakeSleepSeconds": 600,
            "averageRespiration": 14,
            "avgSleepStress": 20,
            "sleepScores": {"overallScore": 80},
            "spo2SleepSummary": {
                "averageSPO2": 95,
                "lowestSPO2": 90,
                "averageHR": 55,
            },
        }
    ]
    nested_buffer = tempfile.SpooledTemporaryFile()
    with zipfile.ZipFile(nested_buffer, "w", zipfile.ZIP_DEFLATED) as nested:
        nested.writestr("activity.fit", b"synthetic FIT placeholder")
    nested_buffer.seek(0)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "DI_CONNECT/DI-Connect-Fitness/user_1_summarizedActivities.json",
            json.dumps(activities),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Aggregator/UDSFile_2025-01-01_2025-01-03.json",
            json.dumps(daily),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/2025-01-01_2025-01-03_user_sleepData.json",
            json.dumps(sleep),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Uploaded-Files/Part1.zip",
            nested_buffer.read(),
        )
    nested_buffer.close()


class GarminImportTests(unittest.TestCase):
    def test_preview_and_import_are_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "garmin.zip"
            database = root / "test.sqlite3"
            _write_test_export(archive)

            preview = preview_garmin_export(archive)
            self.assertTrue(preview["ready"])
            self.assertEqual(preview["activities"]["count"], 1)
            self.assertEqual(preview["daily_metrics"]["count"], 5)
            self.assertEqual(preview["sleep_metrics"]["count"], 11)
            self.assertEqual(preview["archive"]["nested_archives"], 1)
            self.assertEqual(preview["archive"]["extensions"][".fit"], 1)

            first = import_garmin_export(archive, database)
            second = import_garmin_export(archive, database)
            self.assertEqual(first["activities"]["created"], 1)
            self.assertEqual(first["daily_metrics"]["created"], 5)
            self.assertEqual(first["sleep_metrics"]["created"], 11)
            self.assertEqual(second["activities"]["created"], 0)
            self.assertEqual(second["activities"]["updated"], 1)
            self.assertEqual(second["daily_metrics"]["updated"], 5)
            self.assertEqual(second["sleep_metrics"]["updated"], 11)

            with closing(sqlite3.connect(database)) as connection:
                activity = connection.execute(
                    """
                    SELECT duration_seconds, distance_meters, calories_kcal,
                           elevation_gain_meters
                    FROM activities WHERE source_name = 'garmin_export'
                    """
                ).fetchone()
                counts = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM source_files),
                        (SELECT COUNT(*) FROM activities),
                        (SELECT COUNT(*) FROM metric_readings)
                    """
                ).fetchone()

            assert activity is not None
            self.assertAlmostEqual(activity[0], 3600)
            self.assertAlmostEqual(activity[1], 25_000)
            self.assertAlmostEqual(activity[2], 500)
            self.assertAlmostEqual(activity[3], 250)
            self.assertEqual(counts, (1, 1, 16))

    def test_unsafe_archive_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../outside.json", "[]")

            with self.assertRaises(GarminImportError):
                inspect_archive(archive)


if __name__ == "__main__":
    unittest.main()
