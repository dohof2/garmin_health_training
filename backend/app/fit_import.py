from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from garmin_fit_sdk import Decoder, Stream

from .config import data_directory
from .database import connect, migrate
from .garmin_import import (
    GARMIN_SOURCE_NAME,
    default_archive_path,
    inspect_archive,
)


INVENTORY_VERSION = 1


def fit_inventory_path() -> Path:
    return data_directory() / "fit-inventory.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_checkpoint(path: Path, archive_hash: str) -> dict[str, object]:
    if not path.exists():
        return {
            "version": INVENTORY_VERSION,
            "archive_sha256": archive_hash,
            "status": "running",
            "completed_nested_archives": [],
            "fit_files": 0,
            "file_types": {},
            "activity_files": [],
            "decode_failures": [],
        }
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        checkpoint = {}
    if (
        checkpoint.get("version") != INVENTORY_VERSION
        or checkpoint.get("archive_sha256") != archive_hash
    ):
        return {
            "version": INVENTORY_VERSION,
            "archive_sha256": archive_hash,
            "status": "running",
            "completed_nested_archives": [],
            "fit_files": 0,
            "file_types": {},
            "activity_files": [],
            "decode_failures": [],
        }
    return checkpoint


def _decode_fit(content: bytes) -> tuple[dict[str, list[dict]], list[object]]:
    decoder = Decoder(Stream.from_bytes_io(io.BytesIO(content)))
    return decoder.read(
        apply_scale_and_offset=True,
        convert_datetimes_to_dates=True,
        convert_types_to_strings=True,
        enable_crc_check=True,
        expand_sub_fields=False,
        expand_components=False,
        merge_heart_rates=False,
    )


