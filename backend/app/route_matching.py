from __future__ import annotations

from math import asin, cos, radians, sin, sqrt, floor, pi
from pathlib import Path

from .database import connect


EARTH_RADIUS_METERS = 6_371_008.8
MAX_ROUTE_POINTS = 300


Coordinate = tuple[float, float]


def haversine_meters(first: Coordinate, second: Coordinate) -> float:
    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    latitude_delta = lat2 - lat1
    longitude_delta = lon2 - lon1
    value = (
        sin(latitude_delta / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * asin(min(1.0, sqrt(value)))


def load_gps_route(activity_id: str, path: Path | None = None) -> list[Coordinate]:
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT latitude, longitude
            FROM activity_samples
            WHERE activity_id = ?
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
            ORDER BY recorded_at
            """,
            (activity_id,),
        ).fetchall()
    points: list[Coordinate] = []
    for row in rows:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        point = (latitude, longitude)
        if not points or haversine_meters(points[-1], point) >= 1:
            points.append(point)
    return points


def resample_route(
    points: list[Coordinate], maximum_points: int = MAX_ROUTE_POINTS
) -> list[Coordinate]:
    if len(points) <= maximum_points:
        return points
    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine_meters(first, second))
    total = cumulative[-1]
    if total <= 0:
        return [points[0]]

    sampled = [points[0]]
    source_index = 1
    for sample_index in range(1, maximum_points - 1):
        target = total * sample_index / (maximum_points - 1)
        while source_index < len(cumulative) - 1 and cumulative[source_index] < target:
            source_index += 1
        sampled.append(points[source_index])
    sampled.append(points[-1])
    return sampled


def _coverage_percent(
    source: list[Coordinate], target: list[Coordinate], tolerance_meters: float
) -> float:
    if not source or not target:
        return 0.0
    if tolerance_meters <= 0:
        covered = sum(any(haversine_meters(point, candidate) <= tolerance_meters
                          for candidate in target) for point in source)
    else:
        # Latitude separation alone bounds the great-circle distance. Only
        # adjacent latitude cells can contain a point inside the tolerance.
        step = tolerance_meters / EARTH_RADIUS_METERS * 180 / pi
        cells: dict[int, list[Coordinate]] = {}
        for candidate in target:
            cells.setdefault(floor(candidate[0] / step), []).append(candidate)
        covered = 0
        for point in source:
            cell = floor(point[0] / step)
            if any(haversine_meters(point, candidate) <= tolerance_meters
                   for adjacent in (cell - 1, cell, cell + 1)
                   for candidate in cells.get(adjacent, ())):
                covered += 1
    return covered / len(source) * 100


def _ordered_mean_distance(
    reference: list[Coordinate], candidate: list[Coordinate], reverse: bool
) -> float:
    comparison_count = min(100, len(reference), len(candidate))
    if comparison_count < 2:
        return float("inf")
    ordered_candidate = list(reversed(candidate)) if reverse else candidate
    distances = []
    for index in range(comparison_count):
        reference_index = round(index * (len(reference) - 1) / (comparison_count - 1))
        candidate_index = round(index * (len(ordered_candidate) - 1) / (comparison_count - 1))
        distances.append(
            haversine_meters(
                reference[reference_index], ordered_candidate[candidate_index]
            )
        )
    return sum(distances) / len(distances)


def compare_routes(
    reference_points: list[Coordinate],
    candidate_points: list[Coordinate],
    *,
    route_tolerance_meters: float,
    endpoint_tolerance_meters: float,
    allow_reverse_direction: bool,
) -> dict[str, float | str | int | bool]:
    reference = resample_route(reference_points)
    candidate = resample_route(candidate_points)
    if len(reference) < 2 or len(candidate) < 2:
        return {
            "usable": False,
            "reference_points_used": len(reference),
            "candidate_points_used": len(candidate),
            "direction": "unavailable",
            "endpoint_distance_meters": float("inf"),
            "route_overlap_percent": 0.0,
        }

    same_endpoint = max(
        haversine_meters(reference[0], candidate[0]),
        haversine_meters(reference[-1], candidate[-1]),
    )
    reverse_endpoint = max(
        haversine_meters(reference[0], candidate[-1]),
        haversine_meters(reference[-1], candidate[0]),
    )
    same_order = _ordered_mean_distance(reference, candidate, False)
    reverse_order = _ordered_mean_distance(reference, candidate, True)
    reference_is_loop = (
        haversine_meters(reference[0], reference[-1]) <= endpoint_tolerance_meters
    )
    candidate_is_loop = (
        haversine_meters(candidate[0], candidate[-1]) <= endpoint_tolerance_meters
    )

    use_reverse = (
        reverse_endpoint < same_endpoint
        or (
            reference_is_loop
            and candidate_is_loop
            and reverse_order < same_order
        )
    )
    endpoint_distance = reverse_endpoint if use_reverse else same_endpoint
    direction = "reverse" if use_reverse else "same"
    if reference_is_loop and candidate_is_loop and abs(same_order - reverse_order) < 25:
        direction = "loop / direction ambiguous"

    reference_coverage = _coverage_percent(
        reference, candidate, route_tolerance_meters
    )
    candidate_coverage = _coverage_percent(
        candidate, reference, route_tolerance_meters
    )
    overlap = min(reference_coverage, candidate_coverage)
    return {
        "usable": True,
        "reference_points_used": len(reference),
        "candidate_points_used": len(candidate),
        "direction": direction,
        "direction_allowed": allow_reverse_direction or direction != "reverse",
        "endpoint_distance_meters": endpoint_distance,
        "reference_coverage_percent": reference_coverage,
        "candidate_coverage_percent": candidate_coverage,
        "route_overlap_percent": overlap,
        "ordered_mean_distance_meters": reverse_order if use_reverse else same_order,
    }
