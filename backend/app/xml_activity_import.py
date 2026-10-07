from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .database import connect, migrate
from .fit_import import _activity_rows, _datetime, match_activity
from .garmin_import import default_archive_path


MAX_XML_BYTES = 10_000_000
SUPPORTED_FORMATS = {".gpx": "gpx", ".tcx": "tcx"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: object) -> float | None:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _descendant_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag).lower() == name.lower() and child.text:
            return child.text.strip()
    return None


def _haversine_meters(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(value))


def _safe_xml_root(content: bytes) -> ET.Element:
    if len(content) > MAX_XML_BYTES:
        raise ValueError("XML activity file exceeds the size limit")
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("DTD and entity declarations are not supported")
    try:
        return ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError("Invalid activity XML") from error


def _gpx_points(root: ET.Element) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for element in root.iter():
        if _local_name(element.tag).lower() != "trkpt":
            continue
        latitude = _number(element.attrib.get("lat"))
        longitude = _number(element.attrib.get("lon"))
        timestamp = _timestamp(_descendant_text(element, "time"))
        if timestamp is None:
            continue
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("GPX latitude is outside valid bounds")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("GPX longitude is outside valid bounds")
        points.append(
            {
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
                "elevation": _number(_descendant_text(element, "ele")),
                "heart_rate": _number(_descendant_text(element, "hr")),
                "cadence": _number(_descendant_text(element, "cad")),
                "power": _number(_descendant_text(element, "power")),
                "speed": _number(_descendant_text(element, "speed")),
            }
        )
    return points


def _tcx_points(root: ET.Element) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for element in root.iter():
        if _local_name(element.tag).lower() != "trackpoint":
            continue
        timestamp = _timestamp(_descendant_text(element, "Time"))
        if timestamp is None:
            continue
        latitude = _number(_descendant_text(element, "LatitudeDegrees"))
        longitude = _number(_descendant_text(element, "LongitudeDegrees"))
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("TCX latitude is outside valid bounds")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("TCX longitude is outside valid bounds")
        heart_rate = None
        for child in element.iter():
            if _local_name(child.tag).lower() == "heartratebpm":
                heart_rate = _number(_descendant_text(child, "Value"))
                break
        points.append(
            {
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
                "elevation": _number(_descendant_text(element, "AltitudeMeters")),
                "heart_rate": heart_rate,
                "cadence": _number(_descendant_text(element, "Cadence")),
                "power": _number(_descendant_text(element, "Watts")),
                "speed": _number(_descendant_text(element, "Speed")),
                "distance": _number(_descendant_text(element, "DistanceMeters")),
            }
        )
    return points


def parse_activity_xml(content: bytes, file_format: str) -> dict[str, object]:
    root = _safe_xml_root(content)
    if file_format == "gpx":
        points = _gpx_points(root)
    elif file_format == "tcx":
        points = _tcx_points(root)
    else:
        raise ValueError("Unsupported activity XML format")
    if not points:
        raise ValueError("Activity XML contains no timestamped track points")
    points.sort(key=lambda item: item["timestamp"])
    start = points[0]["timestamp"]
    end = points[-1]["timestamp"]
    assert isinstance(start, datetime) and isinstance(end, datetime)

    if file_format == "tcx":
        distances = [
            float(item["distance"])
            for item in points
            if item.get("distance") is not None
        ]
        distance = max(distances) if distances else None
    else:
        distance = 0.0
        previous: tuple[float, float] | None = None
        for item in points:
            if item["latitude"] is None or item["longitude"] is None:
                continue
            current = (float(item["latitude"]), float(item["longitude"]))
            if previous is not None:
                distance += _haversine_meters(previous, current)
            previous = current

    return {
        "session": {
            "start_time": start,
            "total_timer_time": (end - start).total_seconds(),
            "total_distance": distance,
        },
        "points": points,
    }


def _xml_members(archive_path: Path):
    with zipfile.ZipFile(archive_path) as outer:
        for nested_info in outer.infolist():
            if nested_info.is_dir() or not nested_info.filename.lower().endswith(".zip"):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(nested_info))) as nested:
                for info in nested.infolist():
                    suffix = Path(info.filename).suffix.lower()
                    if info.is_dir() or suffix not in SUPPORTED_FORMATS:
                        continue
                    yield {
                        "nested_archive": nested_info.filename,
                        "member": info.filename,
                        "format": SUPPORTED_FORMATS[suffix],
                        "content": nested.read(info),
                    }


