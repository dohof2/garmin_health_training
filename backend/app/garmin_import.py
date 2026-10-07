from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import stat
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from .config import data_directory
from .database import connect, migrate


GARMIN_SOURCE_NAME = "garmin_export"
DEFAULT_ARCHIVE_NAME = "Garmin data.zip"
ACTIVITY_SUFFIX = "summarizedActivities.json"
DAILY_SUMMARY_MARKER = "/DI-Connect-Aggregator/UDSFile_"
SLEEP_SUFFIX = "_sleepData.json"


class GarminImportError(ValueError):
    """Raised when an export is unsafe or does not match the expected schema."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_archive_bytes: int = 1_000_000_000
    max_entries: int = 100_000
    max_expanded_bytes: int = 1_000_000_000
    max_member_bytes: int = 128_000_000
    max_compression_ratio: float = 100.0
    max_nested_depth: int = 2


@dataclass
class _InspectionState:
    entries: int = 0
    files: int = 0
    directories: int = 0
    expanded_bytes: int = 0
    nested_archives: int = 0
    extensions: Counter[str] | None = None

    def __post_init__(self) -> None:
        if self.extensions is None:
            self.extensions = Counter()


DAILY_METRICS: dict[str, tuple[str, str]] = {
    "totalSteps": ("steps", "count"),
    "totalDistanceMeters": ("distance", "m"),
    "activeKilocalories": ("active_calories", "kcal"),
    "bmrKilocalories": ("resting_calories", "kcal"),
    "totalKilocalories": ("total_calories", "kcal"),
    "currentDayRestingHeartRate": ("resting_heart_rate", "bpm"),
    "minHeartRate": ("minimum_heart_rate", "bpm"),
    "maxHeartRate": ("maximum_heart_rate", "bpm"),
    "moderateIntensityMinutes": ("moderate_intensity", "min"),
    "vigorousIntensityMinutes": ("vigorous_intensity", "min"),
    "averageSpo2Value": ("average_spo2", "%"),
    "lowestSpo2Value": ("lowest_spo2", "%"),
}

SLEEP_DURATION_METRICS: dict[str, str] = {
    "deepSleepSeconds": "deep_sleep",
    "lightSleepSeconds": "light_sleep",
    "remSleepSeconds": "rem_sleep",
    "awakeSleepSeconds": "awake_sleep",
    "unmeasurableSeconds": "unmeasurable_sleep",
}


def default_archive_path() -> Path:
    configured = os.getenv("HT_GARMIN_ARCHIVE")
    if configured:
        return Path(configured).expanduser()

    import_directory = data_directory() / "imports"
    preferred = import_directory / DEFAULT_ARCHIVE_NAME
    if preferred.exists():
        return preferred

    archives = sorted(import_directory.glob("*.zip"))
    if len(archives) == 1:
        return archives[0]
    if not archives:
        raise FileNotFoundError(
            f"No Garmin ZIP found in {import_directory}."
        )
    raise GarminImportError(
        "More than one ZIP exists in the import directory; set "
        "HT_GARMIN_ARCHIVE to the intended Garmin export."
    )


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise GarminImportError("Archive contains an invalid member path.")
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts:
        raise GarminImportError("Archive contains an unsafe member path.")
    if member.parts and ":" in member.parts[0]:
        raise GarminImportError("Archive contains an unsafe drive-qualified path.")
    return member


def _member_ratio(info: zipfile.ZipInfo) -> float:
    if info.file_size == 0:
        return 0.0
    if info.compress_size == 0:
        return math.inf
    return info.file_size / info.compress_size


def _inspect_zip(
    archive: zipfile.ZipFile,
    limits: ArchiveLimits,
    state: _InspectionState,
    depth: int,
) -> None:
    nested_members: list[zipfile.ZipInfo] = []
    for info in archive.infolist():
        _safe_member_path(info.filename)
        state.entries += 1
        if state.entries > limits.max_entries:
            raise GarminImportError("Archive exceeds the entry-count safety limit.")
        if info.flag_bits & 0x1:
            raise GarminImportError("Encrypted archive members are not supported.")

        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise GarminImportError("Archive symbolic links are not supported.")

        if info.is_dir():
            state.directories += 1
            continue

        state.files += 1
        state.expanded_bytes += info.file_size
        if info.file_size > limits.max_member_bytes:
            raise GarminImportError("Archive member exceeds the per-file safety limit.")
        if state.expanded_bytes > limits.max_expanded_bytes:
            raise GarminImportError("Archive exceeds the expanded-size safety limit.")
        if _member_ratio(info) > limits.max_compression_ratio:
            raise GarminImportError("Archive member exceeds the compression-ratio limit.")

        member = PurePosixPath(info.filename)
        assert state.extensions is not None
        state.extensions[member.suffix.lower() or "[none]"] += 1
        if member.suffix.lower() == ".zip":
            nested_members.append(info)

    if not nested_members:
        return
    if depth >= limits.max_nested_depth:
        raise GarminImportError("Archive nesting exceeds the configured depth limit.")

    for info in nested_members:
        state.nested_archives += 1
        with archive.open(info) as nested_stream:
            nested_bytes = nested_stream.read(limits.max_member_bytes + 1)
        if len(nested_bytes) > limits.max_member_bytes:
            raise GarminImportError("Nested archive exceeds the per-file safety limit.")
        try:
            with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                _inspect_zip(nested, limits, state, depth + 1)
        except zipfile.BadZipFile as error:
            raise GarminImportError("A nested ZIP is invalid.") from error


def inspect_archive(
    archive_path: Path,
    limits: ArchiveLimits = ArchiveLimits(),
) -> dict[str, object]:
    resolved = archive_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Garmin archive not found: {resolved}")
    archive_size = resolved.stat().st_size
    if archive_size > limits.max_archive_bytes:
        raise GarminImportError("Archive exceeds the configured size limit.")

    state = _InspectionState()
    try:
        with zipfile.ZipFile(resolved) as archive:
            _inspect_zip(archive, limits, state, depth=0)
            corrupt_member = archive.testzip()
    except zipfile.BadZipFile as error:
        raise GarminImportError("The Garmin export is not a valid ZIP archive.") from error
    if corrupt_member is not None:
        raise GarminImportError("The Garmin export failed its CRC integrity check.")

    return {
        "archive_bytes": archive_size,
        "entries": state.entries,
        "files": state.files,
        "directories": state.directories,
        "expanded_bytes": state.expanded_bytes,
        "nested_archives": state.nested_archives,
        "extensions": dict(sorted((state.extensions or {}).items())),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(
    record: dict[str, object],
    key: str,
    *,
    required: bool = False,
    nonnegative: bool = True,
) -> float | None:
    raw = record.get(key)
    if raw is None:
        if required:
            raise GarminImportError(f"A Garmin record is missing required field {key}.")
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise GarminImportError(f"Garmin field {key} must be numeric.")
    value = float(raw)
    if not math.isfinite(value) or (nonnegative and value < 0):
        raise GarminImportError(f"Garmin field {key} has an invalid value.")
    return value


def _utc_iso_from_milliseconds(milliseconds: float) -> str:
    try:
        value = datetime.fromtimestamp(milliseconds / 1000, UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise GarminImportError("Garmin activity contains an invalid timestamp.") from error
    if not 2000 <= value.year <= datetime.now(UTC).year + 1:
        raise GarminImportError("Garmin activity timestamp is outside supported bounds.")
    return value.isoformat().replace("+00:00", "Z")


def _utc_iso_from_gmt_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise GarminImportError(f"Garmin sleep field {field} must be a timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GarminImportError(f"Garmin sleep field {field} is invalid.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    if not 2000 <= parsed.year <= datetime.now(UTC).year + 1:
        raise GarminImportError(f"Garmin sleep field {field} is out of bounds.")
    return parsed.isoformat().replace("+00:00", "Z")


def _record_id(value: object, label: str) -> str:
    if isinstance(value, bool) or value is None:
        raise GarminImportError(f"Garmin {label} is missing.")
    if isinstance(value, float):
        if not value.is_integer():
            raise GarminImportError(f"Garmin {label} is invalid.")
        value = int(value)
    normalized = str(value).strip()
    if not normalized or len(normalized) > 200:
        raise GarminImportError(f"Garmin {label} is invalid.")
    return normalized


def _activity_from_raw(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise GarminImportError("A summarized activity is not a JSON object.")
    source_record_id = _record_id(raw.get("activityId"), "activity ID")
    activity_type = str(raw.get("activityType") or raw.get("sportType") or "unknown")
    if len(activity_type) > 100:
        raise GarminImportError("Garmin activity type is too long.")

    start_ms = _finite_number(raw, "beginTimestamp", required=True)
    duration_ms = _finite_number(raw, "duration", required=True)
    assert start_ms is not None and duration_ms is not None
    if duration_ms > 30 * 24 * 60 * 60 * 1000:
        raise GarminImportError("Garmin activity duration exceeds supported bounds.")
    started_at = _utc_iso_from_milliseconds(start_ms)
    ended_at = (
        datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        + timedelta(milliseconds=duration_ms)
    ).isoformat().replace("+00:00", "Z")

    distance_cm = _finite_number(raw, "distance")
    calories_kj = _finite_number(raw, "calories")
    elevation_cm = _finite_number(raw, "elevationGain")
    name = raw.get("name")
    normalized_name = str(name).strip()[:500] if name not in (None, "") else None
    timezone_id = raw.get("timeZoneId")

    return {
        "id": f"garmin-activity-{source_record_id}",
        "source_record_id": source_record_id,
        "activity_type": activity_type,
        "name": normalized_name,
        "started_at": started_at,
        "ended_at": ended_at,
        "timezone": f"garmin:{timezone_id}" if timezone_id is not None else None,
        "duration_seconds": duration_ms / 1000,
        "distance_meters": distance_cm / 100 if distance_cm is not None else None,
        "calories_kcal": calories_kj / 4.184 if calories_kj is not None else None,
        "elevation_gain_meters": (
            elevation_cm / 100 if elevation_cm is not None else None
        ),
        "raw_json": json.dumps(raw, separators=(",", ":"), allow_nan=False),
    }


def _metrics_from_daily_raw(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, dict):
        raise GarminImportError("A daily summary is not a JSON object.")
    raw_date = raw.get("calendarDate")
    if not isinstance(raw_date, str):
        raise GarminImportError("A daily summary is missing calendarDate.")
    try:
        calendar_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise GarminImportError("A daily summary has an invalid calendarDate.") from error
    if not 2000 <= calendar_date.year <= date.today().year + 1:
        raise GarminImportError("A daily summary date is outside supported bounds.")

    next_date = calendar_date + timedelta(days=1)
    metrics: list[dict[str, object]] = []
    for source_field, (metric_type, unit) in DAILY_METRICS.items():
        value = _finite_number(raw, source_field)
        if value is None:
            continue
        source_record_id = f"daily:{calendar_date.isoformat()}"
        metrics.append(
            {
                "id": f"garmin-{source_record_id}-{metric_type}",
                "source_record_id": source_record_id,
                "metric_type": metric_type,
                "recorded_at": calendar_date.isoformat(),
                "value": value,
                "unit": unit,
                "period_start": calendar_date.isoformat(),
                "period_end": next_date.isoformat(),
                "raw_json": json.dumps(
                    {
                        "calendarDate": calendar_date.isoformat(),
                        "sourceField": source_field,
                        "value": value,
                    },
                    separators=(",", ":"),
                ),
            }
        )
    return metrics


def _metrics_from_sleep_raw(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, dict):
        raise GarminImportError("A sleep record is not a JSON object.")
    raw_date = raw.get("calendarDate")
    if not isinstance(raw_date, str):
        raise GarminImportError("A sleep record is missing calendarDate.")
    try:
        calendar_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise GarminImportError("A sleep record has an invalid calendarDate.") from error

    period_start = _utc_iso_from_gmt_string(
        raw.get("sleepStartTimestampGMT"), "sleepStartTimestampGMT"
    )
    period_end = _utc_iso_from_gmt_string(
        raw.get("sleepEndTimestampGMT"), "sleepEndTimestampGMT"
    )
    if period_end <= period_start:
        raise GarminImportError("A sleep record ends before it starts.")

    source_record_id = f"sleep:{calendar_date.isoformat()}"
    metrics: list[dict[str, object]] = []

    def add_metric(
        metric_type: str,
        value: float,
        unit: str,
        source_field: str,
    ) -> None:
        metrics.append(
            {
                "id": f"garmin-{source_record_id}-{metric_type}",
                "source_record_id": source_record_id,
                "metric_type": metric_type,
                "recorded_at": calendar_date.isoformat(),
                "value": value,
                "unit": unit,
                "period_start": period_start,
                "period_end": period_end,
                "raw_json": json.dumps(
                    {
                        "calendarDate": calendar_date.isoformat(),
                        "sourceField": source_field,
                        "value": value,
                    },
                    separators=(",", ":"),
                ),
            }
        )

    stage_values: list[float] = []
    for source_field, metric_type in SLEEP_DURATION_METRICS.items():
        value = _finite_number(raw, source_field)
        if value is None:
            continue
        add_metric(metric_type, value, "s", source_field)
        if source_field in {
            "deepSleepSeconds",
            "lightSleepSeconds",
            "remSleepSeconds",
        }:
            stage_values.append(value)
    if stage_values:
        add_metric("sleep_duration", sum(stage_values), "s", "calculatedSleepStages")

    for source_field, metric_type, unit in (
        ("avgSleepStress", "sleep_stress", "score"),
        ("averageRespiration", "sleep_respiration", "breaths/min"),
    ):
        value = _finite_number(raw, source_field)
        if value is not None:
            add_metric(metric_type, value, unit, source_field)

    sleep_scores = raw.get("sleepScores")
    if sleep_scores is not None:
        if not isinstance(sleep_scores, dict):
            raise GarminImportError("Garmin sleepScores must be an object.")
        score = _finite_number(sleep_scores, "overallScore")
        if score is not None:
            add_metric("sleep_score", score, "score", "sleepScores.overallScore")

    spo2_summary = raw.get("spo2SleepSummary")
    if spo2_summary is not None:
        if not isinstance(spo2_summary, dict):
            raise GarminImportError("Garmin spo2SleepSummary must be an object.")
        for source_field, metric_type, unit in (
            ("averageSPO2", "sleep_spo2_average", "%"),
            ("lowestSPO2", "sleep_spo2_lowest", "%"),
            ("averageHR", "sleep_average_heart_rate", "bpm"),
        ):
            value = _finite_number(spo2_summary, source_field)
            if value is not None:
                add_metric(
                    metric_type,
                    value,
                    unit,
                    f"spo2SleepSummary.{source_field}",
                )
    return metrics


def _load_records(
    archive_path: Path,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, int],
]:
    activities: list[dict[str, object]] = []
    daily_metrics: list[dict[str, object]] = []
    sleep_metrics: list[dict[str, object]] = []
    source_counts = {
        "activity_json_files": 0,
        "daily_json_files": 0,
        "sleep_json_files": 0,
    }

    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".json"):
                continue
            is_activity = info.filename.endswith(ACTIVITY_SUFFIX)
            is_daily = DAILY_SUMMARY_MARKER in info.filename
            is_sleep = info.filename.endswith(SLEEP_SUFFIX)
            if not is_activity and not is_daily and not is_sleep:
                continue
            if info.file_size > ArchiveLimits().max_member_bytes:
                raise GarminImportError("Target JSON exceeds the per-file safety limit.")
            try:
                with archive.open(info) as stream:
                    document = json.load(stream)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise GarminImportError("A required Garmin JSON file is invalid.") from error

            if not isinstance(document, list):
                raise GarminImportError("A required Garmin JSON root must be a list.")
            if is_activity:
                source_counts["activity_json_files"] += 1
                for wrapper in document:
                    if not isinstance(wrapper, dict):
                        raise GarminImportError("Activity export wrapper is invalid.")
                    exported = wrapper.get("summarizedActivitiesExport")
                    if not isinstance(exported, list):
                        raise GarminImportError(
                            "Activity export is missing summarizedActivitiesExport."
                        )
                    activities.extend(_activity_from_raw(item) for item in exported)
            elif is_daily:
                source_counts["daily_json_files"] += 1
                for item in document:
                    daily_metrics.extend(_metrics_from_daily_raw(item))
            else:
                source_counts["sleep_json_files"] += 1
                for item in document:
                    sleep_metrics.extend(_metrics_from_sleep_raw(item))

    if not activities:
        raise GarminImportError("No summarized activities were found in the export.")
    if not daily_metrics:
        raise GarminImportError("No supported daily metrics were found in the export.")
    activity_ids = [str(item["source_record_id"]) for item in activities]
    if len(activity_ids) != len(set(activity_ids)):
        raise GarminImportError("The export contains duplicate summarized activity IDs.")
    metric_ids = [
        str(item["id"]) for item in [*daily_metrics, *sleep_metrics]
    ]
    if len(metric_ids) != len(set(metric_ids)):
        raise GarminImportError("The export contains duplicate metric records.")
    return activities, daily_metrics, sleep_metrics, source_counts


def preview_garmin_export(
    archive_path: Path | None = None,
    limits: ArchiveLimits = ArchiveLimits(),
) -> dict[str, object]:
    path = (archive_path or default_archive_path()).expanduser().resolve()
    inspection = inspect_archive(path, limits)
    activities, daily_metrics, sleep_metrics, source_counts = _load_records(path)
    activity_dates = sorted(str(item["started_at"]) for item in activities)
    metric_dates = sorted(str(item["recorded_at"]) for item in daily_metrics)
    sleep_dates = sorted(str(item["recorded_at"]) for item in sleep_metrics)
    activity_types = Counter(str(item["activity_type"]) for item in activities)
    metric_types = Counter(str(item["metric_type"]) for item in daily_metrics)
    sleep_types = Counter(str(item["metric_type"]) for item in sleep_metrics)
    return {
        "ready": True,
        "archive": {
            "name": path.name,
            "sha256": _sha256(path),
            **inspection,
        },
        "source_files": source_counts,
        "activities": {
            "count": len(activities),
            "date_start": activity_dates[0],
            "date_end": activity_dates[-1],
            "types": dict(activity_types.most_common()),
        },
        "daily_metrics": {
            "count": len(daily_metrics),
            "date_start": metric_dates[0],
            "date_end": metric_dates[-1],
            "types": dict(sorted(metric_types.items())),
        },
        "sleep_metrics": {
            "count": len(sleep_metrics),
            "date_start": sleep_dates[0] if sleep_dates else None,
            "date_end": sleep_dates[-1] if sleep_dates else None,
            "types": dict(sorted(sleep_types.items())),
        },
    }


def import_garmin_export(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    path = (archive_path or default_archive_path()).expanduser().resolve()
    preview = preview_garmin_export(path)
    activities, daily_metrics, sleep_metrics, _ = _load_records(path)
    metrics = [*daily_metrics, *sleep_metrics]
    archive_hash = str(preview["archive"]["sha256"])
    source_file_id = f"garmin-export-{archive_hash}"

    migrate(database_path)
    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_activities = {
            row[0]
            for row in connection.execute(
                "SELECT source_record_id FROM activities WHERE source_name = ?",
                (GARMIN_SOURCE_NAME,),
            )
        }
        existing_metrics = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT source_record_id, metric_type
                FROM metric_readings
                WHERE source_name = ?
                """,
                (GARMIN_SOURCE_NAME,),
            )
        }
        connection.execute(
            """
            INSERT INTO source_files(
                id, original_name, content_hash, media_type, byte_size, stored_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                original_name = excluded.original_name,
                byte_size = excluded.byte_size,
                stored_path = excluded.stored_path
            """,
            (
                source_file_id,
                path.name,
                archive_hash,
                "application/zip",
                path.stat().st_size,
                str(path),
            ),
        )

        for activity in activities:
            connection.execute(
                """
                INSERT INTO activities(
                    id, source_name, source_record_id, source_file_id,
                    activity_type, name, started_at, ended_at, timezone,
                    duration_seconds, distance_meters, calories_kcal,
                    elevation_gain_meters, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name, source_record_id) DO UPDATE SET
                    source_file_id = excluded.source_file_id,
                    activity_type = excluded.activity_type,
                    name = excluded.name,
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at,
                    timezone = excluded.timezone,
                    duration_seconds = excluded.duration_seconds,
                    distance_meters = excluded.distance_meters,
                    calories_kcal = excluded.calories_kcal,
                    elevation_gain_meters = excluded.elevation_gain_meters,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    activity["id"],
                    GARMIN_SOURCE_NAME,
                    activity["source_record_id"],
                    source_file_id,
                    activity["activity_type"],
                    activity["name"],
                    activity["started_at"],
                    activity["ended_at"],
                    activity["timezone"],
                    activity["duration_seconds"],
                    activity["distance_meters"],
                    activity["calories_kcal"],
                    activity["elevation_gain_meters"],
                    activity["raw_json"],
                ),
            )

        for metric in metrics:
            connection.execute(
                """
                INSERT INTO metric_readings(
                    id, source_name, source_record_id, source_file_id,
                    metric_type, recorded_at, value, unit,
                    period_start, period_end, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name, source_record_id, metric_type) DO UPDATE SET
                    source_file_id = excluded.source_file_id,
                    recorded_at = excluded.recorded_at,
                    value = excluded.value,
                    unit = excluded.unit,
                    period_start = excluded.period_start,
                    period_end = excluded.period_end,
                    raw_json = excluded.raw_json
                """,
                (
                    metric["id"],
                    GARMIN_SOURCE_NAME,
                    metric["source_record_id"],
                    source_file_id,
                    metric["metric_type"],
                    metric["recorded_at"],
                    metric["value"],
                    metric["unit"],
                    metric["period_start"],
                    metric["period_end"],
                    metric["raw_json"],
                ),
            )

    activity_keys = {str(item["source_record_id"]) for item in activities}
    daily_keys = {
        (str(item["source_record_id"]), str(item["metric_type"]))
        for item in daily_metrics
    }
    sleep_keys = {
        (str(item["source_record_id"]), str(item["metric_type"]))
        for item in sleep_metrics
    }
    return {
        "status": "completed",
        "archive_sha256": archive_hash,
        "activities": {
            "total": len(activity_keys),
            "created": len(activity_keys - existing_activities),
            "updated": len(activity_keys & existing_activities),
        },
        "daily_metrics": {
            "total": len(daily_keys),
            "created": len(daily_keys - existing_metrics),
            "updated": len(daily_keys & existing_metrics),
        },
        "sleep_metrics": {
            "total": len(sleep_keys),
            "created": len(sleep_keys - existing_metrics),
            "updated": len(sleep_keys & existing_metrics),
        },
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Preview or import a Garmin export.")
    parser.add_argument("action", choices=("preview", "import"))
    parser.add_argument("archive", nargs="?", type=Path)
    arguments = parser.parse_args()
    result = (
        preview_garmin_export(arguments.archive)
        if arguments.action == "preview"
        else import_garmin_export(arguments.archive)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
