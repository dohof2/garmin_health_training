from __future__ import annotations

import unittest
import random

from app.route_matching import compare_routes, haversine_meters, resample_route, _coverage_percent


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

    def test_indexed_coverage_matches_exact_scan_at_boundaries_and_poles(self):
        rng = random.Random(17)
        for latitude in (-89.9, -32, 0, 32, 89.9):
            source = [(latitude + rng.uniform(-.005,.005), rng.uniform(-180,180)) for _ in range(50)]
            target = [(lat + rng.uniform(-.001,.001), lon + rng.uniform(-.001,.001)) for lat,lon in source]
            for tolerance in (0, 20, 100, 500):
                exact = sum(any(haversine_meters(p,q) <= tolerance for q in target) for p in source) / len(source) * 100
                self.assertEqual(_coverage_percent(source,target,tolerance), exact)
        self.assertEqual(_coverage_percent([],target,100),0)

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
