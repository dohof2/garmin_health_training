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

from .config import data_directory
from .database import connect, migrate
from .fit_import import _atomic_write_json, _decode_fit, _sha256
from .garmin_import import GARMIN_SOURCE_NAME, default_archive_path, inspect_archive


INVENTORY_VERSION = 3
BATCH_SIZE = 100
FIT_EPOCH_UNIX_SECONDS = 631_065_600


def monitoring_inventory_path() -> Path:
    return data_directory() / "monitoring-fit-inventory.json"


def _timestamp(value: object) -> str | None:
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
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    if not 2000 <= parsed.year <= datetime.now(UTC).year + 1:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _valid_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def extract_health_samples(
    messages: dict[str, list[dict]],
) -> dict[str, dict[str, object]]:
    samples: dict[str, dict[str, object]] = {}

    def sample_at(value: object) -> dict[str, object] | None:
        recorded_at = _timestamp(value)
        if recorded_at is None:
            return None
        return samples.setdefault(
            recorded_at,
            {
                "recorded_at": recorded_at,
                "heart_rate_bpm": None,
                "stress_level": None,
                "respiration_rate": None,
            },
        )

    timestamp_anchor: int | None = None
    for message in messages.get("monitoring_mesgs", []):
        full_timestamp = _timestamp(message.get("timestamp"))
        message_timestamp: object = message.get("timestamp")
        if full_timestamp is not None:
            timestamp_anchor = int(
                datetime.fromisoformat(full_timestamp.replace("Z", "+00:00")).timestamp()
            ) - FIT_EPOCH_UNIX_SECONDS
        else:
            compressed_timestamp = message.get("timestamp_16")
            if timestamp_anchor is not None and isinstance(compressed_timestamp, int):
                reconstructed = (timestamp_anchor & ~0xFFFF) | compressed_timestamp
                if reconstructed < timestamp_anchor:
                    reconstructed += 0x10000
                timestamp_anchor = reconstructed
                message_timestamp = datetime.fromtimestamp(
                    reconstructed + FIT_EPOCH_UNIX_SECONDS,
                    tz=UTC,
                )

        heart_rate = _valid_number(message.get("heart_rate"))
        if heart_rate is None or not 20 <= heart_rate <= 250:
            continue
        sample = sample_at(message_timestamp)
        if sample is not None:
            sample["heart_rate_bpm"] = int(heart_rate)

    for message in messages.get("stress_level_mesgs", []):
        stress = _valid_number(message.get("stress_level_value"))
        if stress is None or not 0 <= stress <= 100:
            continue
        sample = sample_at(message.get("stress_level_time"))
        if sample is not None:
            sample["stress_level"] = int(stress)

    for message in messages.get("respiration_rate_mesgs", []):
        respiration = _valid_number(message.get("respiration_rate"))
        if respiration is None or not 0 < respiration <= 100:
            continue
        sample = sample_at(message.get("timestamp"))
        if sample is not None:
            sample["respiration_rate"] = respiration

    return samples


def _new_inventory(archive_hash: str) -> dict[str, object]:
    return {
        "version": INVENTORY_VERSION,
        "archive_sha256": archive_hash,
        "status": "running",
        "completed_nested_archives": [],
        "scanned_fit_files": 0,
        "monitoring_files": [],
        "file_types": {},
        "decode_failures": [],
    }


def _load_inventory(path: Path, archive_hash: str) -> dict[str, object]:
    if not path.exists():
        return _new_inventory(archive_hash)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _new_inventory(archive_hash)
    if (
        value.get("version") != INVENTORY_VERSION
        or value.get("archive_sha256") != archive_hash
    ):
        return _new_inventory(archive_hash)
    return value


