from __future__ import annotations

import unittest
from datetime import date

from app.time_utils import (
    calendar_date,
    monday_sunday_week,
    select_timezone,
    timezone_info,
)


class TimeUtilityTests(unittest.TestCase):
    def test_utc_timestamp_resolves_to_israel_calendar_date_after_dst_start(self) -> None:
        timestamp = "2026-03-27T21:30:00Z"

        self.assertEqual(calendar_date(timestamp, "UTC"), date(2026, 3, 27))
        self.assertEqual(
            calendar_date(timestamp, "Asia/Jerusalem"),
            date(2026, 3, 28),
        )

    def test_week_boundaries_remain_monday_sunday_across_dst_dates(self) -> None:
        self.assertEqual(
            monday_sunday_week(date(2026, 3, 28)),
            (date(2026, 3, 23), date(2026, 3, 29)),
        )
        self.assertEqual(
            monday_sunday_week(date(2026, 10, 25)),
            (date(2026, 10, 19), date(2026, 10, 25)),
        )

    def test_unknown_timezone_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown timezone"):
            timezone_info("Not/A_Timezone")

    def test_proprietary_garmin_timezone_uses_browser_fallback(self) -> None:
        self.assertEqual(
            select_timezone("garmin:473", "Asia/Jerusalem"),
            "Asia/Jerusalem",
        )


if __name__ == "__main__":
    unittest.main()
