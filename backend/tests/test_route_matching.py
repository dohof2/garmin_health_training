from __future__ import annotations

import unittest

from app.route_matching import compare_routes, haversine_meters, resample_route


class RouteMatchingTests(unittest.TestCase):
    def test_haversine_and_resampling_are_bounded(self) -> None:
        self.assertAlmostEqual(
            haversine_meters((32.0, 34.8), (32.001, 34.8)),
            111.2,
            delta=0.5,
        )
        route = [(32.0 + index * 0.0001, 34.8) for index in range(500)]
        sampled = resample_route(route, 50)
        self.assertEqual(len(sampled), 50)
        self.assertEqual(sampled[0], route[0])
        self.assertEqual(sampled[-1], route[-1])

    def test_same_and_reverse_routes_report_direction_and_overlap(self) -> None:
        reference = [(32.0 + index * 0.001, 34.8 + index * 0.001) for index in range(20)]
        nearby = [(lat + 0.0001, lon) for lat, lon in reference]
        same = compare_routes(
            reference,
            nearby,
            route_tolerance_meters=100,
            endpoint_tolerance_meters=500,
            allow_reverse_direction=True,
        )
        reverse = compare_routes(
            reference,
            list(reversed(nearby)),
            route_tolerance_meters=100,
            endpoint_tolerance_meters=500,
            allow_reverse_direction=True,
        )
        reverse_disallowed = compare_routes(
            reference,
            list(reversed(nearby)),
            route_tolerance_meters=100,
            endpoint_tolerance_meters=500,
            allow_reverse_direction=False,
        )

        self.assertTrue(same["usable"])
        self.assertEqual(same["direction"], "same")
        self.assertEqual(reverse["direction"], "reverse")
        self.assertFalse(reverse_disallowed["direction_allowed"])
        self.assertGreaterEqual(same["route_overlap_percent"], 99)
        self.assertGreaterEqual(reverse["route_overlap_percent"], 99)


if __name__ == "__main__":
    unittest.main()
