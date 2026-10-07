from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from .database import connect, migrate
from .fit_import import _decode_fit, _sha256
from .garmin_import import GARMIN_SOURCE_NAME, default_archive_path, inspect_archive


IDENTITY_KEYS = {
    "deviceid",
    "ownerdisplayname",
    "ownerid",
    "primarytrainingdevice",
    "profileid",
    "serialnumber",
    "userprofileid",
    "userprofilepk",
}

METRIC_PREFIXES = {
    "ActivityVo2Max": "activity_vo2_max",
    "CyclingAbility": "cycling_ability",
    "MetricsAcuteTrainingLoad": "acute_training_load",
    "MetricsHeatAltitudeAcclimation": "heat_altitude_acclimation",
    "MetricsMaxMetData": "max_met_fitness",
    "RunRacePredictions": "race_predictions",
    "TrainingHistory": "training_history",
}

EXACT_JSON_CATEGORIES = {
    "DI_CONNECT/DI-Connect-Fitness/dohof2_gear.json": "gear",
    "DI_CONNECT/DI-Connect-Fitness/dohof2_personalRecord.json": "personal_records",
    "DI_CONNECT/DI-Connect-Fitness/dohof2_trainingPlan.json": "training_plans",
    "DI_CONNECT/DI-Connect-Fitness/dohof2_weekly_training_report.json": "weekly_training_reports",
    "DI_CONNECT/DI-Connect-Fitness/dohof2_workout.json": "workouts",
    "DI_CONNECT/DI-Connect-Routing/dohof2_courses_1790751506315.json": "courses",
    "DI_CONNECT/DI-Connect-Routing/dohof2_powerguidances_1790751507057.json": "power_guidance",
    "DI_CONNECT/DI-Connect-User/CalendarItems.json": "calendar_items",
    "DI_CONNECT/DI-Connect-User/GoalsFile.json": "goals",
    "DI_CONNECT/DI-Connect-Wellness/2923446_bioMetrics_latest.json": "biometrics_latest",
    "DI_CONNECT/DI-Connect-Wellness/2923446_fitnessAgeData.json": "fitness_age",
    "DI_CONNECT/DI-Connect-Wellness/2923446_heartRateZones.json": "heart_rate_zones",
    "DI_CONNECT/DI-Connect-Wellness/2923446_powerZones.json": "power_zones",
    "DI_CONNECT/DI-Connect-Wellness/2923446_userBioMetricProfileData.json": "biometric_profile",
    "DI_CONNECT/DI-Connect-Wellness/2923446_userBioMetrics.json": "biometrics_history",
    "DI_CONNECT/DI-GOLF/Golf-CLUB.json": "golf_clubs",
    "DI_CONNECT/DI-GOLF/Golf-CLUB_TYPES.json": "golf_club_types",
    "DI_TACX/DI-Tacx-WorkoutsExport/workouts-0.json": "tacx_workouts",
}

FIT_BACKUPS = {
    "DI_CONNECT/DI-Connect-Fitness/dohof2_AdaptiveCoachingSchedule_Part1.zip":
        "adaptive_coaching_backup",
    "DI_CONNECT/DI-Connect-Fitness/dohof2_PrimaryTrainingBackup_Part1.zip":
        "primary_training_backup",
    "DI_CONNECT/DI-Connect-Metrics/dohof2_LhaBackup_Part1.zip":
        "lha_metrics_backup",
}

TACX_XML_PREFIX = "DI_TACX/DI-Tacx-WorkoutDetailExport/"


class ExtendedArchiveImportError(ValueError):
    """Raised when an in-scope extended archive file cannot be parsed safely."""


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item)
            for key, item in value.items()
            if _normalized_key(key) not in IDENTITY_KEYS
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _category_for_json(member_name: str) -> str | None:
    if member_name in EXACT_JSON_CATEGORIES:
        return EXACT_JSON_CATEGORIES[member_name]
    name = Path(member_name).name
    if member_name.startswith("DI_CONNECT/DI-Connect-Metrics/"):
        for prefix, category in METRIC_PREFIXES.items():
            if name.startswith(prefix):
                return category
    if member_name.startswith("DI_CONNECT/DI-Connect-User/UserGoal_"):
        return "goal_history"
    return None