def preview_xml_activity_import(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    activities = _activity_rows(database_path)
    used: set[str] = set()
    formats: dict[str, int] = {"gpx": 0, "tcx": 0}
    files = matched = points = unmatched = 0
    for member in _xml_members(archive):
        files += 1
        formats[str(member["format"])] += 1
        parsed = parse_activity_xml(
            bytes(member["content"]), str(member["format"])
        )
        points += len(parsed["points"])
        activity, _ = match_activity(parsed["session"], activities, used)
        if activity is None:
            unmatched += 1
        else:
            matched += 1
            used.add(str(activity["id"]))
    return {
        "ready": unmatched == 0,
        "files": files,
        "formats": formats,
        "points": points,
        "matched_activities": matched,
        "unmatched_files": unmatched,
    }


def _sample_tuples(
    activity_id: str, points: list[dict[str, object]]
) -> list[tuple[object, ...]]:
    samples: dict[str, tuple[object, ...]] = {}
    for point in points:
        timestamp = point["timestamp"]
        assert isinstance(timestamp, datetime)
        recorded_at = timestamp.isoformat().replace("+00:00", "Z")
        heart_rate = point.get("heart_rate")
        samples[recorded_at] = (
            activity_id,
            recorded_at,
            point.get("latitude"),
            point.get("longitude"),
            point.get("elevation"),
            int(float(heart_rate)) if heart_rate is not None else None,
            point.get("cadence"),
            point.get("power"),
            point.get("speed"),
        )
    return list(samples.values())


def import_xml_activity_details(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    migrate(database_path)
    activities = _activity_rows(database_path)
    with connect(database_path) as connection:
        archive_source = connection.execute(
            """
            SELECT id FROM source_files
            WHERE stored_path = ? AND media_type = 'application/zip'
            """,
            (str(archive),),
        ).fetchone()
        if archive_source is None:
            raise ValueError("Run the Garmin JSON import before XML detail import.")
        archive_source_id = str(archive_source[0])
        completed = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT nested_archive, member_name
                FROM xml_activity_import_files WHERE status = 'completed'
                """
            )
        }
        used = {
            row[0]
            for row in connection.execute(
                """
                SELECT activity_id FROM xml_activity_import_files
                WHERE status = 'completed' AND activity_id IS NOT NULL
                """
            )
        }

    imported_files = imported_samples = unmatched_files = failed_files = 0
    resumed_files = len(completed)
    for member in _xml_members(archive):
        member_key = (str(member["nested_archive"]), str(member["member"]))
        if member_key in completed:
            continue
        content = bytes(member["content"])
        content_hash = hashlib.sha256(content).hexdigest()
        detail_source_id = f"garmin-{member['format']}-{content_hash}"
        tracking_id = hashlib.sha256("\n".join(member_key).encode()).hexdigest()
        try:
            parsed = parse_activity_xml(content, str(member["format"]))
            activity, _ = match_activity(parsed["session"], activities, used)
            status = "completed" if activity is not None else "unmatched"
            samples = (
                _sample_tuples(str(activity["id"]), parsed["points"])
                if activity is not None
                else []
            )
            with connect(database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO source_files(
                        id, original_name, content_hash, media_type,
                        byte_size, stored_path
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(content_hash) DO UPDATE SET
                        byte_size = excluded.byte_size,
                        stored_path = excluded.stored_path
                    """,
                    (
                        detail_source_id,
                        Path(str(member["member"])).name,
                        content_hash,
                        f"application/{member['format']}+xml",
                        len(content),
                        f"{archive}!/{member['nested_archive']}!/{member['member']}",
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO activity_samples(
                        activity_id, recorded_at, latitude, longitude,
                        elevation_meters, heart_rate_bpm, cadence_rpm,
                        power_watts, speed_mps
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(activity_id, recorded_at) DO UPDATE SET
                        latitude = COALESCE(excluded.latitude, latitude),
                        longitude = COALESCE(excluded.longitude, longitude),
                        elevation_meters = COALESCE(excluded.elevation_meters, elevation_meters),
                        heart_rate_bpm = COALESCE(excluded.heart_rate_bpm, heart_rate_bpm),
                        cadence_rpm = COALESCE(excluded.cadence_rpm, cadence_rpm),
                        power_watts = COALESCE(excluded.power_watts, power_watts),
                        speed_mps = COALESCE(excluded.speed_mps, speed_mps)
                    """,
                    samples,
                )
                connection.execute(
                    """
                    INSERT INTO xml_activity_import_files(
                        id, archive_source_file_id, detail_source_file_id,
                        nested_archive, member_name, content_hash, file_format,
                        activity_id, status, point_count, imported_samples,
                        error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(nested_archive, member_name) DO UPDATE SET
                        activity_id = excluded.activity_id,
                        status = excluded.status,
                        point_count = excluded.point_count,
                        imported_samples = excluded.imported_samples,
                        error_message = excluded.error_message,
                        imported_at = CURRENT_TIMESTAMP
                    """,
                    (
                        f"xml-import-{tracking_id}",
                        archive_source_id,
                        detail_source_id,
                        member["nested_archive"],
                        member["member"],
                        content_hash,
                        member["format"],
                        str(activity["id"]) if activity is not None else None,
                        status,
                        len(parsed["points"]),
                        len(samples),
                        None if activity is not None else "No unique activity match",
                    ),
                )
            if activity is None:
                unmatched_files += 1
            else:
                imported_files += 1
                imported_samples += len(samples)
                used.add(str(activity["id"]))
        except Exception as error:
            failed_files += 1
            with connect(database_path) as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO source_files(
                        id, original_name, content_hash, media_type,
                        byte_size, stored_path
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail_source_id,
                        Path(str(member["member"])).name,
                        content_hash,
                        f"application/{member['format']}+xml",
                        len(content),
                        f"{archive}!/{member['nested_archive']}!/{member['member']}",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO xml_activity_import_files(
                        id, archive_source_file_id, detail_source_file_id,
                        nested_archive, member_name, content_hash, file_format,
                        status, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', ?)
                    ON CONFLICT(nested_archive, member_name) DO UPDATE SET
                        status = 'failed', error_message = excluded.error_message,
                        imported_at = CURRENT_TIMESTAMP
                    """,
                    (
                        f"xml-import-{tracking_id}",
                        archive_source_id,
                        detail_source_id,
                        member["nested_archive"],
                        member["member"],
                        content_hash,
                        member["format"],
                        type(error).__name__,
                    ),
                )

    return {
        "status": "completed" if failed_files == 0 else "completed_with_failures",
        "imported_files": imported_files,
        "resumed_files": resumed_files,
        "unmatched_files": unmatched_files,
        "failed_files": failed_files,
        "imported_samples": imported_samples,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Preview or import GPX/TCX detail.")
    parser.add_argument("action", choices=("preview", "import"))
    parser.add_argument("archive", nargs="?", type=Path)
    arguments = parser.parse_args()
    result = (
        preview_xml_activity_import(arguments.archive)
        if arguments.action == "preview"
        else import_xml_activity_details(arguments.archive)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
