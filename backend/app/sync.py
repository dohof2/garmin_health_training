from __future__ import annotations

import hashlib
import io
import json
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .database import connect, migrate
from .fit_import import _decode_fit, _sample_rows


SYNC_DATA_TYPES = (
    "activities",
    "daily_metrics",
    "sleep_metrics",
    "hrv_metrics",
    "weight_metrics",
)


class SyncError(RuntimeError):
    pass


class SyncAlreadyRunning(SyncError):
    pass


class SyncConnectionRequired(SyncError):
    pass


class SyncInterrupted(SyncError):
    pass


class SyncProvider(Protocol):
    provider_name: str
    connection_status: str
    supports_updated_since: bool

    def fetch(self, data_type: str, start_date: date, end_date: date) -> list[dict[str, object]]:
        """Return normalized source records for a complete inclusive interval."""


@dataclass
class SimulatedGarminProvider:
    records: dict[str, list[dict[str, object]]]
    failed_intervals: set[tuple[str, str]] | None = None
    provider_name: str = "garmin_connect_simulated"
    connection_status: str = "connected"
    supports_updated_since: bool = False

    def fetch(self, data_type: str, start_date: date, end_date: date) -> list[dict[str, object]]:
        if self.failed_intervals and (data_type, start_date.isoformat()) in self.failed_intervals:
            raise SyncError(f"Simulated {data_type} failure for {start_date.isoformat()}")
        date_field = "started_at" if data_type == "activities" else "recorded_at"
        return [
            dict(record)
            for record in self.records.get(data_type, [])
            if start_date.isoformat()
            <= str(record[date_field])[:10]
            <= end_date.isoformat()
        ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_bounds(connection: object, data_type: str) -> tuple[str | None, str | None]:
    if data_type == "activities":
        row = connection.execute(
            """
            SELECT MIN(substr(started_at, 1, 10)), MAX(substr(started_at, 1, 10))
            FROM activities WHERE deleted_at IS NULL
            """
        ).fetchone()
    elif data_type == "daily_metrics":
        row = connection.execute(
            """
            SELECT MIN(substr(recorded_at, 1, 10)), MAX(substr(recorded_at, 1, 10))
            FROM metric_readings WHERE source_record_id LIKE 'daily:%'
            """
        ).fetchone()
    elif data_type == "sleep_metrics":
        row = connection.execute(
            """
            SELECT MIN(substr(recorded_at, 1, 10)), MAX(substr(recorded_at, 1, 10))
            FROM metric_readings WHERE source_record_id LIKE 'sleep:%'
            """
        ).fetchone()
    elif data_type == "hrv_metrics":
        row = connection.execute(
            """
            SELECT MIN(substr(recorded_at, 1, 10)), MAX(substr(recorded_at, 1, 10))
            FROM metric_readings WHERE source_record_id LIKE 'hrv:%'
            """
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT MIN(substr(recorded_at, 1, 10)), MAX(substr(recorded_at, 1, 10))
            FROM metric_readings
            WHERE metric_type IN ('weight', 'bmi', 'body_fat', 'body_water', 'bone_mass', 'muscle_mass')
            """
        ).fetchone()
    return (row[0], row[1])


def ensure_sync_checkpoints(path: Path | None = None) -> None:
    """Seed online catch-up boundaries from imported coverage without claiming empty days."""
    migrate(path)
    with connect(path) as connection:
        for data_type in SYNC_DATA_TYPES:
            if connection.execute(
                "SELECT 1 FROM sync_checkpoints WHERE data_type = ?", (data_type,)
            ).fetchone():
                continue
            coverage_start, coverage_end = _source_bounds(connection, data_type)
            connection.execute(
                """
                INSERT INTO sync_checkpoints(
                    data_type, provider_name, coverage_start, coverage_end,
                    seeded_from_import, status
                ) VALUES (?, 'garmin_connect', ?, ?, ?, 'pending')
                ON CONFLICT(data_type) DO NOTHING
                """,
                (data_type, coverage_start, coverage_end, int(coverage_end is not None)),
            )


def recover_interrupted_sync_jobs(path: Path | None = None) -> int:
    """Mark jobs left running by a stopped app as safely retryable."""
    migrate(path)
    with connect(path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                error_message = 'Interrupted when the app session ended; safe to retry',
                finished_at = ?
            WHERE job_type = 'garmin_sync' AND status = 'running'
            """,
            (_now(),),
        )
        return cursor.rowcount


def _checkpoint_rows(path: Path | None = None) -> list[dict[str, object]]:
    ensure_sync_checkpoints(path)
    with connect(path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT data_type, provider_name, coverage_start, coverage_end,
                       seeded_from_import, last_attempt_at, last_success_at,
                       last_source_updated_at, last_reconciled_start,
                       last_reconciled_end, status, error_message
                FROM sync_checkpoints ORDER BY data_type
                """
            )
        ]


def sync_plan(
    through_date: date,
    path: Path | None = None,
    *,
    overlap_days: int | None = None,
    reconcile_from: date | None = None,
) -> dict[str, object]:
    ensure_sync_checkpoints(path)
    with connect(path) as connection:
        configured_overlap = connection.execute(
            "SELECT overlap_days FROM sync_settings WHERE id = 1"
        ).fetchone()[0]
    overlap = configured_overlap if overlap_days is None else overlap_days
    if overlap < 0 or overlap > 30:
        raise ValueError("overlap_days must be between 0 and 30")

    plans: list[dict[str, object]] = []
    for checkpoint in _checkpoint_rows(path):
        coverage_start = (
            date.fromisoformat(str(checkpoint["coverage_start"]))
            if checkpoint["coverage_start"]
            else None
        )
        coverage_end = (
            date.fromisoformat(str(checkpoint["coverage_end"]))
            if checkpoint["coverage_end"]
            else None
        )
        if reconcile_from:
            start = reconcile_from
            kind = "reconciliation"
        elif coverage_end:
            gap_start = coverage_end + timedelta(days=1)
            overlap_start = coverage_end - timedelta(days=max(overlap - 1, 0))
            if coverage_start:
                overlap_start = max(overlap_start, coverage_start)
            start = min(gap_start, overlap_start) if overlap else gap_start
            kind = "catch_up"
        else:
            start = through_date
            kind = "catch_up"
        days = max((through_date - start).days + 1, 0)
        plans.append(
            {
                "data_type": checkpoint["data_type"],
                "start_date": start.isoformat() if days else None,
                "end_date": through_date.isoformat() if days else None,
                "days": days,
                "overlap_days": overlap if not reconcile_from else 0,
                "kind": kind,
                "coverage_end": checkpoint["coverage_end"],
            }
        )
    return {
        "through_date": through_date.isoformat(),
        "data_types": plans,
        "total_intervals": sum(int(item["days"]) for item in plans),
        "limitation": (
            "Recent overlap catches late uploads and corrections. Older changes require "
            "a selectable historical reconciliation range when updated-since is unavailable."
        ),
    }


def set_sync_schedule(enabled: bool, path: Path | None = None) -> dict[str, object]:
    """Enable or disable daily synchronization while the app is open."""
    migrate(path)
    with connect(path) as connection:
        connection.execute(
            """
            UPDATE sync_settings
            SET schedule_enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (int(enabled),),
        )
    return sync_status(path)


def scheduled_sync_decision(
    through_date: date, path: Path | None = None
) -> dict[str, object]:
    """Return whether the open app should run its at-most-daily catch-up."""
    status = sync_status(path)
    if not status["schedule_enabled"]:
        return {"due": False, "reason": "disabled", "through_date": through_date.isoformat()}
    if status["connection_status"] != "connected":
        return {
            "due": False,
            "reason": "connection_required",
            "through_date": through_date.isoformat(),
        }
    checkpoints = status["checkpoints"]
    up_to_date = all(
        checkpoint["status"] == "synced"
        and checkpoint["last_success_at"]
        and checkpoint["coverage_end"]
        and date.fromisoformat(str(checkpoint["coverage_end"])) >= through_date
        for checkpoint in checkpoints
    )
    return {
        "due": not up_to_date,
        "reason": "catch_up_required" if not up_to_date else "up_to_date",
        "through_date": through_date.isoformat(),
    }


def _job_start(trigger: str, total: int, path: Path | None) -> str:
    job_id = f"sync-{uuid.uuid4()}"
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM jobs WHERE job_type = 'garmin_sync' AND status = 'running'"
        ).fetchone():
            raise SyncAlreadyRunning("A synchronization job is already running")
        connection.execute(
            """
            INSERT INTO jobs(
                id, job_type, status, progress_total, checkpoint_json, started_at
            ) VALUES (?, 'garmin_sync', 'running', ?, ?, ?)
            """,
            (job_id, total, json.dumps({"trigger": trigger}), _now()),
        )
    return job_id


