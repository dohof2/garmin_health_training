from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .database import connect, migrate


SYNTHETIC_SOURCE_NAME = "synthetic_fixture"
SYNTHETIC_SOURCE_FILE_ID = "synthetic-fixture-history-v1"
SYNTHETIC_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_history.json"
)


def seed_synthetic_history(path: Path | None = None) -> dict[str, int]:
    """Idempotently load clearly labeled synthetic history into SQLite."""
    migrate(path)
    content = SYNTHETIC_FIXTURE.read_bytes()
    fixture = json.loads(content)

    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO source_files(
                id, original_name, content_hash, media_type, byte_size, stored_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content_hash = excluded.content_hash,
                byte_size = excluded.byte_size,
                stored_path = excluded.stored_path
            """,
            (
                SYNTHETIC_SOURCE_FILE_ID,
                SYNTHETIC_FIXTURE.name,
                hashlib.sha256(content).hexdigest(),
                "application/json",
                len(content),
                str(SYNTHETIC_FIXTURE),
            ),
        )

        for activity in fixture["activities"]:
            connection.execute(
                """
                INSERT INTO activities(
                    id, source_name, source_record_id, source_file_id,
                    activity_type, name, started_at, ended_at, timezone,
                    duration_seconds, distance_meters, calories_kcal,
                    elevation_gain_meters, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
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
                    SYNTHETIC_SOURCE_NAME,
                    activity["source_record_id"],
                    SYNTHETIC_SOURCE_FILE_ID,
                    activity["activity_type"],
                    activity["name"],
                    activity["started_at"],
                    activity["ended_at"],
                    activity["timezone"],
                    activity["duration_seconds"],
                    activity["distance_meters"],
                    activity["calories_kcal"],
                    activity["elevation_gain_meters"],
                    json.dumps(activity, separators=(",", ":")),
                ),
            )

        for sample in fixture["activity_samples"]:
            connection.execute(
                """
                INSERT INTO activity_samples(
                    activity_id, recorded_at, heart_rate_bpm, cadence_rpm,
                    power_watts, speed_mps, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, recorded_at) DO UPDATE SET
                    heart_rate_bpm = excluded.heart_rate_bpm,
                    cadence_rpm = excluded.cadence_rpm,
                    power_watts = excluded.power_watts,
                    speed_mps = excluded.speed_mps,
                    raw_json = excluded.raw_json
                """,
                (
                    sample["activity_id"],
                    sample["recorded_at"],
                    sample["heart_rate_bpm"],
                    sample["cadence_rpm"],
                    sample["power_watts"],
                    sample["speed_mps"],
                    json.dumps(sample, separators=(",", ":")),
                ),
            )

        for metric in fixture["metric_readings"]:
            connection.execute(
                """
                INSERT INTO metric_readings(
                    id, source_name, source_record_id, source_file_id,
                    metric_type, recorded_at, value, unit, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    metric_type = excluded.metric_type,
                    recorded_at = excluded.recorded_at,
                    value = excluded.value,
                    unit = excluded.unit,
                    raw_json = excluded.raw_json
                """,
                (
                    metric["id"],
                    SYNTHETIC_SOURCE_NAME,
                    metric["source_record_id"],
                    SYNTHETIC_SOURCE_FILE_ID,
                    metric["metric_type"],
                    metric["recorded_at"],
                    metric["value"],
                    metric["unit"],
                    json.dumps(metric, separators=(",", ":")),
                ),
            )

    return {
        "activities": len(fixture["activities"]),
        "activity_samples": len(fixture["activity_samples"]),
        "metric_readings": len(fixture["metric_readings"]),
    }


if __name__ == "__main__":
    counts = seed_synthetic_history()
    print(
        "Loaded synthetic history: "
        f"{counts['activities']} activities, "
        f"{counts['activity_samples']} samples, "
        f"{counts['metric_readings']} metrics."
    )