def build_fit_inventory(
    archive_path: Path | None = None,
    checkpoint_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inspect_archive(archive)
    archive_hash = _sha256(archive)
    destination = checkpoint_path or fit_inventory_path()
    report = _load_checkpoint(destination, archive_hash)
    if report.get("status") == "complete":
        return report

    completed = set(report.get("completed_nested_archives", []))
    file_types = Counter(
        {str(key): int(value) for key, value in dict(report["file_types"]).items()}
    )
    activity_files = list(report["activity_files"])
    failures = list(report["decode_failures"])
    fit_files = int(report["fit_files"])

    with zipfile.ZipFile(archive) as outer:
        nested_names = sorted(
            info.filename
            for info in outer.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".zip")
        )
        for nested_name in nested_names:
            if nested_name in completed:
                continue
            nested_fit_files = 0
            print(f"Scanning FIT archive: {nested_name}", file=sys.stderr, flush=True)
            with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as nested:
                for info in nested.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".fit"):
                        continue
                    nested_fit_files += 1
                    fit_files += 1
                    content = nested.read(info)
                    try:
                        messages, errors = _decode_fit(content)
                        file_id = (messages.get("file_id_mesgs") or [{}])[0]
                        file_type = str(file_id.get("type", "unknown"))
                        file_types[file_type] += 1
                        if file_type == "activity":
                            session = (messages.get("session_mesgs") or [{}])[0]
                            started_at = session.get("start_time") or file_id.get(
                                "time_created"
                            )
                            if isinstance(started_at, datetime):
                                started_at = started_at.isoformat()
                            activity_files.append(
                                {
                                    "nested_archive": nested_name,
                                    "member": info.filename,
                                    "bytes": info.file_size,
                                    "sha256": hashlib.sha256(content).hexdigest(),
                                    "started_at": started_at,
                                    "record_count": len(
                                        messages.get("record_mesgs") or []
                                    ),
                                    "session_count": len(
                                        messages.get("session_mesgs") or []
                                    ),
                                    "decode_errors": len(errors),
                                }
                            )
                        elif errors:
                            failures.append(
                                {
                                    "nested_archive": nested_name,
                                    "member": info.filename,
                                    "reason": "decoder_reported_errors",
                                    "count": len(errors),
                                }
                            )
                    except Exception as error:
                        failures.append(
                            {
                                "nested_archive": nested_name,
                                "member": info.filename,
                                "reason": type(error).__name__,
                            }
                        )

                    if nested_fit_files % 5000 == 0:
                        print(
                            f"  scanned {nested_fit_files:,} FIT files",
                            file=sys.stderr,
                            flush=True,
                        )

            completed.add(nested_name)
            report.update(
                {
                    "status": "running",
                    "completed_nested_archives": sorted(completed),
                    "fit_files": fit_files,
                    "file_types": dict(sorted(file_types.items())),
                    "activity_files": activity_files,
                    "decode_failures": failures,
                }
            )
            _atomic_write_json(destination, report)

    report.update(
        {
            "status": "complete",
            "completed_nested_archives": sorted(completed),
            "fit_files": fit_files,
            "file_types": dict(sorted(file_types.items())),
            "activity_files": activity_files,
            "activity_file_count": len(activity_files),
            "activity_record_count": sum(
                int(item["record_count"]) for item in activity_files
            ),
            "decode_failures": failures,
            "decode_failure_count": len(failures),
        }
    )
    _atomic_write_json(destination, report)
    return report


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _activity_rows(database_path: Path | None = None) -> list[dict[str, object]]:
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, source_record_id, started_at, duration_seconds,
                   distance_meters
            FROM activities
            WHERE source_name = ?
            """,
            (GARMIN_SOURCE_NAME,),
        ).fetchall()
    return [dict(row) for row in rows]


def match_activity(
    session: dict[str, object],
    activities: list[dict[str, object]],
    used_activity_ids: set[str] | None = None,
) -> tuple[dict[str, object] | None, float | None]:
    """Match one FIT session using time plus independently measured totals."""
    started_at = _datetime(session.get("start_time"))
    if started_at is None:
        return None, None
    fit_duration = _number(
        session.get("total_timer_time") or session.get("total_elapsed_time")
    )
    fit_distance = _number(session.get("total_distance"))
    used = used_activity_ids or set()
    candidates: list[tuple[float, dict[str, object]]] = []

    for activity in activities:
        if str(activity["id"]) in used:
            continue
        activity_start = _datetime(activity.get("started_at"))
        if activity_start is None:
            continue
        time_delta = abs((started_at - activity_start).total_seconds())
        if time_delta > 15 * 60:
            continue

        activity_duration = _number(activity.get("duration_seconds"))
        duration_delta = (
            abs(fit_duration - activity_duration)
            if fit_duration is not None and activity_duration is not None
            else None
        )
        if duration_delta is not None and duration_delta > max(
            15, activity_duration * 0.03
        ):
            continue

        activity_distance = _number(activity.get("distance_meters"))
        distance_delta = (
            abs(fit_distance - activity_distance)
            if fit_distance is not None and activity_distance is not None
            else None
        )
        if distance_delta is not None and distance_delta > max(
            150, activity_distance * 0.03
        ):
            continue

        score = time_delta
        if duration_delta is not None:
            score += duration_delta / 5
        if distance_delta is not None:
            score += distance_delta / 25
        candidates.append((score, activity))

    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0])
    if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 1:
        return None, None
    return candidates[0][1], candidates[0][0]


def _activity_fit_members(
    archive_path: Path,
    inventory: dict[str, object],
    skip_members: set[tuple[str, str]] | None = None,
):
    skipped = skip_members or set()
    grouped: dict[str, list[dict[str, object]]] = {}
    for metadata in inventory["activity_files"]:
        assert isinstance(metadata, dict)
        member_key = (
            str(metadata["nested_archive"]),
            str(metadata["member"]),
        )
        if member_key in skipped:
            continue
        grouped.setdefault(str(metadata["nested_archive"]), []).append(metadata)

    with zipfile.ZipFile(archive_path) as outer:
        for nested_name, members in sorted(grouped.items()):
            with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as nested:
                for metadata in members:
                    content = nested.read(str(metadata["member"]))
                    messages, errors = _decode_fit(content)
                    yield metadata, content, messages, errors


def preview_fit_activity_import(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inventory = build_fit_inventory(archive)
    activities = _activity_rows(database_path)
    used: set[str] = set()
    matched = 0
    unmatched = 0
    decoder_errors = 0

    for _, _, messages, errors in _activity_fit_members(archive, inventory):
        decoder_errors += len(errors)
        session = (messages.get("session_mesgs") or [{}])[0]
        activity, _ = match_activity(session, activities, used)
        if activity is None:
            unmatched += 1
        else:
            matched += 1
            used.add(str(activity["id"]))

    return {
        "ready": unmatched == 0 and decoder_errors == 0,
        "activity_fit_files": int(inventory["activity_file_count"]),
        "record_messages": int(inventory["activity_record_count"]),
        "matched_activities": matched,
        "unmatched_fit_files": unmatched,
        "activities_without_fit": len(activities) - len(used),
        "decoder_errors": decoder_errors,
    }


def _coordinate(value: object) -> float | None:
    number = _number(value)
    return number * 180 / 2**31 if number is not None else None


def _sample_rows(
    activity_id: str,
    records: list[dict[str, object]],
) -> list[tuple[object, ...]]:
    samples: dict[str, tuple[object, ...]] = {}
    for record in records:
        timestamp = _datetime(record.get("timestamp"))
        if timestamp is None:
            continue
        recorded_at = timestamp.isoformat().replace("+00:00", "Z")
        altitude = _number(record.get("enhanced_altitude"))
        if altitude is None:
            altitude = _number(record.get("altitude"))
        speed = _number(record.get("enhanced_speed"))
        if speed is None:
            speed = _number(record.get("speed"))
        heart_rate = _number(record.get("heart_rate"))
        samples[recorded_at] = (
            activity_id,
            recorded_at,
            _coordinate(record.get("position_lat")),
            _coordinate(record.get("position_long")),
            altitude,
            int(heart_rate) if heart_rate is not None else None,
            _number(record.get("cadence")),
            _number(record.get("power")),
            speed,
        )
    return list(samples.values())


def _fit_activity_type(session: dict[str, object]) -> str:
    sport = str(session.get("sport") or "unknown")
    sub_sport = str(session.get("sub_sport") or "")
    if sport == "cycling" and sub_sport == "mountain":
        return "mountain_biking"
    if sport == "cycling" and sub_sport in {"indoor_cycling", "spin"}:
        return "indoor_cycling"
    return sport


def _create_fit_only_activity(
    *,
    database_path: Path | None,
    fit_source_id: str,
    content_hash: str,
    session: dict[str, object],
) -> dict[str, object]:
    started_at = _datetime(session.get("start_time"))
    duration = _number(
        session.get("total_timer_time") or session.get("total_elapsed_time")
    )
    if started_at is None or duration is None or duration < 0:
        raise ValueError("FIT-only activity lacks a valid start time or duration")
    started_iso = started_at.isoformat().replace("+00:00", "Z")
    ended_iso = datetime.fromtimestamp(
        started_at.timestamp() + duration, UTC
    ).isoformat().replace("+00:00", "Z")
    activity_type = _fit_activity_type(session)
    profile_name = session.get("sport_profile_name")
    name = (
        str(profile_name).strip()
        if profile_name not in (None, "")
        else activity_type.replace("_", " ").title()
    )
    activity_id = f"garmin-fit-activity-{content_hash}"
    source_record_id = f"fit:{content_hash}"
    evidence = {
        "source": "FIT session",
        "sport": session.get("sport"),
        "subSport": session.get("sub_sport"),
        "startTime": started_iso,
        "durationSeconds": duration,
        "distanceMeters": _number(session.get("total_distance")),
    }

    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO activities(
                id, source_name, source_record_id, source_file_id,
                activity_type, name, started_at, ended_at,
                duration_seconds, distance_meters, calories_kcal,
                elevation_gain_meters, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name, source_record_id) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                activity_type = excluded.activity_type,
                name = excluded.name,
                started_at = excluded.started_at,
                ended_at = excluded.ended_at,
                duration_seconds = excluded.duration_seconds,
                distance_meters = excluded.distance_meters,
                calories_kcal = excluded.calories_kcal,
                elevation_gain_meters = excluded.elevation_gain_meters,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                activity_id,
                GARMIN_SOURCE_NAME,
                source_record_id,
                fit_source_id,
                activity_type,
                name[:500],
                started_iso,
                ended_iso,
                duration,
                _number(session.get("total_distance")),
                _number(session.get("total_calories")),
                _number(session.get("total_ascent")),
                json.dumps(evidence, separators=(",", ":"), default=str),
            ),
        )

    return {
        "id": activity_id,
        "source_record_id": source_record_id,
        "started_at": started_iso,
        "duration_seconds": duration,
        "distance_meters": _number(session.get("total_distance")),
    }


def _record_fit_status(
    *,
    database_path: Path | None,
    archive_source_id: str,
    fit_source_id: str,
    metadata: dict[str, object],
    activity_id: str | None,
    status: str,
    record_count: int,
    imported_samples: int,
    error_message: str | None,
) -> None:
    member_identity = hashlib.sha256(
        f"{metadata['nested_archive']}\n{metadata['member']}".encode()
    ).hexdigest()
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO fit_import_files(
                id, archive_source_file_id, fit_source_file_id,
                nested_archive, member_name, content_hash, file_type,
                activity_id, status, record_count, imported_samples,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, 'activity', ?, ?, ?, ?, ?)
            ON CONFLICT(nested_archive, member_name) DO UPDATE SET
                content_hash = excluded.content_hash,
                fit_source_file_id = excluded.fit_source_file_id,
                activity_id = excluded.activity_id,
                status = excluded.status,
                record_count = excluded.record_count,
                imported_samples = excluded.imported_samples,
                error_message = excluded.error_message,
                imported_at = CURRENT_TIMESTAMP
            """,
            (
                f"fit-import-{member_identity}",
                archive_source_id,
                fit_source_id,
                metadata["nested_archive"],
                metadata["member"],
                metadata["sha256"],
                activity_id,
                status,
                record_count,
                imported_samples,
                error_message,
            ),
        )


