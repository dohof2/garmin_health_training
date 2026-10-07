from __future__ import annotations

import argparse
import hashlib
import json
import math
import uuid
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from .database import connect, migrate
from .fit_import import _sha256
from .garmin_import import GARMIN_SOURCE_NAME, default_archive_path, inspect_archive


HYDRATION_MARKER = "HydrationLogFile_"
ABNORMAL_HR_SUFFIX = "_AbnormalHrEvents.json"
NUTRITION_SUFFIX = "_nutritionLogs.json"


class WellnessImportError(ValueError):
    """Raised when a selected wellness JSON file has an invalid schema."""


def _calendar_date(value: object) -> str:
    if not isinstance(value, str):
        raise WellnessImportError("Record is missing calendarDate.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise WellnessImportError("Record has an invalid calendarDate.") from error
    if not 2000 <= parsed.year <= datetime.now(UTC).year + 1:
        raise WellnessImportError("Record calendarDate is outside supported bounds.")
    return parsed.isoformat()


def _timestamp(value: object, field: str, *, utc: bool) -> str:
    if not isinstance(value, str):
        raise WellnessImportError(f"Record is missing {field}.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WellnessImportError(f"Record has an invalid {field}.") from error
    if not 2000 <= parsed.year <= datetime.now(UTC).year + 1:
        raise WellnessImportError(f"Record {field} is outside supported bounds.")
    if utc:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        else:
            parsed = parsed.astimezone(UTC)
        return parsed.isoformat().replace("+00:00", "Z")
    return parsed.isoformat()


def _number(
    record: dict[str, object],
    field: str,
    *,
    required: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    value = record.get(field)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WellnessImportError(f"Record has an invalid {field}.")
    number = float(value)
    if not math.isfinite(number):
        raise WellnessImportError(f"Record has a non-finite {field}.")
    if minimum is not None and number < minimum:
        raise WellnessImportError(f"Record {field} is below the supported range.")
    if maximum is not None and number > maximum:
        raise WellnessImportError(f"Record {field} exceeds the supported range.")
    return number


def _fingerprint(category: str, values: dict[str, object]) -> str:
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{category}\n{canonical}".encode()).hexdigest()


def _parse_hydration(record: object) -> dict[str, object]:
    if not isinstance(record, dict):
        raise WellnessImportError("Hydration entry is not an object.")
    calendar_date = _calendar_date(record.get("calendarDate"))
    recorded_at = _timestamp(
        record.get("persistedTimestampGMT"), "persistedTimestampGMT", utc=True
    )
    local_recorded_at = _timestamp(
        record.get("timestampLocal"), "timestampLocal", utc=False
    )
    source = record.get("hydrationSource")
    if not isinstance(source, str) or not source or len(source) > 64:
        raise WellnessImportError("Hydration entry has an invalid source.")
    value_ml = _number(
        record, "valueInML", required=True, minimum=-10_000, maximum=50_000
    )
    estimated = _number(
        record, "estimatedSweatLossInML", minimum=0, maximum=50_000
    )
    measured = _number(
        record, "measuredSweatLossInML", minimum=0, maximum=50_000
    )
    duration = _number(record, "duration", minimum=0, maximum=604_800)
    capped = record.get("capped")
    if not isinstance(capped, bool):
        raise WellnessImportError("Hydration entry has an invalid capped flag.")
    activity_id = record.get("activityId")
    if activity_id is not None and (
        isinstance(activity_id, bool) or not isinstance(activity_id, (int, str))
    ):
        raise WellnessImportError("Hydration entry has an invalid activityId.")

    semantic = {
        "calendar_date": calendar_date,
        "recorded_at": recorded_at,
        "local_recorded_at": local_recorded_at,
        "hydration_source": source,
        "value_ml": value_ml,
        "estimated_sweat_loss_ml": estimated,
        "measured_sweat_loss_ml": measured,
        "duration_seconds": duration,
        "activity_source_record_id": str(activity_id) if activity_id is not None else None,
        "capped": int(capped),
    }
    exported_uuid = record.get("uuid")
    uuid_value = exported_uuid.get("uuid") if isinstance(exported_uuid, dict) else None
    if isinstance(uuid_value, str):
        try:
            source_record_id = str(uuid.UUID(uuid_value))
        except ValueError as error:
            raise WellnessImportError("Hydration entry has an invalid UUID.") from error
    else:
        source_record_id = _fingerprint("hydration", semantic)
    return {
        "id": f"garmin-hydration-{hashlib.sha256(source_record_id.encode()).hexdigest()}",
        "source_record_id": source_record_id,
        **semantic,
    }


def _parse_abnormal_hr(record: object) -> dict[str, object]:
    if not isinstance(record, dict):
        raise WellnessImportError("Abnormal-heart-rate entry is not an object.")
    calendar_date = _calendar_date(record.get("calendarDate"))
    recorded_at = _timestamp(
        record.get("abnormalHrEventGMT"), "abnormalHrEventGMT", utc=True
    )
    heart_rate = _number(
        record, "abnormalHrValue", required=True, minimum=20, maximum=300
    )
    threshold = _number(
        record, "abnormalHrThresholdValue", required=True, minimum=20, maximum=300
    )
    semantic = {
        "calendar_date": calendar_date,
        "recorded_at": recorded_at,
        "heart_rate_bpm": int(heart_rate),
        "threshold_bpm": int(threshold),
    }
    source_record_id = _fingerprint("abnormal_hr", semantic)
    return {
        "id": f"garmin-abnormal-hr-{source_record_id}",
        "source_record_id": source_record_id,
        **semantic,
    }


def _parse_nutrition(record: object) -> dict[str, object]:
    if not isinstance(record, dict):
        raise WellnessImportError("Nutrition entry is not an object.")
    calendar_date = _calendar_date(record.get("calendarDate"))
    values = record.get("mfpCalorie")
    if not isinstance(values, dict):
        raise WellnessImportError("Nutrition entry is missing mfpCalorie.")
    calories = _number(values, "calorie", minimum=0, maximum=100_000)
    goal = _number(values, "calorieGoal", minimum=0, maximum=100_000)
    if calories is None and goal is None:
        raise WellnessImportError("Nutrition entry has no supported calorie values.")
    source_record_id = f"nutrition:{calendar_date}"
    return {
        "id": f"garmin-nutrition-{calendar_date}",
        "source_record_id": source_record_id,
        "calendar_date": calendar_date,
        "calories_consumed": calories,
        "calorie_goal": goal,
    }


def _selected_category(member_name: str) -> str | None:
    name = Path(member_name).name
    if HYDRATION_MARKER in name and name.endswith(".json"):
        return "hydration"
    if name.endswith(ABNORMAL_HR_SUFFIX):
        return "abnormal_hr"
    if name.endswith(NUTRITION_SUFFIX):
        return "nutrition"
    return None


def _load_selected_files(archive: Path) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            category = _selected_category(info.filename)
            if info.is_dir() or category is None:
                continue
            content = source.read(info)
            metadata: dict[str, object] = {
                "member_name": info.filename,
                "category": category,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "source_record_count": 0,
                "records": [],
                "error": None,
            }
            try:
                payload = json.loads(content)
                if not isinstance(payload, list):
                    raise WellnessImportError("Selected JSON file is not an array.")
                parser = {
                    "hydration": _parse_hydration,
                    "abnormal_hr": _parse_abnormal_hr,
                    "nutrition": _parse_nutrition,
                }[category]
                records = [parser(record) for record in payload]
                metadata["source_record_count"] = len(payload)
                metadata["records"] = records
            except (UnicodeDecodeError, json.JSONDecodeError, WellnessImportError) as error:
                metadata["error"] = str(error)
            selected.append(metadata)
    if not selected:
        raise WellnessImportError(
            "No hydration, abnormal-heart-rate, or nutrition files found."
        )
    return selected


def preview_wellness_import(archive_path: Path | None = None) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inspect_archive(archive)
    files = _load_selected_files(archive)
    counts = Counter()
    unique: dict[str, set[str]] = {
        "hydration": set(),
        "abnormal_hr": set(),
        "nutrition": set(),
    }
    dates: dict[str, list[str]] = {
        "hydration": [],
        "abnormal_hr": [],
        "nutrition": [],
    }
    failures = []
    for item in files:
        category = str(item["category"])
        counts[category] += int(item["source_record_count"])
        if item["error"]:
            failures.append(
                {"member_name": item["member_name"], "error": item["error"]}
            )
        for record in item["records"]:
            unique[category].add(str(record["source_record_id"]))
            dates[category].append(str(record["calendar_date"]))
    return {
        "ready": not failures,
        "archive": archive.name,
        "files": len(files),
        "hydration": {
            "files": sum(item["category"] == "hydration" for item in files),
            "source_records": counts["hydration"],
            "unique_records": len(unique["hydration"]),
            "duplicates": counts["hydration"] - len(unique["hydration"]),
            "date_start": min(dates["hydration"], default=None),
            "date_end": max(dates["hydration"], default=None),
        },
        "abnormal_heart_rate": {
            "files": sum(item["category"] == "abnormal_hr" for item in files),
            "source_records": counts["abnormal_hr"],
            "unique_records": len(unique["abnormal_hr"]),
            "duplicates": counts["abnormal_hr"] - len(unique["abnormal_hr"]),
            "date_start": min(dates["abnormal_hr"], default=None),
            "date_end": max(dates["abnormal_hr"], default=None),
        },
        "nutrition": {
            "files": sum(item["category"] == "nutrition" for item in files),
            "source_records": counts["nutrition"],
            "unique_records": len(unique["nutrition"]),
            "duplicates": counts["nutrition"] - len(unique["nutrition"]),
            "date_start": min(dates["nutrition"], default=None),
            "date_end": max(dates["nutrition"], default=None),
        },
        "failures": failures,
    }


def import_wellness_records(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inspect_archive(archive)
    archive_hash = _sha256(archive)
    files = _load_selected_files(archive)
    migrate(database_path)

    all_hydration: dict[str, dict[str, object]] = {}
    all_abnormal_hr: dict[str, dict[str, object]] = {}
    all_nutrition: dict[str, dict[str, object]] = {}
    for item in files:
        if item["error"]:
            continue
        target = {
            "hydration": all_hydration,
            "abnormal_hr": all_abnormal_hr,
            "nutrition": all_nutrition,
        }[str(item["category"])]
        for record in item["records"]:
            target[str(record["source_record_id"])] = record

    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT id FROM source_files WHERE content_hash = ?", (archive_hash,)
        ).fetchone()
        if source is None:
            raise WellnessImportError("Run the Garmin JSON import before wellness import.")
        archive_source_id = str(source[0])
        completed = {
            row[0]
            for row in connection.execute(
                "SELECT member_name FROM wellness_json_import_files WHERE status = 'completed'"
            )
        }

        pending = [item for item in files if item["member_name"] not in completed]
        hydration: dict[str, dict[str, object]] = {}
        abnormal_hr: dict[str, dict[str, object]] = {}
        nutrition: dict[str, dict[str, object]] = {}
        failed_files = 0
        for item in pending:
            if item["error"]:
                failed_files += 1
                continue
            target = {
                "hydration": hydration,
                "abnormal_hr": abnormal_hr,
                "nutrition": nutrition,
            }[str(item["category"])]
            for record in item["records"]:
                target[str(record["source_record_id"])] = record

        existing_hydration = {
            row[0]
            for row in connection.execute(
                "SELECT source_record_id FROM hydration_events WHERE source_name = ?",
                (GARMIN_SOURCE_NAME,),
            )
        }
        existing_abnormal = {
            row[0]
            for row in connection.execute(
                """
                SELECT source_record_id FROM abnormal_heart_rate_events
                WHERE source_name = ?
                """,
                (GARMIN_SOURCE_NAME,),
            )
        }
        existing_nutrition = {
            row[0]
            for row in connection.execute(
                """
                SELECT source_record_id FROM garmin_nutrition_daily
                WHERE source_name = ?
                """,
                (GARMIN_SOURCE_NAME,),
            )
        }

        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            """
            INSERT INTO hydration_events(
                id, source_name, source_file_id, source_record_id, calendar_date,
                recorded_at, local_recorded_at, hydration_source, value_ml,
                estimated_sweat_loss_ml, measured_sweat_loss_ml, duration_seconds,
                activity_source_record_id, capped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name, source_record_id) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                calendar_date = excluded.calendar_date,
                recorded_at = excluded.recorded_at,
                local_recorded_at = excluded.local_recorded_at,
                hydration_source = excluded.hydration_source,
                value_ml = excluded.value_ml,
                estimated_sweat_loss_ml = excluded.estimated_sweat_loss_ml,
                measured_sweat_loss_ml = excluded.measured_sweat_loss_ml,
                duration_seconds = excluded.duration_seconds,
                activity_source_record_id = excluded.activity_source_record_id,
                capped = excluded.capped,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    record["id"], GARMIN_SOURCE_NAME, archive_source_id,
                    record["source_record_id"], record["calendar_date"],
                    record["recorded_at"], record["local_recorded_at"],
                    record["hydration_source"], record["value_ml"],
                    record["estimated_sweat_loss_ml"], record["measured_sweat_loss_ml"],
                    record["duration_seconds"], record["activity_source_record_id"],
                    record["capped"],
                )
                for record in hydration.values()
            ],
        )
        connection.executemany(
            """
            INSERT INTO garmin_nutrition_daily(
                id, source_name, source_file_id, source_record_id,
                calendar_date, calories_consumed, calorie_goal
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name, source_record_id) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                calendar_date = excluded.calendar_date,
                calories_consumed = excluded.calories_consumed,
                calorie_goal = excluded.calorie_goal,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    record["id"], GARMIN_SOURCE_NAME, archive_source_id,
                    record["source_record_id"], record["calendar_date"],
                    record["calories_consumed"], record["calorie_goal"],
                )
                for record in nutrition.values()
            ],
        )
        connection.executemany(
            """
            INSERT INTO abnormal_heart_rate_events(
                id, source_name, source_file_id, source_record_id, calendar_date,
                recorded_at, heart_rate_bpm, threshold_bpm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name, source_record_id) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                calendar_date = excluded.calendar_date,
                recorded_at = excluded.recorded_at,
                heart_rate_bpm = excluded.heart_rate_bpm,
                threshold_bpm = excluded.threshold_bpm,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    record["id"], GARMIN_SOURCE_NAME, archive_source_id,
                    record["source_record_id"], record["calendar_date"],
                    record["recorded_at"], record["heart_rate_bpm"],
                    record["threshold_bpm"],
                )
                for record in abnormal_hr.values()
            ],
        )
        for item in pending:
            status = "failed" if item["error"] else "completed"
            normalized_count = (
                0
                if item["error"]
                else len(
                    {
                        str(record["source_record_id"])
                        for record in item["records"]
                    }
                )
            )
            identity = hashlib.sha256(str(item["member_name"]).encode()).hexdigest()
            connection.execute(
                """
                INSERT INTO wellness_json_import_files(
                    id, archive_source_file_id, member_name, category,
                    content_hash, status, source_record_count,
                    normalized_record_count, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(member_name) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    source_record_count = excluded.source_record_count,
                    normalized_record_count = excluded.normalized_record_count,
                    error_message = excluded.error_message,
                    imported_at = CURRENT_TIMESTAMP
                """,
                (
                    f"wellness-json-{identity}", archive_source_id,
                    item["member_name"], item["category"], item["content_hash"],
                    status, item["source_record_count"], normalized_count,
                    item["error"],
                ),
            )

    return {
        "status": "completed" if failed_files == 0 else "completed_with_failures",
        "files": len(files),
        "imported_files": len(pending) - failed_files,
        "resumed_files": len(completed),
        "failed_files": failed_files,
        "hydration": {
            "total": len(all_hydration),
            "created": len(set(hydration) - existing_hydration),
            "updated": len(set(hydration) & existing_hydration),
        },
        "abnormal_heart_rate": {
            "total": len(all_abnormal_hr),
            "created": len(set(abnormal_hr) - existing_abnormal),
            "updated": len(set(abnormal_hr) & existing_abnormal),
        },
        "nutrition": {
            "total": len(all_nutrition),
            "created": len(set(nutrition) - existing_nutrition),
            "updated": len(set(nutrition) & existing_nutrition),
        },
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Preview or import Garmin wellness JSON.")
    parser.add_argument("action", choices=("preview", "import"))
    parser.add_argument("archive", nargs="?", type=Path)
    arguments = parser.parse_args()
    result = (
        preview_wellness_import(arguments.archive)
        if arguments.action == "preview"
        else import_wellness_records(arguments.archive)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