def _activity_values(record: dict[str, object]) -> dict[str, object]:
    source_id = str(record.get("source_record_id") or "").strip()
    started_at = str(record.get("started_at") or "").strip()
    activity_type = str(record.get("activity_type") or "").strip()
    if not source_id or (not record.get("deleted") and (not started_at or not activity_type)):
        raise SyncError("Activity record is missing a source ID, timestamp, or type")
    public_record = {key: value for key, value in record.items() if not key.startswith("_")}
    return {
        "source_record_id": source_id,
        "activity_type": activity_type,
        "name": record.get("name"),
        "started_at": started_at,
        "ended_at": record.get("ended_at"),
        "timezone": record.get("timezone"),
        "duration_seconds": record.get("duration_seconds"),
        "distance_meters": record.get("distance_meters"),
        "calories_kcal": record.get("calories_kcal"),
        "elevation_gain_meters": record.get("elevation_gain_meters"),
        "source_updated_at": record.get("source_updated_at"),
        "deleted_at": _now() if record.get("deleted") else None,
        "raw_json": json.dumps(public_record, separators=(",", ":"), sort_keys=True),
    }


def _activity_fingerprint_match(
    connection: object, values: dict[str, object]
) -> object | None:
    """Match an archive-only activity when Garmin later supplies its stable ID."""
    candidates: list[tuple[float, object]] = []
    rows = connection.execute(
        """
        SELECT * FROM activities
        WHERE deleted_at IS NULL
          AND ABS((julianday(started_at) - julianday(?)) * 86400) <= 900
        """,
        (values["started_at"],),
    ).fetchall()
    for candidate in rows:
        comparable = 0
        score = abs(
            float(
                connection.execute(
                    "SELECT (julianday(?) - julianday(?)) * 86400",
                    (candidate["started_at"], values["started_at"]),
                ).fetchone()[0]
                or 0
            )
        )
        for field, absolute_tolerance, relative_tolerance, weight in (
            ("duration_seconds", 15.0, 0.03, 5.0),
            ("distance_meters", 150.0, 0.03, 25.0),
        ):
            incoming = values[field]
            stored = candidate[field]
            if incoming is None or stored is None:
                continue
            comparable += 1
            delta = abs(float(incoming) - float(stored))
            if delta > max(absolute_tolerance, abs(float(stored)) * relative_tolerance):
                break
            score += delta / weight
        else:
            if comparable:
                candidates.append((score, candidate))
    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return None
    if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 1:
        return None
    return candidates[0][1]


