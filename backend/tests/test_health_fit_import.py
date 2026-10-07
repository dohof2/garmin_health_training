from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.health_fit_import import extract_health_samples


class HealthFitImportTests(unittest.TestCase):
    def test_extracts_supported_values_and_filters_sentinels(self) -> None:
        timestamp = datetime(2025, 1, 1, 6, 0, tzinfo=UTC)
        messages = {
            "monitoring_mesgs": [
                {"timestamp": timestamp, "heart_rate": 65},
                {"timestamp": "2025-01-01T06:01:00Z", "heart_rate": 0},
            ],
            "stress_level_mesgs": [
                {"stress_level_time": timestamp, "stress_level_value": 25},
                {
                    "stress_level_time": "2025-01-01T06:01:00Z",
                    "stress_level_value": -2,
                },
            ],
            "respiration_rate_mesgs": [
                {"timestamp": timestamp, "respiration_rate": 14.5},
                {"timestamp": "2025-01-01T06:01:00Z", "respiration_rate": -2},
            ],
        }
        samples = extract_health_samples(messages)
        self.assertEqual(len(samples), 1)
        sample = samples["2025-01-01T06:00:00Z"]
        self.assertEqual(sample["heart_rate_bpm"], 65)
        self.assertEqual(sample["stress_level"], 25)
        self.assertEqual(sample["respiration_rate"], 14.5)

    def test_reconstructs_monitoring_heart_rate_timestamp_16(self) -> None:
        messages = {
            "monitoring_mesgs": [
                {"timestamp": datetime(2021, 11, 4, 5, 15, tzinfo=UTC)},
                {"timestamp_16": 8336, "heart_rate": 73},
            ]
        }
        samples = extract_health_samples(messages)
        self.assertEqual(
            samples["2021-11-04T05:16:00Z"]["heart_rate_bpm"],
            73,
        )


if __name__ == "__main__":
    unittest.main()
