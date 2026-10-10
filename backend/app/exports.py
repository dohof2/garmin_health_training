from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from .config import data_directory, database_path
from .database import connect, migrate


EXPORT_SCHEMA_VERSION = 1
BACKUP_FORMAT = "garmin-health-training-backup"
MAX_BACKUP_FILES = 100_000
MAX_BACKUP_EXPANDED_BYTES = 20 * 1024 * 1024 * 1024

CSV_DATASETS: dict[str, tuple[str, str]] = {
    "activities": (
        """
        SELECT id, source_name, source_record_id, activity_type, name,
               started_at, ended_at, timezone, duration_seconds,
               distance_meters, calories_kcal, elevation_gain_meters,
               source_updated_at, deleted_at, created_at, updated_at
        FROM activities
        """,
        "started_at",
    ),
    "metrics": (
        """
        SELECT id, source_name, source_record_id, metric_type, recorded_at,
               value, unit, period_start, period_end, created_at
        FROM metric_readings
        """,
        "recorded_at",
    ),
    "training": (
        """
        SELECT id, training_plan_id, sport, title, scheduled_for,
               definition_json, garmin_workout_id, publish_status,
               revision, completion_status, created_at, updated_at
        FROM planned_workouts
        """,
        "scheduled_for",
    ),
    "nutrition": (
        """
        SELECT id, source_name, source_record_id, calendar_date,
               calories_consumed, calorie_goal, created_at, updated_at
        FROM garmin_nutrition_daily
        """,
        "calendar_date",
    ),
    "meals": (
        """SELECT i.rowid AS rowid,m.id AS meal_id,m.eaten_at,m.meal_type,m.notes,m.revision,m.deleted_at,
                  i.name,i.quantity,i.unit,i.calories_kcal,i.protein_grams,i.fat_grams,
                  i.carbohydrate_grams,i.source,i.detail_json
           FROM meals m JOIN meal_items i ON i.meal_id=m.id""",
        "eaten_at",
    ),
}

PORTABLE_TABLES = (
    "meal_revisions",
    "food_library",
    "food_library_revisions",
    "nutrition_day_targets",
    "training_preferences",
    "training_preference_revisions",
    "training_workout_revisions",
    "training_feedback",
    "readiness_configs",
    "readiness_settings",
    "readiness_calculations",
    "activities",
    "activity_samples",
    "activity_metrics",
    "garmin_sync_payloads",
    "metric_readings",
    "health_samples",
    "hydration_events",
    "abnormal_heart_rate_events",
    "garmin_nutrition_daily",
    "garmin_archive_records",
    "user_profile",
    "goals",
    "dashboard_cards",
    "training_plans",
    "planned_workouts",
    "nutrition_targets",
    "meals",
    "meal_items",
    "equipment",
    "maintenance_events",
    "maintenance_event_revisions",
)

TABLE_DATE_COLUMNS = {
    "nutrition_day_targets": "calendar_date",
    "readiness_calculations": "calendar_date",
    "garmin_sync_payloads": "calendar_date",
    "activities": "started_at",
    "activity_samples": "recorded_at",
    "metric_readings": "recorded_at",
    "health_samples": "recorded_at",
    "hydration_events": "calendar_date",
    "abnormal_heart_rate_events": "calendar_date",
    "garmin_nutrition_daily": "calendar_date",
    "garmin_archive_records": "record_date",
    "goals": "target_date",
    "training_plans": "starts_on",
    "planned_workouts": "scheduled_for",
    "nutrition_targets": "effective_from",
    "meals": "eaten_at",
    "maintenance_events": "event_date",
}


class ExportError(ValueError):
    pass