def _activity_needs_detail(
    record: dict[str, object], path: Path | None = None
) -> bool:
    values = _activity_values(record)
    with connect(path) as connection:
        existing = connection.execute(
            "SELECT * FROM activities WHERE source_record_id = ? LIMIT 1",
            (values["source_record_id"],),
        ).fetchone()
        if existing is None:
            existing = _activity_fingerprint_match(connection, values)
        if existing is None:
            return True
        return (
            connection.execute(
                "SELECT COUNT(*) FROM activity_samples WHERE activity_id = ?",
                (existing["id"],),
            ).fetchone()[0]
            == 0
        )


def _fit_content(payload: bytes) -> bytes:
    if len(payload) > 50 * 1024 * 1024:
        raise SyncError("Downloaded Garmin activity detail exceeds the 50 MiB limit")
    stream = io.BytesIO(payload)
    if not zipfile.is_zipfile(stream):
        return payload
    with zipfile.ZipFile(stream) as archive:
        members = [
            item
            for item in archive.infolist()
            if not item.is_dir()
            and Path(item.filename).suffix.lower() == ".fit"
            and Path(item.filename).name == item.filename
        ]
        if len(members) != 1:
            raise SyncError("Garmin activity detail must contain exactly one safe FIT file")
        if members[0].file_size > 50 * 1024 * 1024:
            raise SyncError("Downloaded Garmin FIT file exceeds the 50 MiB limit")
        return archive.read(members[0])