def import_fit_activity_samples(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inventory = build_fit_inventory(archive)
    migrate(database_path)
    activities = _activity_rows(database_path)

    with connect(database_path) as connection:
        archive_source = connection.execute(
            "SELECT id FROM source_files WHERE content_hash = ?",
            (inventory["archive_sha256"],),
        ).fetchone()
        if archive_source is None:
            raise ValueError("Run the Garmin JSON import before FIT detail import.")
        archive_source_id = str(archive_source[0])
        completed_members = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT nested_archive, member_name
                FROM fit_import_files WHERE status = 'completed'
                """
            )
        }
        used_activity_ids = {
            row[0]
            for row in connection.execute(
                """
                SELECT activity_id FROM fit_import_files
                WHERE status = 'completed' AND activity_id IS NOT NULL
                """
            )
        }

    inventory_members = {
        (str(item["nested_archive"]), str(item["member"]))
        for item in inventory["activity_files"]
        if isinstance(item, dict)
    }
    imported_files = 0
    resumed_files = len(completed_members & inventory_members)
    unmatched_files = 0
    failed_files = 0
    imported_samples = 0
    created_activities = 0
    duplicate_files = 0

    for index, (metadata, content, messages, errors) in enumerate(
        _activity_fit_members(archive, inventory, completed_members), start=1
    ):
        content_hash = str(metadata["sha256"])
        fit_source_id = f"garmin-fit-{content_hash}"
        try:
            if errors:
                raise ValueError(f"FIT decoder reported {len(errors)} errors")
            session = (messages.get("session_mesgs") or [{}])[0]
            activity, _ = match_activity(session, activities, used_activity_ids)

            with connect(database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO source_files(
                        id, original_name, content_hash, media_type,
                        byte_size, stored_path
                    ) VALUES (?, ?, ?, 'application/vnd.ant.fit', ?, ?)
                    ON CONFLICT(content_hash) DO UPDATE SET
                        byte_size = excluded.byte_size,
                        stored_path = excluded.stored_path
                    """,
                    (
                        fit_source_id,
                        Path(str(metadata["member"])).name,
                        content_hash,
                        len(content),
                        f"{archive}!/{metadata['nested_archive']}!/{metadata['member']}",
                    ),
                )

            if activity is None:
                duplicate_activity, _ = match_activity(session, activities, set())
                if (
                    duplicate_activity is not None
                    and str(duplicate_activity["id"]) in used_activity_ids
                ):
                    _record_fit_status(
                        database_path=database_path,
                        archive_source_id=archive_source_id,
                        fit_source_id=fit_source_id,
                        metadata=metadata,
                        activity_id=str(duplicate_activity["id"]),
                        status="completed",
                        record_count=len(messages.get("record_mesgs") or []),
                        imported_samples=0,
                        error_message="Duplicate FIT content/path",
                    )
                    duplicate_files += 1
                    continue
                activity = _create_fit_only_activity(
                    database_path=database_path,
                    fit_source_id=fit_source_id,
                    content_hash=content_hash,
                    session=session,
                )
                activities.append(activity)
                created_activities += 1

            activity_id = str(activity["id"])
            samples = _sample_rows(
                activity_id, messages.get("record_mesgs") or []
            )
            with connect(database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.executemany(
                    """
                    INSERT INTO activity_samples(
                        activity_id, recorded_at, latitude, longitude,
                        elevation_meters, heart_rate_bpm, cadence_rpm,
                        power_watts, speed_mps
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(activity_id, recorded_at) DO UPDATE SET
                        latitude = excluded.latitude,
                        longitude = excluded.longitude,
                        elevation_meters = excluded.elevation_meters,
                        heart_rate_bpm = excluded.heart_rate_bpm,
                        cadence_rpm = excluded.cadence_rpm,
                        power_watts = excluded.power_watts,
                        speed_mps = excluded.speed_mps
                    """,
                    samples,
                )
                connection.execute(
                    "UPDATE activities SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (activity_id,),
                )
            _record_fit_status(
                database_path=database_path,
                archive_source_id=archive_source_id,
                fit_source_id=fit_source_id,
                metadata=metadata,
                activity_id=activity_id,
                status="completed",
                record_count=len(messages.get("record_mesgs") or []),
                imported_samples=len(samples),
                error_message=None,
            )
            imported_files += 1
            imported_samples += len(samples)
            used_activity_ids.add(activity_id)
        except Exception as error:
            _record_fit_status(
                database_path=database_path,
                archive_source_id=archive_source_id,
                fit_source_id=fit_source_id,
                metadata=metadata,
                activity_id=None,
                status="failed",
                record_count=len(messages.get("record_mesgs") or []),
                imported_samples=0,
                error_message=type(error).__name__,
            )
            failed_files += 1

        if index % 50 == 0:
            print(
                f"Processed {index:,}/{inventory['activity_file_count']:,} activity FIT files",
                file=sys.stderr,
                flush=True,
            )

    return {
        "status": "completed" if failed_files == 0 else "completed_with_failures",
        "activity_fit_files": int(inventory["activity_file_count"]),
        "imported_files": imported_files,
        "resumed_files": resumed_files,
        "unmatched_files": unmatched_files,
        "failed_files": failed_files,
        "imported_samples": imported_samples,
        "created_fit_only_activities": created_activities,
        "duplicate_files": duplicate_files,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Inventory nested Garmin FIT files.")
    parser.add_argument("action", choices=("inventory", "preview", "import"))
    parser.add_argument("archive", nargs="?", type=Path)
    arguments = parser.parse_args()
    if arguments.action == "inventory":
        report = build_fit_inventory(arguments.archive)
        result = {
            "status": report["status"],
            "fit_files": report["fit_files"],
            "file_types": report["file_types"],
            "activity_file_count": report.get("activity_file_count", 0),
            "activity_record_count": report.get("activity_record_count", 0),
            "decode_failure_count": report.get("decode_failure_count", 0),
            "checkpoint": str(fit_inventory_path()),
        }
    elif arguments.action == "preview":
        result = preview_fit_activity_import(arguments.archive)
    else:
        result = import_fit_activity_samples(arguments.archive)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
