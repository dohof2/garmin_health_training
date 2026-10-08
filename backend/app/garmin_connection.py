from __future__ import annotations

import os
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from garminconnect.client import token_file_path

from .config import data_directory
from .database import connect, migrate
from .sync import SyncConnectionRequired, SyncError


ClientFactory = Callable[..., Garmin]
_pending_lock = threading.Lock()
_pending_client: Garmin | None = None


def garmin_token_directory() -> Path:
    path = data_directory() / "credentials" / "garmin"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def garmin_token_file() -> Path:
    return token_file_path(str(garmin_token_directory()))


def _save_private_tokens(client: Garmin) -> None:
    """Persist only Garmin's session tokens and enforce owner-only access."""
    client.client.dump(str(garmin_token_directory()))
    token = garmin_token_file()
    if not token.is_file():
        raise GarminConnectAuthenticationError(
            "Garmin did not create a reusable session"
        )
    os.chmod(token, 0o600)


def _set_connection_status(
    status: str,
    path: Path | None = None,
    error_message: str | None = None,
) -> None:
    migrate(path)
    with connect(path) as connection:
        connection.execute(
            """
            UPDATE sync_settings
            SET connection_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (status,),
        )
        connection.execute(
            """
            UPDATE sync_checkpoints
            SET status = CASE
                    WHEN ? = 'connected' AND status = 'reconnect_required' THEN 'pending'
                    WHEN ? = 'connected' THEN status
                    ELSE 'reconnect_required'
                END,
                error_message = ?, updated_at = CURRENT_TIMESTAMP
            """,
            (status, status, error_message),
        )


def connection_state(path: Path | None = None) -> dict[str, object]:
    migrate(path)
    token = garmin_token_file()
    with connect(path) as connection:
        settings = connection.execute(
            "SELECT connection_status, updated_at FROM sync_settings WHERE id = 1"
        ).fetchone()
    with _pending_lock:
        mfa_pending = _pending_client is not None
    return {
        "status": "mfa_required" if mfa_pending else settings["connection_status"],
        "has_saved_session": token.is_file(),
        "mfa_pending": mfa_pending,
        "token_storage": "local_private_file",
        "updated_at": settings["updated_at"],
    }


def _friendly_error(error: Exception) -> str:
    if isinstance(error, GarminConnectTooManyRequestsError):
        return "Garmin temporarily rate-limited sign-in. Wait a few minutes before retrying."
    if isinstance(error, GarminConnectAuthenticationError):
        return "Garmin rejected the sign-in. Check the email/password or complete account verification."
    if isinstance(error, GarminConnectConnectionError):
        return "Garmin could not be reached or blocked the login request. Try again later."
    return "Garmin sign-in failed without storing the password."


def begin_login(
    email: str,
    password: str,
    path: Path | None = None,
    client_factory: ClientFactory = Garmin,
) -> dict[str, object]:
    global _pending_client
    if not email.strip() or not password:
        raise ValueError("Email and password are required")
    token_directory = garmin_token_directory()
    client = client_factory(
        email=email.strip(),
        password=password,
        return_on_mfa=True,
        verify_login=True,
    )
    try:
        mfa_status, _ = client.login(str(token_directory))
        client.password = None
        if mfa_status == "needs_mfa":
            with _pending_lock:
                _pending_client = client
            return {
                "status": "mfa_required",
                "message": "Enter the one-time code sent by Garmin.",
            }
        # garminconnect returns early when return_on_mfa=True, including for
        # successful non-MFA logins, so it does not persist tokens itself.
        _save_private_tokens(client)
        with _pending_lock:
            _pending_client = None
        _set_connection_status("connected", path)
        return {"status": "connected", "message": "Garmin connection established."}
    except Exception as error:
        client.password = None
        with _pending_lock:
            _pending_client = None
        _set_connection_status("reconnect_required", path, _friendly_error(error))
        raise SyncConnectionRequired(_friendly_error(error)) from error


def complete_mfa(code: str, path: Path | None = None) -> dict[str, object]:
    global _pending_client
    if not code.strip():
        raise ValueError("The Garmin verification code is required")
    with _pending_lock:
        client = _pending_client
    if client is None:
        raise SyncConnectionRequired("No Garmin MFA sign-in is waiting for a code")
    try:
        client.resume_login({}, code.strip())
        _save_private_tokens(client)
        client.password = None
        with _pending_lock:
            _pending_client = None
        _set_connection_status("connected", path)
        return {"status": "connected", "message": "Garmin connection established."}
    except Exception as error:
        client.password = None
        with _pending_lock:
            _pending_client = None
        _set_connection_status("reconnect_required", path, _friendly_error(error))
        raise SyncConnectionRequired(_friendly_error(error)) from error


def load_client(path: Path | None = None, client_factory: ClientFactory = Garmin) -> Garmin:
    token = garmin_token_file()
    if not token.is_file():
        _set_connection_status("not_connected", path)
        raise SyncConnectionRequired("Garmin Connect is not signed in")
    client = client_factory()
    try:
        client.login(str(garmin_token_directory()))
        _set_connection_status("connected", path)
        return client
    except Exception as error:
        _set_connection_status("reconnect_required", path, _friendly_error(error))
        raise SyncConnectionRequired(_friendly_error(error)) from error


def disconnect(path: Path | None = None, client_factory: ClientFactory = Garmin) -> dict[str, object]:
    global _pending_client
    token_directory = garmin_token_directory()
    try:
        client_factory().logout(str(token_directory))
    except Exception:
        garmin_token_file().unlink(missing_ok=True)
    with _pending_lock:
        _pending_client = None
    _set_connection_status("not_connected", path)
    return {"status": "not_connected", "message": "Saved Garmin session removed."}


def read_only_probe(path: Path | None = None, client_factory: ClientFactory = Garmin) -> dict[str, object]:
    client = load_client(path, client_factory)
    today = date.today().isoformat()
    try:
        summary = client.get_user_summary(today)
        activities = client.get_activities_by_date(today, today)
    except Exception as error:
        message = _friendly_error(error)
        if isinstance(error, GarminConnectAuthenticationError):
            _set_connection_status("reconnect_required", path, message)
        raise SyncError(message) from error
    return {
        "status": "ok",
        "date": today,
        "summary_available": bool(summary),
        "summary_fields": len(summary) if isinstance(summary, dict) else 0,
        "activities_today": len(activities) if isinstance(activities, list) else 0,
        "writes_performed": 0,
    }


def _iso_timestamp(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "T")
    if len(text) == 10:
        return text
    if text.endswith("Z") or "+" in text[10:] or "-" in text[10:]:
        return text
    return text + "Z"


def _activity_type(record: dict[str, object]) -> str:
    raw = record.get("activityType")
    if isinstance(raw, dict):
        return str(raw.get("typeKey") or raw.get("parentTypeId") or "unknown")
    return str(raw or record.get("activityTypeDTO") or "unknown")


def _normalise_activity(record: dict[str, object]) -> dict[str, object]:
    source_id = record.get("activityId") or record.get("activityUUID")
    if source_id is None:
        raise SyncError("Garmin activity response is missing its activity ID")
    started_at = _iso_timestamp(record.get("startTimeGMT") or record.get("startTimeLocal"))
    if not started_at:
        raise SyncError("Garmin activity response is missing its start time")
    timezone_value = record.get("timeZoneUnitDTO")
    timezone_name = (
        timezone_value.get("unitKey") if isinstance(timezone_value, dict) else None
    )
    return {
        "source_record_id": str(source_id),
        "activity_type": _activity_type(record),
        "name": record.get("activityName"),
        "started_at": started_at,
        "ended_at": None,
        "timezone": timezone_name,
        "duration_seconds": record.get("duration"),
        "distance_meters": record.get("distance"),
        "calories_kcal": record.get("calories"),
        "elevation_gain_meters": record.get("elevationGain"),
        "source_updated_at": _iso_timestamp(
            record.get("lastUpdated") or record.get("lastUpdateDate")
        ),
    }


DAILY_METRICS = {
    "totalSteps": ("steps", "count"),
    "totalDistanceMeters": ("distance", "m"),
    "totalKilocalories": ("total_calories", "kcal"),
    "activeKilocalories": ("active_calories", "kcal"),
    "bmrKilocalories": ("resting_calories", "kcal"),
    "restingHeartRate": ("resting_heart_rate", "bpm"),
    "minHeartRate": ("minimum_heart_rate", "bpm"),
    "maxHeartRate": ("maximum_heart_rate", "bpm"),
    "moderateIntensityMinutes": ("moderate_intensity", "min"),
    "vigorousIntensityMinutes": ("vigorous_intensity", "min"),
    "averageStressLevel": ("average_stress", "score"),
    "averageSpo2": ("average_spo2", "%"),
    "lowestSpo2": ("lowest_spo2", "%"),
    "avgWakingRespirationValue": ("waking_respiration", "breaths/min"),
    "bodyBatteryAtWakeTime": ("body_battery_at_wake", "score"),
    "bodyBatteryHighestValue": ("body_battery_high", "score"),
    "bodyBatteryLowestValue": ("body_battery_low", "score"),
    "bodyBatteryMostRecentValue": ("body_battery_latest", "score"),
    "bodyBatteryChargedValue": ("body_battery_charged", "score"),
    "bodyBatteryDrainedValue": ("body_battery_drained", "score"),
    "floorsAscended": ("floors_ascended", "count"),
    "floorsDescended": ("floors_descended", "count"),
    "dailyStepGoal": ("step_goal", "count"),
    "intensityMinutesGoal": ("intensity_minutes_goal", "min"),
    "activeSeconds": ("active_duration", "s"),
    "highlyActiveSeconds": ("highly_active_duration", "s"),
    "sedentarySeconds": ("sedentary_duration", "s"),
}


def _normalise_summary(record: dict[str, object], calendar_date: str) -> list[dict[str, object]]:
    source_updated = _iso_timestamp(record.get("lastUpdated") or record.get("lastUpdateDate"))
    metrics: list[dict[str, object]] = []
    for source_field, (metric_type, unit) in DAILY_METRICS.items():
        value = record.get(source_field)
        if value is None:
            continue
        metrics.append(
            {
                "source_record_id": f"daily:{calendar_date}",
                "metric_type": metric_type,
                "recorded_at": calendar_date,
                "value": value,
                "unit": unit,
                "period_start": calendar_date,
                "period_end": calendar_date,
                "source_updated_at": source_updated,
            }
        )
    return metrics


def _millisecond_timestamp(value: object) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, UTC).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return None


def _metric(
    source_record_id: str,
    metric_type: str,
    recorded_at: str,
    value: object,
    unit: str,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict[str, object] | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return {
        "source_record_id": source_record_id,
        "metric_type": metric_type,
        "recorded_at": recorded_at,
        "value": number,
        "unit": unit,
        "period_start": period_start or recorded_at,
        "period_end": period_end or recorded_at,
    }


def _normalise_sleep(record: object, calendar_date: str) -> list[dict[str, object]]:
    if not isinstance(record, dict):
        return []
    daily = record.get("dailySleepDTO")
    if not isinstance(daily, dict):
        return []
    source_id = f"sleep:{calendar_date}"
    period_start = _millisecond_timestamp(daily.get("sleepStartTimestampGMT"))
    period_end = _millisecond_timestamp(daily.get("sleepEndTimestampGMT"))
    fields = (
        ("sleepTimeSeconds", "sleep_duration", "s"),
        ("deepSleepSeconds", "deep_sleep", "s"),
        ("lightSleepSeconds", "light_sleep", "s"),
        ("remSleepSeconds", "rem_sleep", "s"),
        ("awakeSleepSeconds", "awake_sleep", "s"),
        ("unmeasurableSleepSeconds", "unmeasurable_sleep", "s"),
        ("averageRespirationValue", "sleep_respiration", "breaths/min"),
        ("avgSleepStress", "sleep_stress", "score"),
        ("restingHeartRate", "sleep_resting_heart_rate", "bpm"),
    )
    metrics = [
        metric
        for field, metric_type, unit in fields
        if (metric := _metric(source_id, metric_type, calendar_date, daily.get(field), unit, period_start, period_end))
    ]
    scores = daily.get("sleepScores")
    overall = scores.get("overall") if isinstance(scores, dict) else None
    score_value = overall.get("value") if isinstance(overall, dict) else None
    if metric := _metric(source_id, "sleep_score", calendar_date, score_value, "score", period_start, period_end):
        metrics.append(metric)
    for field, metric_type, unit in (
        ("avgOvernightHrv", "sleep_hrv_average", "ms"),
        ("bodyBatteryChange", "sleep_body_battery_change", "score"),
    ):
        if metric := _metric(source_id, metric_type, calendar_date, record.get(field), unit, period_start, period_end):
            metrics.append(metric)
    return metrics


def _normalise_hrv(record: object, calendar_date: str) -> list[dict[str, object]]:
    if not isinstance(record, dict):
        return []
    summary = record.get("hrvSummary")
    if not isinstance(summary, dict):
        return []
    source_id = f"hrv:{calendar_date}"
    metrics: list[dict[str, object]] = []
    for field, metric_type in (
        ("lastNightAvg", "hrv_last_night_average"),
        ("lastNight5MinHigh", "hrv_last_night_5min_high"),
        ("weeklyAvg", "hrv_weekly_average"),
    ):
        if metric := _metric(source_id, metric_type, calendar_date, summary.get(field), "ms"):
            metrics.append(metric)
    return metrics


def _normalise_weight(record: object, calendar_date: str) -> list[dict[str, object]]:
    if not isinstance(record, dict):
        return []
    summaries = record.get("dailyWeightSummaries")
    if not isinstance(summaries, list):
        return []
    metrics: list[dict[str, object]] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        samples = summary.get("allWeightMetrics")
        if not isinstance(samples, list):
            continue
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict):
                continue
            source_id = str(sample.get("samplePk") or f"weight:{calendar_date}:{index}")
            recorded_at = _millisecond_timestamp(sample.get("timestampGMT")) or calendar_date
            for field, metric_type, unit, divisor in (
                ("weight", "weight", "kg", 1000),
                ("bmi", "bmi", "kg/m2", 1),
                ("bodyFat", "body_fat", "%", 1),
                ("bodyWater", "body_water", "%", 1),
                ("boneMass", "bone_mass", "kg", 1000),
                ("muscleMass", "muscle_mass", "kg", 1000),
            ):
                raw = sample.get(field)
                value = float(raw) / divisor if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
                if metric := _metric(source_id, metric_type, recorded_at, value, unit):
                    metrics.append(metric)
    return metrics


class GarminConnectProvider:
    provider_name = "garmin_connect"
    connection_status = "connected"
    supports_updated_since = False

    def __init__(self, client: Garmin):
        self.client = client

    @classmethod
    def from_saved_session(cls, path: Path | None = None) -> "GarminConnectProvider":
        return cls(load_client(path))

    def fetch(self, data_type: str, start_date: date, end_date: date) -> list[dict[str, object]]:
        if data_type == "activities":
            records = self.client.get_activities_by_date(
                start_date.isoformat(), end_date.isoformat()
            )
            return [_normalise_activity(dict(record)) for record in records]
        if data_type == "daily_metrics":
            metrics: list[dict[str, object]] = []
            day = start_date
            while day <= end_date:
                summary = self.client.get_user_summary(day.isoformat())
                if isinstance(summary, dict):
                    metrics.extend(_normalise_summary(summary, day.isoformat()))
                day = date.fromordinal(day.toordinal() + 1)
            return metrics
        if data_type == "sleep_metrics":
            metrics: list[dict[str, object]] = []
            day = start_date
            while day <= end_date:
                metrics.extend(_normalise_sleep(self.client.get_sleep_data(day.isoformat()), day.isoformat()))
                day = date.fromordinal(day.toordinal() + 1)
            return metrics
        if data_type == "hrv_metrics":
            metrics: list[dict[str, object]] = []
            day = start_date
            while day <= end_date:
                metrics.extend(_normalise_hrv(self.client.get_hrv_data(day.isoformat()), day.isoformat()))
                day = date.fromordinal(day.toordinal() + 1)
            return metrics
        if data_type == "weight_metrics":
            records = self.client.get_weigh_ins(start_date.isoformat(), end_date.isoformat())
            return _normalise_weight(records, start_date.isoformat())
        raise SyncError(f"Unsupported Garmin data type: {data_type}")

    def fetch_activity_detail(self, source_record_id: str) -> bytes:
        """Download Garmin's original FIT bundle for sensor-level samples."""
        return self.client.download_activity(
            source_record_id,
            Garmin.ActivityDownloadFormat.ORIGINAL,
        )