def build_monitoring_inventory(
    archive_path: Path | None = None,
    destination: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    inspect_archive(archive)
    archive_hash = _sha256(archive)
    output = destination or monitoring_inventory_path()
    report = _load_inventory(output, archive_hash)
    if report.get("status") == "complete":
        return report

    completed = set(report["completed_nested_archives"])
    scanned = int(report["scanned_fit_files"])
    monitoring_files = list(report["monitoring_files"])
    failures = list(report["decode_failures"])
    file_types = Counter(
        {str(key): int(value) for key, value in dict(report["file_types"]).items()}
    )

    with zipfile.ZipFile(archive) as outer:
        nested_names = sorted(
            info.filename
            for info in outer.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".zip")
        )
        for nested_name in nested_names:
            if nested_name in completed:
                continue
            nested_count = 0
            print(
                f"Scanning monitoring archive: {nested_name}",
                file=sys.stderr,
                flush=True,
            )
            with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as nested:
                for info in nested.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".fit"):
                        continue
                    nested_count += 1
                    scanned += 1
                    content = nested.read(info)
                    try:
                        messages, errors = _decode_fit(content)
                        file_id = (messages.get("file_id_mesgs") or [{}])[0]
                        file_type = str(file_id.get("type", "unknown"))
                        file_types[file_type] += 1
                        samples = extract_health_samples(messages)
                        if samples:
                            value_counts = Counter()
                            for sample in samples.values():
                                if sample["heart_rate_bpm"] is not None:
                                    value_counts["heart_rate"] += 1
                                if sample["stress_level"] is not None:
                                    value_counts["stress"] += 1
                                if sample["respiration_rate"] is not None:
                                    value_counts["respiration"] += 1
                            monitoring_files.append(
                                {
                                    "nested_archive": nested_name,
                                    "member": info.filename,
                                    "bytes": info.file_size,
                                    "sha256": hashlib.sha256(content).hexdigest(),
                                    "file_type": file_type,
                                    "sample_count": len(samples),
                                    "value_counts": dict(value_counts),
                                    "decode_errors": len(errors),
                                }
                            )
                        if errors:
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
                    if nested_count % 5000 == 0:
                        print(
                            f"  scanned {nested_count:,} FIT files",
                            file=sys.stderr,
                            flush=True,
                        )
            completed.add(nested_name)
            report.update(
                {
                    "completed_nested_archives": sorted(completed),
                    "scanned_fit_files": scanned,
                    "monitoring_files": monitoring_files,
                    "file_types": dict(sorted(file_types.items())),
                    "decode_failures": failures,
                }
            )
            _atomic_write_json(output, report)

    totals = Counter()
    for item in monitoring_files:
        totals.update(item["value_counts"])
    report.update(
        {
            "status": "complete",
            "monitoring_file_count": len(monitoring_files),
            "candidate_sample_count": sum(
                int(item["sample_count"]) for item in monitoring_files
            ),
            "candidate_value_counts": dict(totals),
            "decode_failure_count": len(failures),
        }
    )
    _atomic_write_json(output, report)
    return report


def preview_health_fit_import(archive_path: Path | None = None) -> dict[str, object]:
    report = build_monitoring_inventory(archive_path)
    return {
        "ready": int(report["decode_failure_count"]) == 0,
        "scanned_fit_files": report["scanned_fit_files"],
        "monitoring_files": report["monitoring_file_count"],
        "candidate_samples": report["candidate_sample_count"],
        "candidate_values": report["candidate_value_counts"],
        "decode_failures": report["decode_failure_count"],
    }