def _upsert_activity_detail(
    connection: object, source_record_id: str, payload: bytes
) -> int:
    activity = connection.execute(
        "SELECT id FROM activities WHERE source_record_id = ? LIMIT 1",
        (source_record_id,),
    ).fetchone()
    if activity is None:
        raise SyncError("Activity detail could not be matched after summary import")
    messages, errors = _decode_fit(_fit_content(payload))
    if errors:
        raise SyncError(f"Garmin FIT detail reported {len(errors)} decoder errors")
    samples = _sample_rows(
        str(activity["id"]),
        list(messages.get("record_mesgs") or []),
    )
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
    return len(samples)


def _upsert_activity(connection: object, record: dict[str, object]) -> str:
    values = _activity_values(record)
    existing = connection.execute(
        """
        SELECT * FROM activities
        WHERE source_record_id = ?
        ORDER BY CASE source_name WHEN 'garmin_connect' THEN 0 ELSE 1 END, created_at
        LIMIT 1
        """,
        (values["source_record_id"],),
    ).fetchone()
    if existing is None and not record.get("deleted"):
        existing = _activity_fingerprint_match(connection, values)
    if record.get("deleted") and existing is None:
        return "unchanged"
    if record.get("deleted") and existing["deleted_at"]:
        values["deleted_at"] = existing["deleted_at"]
    if existing is None:
        identifier = "garmin-connect-activity-" + hashlib.sha256(
            str(values["source_record_id"]).encode()
        ).hexdigest()[:24]
        connection.execute(
            """
            INSERT INTO activities(
                id, source_name, source_record_id, activity_type, name,
                started_at, ended_at, timezone, duration_seconds,
                distance_meters, calories_kcal, elevation_gain_meters,
                source_updated_at, deleted_at, raw_json
            ) VALUES (?, 'garmin_connect', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identifier,
                values["source_record_id"],
                values["activity_type"],
                values["name"],
                values["started_at"],
                values["ended_at"],
                values["timezone"],
                values["duration_seconds"],
                values["distance_meters"],
                values["calories_kcal"],
                values["elevation_gain_meters"],
                values["source_updated_at"],
                values["deleted_at"],
                values["raw_json"],
            ),
        )
        return "created"

    compared = (
        "activity_type",
        "name",
        "started_at",
        "ended_at",
        "timezone",
        "duration_seconds",
        "distance_meters",
        "calories_kcal",
        "elevation_gain_meters",
        "source_updated_at",
        "deleted_at",
        "raw_json",
    )
    if existing["source_record_id"] == values["source_record_id"] and all(
        existing[key] == values[key] for key in compared
    ):
        return "unchanged"
    connection.execute(
        """
        UPDATE activities SET
            source_record_id = ?,
            activity_type = ?, name = ?, started_at = ?, ended_at = ?, timezone = ?,
            duration_seconds = ?, distance_meters = ?, calories_kcal = ?,
            elevation_gain_meters = ?, source_updated_at = ?, deleted_at = ?,
            raw_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (values["source_record_id"],)
        + tuple(values[key] for key in compared)
        + (existing["id"],),
    )
    return "updated"


def _metric_values(record: dict[str, object]) -> dict[str, object]:
    required = ("source_record_id", "metric_type", "recorded_at", "value", "unit")
    if any(record.get(key) is None for key in required):
        raise SyncError("Metric record is missing an identifier, timestamp, value, or unit")
    return {
        "source_record_id": str(record["source_record_id"]),
        "metric_type": str(record["metric_type"]),
        "recorded_at": str(record["recorded_at"]),
        "value": float(record["value"]),
        "unit": str(record["unit"]),
        "period_start": record.get("period_start"),
        "period_end": record.get("period_end"),
        "source_updated_at": record.get("source_updated_at"),
        "raw_json": json.dumps(record, separators=(",", ":"), sort_keys=True),
    }


