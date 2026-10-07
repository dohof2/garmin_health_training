from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.fit_import import _coordinate, _fit_activity_type, match_activity


class FitMatchingTests(unittest.TestCase):
    def test_matches_by_time_duration_and_distance(self) -> None:
        activities = [
            {
                "id": "a1",
                "source_record_id": "1",
                "started_at": "2025-01-01T06:00:00Z",
                "duration_seconds": 3600.0,
                "distance_meters": 25_000.0,
            },
            {
                "id": "a2",
                "source_record_id": "2",
                "started_at": "2025-01-01T06:00:20Z",
                "duration_seconds": 1800.0,
                "distance_meters": 5_000.0,
            },
        ]
        session = {
            "start_time": datetime(2025, 1, 1, 6, 0, 18, tzinfo=UTC),
            "total_timer_time": 3600.5,
            "total_distance": 25_001.0,
        }

        match, score = match_activity(session, activities)
        self.assertIsNotNone(match)
        assert match is not None and score is not None
        self.assertEqual(match["id"], "a1")
        self.assertGreaterEqual(score, 0)

    def test_does_not_reuse_an_activity(self) -> None:
        activities = [
            {
                "id": "a1",
                "started_at": "2025-01-01T06:00:00Z",
                "duration_seconds": 3600.0,
                "distance_meters": 25_000.0,
            }
        ]
        session = {
            "start_time": datetime(2025, 1, 1, 6, 0, tzinfo=UTC),
            "total_timer_time": 3600.0,
            "total_distance": 25_000.0,
        }
        match, _ = match_activity(session, activities, {"a1"})
        self.assertIsNone(match)

    def test_converts_fit_semicircles_to_degrees(self) -> None:
        self.assertAlmostEqual(_coordinate(2**30), 90.0)
        self.assertAlmostEqual(_coordinate(-(2**30)), -90.0)

    def test_maps_mountain_cycling_activity_type(self) -> None:
        self.assertEqual(
            _fit_activity_type({"sport": "cycling", "sub_sport": "mountain"}),
            "mountain_biking",
        )


if __name__ == "__main__":
    unittest.main()