def _flatten_json(category: str, payload: object) -> list[tuple[str, object]]:
    root = payload[0] if isinstance(payload, list) and len(payload) == 1 else payload
    wrappers: dict[str, dict[str, str]] = {
        "gear": {
            "gearDTOS": "gear",
            "gearActivityDTOs": "gear_activity_links",
            "gearActivityTypeDTOS": "gear_activity_types",
            "gearCollections": "gear_collections",
        },
        "personal_records": {"personalRecords": "personal_records"},
        "training_plans": {
            "trainingPlans": "training_plans",
            "trainingScheduledNoteDTOS": "training_scheduled_notes",
        },
        "weekly_training_reports": {
            "weeklyTrainingReportExport": "weekly_training_reports"
        },
        "workouts": {
            "workoutList": "workouts",
            "workoutScheduleList": "workout_schedules",
        },
        "calendar_items": {
            "calendarEvents": "calendar_events",
            "calendarEventsParticipation": "calendar_event_participation",
        },
        "goals": {"goalDTOList": "goals"},
        "golf_clubs": {"data": "golf_clubs"},
        "golf_club_types": {"data": "golf_club_types"},
        "tacx_workouts": {"items": "tacx_workouts"},
    }
    mapping = wrappers.get(category)
    if mapping and isinstance(root, dict):
        output: list[tuple[str, object]] = []
        for key, record_category in mapping.items():
            value = root.get(key, [])
            if isinstance(value, dict):
                output.extend((record_category, {"key": k, "value": v}) for k, v in value.items())
            elif isinstance(value, list):
                output.extend((record_category, item) for item in value)
        return output
    if isinstance(payload, list):
        return [(category, item) for item in payload]
    return [(category, payload)]