def _upsert_metric(connection: object, record: dict[str, object]) -> str:
    values = _metric_values(record)
    exact = connection.execute(
        """
        SELECT * FROM metric_readings
        WHERE source_record_id = ? AND metric_type = ?
        ORDER BY CASE source_name WHEN 'garmin_connect' THEN 0 ELSE 1 END, created_at
        LIMIT 1
        """,
        (values["source_record_id"], values["metric_type"]),
    ).fetchone()
    candidates: list[object] = []
    if str(values["source_record_id"]).startswith(("daily:", "sleep:")):
        candidates = connection.execute(
            """
            SELECT * FROM metric_readings
            WHERE metric_type = ?
              AND substr(recorded_at, 1, 10) = substr(?, 1, 10)
              AND source_name IN ('garmin_export', 'garmin_connect')
            ORDER BY CASE source_name WHEN 'garmin_export' THEN 0 ELSE 1 END, created_at
            """,
            (values["metric_type"], values["recorded_at"]),
        ).fetchall()
    existing = candidates[0] if candidates else exact
    if existing is not None and len(candidates) > 1:
        duplicate_ids = [row["id"] for row in candidates if row["id"] != existing["id"]]
        connection.executemany(
            "DELETE FROM metric_readings WHERE id = ?",
            [(identifier,) for identifier in duplicate_ids],
        )
    compared = (
        "recorded_at",
        "value",
        "unit",
        "period_start",
        "period_end",
        "source_updated_at",
        "raw_json",
    )
    if (
        existing is not None
        and existing["source_record_id"] == values["source_record_id"]
        and all(existing[key] == values[key] for key in compared)
    ):
        return "unchanged"
    if existing is not None:
        connection.execute(
            """
            UPDATE metric_readings SET
                source_record_id = ?, recorded_at = ?, value = ?, unit = ?, period_start = ?, period_end = ?,
                source_updated_at = ?, raw_json = ?
            WHERE id = ?
            """,
            (values["source_record_id"],)
            + tuple(values[key] for key in compared)
            + (existing["id"],),
        )
        return "updated"
    identifier = "garmin-connect-metric-" + hashlib.sha256(
        f"{values['source_record_id']}:{values['metric_type']}".encode()
    ).hexdigest()[:24]
    connection.execute(
        """
        INSERT INTO metric_readings(
            id, source_name, source_record_id, metric_type, recorded_at,
            value, unit, period_start, period_end, source_updated_at, raw_json
        ) VALUES (?, 'garmin_connect', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            identifier,
            values["source_record_id"],
            values["metric_type"],
            values["recorded_at"],
            values["value"],
            values["unit"],
            values["period_start"],
            values["period_end"],
            values["source_updated_at"],
            values["raw_json"],
        ),
    )
    return "created"


def _commit_interval(
    job_id: str,
    data_type: str,
    interval_date: date,
    interval_kind: str,
    records: list[dict[str, object]],
    old_coverage_end: date | None,
    path: Path | None,
) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "unchanged": 0, "detail_samples": 0}
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for record in records:
            result = (
                _upsert_activity(connection, record)
                if data_type == "activities"
                else _upsert_metric(connection, record)
            )
            counts[result] += 1
            detail = record.get("_detail_fit")
            if data_type == "activities" and isinstance(detail, bytes):
                counts["detail_samples"] += _upsert_activity_detail(
                    connection,
                    str(record["source_record_id"]),
                    detail,
                )
        day = interval_date.isoformat()
        connection.execute(
            """
            INSERT INTO sync_intervals(
                job_id, data_type, interval_start, interval_end, interval_kind,
                status, records_received, records_created, records_updated,
                records_unchanged, empty_result
            ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                data_type,
                day,
                day,
                interval_kind,
                len(records),
                counts["created"],
                counts["updated"],
                counts["unchanged"],
                int(not records),
            ),
        )
        coverage_end = max(old_coverage_end, interval_date) if old_coverage_end else interval_date
        source_updates = [str(record["source_updated_at"]) for record in records if record.get("source_updated_at")]
        connection.execute(
            """
            UPDATE sync_checkpoints SET
                coverage_end = ?, last_attempt_at = ?, last_success_at = ?,
                last_source_updated_at = COALESCE(?, last_source_updated_at),
                last_reconciled_start = CASE WHEN ? = 'reconciliation' THEN COALESCE(last_reconciled_start, ?) ELSE last_reconciled_start END,
                last_reconciled_end = CASE WHEN ? = 'reconciliation' THEN ? ELSE last_reconciled_end END,
                status = 'syncing', error_message = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE data_type = ?
            """,
            (
                coverage_end.isoformat(),
                _now(),
                _now(),
                max(source_updates) if source_updates else None,
                interval_kind,
                day,
                interval_kind,
                day,
                data_type,
            ),
        )
        connection.execute(
            "UPDATE jobs SET progress_current = progress_current + 1 WHERE id = ?",
            (job_id,),
        )
    return counts