def _validate_range(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and start_date > end_date:
        raise ExportError("The start date must be on or before the end date")


def _dated_query(
    base_query: str,
    date_column: str | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[str, tuple[str, ...]]:
    filters: list[str] = []
    values: list[str] = []
    if date_column and start_date:
        filters.append(f"date({date_column}) >= date(?)")
        values.append(start_date.isoformat())
    if date_column and end_date:
        filters.append(f"date({date_column}) <= date(?)")
        values.append(end_date.isoformat())
    query = base_query.strip()
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += f" ORDER BY {date_column or 'rowid'}, rowid"
    return query, tuple(values)


def _spreadsheet_safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(
    dataset: str,
    output_path: Path,
    start_date: date | None = None,
    end_date: date | None = None,
    path: Path | None = None,
) -> dict[str, object]:
    """Write one allow-listed, date-filtered dataset as UTF-8 CSV."""
    _validate_range(start_date, end_date)
    if dataset not in CSV_DATASETS:
        raise ExportError(f"Unknown CSV dataset: {dataset}")
    base_query, date_column = CSV_DATASETS[dataset]
    query, values = _dated_query(base_query, date_column, start_date, end_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(path) as connection, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as output:
        cursor = connection.execute(query, values)
        fieldnames = [item[0] for item in cursor.description]
        writer = csv.writer(output)
        writer.writerow(fieldnames)
        count = 0
        for row in cursor:
            writer.writerow([_spreadsheet_safe(value) for value in row])
            count += 1
    return {
        "dataset": dataset,
        "records": count,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "path": str(output_path),
    }


def export_json(
    output_path: Path,
    start_date: date | None = None,
    end_date: date | None = None,
    path: Path | None = None,
) -> dict[str, object]:
    """Stream a versioned portable JSON document without loading it into memory."""
    _validate_range(start_date, end_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    metadata = {
        "format": "garmin-health-training-portable-json",
        "schema_version": EXPORT_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "date_range": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        },
    }

    with connect(path) as connection, output_path.open("w", encoding="utf-8") as output:
        output.write("{\n  \"metadata\": ")
        json.dump(metadata, output, ensure_ascii=False, separators=(",", ":"))
        output.write(",\n  \"tables\": {")
        for table_index, table in enumerate(PORTABLE_TABLES):
            if table_index:
                output.write(",")
            output.write(f"\n    {json.dumps(table)}: [")
            query, values = _dated_query(
                f"SELECT * FROM {table}",
                TABLE_DATE_COLUMNS.get(table),
                start_date,
                end_date,
            )
            if table in ("activity_metrics", "training_feedback", "training_workout_revisions", "meal_items", "meal_revisions") and (start_date or end_date):
                meal_child=table in ("meal_items", "meal_revisions")
                parent = "meals" if meal_child else "activities" if table == "activity_metrics" else "planned_workouts"
                date_column = "eaten_at" if meal_child else "started_at" if table == "activity_metrics" else "scheduled_for"
                child_column = "meal_id" if meal_child else "activity_id" if table == "activity_metrics" else "workout_id"
                parent_query, values = _dated_query(
                    f"SELECT id FROM {parent}", date_column, start_date, end_date
                )
                query = (
                    f"SELECT * FROM {table} WHERE {child_column} IN ("
                    + parent_query + ") ORDER BY rowid"
                )
            count = 0
            for row in connection.execute(query, values):
                if count:
                    output.write(",")
                output.write("\n      ")
                json.dump(dict(row), output, ensure_ascii=False, separators=(",", ":"))
                count += 1
            if count:
                output.write("\n    ")
            output.write("]")
            counts[table] = count
        output.write("\n  }\n}\n")
    return {"schema_version": EXPORT_SCHEMA_VERSION, "tables": counts, "path": str(output_path)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).name).strip("-.")
    return cleaned or "source-file"


def _database_snapshot(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source)) as source_connection, closing(
        sqlite3.connect(destination)
    ) as destination_connection:
        source_connection.backup(destination_connection)


def _backup_source_paths(path: Path | None) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    with connect(path) as connection:
        for row in connection.execute(
            "SELECT stored_path FROM source_files WHERE stored_path IS NOT NULL ORDER BY id"
        ):
            stored = str(row[0]).split("!/", 1)[0]
            candidate = Path(stored).expanduser().resolve()
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                files.append(candidate)
    return files


def original_activity_inventory(path: Path | None = None) -> dict[str, object]:
    """Describe preserved FIT/TCX/GPX sources without exposing filesystem paths."""
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT sf.id, sf.original_name, sf.media_type, sf.byte_size,
                            sf.content_hash, sf.stored_path
            FROM source_files AS sf
            JOIN (
                SELECT fit_source_file_id AS source_file_id
                FROM fit_import_files WHERE status = 'completed'
                UNION
                SELECT detail_source_file_id AS source_file_id
                FROM xml_activity_import_files WHERE status = 'completed'
            ) AS activity_sources ON activity_sources.source_file_id = sf.id
            WHERE sf.stored_path IS NOT NULL
            ORDER BY sf.original_name, sf.id
            """
        ).fetchall()
    formats: dict[str, int] = {}
    total_bytes = 0
    for row in rows:
        suffix = Path(str(row["original_name"])).suffix.lower().lstrip(".") or "other"
        formats[suffix] = formats.get(suffix, 0) + 1
        total_bytes += int(row["byte_size"])
    return {
        "files": len(rows),
        "bytes": total_bytes,
        "formats": dict(sorted(formats.items())),
        "available": bool(rows),
    }


def _original_activity_rows(path: Path | None) -> list[sqlite3.Row]:
    with connect(path) as connection:
        return connection.execute(
            """
            SELECT DISTINCT sf.id, sf.original_name, sf.content_hash, sf.stored_path
            FROM source_files AS sf
            JOIN (
                SELECT fit_source_file_id AS source_file_id
                FROM fit_import_files WHERE status = 'completed'
                UNION
                SELECT detail_source_file_id AS source_file_id
                FROM xml_activity_import_files WHERE status = 'completed'
            ) AS activity_sources ON activity_sources.source_file_id = sf.id
            WHERE sf.stored_path IS NOT NULL
            ORDER BY sf.id
            """
        ).fetchall()


def _read_nested_source(stored_path: str) -> bytes:
    parts = stored_path.split("!/")
    outer = Path(parts[0]).expanduser().resolve()
    if not outer.is_file():
        raise ExportError("An original activity source is no longer available")
    if len(parts) == 1:
        return outer.read_bytes()
    content: bytes | None = None
    with zipfile.ZipFile(outer) as archive:
        content = archive.read(parts[1])
    for member in parts[2:]:
        with zipfile.ZipFile(io.BytesIO(content)) as nested:
            content = nested.read(member)
    return content


def create_original_activity_bundle(
    output_path: Path,
    path: Path | None = None,
) -> dict[str, object]:
    """Package preserved activity FIT/TCX/GPX bytes without inventing new files."""
    rows = _original_activity_rows(path)
    if not rows:
        raise ExportError("No preserved original activity files are available")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, row in enumerate(rows, start=1):
            content = _read_nested_source(str(row["stored_path"]))
            if hashlib.sha256(content).hexdigest() != row["content_hash"]:
                raise ExportError("An original activity file failed its checksum check")
            name = _safe_name(str(row["original_name"]))
            archive.writestr(f"activity-files/{index:05d}-{name}", content)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "garmin-health-training-original-activity-files",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "file_count": len(rows),
                    "note": "Preserved source bytes; no FIT, TCX, or GPX files were generated.",
                },
                indent=2,
            )
            + "\n",
        )
    return {"files": len(rows), "path": str(output_path), "byte_size": output_path.stat().st_size}


def create_backup(
    output_path: Path,
    path: Path | None = None,
    *,
    include_originals: bool = False,
) -> dict[str, object]:
    """Create a ZIP containing a consistent database snapshot and optional originals."""
    source_database = (path or database_path()).resolve()
    if not source_database.is_file():
        raise ExportError("The application database does not exist")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="health-training-backup-") as temporary:
        snapshot = Path(temporary) / "database.sqlite3"
        _database_snapshot(source_database, snapshot)
        with closing(sqlite3.connect(snapshot)) as connection:
            connection.row_factory = sqlite3.Row
            migrations = [
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            table_counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in PORTABLE_TABLES
            }

        originals = _backup_source_paths(path) if include_originals else []
        manifest = {
            "format": BACKUP_FORMAT,
            "schema_version": EXPORT_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                "path": "database.sqlite3",
                "sha256": _sha256(snapshot),
                "migrations": migrations,
                "table_counts": table_counts,
            },
            "originals": {
                "included": include_originals,
                "count": len(originals),
            },
            "excluded": ["credentials", "session_tokens", "environment_files"],
        }
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "database.sqlite3")
            for index, original in enumerate(originals, start=1):
                archive.write(original, f"originals/{index:04d}-{_safe_name(original.name)}")
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
    return {**manifest, "path": str(output_path), "byte_size": output_path.stat().st_size}


def _validate_zip_members(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_BACKUP_FILES:
        raise ExportError("Backup contains too many files")
    if sum(info.file_size for info in infos) > MAX_BACKUP_EXPANDED_BYTES:
        raise ExportError("Backup expands beyond the allowed size")
    for info in infos:
        member = PurePosixPath(info.filename)
        if member.is_absolute() or ".." in member.parts or info.filename.startswith(("/", "\\")):
            raise ExportError("Backup contains an unsafe path")
        if info.flag_bits & 0x1:
            raise ExportError("Encrypted backups are not supported")


def preview_restore(backup_path: Path) -> dict[str, object]:
    """Validate a backup without extracting it or changing application data."""
    try:
        with tempfile.TemporaryDirectory(prefix="health-training-restore-preview-") as temporary:
            candidate = Path(temporary) / "database.sqlite3"
            with zipfile.ZipFile(backup_path) as archive:
                _validate_zip_members(archive)
                names = set(archive.namelist())
                if not {"manifest.json", "database.sqlite3"}.issubset(names):
                    raise ExportError("Backup is missing its manifest or database")
                try:
                    manifest = json.loads(archive.read("manifest.json"))
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise ExportError("Backup manifest is invalid") from error
                if manifest.get("format") != BACKUP_FORMAT:
                    raise ExportError("This is not a Garmin Health & Training backup")
                if manifest.get("schema_version") != EXPORT_SCHEMA_VERSION:
                    raise ExportError("Backup schema version is not supported")
                digest = hashlib.sha256()
                with archive.open("database.sqlite3") as source, candidate.open("wb") as output:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                        output.write(block)
                expected_hash = manifest.get("database", {}).get("sha256")
                actual_hash = digest.hexdigest()
                if not expected_hash or actual_hash != expected_hash:
                    raise ExportError("Backup database checksum does not match")

            with closing(
                sqlite3.connect(f"file:{candidate}?mode=ro", uri=True)
            ) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
                available_tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                missing_tables = sorted(set(PORTABLE_TABLES) - available_tables)
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in PORTABLE_TABLES
                    if table in available_tables
                }
        if integrity != "ok":
            raise ExportError("Backup database integrity check failed")
        if foreign_key_errors:
            raise ExportError("Backup contains broken database relationships")
        if missing_tables:
            raise ExportError("Backup is missing required application tables")
        return {
            "ready": True,
            "schema_version": manifest["schema_version"],
            "created_at": manifest.get("created_at"),
            "database_sha256": actual_hash,
            "table_counts": counts,
            "originals": manifest.get("originals", {"included": False, "count": 0}),
            "credentials_included": False,
            "message": "Preview passed. No application data was changed.",
        }
    except zipfile.BadZipFile as error:
        raise ExportError("The selected file is not a valid ZIP backup") from error


def restore_backup(backup_path: Path, target_path: Path) -> dict[str, object]:
    """Restore a validated backup to an explicit target, primarily for round-trip tests."""
    preview = preview_restore(backup_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup_path) as archive, tempfile.TemporaryDirectory(
        prefix="health-training-restore-"
    ) as temporary:
        restored = Path(temporary) / "database.sqlite3"
        with archive.open("database.sqlite3") as source, restored.open("wb") as output:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                output.write(block)
        _database_snapshot(restored, target_path)
    migrate(target_path)
    return {**preview, "restored_to": str(target_path)}


def temporary_export_path(suffix: str) -> Path:
    export_directory = data_directory() / "exports"
    export_directory.mkdir(parents=True, exist_ok=True)
    handle, raw_path = tempfile.mkstemp(prefix="health-training-", suffix=suffix, dir=export_directory)
    os.close(handle)
    Path(raw_path).unlink(missing_ok=True)
    return Path(raw_path)