def _record_date(value: object) -> str | None:
    candidates = (
        "calendarDate", "date", "asOfDateGmt", "timestampGmt", "timestamp",
        "updateTimestamp", "createTimestamp", "createdDate", "prStartTimeGMT",
        "dateBegin", "preparedOn",
    )
    if isinstance(value, dict):
        for key in candidates:
            candidate = value.get(key)
            if isinstance(candidate, str) and len(candidate) >= 10:
                prefix = candidate[:10]
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", prefix):
                    return prefix
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                timestamp = float(candidate)
                if timestamp > 10_000_000_000:
                    timestamp /= 1000
                try:
                    parsed = datetime.fromtimestamp(timestamp, tz=UTC)
                except (OverflowError, OSError, ValueError):
                    parsed = None
                if parsed is not None and 2000 <= parsed.year <= datetime.now(UTC).year + 1:
                    return parsed.date().isoformat()
        for item in value.values():
            found = _record_date(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _record_date(item)
            if found:
                return found
    return None


def _normalized_record(category: str, payload: object) -> dict[str, object]:
    sanitized = sanitize_payload(payload)
    canonical = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(f"{category}\n{canonical}".encode()).hexdigest()
    return {
        "id": f"garmin-archive-{fingerprint}",
        "category": category,
        "source_record_id": fingerprint,
        "record_date": _record_date(sanitized),
        "payload_json": canonical,
    }


def _parse_json_file(category: str, content: bytes) -> list[dict[str, object]]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtendedArchiveImportError("Invalid JSON content.") from error
    return [
        _normalized_record(record_category, record)
        for record_category, record in _flatten_json(category, payload)
    ]


def _parse_xml_file(category: str, content: bytes) -> list[dict[str, object]]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ExtendedArchiveImportError("Invalid XML content.") from error
    payload = {
        "root_tag": root.tag.rsplit("}", 1)[-1],
        "xml": content.decode("utf-8"),
    }
    return [_normalized_record(category, payload)]


def _parse_fit_backup(
    category: str, nested_name: str, content: bytes
) -> list[dict[str, object]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as nested:
            fit_members = [
                info for info in nested.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".fit")
            ]
            if len(fit_members) != 1:
                raise ExtendedArchiveImportError(
                    f"{nested_name} must contain exactly one FIT file."
                )
            messages, errors = _decode_fit(nested.read(fit_members[0]))
    except zipfile.BadZipFile as error:
        raise ExtendedArchiveImportError("Invalid nested FIT backup ZIP.") from error
    if errors:
        raise ExtendedArchiveImportError("FIT decoder reported errors.")
    records: list[dict[str, object]] = []
    for message_type, rows in messages.items():
        if message_type in {"file_id_mesgs", "file_creator_mesgs", "device_info_mesgs"}:
            continue
        for row in rows:
            records.append(_normalized_record(f"{category}:{message_type}", row))
    return records


def _classification(member_name: str) -> tuple[str, str, str]:
    json_category = _category_for_json(member_name)
    if json_category:
        return "imported", json_category, "Health/training JSON imported"
    if member_name in FIT_BACKUPS:
        return "imported", FIT_BACKUPS[member_name], "Training/metrics FIT backup imported"
    if member_name.startswith(TACX_XML_PREFIX) and member_name.endswith(".xml"):
        return "imported", "tacx_workout_detail", "Tacx workout detail imported"

    handled_markers = (
        "HydrationLogFile_", "UDSFile_", "summarizedActivities.json",
        "sleepData.json", "AbnormalHrEvents.json", "nutritionLogs.json",
    )
    if any(marker in member_name for marker in handled_markers):
        return "handled_elsewhere", "existing_import", "Handled by a dedicated importer"
    if member_name.startswith("DI_CONNECT/DI-Connect-Uploaded-Files/"):
        return "handled_elsewhere", "uploaded_activity_files", "FIT/GPX/TCX inventory completed"

    excluded_prefixes = (
        "DI_CONNECT/DI-Connect-Social/", "DI_CONNECT/DI-Connect-Device/",
        "DI_LIVETRACK/", "DI_MEDIA_GDPR_SERVICE/", "DI_CONNECT_IQ/",
        "DI_FACEIT_CLOUD/", "IT_CONSENT_HISTORY/", "IT_DEVICE_AND_CONTENT/",
        "IT_FORMS/", "IT_GLOBAL_EVENT/", "customer_data/",
        "DI_TACX/DI-Tacx-Device/", "DI_TACX/DI-Tacx-SubscriptionsExport/",
        "DI_TACX/DI-Tacx-User/",
    )
    excluded_user_names = {
        "dohof2-profile-image-large.jpg", "dohof2-profile-image-medium.jpg",
        "dohof2-profile-image-small.jpg", "dohof2-social-profile.json",
        "user_contact.json", "user_profile.json", "user_profile_suica.json",
        "user_reminders.json", "user_settings.json",
    }
    if member_name.startswith(excluded_prefixes) or Path(member_name).name in excluded_user_names:
        return "excluded", "private_administrative", "Account, social, device, location, or administrative data"
    if member_name.endswith(".zip"):
        return "container", "nested_archive", "Nested archive classified separately"
    return "unsupported", "unclassified", "No safe application mapping"


def _load_extended_files(archive: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    selected: list[dict[str, object]] = []
    catalog: list[dict[str, object]] = []
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            if info.is_dir():
                continue
            classification, category, reason = _classification(info.filename)
            catalog.append(
                {
                    "member_name": info.filename,
                    "category": category,
                    "classification": classification,
                    "reason": reason,
                    "byte_size": info.file_size,
                }
            )
            if classification != "imported":
                continue
            content = source.read(info)
            item: dict[str, object] = {
                "member_name": info.filename,
                "category": category,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "media_type": "application/json",
                "records": [],
                "error": None,
            }
            try:
                if info.filename in FIT_BACKUPS:
                    item["media_type"] = "application/zip"
                    item["records"] = _parse_fit_backup(category, info.filename, content)
                elif info.filename.endswith(".xml"):
                    item["media_type"] = "application/xml"
                    item["records"] = _parse_xml_file(category, content)
                else:
                    item["records"] = _parse_json_file(category, content)
            except ExtendedArchiveImportError as error:
                item["error"] = str(error)
            selected.append(item)
    return selected, catalog


def preview_extended_archive_import(archive_path: Path | None = None) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inspect_archive(archive)
    files, catalog = _load_extended_files(archive)
    categories = Counter()
    unique: set[tuple[str, str]] = set()
    dates: list[str] = []
    failures = []
    for item in files:
        if item["error"]:
            failures.append({"member_name": item["member_name"], "error": item["error"]})
        for record in item["records"]:
            categories[str(record["category"])] += 1
            unique.add((str(record["category"]), str(record["source_record_id"])))
            if record["record_date"]:
                dates.append(str(record["record_date"]))
    classifications = Counter(str(item["classification"]) for item in catalog)
    return {
        "ready": not failures and classifications["unsupported"] == 0,
        "selected_files": len(files),
        "source_records": sum(categories.values()),
        "unique_records": len(unique),
        "date_start": min(dates, default=None),
        "date_end": max(dates, default=None),
        "categories": dict(sorted(categories.items())),
        "catalog": dict(sorted(classifications.items())),
        "failures": failures,
    }


def import_extended_archive(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inspect_archive(archive)
    archive_hash = _sha256(archive)
    files, catalog = _load_extended_files(archive)
    migrate(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT id FROM source_files WHERE content_hash = ?", (archive_hash,)
        ).fetchone()
        if source is None:
            raise ExtendedArchiveImportError("Run the Garmin JSON import first.")
        archive_source_id = str(source[0])
        completed = {
            row[0]
            for row in connection.execute(
                "SELECT member_name FROM extended_archive_import_files WHERE status = 'completed'"
            )
        }
        pending = [item for item in files if item["member_name"] not in completed]
        records: dict[tuple[str, str], dict[str, object]] = {}
        for item in pending:
            if item["error"]:
                continue
            for record in item["records"]:
                records[(str(record["category"]), str(record["source_record_id"]))] = record
        existing = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT category, source_record_id FROM garmin_archive_records
                WHERE source_name = ?
                """,
                (GARMIN_SOURCE_NAME,),
            )
        }

        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            """
            INSERT INTO garmin_archive_records(
                id, source_name, source_file_id, category, source_record_id,
                record_date, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name, category, source_record_id) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                record_date = excluded.record_date,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    record["id"], GARMIN_SOURCE_NAME, archive_source_id,
                    record["category"], record["source_record_id"],
                    record["record_date"], record["payload_json"],
                )
                for record in records.values()
            ],
        )
        failed_files = 0
        for item in pending:
            failed = bool(item["error"])
            failed_files += int(failed)
            unique_count = len(
                {
                    (str(record["category"]), str(record["source_record_id"]))
                    for record in item["records"]
                }
            )
            identity = hashlib.sha256(str(item["member_name"]).encode()).hexdigest()
            connection.execute(
                """
                INSERT INTO extended_archive_import_files(
                    id, archive_source_file_id, member_name, category, content_hash,
                    media_type, status, source_record_count,
                    normalized_record_count, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(member_name) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    media_type = excluded.media_type,
                    status = excluded.status,
                    source_record_count = excluded.source_record_count,
                    normalized_record_count = excluded.normalized_record_count,
                    error_message = excluded.error_message,
                    imported_at = CURRENT_TIMESTAMP
                """,
                (
                    f"extended-archive-{identity}", archive_source_id,
                    item["member_name"], item["category"], item["content_hash"],
                    item["media_type"], "failed" if failed else "completed",
                    len(item["records"]), unique_count, item["error"],
                ),
            )
        connection.executemany(
            """
            INSERT INTO garmin_archive_file_catalog(
                member_name, category, classification, reason, byte_size
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(member_name) DO UPDATE SET
                category = excluded.category,
                classification = excluded.classification,
                reason = excluded.reason,
                byte_size = excluded.byte_size,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    item["member_name"], item["category"], item["classification"],
                    item["reason"], item["byte_size"],
                )
                for item in catalog
            ],
        )

        backfilled_dates = 0
        missing_dates = connection.execute(
            """
            SELECT id, payload_json FROM garmin_archive_records
            WHERE source_name = ? AND record_date IS NULL
            """,
            (GARMIN_SOURCE_NAME,),
        ).fetchall()
        for row in missing_dates:
            inferred_date = _record_date(json.loads(row["payload_json"]))
            if inferred_date is None:
                continue
            connection.execute(
                "UPDATE garmin_archive_records SET record_date = ? WHERE id = ?",
                (inferred_date, row["id"]),
            )
            backfilled_dates += 1

        stored = connection.execute(
            "SELECT COUNT(*) FROM garmin_archive_records WHERE source_name = ?",
            (GARMIN_SOURCE_NAME,),
        ).fetchone()[0]
    return {
        "status": "completed" if failed_files == 0 else "completed_with_failures",
        "selected_files": len(files),
        "imported_files": len(pending) - failed_files,
        "resumed_files": len(completed),
        "failed_files": failed_files,
        "created_records": len(set(records) - existing),
        "updated_records": len(set(records) & existing),
        "stored_records": stored,
        "backfilled_dates": backfilled_dates,
        "catalog": dict(Counter(str(item["classification"]) for item in catalog)),
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Import remaining Garmin archive records.")
    parser.add_argument("action", choices=("preview", "import"))
    parser.add_argument("archive", nargs="?", type=Path)
    arguments = parser.parse_args()
    result = (
        preview_extended_archive_import(arguments.archive)
        if arguments.action == "preview"
        else import_extended_archive(arguments.archive)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