def _record_failure(
    job_id: str,
    data_type: str,
    interval_date: date,
    interval_kind: str,
    error: Exception,
    path: Path | None,
) -> None:
    message = str(error)[:500]
    day = interval_date.isoformat()
    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO sync_intervals(
                job_id, data_type, interval_start, interval_end,
                interval_kind, status, error_message
            ) VALUES (?, ?, ?, ?, ?, 'failed', ?)
            """,
            (job_id, data_type, day, day, interval_kind, message),
        )
        connection.execute(
            """
            UPDATE sync_checkpoints SET
                last_attempt_at = ?, status = 'failed', error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE data_type = ?
            """,
            (_now(), message, data_type),
        )


def run_sync(
    provider: SyncProvider,
    through_date: date,
    path: Path | None = None,
    *,
    trigger: str = "manual",
    overlap_days: int | None = None,
    reconcile_from: date | None = None,
    interrupt_after: int | None = None,
    request_delay_seconds: float = 0,
) -> dict[str, object]:
    """Run manual or scheduled sync through the same durable interval pipeline."""
    if provider.connection_status != "connected":
        raise SyncConnectionRequired("Garmin connection needs sign-in or renewal")
    if request_delay_seconds < 0 or request_delay_seconds > 60:
        raise ValueError("request_delay_seconds must be between 0 and 60")
    plan = sync_plan(
        through_date,
        path,
        overlap_days=overlap_days,
        reconcile_from=reconcile_from,
    )
    job_id = _job_start(trigger, int(plan["total_intervals"]), path)
    completed = 0
    totals = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "received": 0,
        "detail_samples": 0,
    }
    failures: list[dict[str, str]] = []
    try:
        with connect(path) as connection:
            connection.execute(
                """
                UPDATE sync_settings
                SET connection_status = 'connected',
                    last_scheduled_at = CASE WHEN ? = 'scheduled' THEN ? ELSE last_scheduled_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (trigger, _now()),
            )
        for data_plan in plan["data_types"]:
            if not data_plan["start_date"]:
                continue
            data_type = str(data_plan["data_type"])
            start = date.fromisoformat(str(data_plan["start_date"]))
            old_end = (
                date.fromisoformat(str(data_plan["coverage_end"]))
                if data_plan["coverage_end"]
                else None
            )
            with connect(path) as connection:
                connection.execute(
                    """
                    UPDATE sync_checkpoints SET
                        status = 'syncing',
                        error_message = NULL,
                        last_reconciled_start = CASE WHEN ? IS NOT NULL THEN ? ELSE last_reconciled_start END,
                        last_reconciled_end = CASE WHEN ? IS NOT NULL THEN NULL ELSE last_reconciled_end END
                    WHERE data_type = ?
                    """,
                    (
                        reconcile_from.isoformat() if reconcile_from else None,
                        reconcile_from.isoformat() if reconcile_from else None,
                        reconcile_from.isoformat() if reconcile_from else None,
                        data_type,
                    ),
                )
            for offset in range((through_date - start).days + 1):
                interval_date = start + timedelta(days=offset)
                interval_kind = (
                    "reconciliation"
                    if reconcile_from
                    else "overlap"
                    if old_end and interval_date <= old_end
                    else "gap"
                )
                try:
                    records = provider.fetch(data_type, interval_date, interval_date)
                    detail_fetcher = getattr(provider, "fetch_activity_detail", None)
                    if data_type == "activities" and callable(detail_fetcher):
                        for record in records:
                            if not record.get("deleted") and _activity_needs_detail(record, path):
                                record["_detail_fit"] = detail_fetcher(
                                    str(record["source_record_id"])
                                )
                    if request_delay_seconds:
                        time.sleep(request_delay_seconds)
                    counts = _commit_interval(
                        job_id,
                        data_type,
                        interval_date,
                        interval_kind,
                        records,
                        old_end,
                        path,
                    )
                    totals["received"] += len(records)
                    for key in ("created", "updated", "unchanged"):
                        totals[key] += counts[key]
                    totals["detail_samples"] += counts["detail_samples"]
                    old_end = max(old_end, interval_date) if old_end else interval_date
                    completed += 1
                    if interrupt_after is not None and completed >= interrupt_after:
                        raise SyncInterrupted("Simulated interruption after a committed interval")
                except SyncInterrupted:
                    raise
                except Exception as error:
                    _record_failure(job_id, data_type, interval_date, interval_kind, error, path)
                    failures.append({"data_type": data_type, "date": interval_date.isoformat(), "error": str(error)})
                    break
            if not any(item["data_type"] == data_type for item in failures):
                with connect(path) as connection:
                    connection.execute(
                        """
                        UPDATE sync_checkpoints SET status = 'synced', error_message = NULL,
                            last_success_at = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE data_type = ?
                        """,
                        (_now(), data_type),
                    )
        status = "failed" if failures else "completed"
        with connect(path) as connection:
            connection.execute(
                """
                UPDATE jobs SET status = ?, checkpoint_json = ?, error_message = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps({"trigger": trigger, "totals": totals, "failures": failures}),
                    "One or more data types remain pending" if failures else None,
                    _now(),
                    job_id,
                ),
            )
        return {"job_id": job_id, "status": status, "trigger": trigger, "totals": totals, "failures": failures}
    except Exception as error:
        with connect(path) as connection:
            connection.execute(
                """
                UPDATE jobs SET status = 'failed', error_message = ?, checkpoint_json = ?, finished_at = ?
                WHERE id = ?
                """,
                (str(error)[:500], json.dumps({"trigger": trigger, "totals": totals}), _now(), job_id),
            )
        raise


def sync_status(path: Path | None = None) -> dict[str, object]:
    ensure_sync_checkpoints(path)
    with connect(path) as connection:
        settings = dict(connection.execute("SELECT * FROM sync_settings WHERE id = 1").fetchone())
        last_job_row = connection.execute(
            """
            SELECT id, status, progress_current, progress_total, checkpoint_json,
                   error_message, created_at, started_at, finished_at
            FROM jobs WHERE job_type = 'garmin_sync'
            ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()
        empty_intervals = connection.execute(
            "SELECT COUNT(*) FROM sync_intervals WHERE status = 'completed' AND empty_result = 1"
        ).fetchone()[0]
    last_job = dict(last_job_row) if last_job_row else None
    if last_job and last_job.get("checkpoint_json"):
        last_job["checkpoint"] = json.loads(str(last_job.pop("checkpoint_json")))
    connection_ready = settings["connection_status"] == "connected"
    if not connection_ready:
        next_action = "Sign in locally to Garmin Connect to enable synchronization"
    elif any(item["status"] == "failed" for item in _checkpoint_rows(path)):
        next_action = "Retry synchronization; one or more data types remain pending"
    elif settings["schedule_enabled"]:
        next_action = "Daily catch-up is enabled while the app is open"
    else:
        next_action = "Synchronization is ready; daily open-session sync is off"
    return {
        "provider": settings["provider_name"],
        "connection_status": settings["connection_status"],
        "schedule_enabled": bool(settings["schedule_enabled"]),
        "schedule_scope": "open_app_session_only",
        "overlap_days": settings["overlap_days"],
        "supports_updated_since": False,
        "checkpoints": _checkpoint_rows(path),
        "verified_empty_intervals": empty_intervals,
        "last_job": last_job,
        "live_sync_ready": connection_ready,
        "next_action": next_action,
    }