def _commit_batch(
    *,
    database_path: Path | None,
    archive_source_id: str,
    batch: list[tuple[dict[str, object], dict[str, dict[str, object]]]],
) -> int:
    combined: dict[str, dict[str, object]] = {}
    for _, samples in batch:
        for recorded_at, sample in samples.items():
            target = combined.setdefault(recorded_at, dict(sample))
            for field in ("heart_rate_bpm", "stress_level", "respiration_rate"):
                if sample[field] is not None:
                    target[field] = sample[field]

    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            """
            INSERT INTO health_samples(
                source_name, source_file_id, recorded_at,
                heart_rate_bpm, stress_level, respiration_rate
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name, recorded_at) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                heart_rate_bpm = COALESCE(excluded.heart_rate_bpm, heart_rate_bpm),
                stress_level = COALESCE(excluded.stress_level, stress_level),
                respiration_rate = COALESCE(excluded.respiration_rate, respiration_rate),
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    GARMIN_SOURCE_NAME,
                    archive_source_id,
                    sample["recorded_at"],
                    sample["heart_rate_bpm"],
                    sample["stress_level"],
                    sample["respiration_rate"],
                )
                for sample in combined.values()
            ],
        )
        for metadata, samples in batch:
            identity = hashlib.sha256(
                f"{metadata['nested_archive']}\n{metadata['member']}".encode()
            ).hexdigest()
            connection.execute(
                """
                INSERT INTO monitoring_fit_import_files(
                    id, archive_source_file_id, nested_archive, member_name,
                    content_hash, status, sample_count
                ) VALUES (?, ?, ?, ?, ?, 'completed', ?)
                ON CONFLICT(nested_archive, member_name) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    status = 'completed',
                    sample_count = excluded.sample_count,
                    error_message = NULL,
                    imported_at = CURRENT_TIMESTAMP
                """,
                (
                    f"monitoring-fit-{identity}",
                    archive_source_id,
                    metadata["nested_archive"],
                    metadata["member"],
                    metadata["sha256"],
                    len(samples),
                ),
            )
    return len(combined)


def import_health_fit_samples(
    archive_path: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, object]:
    archive = (archive_path or default_archive_path()).expanduser().resolve()
    report = build_monitoring_inventory(archive)
    migrate(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT id FROM source_files WHERE content_hash = ?",
            (report["archive_sha256"],),
        ).fetchone()
        if source is None:
            raise ValueError("Run the Garmin JSON import before monitoring import.")
        archive_source_id = str(source[0])
        completed = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT nested_archive, member_name
                FROM monitoring_fit_import_files WHERE status = 'completed'
                """
            )
        }

    grouped: dict[str, list[dict[str, object]]] = {}
    for metadata in report["monitoring_files"]:
        key = (str(metadata["nested_archive"]), str(metadata["member"]))
        if key in completed:
            continue
        grouped.setdefault(str(metadata["nested_archive"]), []).append(metadata)

    processed_files = failed_files = upserted_samples = 0
    batch: list[tuple[dict[str, object], dict[str, dict[str, object]]]] = []
    with zipfile.ZipFile(archive) as outer:
        for nested_name, members in sorted(grouped.items()):
            with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as nested:
                for metadata in members:
                    try:
                        content = nested.read(str(metadata["member"]))
                        if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
                            raise ValueError("Monitoring FIT hash changed")
                        messages, errors = _decode_fit(content)
                        if errors:
                            raise ValueError("FIT decoder reported errors")
                        batch.append((metadata, extract_health_samples(messages)))
                        if len(batch) >= BATCH_SIZE:
                            upserted_samples += _commit_batch(
                                database_path=database_path,
                                archive_source_id=archive_source_id,
                                batch=batch,
                            )
                            processed_files += len(batch)
                            batch = []
                            if processed_files % 1000 == 0:
                                print(
                                    f"Imported {processed_files:,}/{report['monitoring_file_count']:,} monitoring FIT files",
                                    file=sys.stderr,
                                    flush=True,
                                )
                    except Exception:
                        failed_files += 1
            if batch:
                upserted_samples += _commit_batch(
                    database_path=database_path,
                    archive_source_id=archive_source_id,
                    batch=batch,
                )
                processed_files += len(batch)
                batch = []

    with connect(database_path) as connection:
        stored_samples = connection.execute(
            "SELECT COUNT(*) FROM health_samples WHERE source_name = ?",
            (GARMIN_SOURCE_NAME,),
        ).fetchone()[0]
    return {
        "status": "completed" if failed_files == 0 else "completed_with_failures",
        "monitoring_files": int(report["monitoring_file_count"]),
        "imported_files": processed_files,
        "resumed_files": len(completed),
        "failed_files": failed_files,
        "upserted_batch_samples": upserted_samples,
        "stored_health_samples": stored_samples,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Inventory or import health FIT data.")
    parser.add_argument("action", choices=("inventory", "preview", "import"))
    parser.add_argument("archive", nargs="?", type=Path)
    arguments = parser.parse_args()
    if arguments.action == "inventory":
        report = build_monitoring_inventory(arguments.archive)
        result = {
            "status": report["status"],
            "scanned_fit_files": report["scanned_fit_files"],
            "health_files": report["monitoring_file_count"],
            "candidate_samples": report["candidate_sample_count"],
            "candidate_values": report["candidate_value_counts"],
            "decode_failures": report["decode_failure_count"],
        }
    elif arguments.action == "preview":
        result = preview_health_fit_import(arguments.archive)
    else:
        result = import_health_fit_samples(arguments.archive)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
