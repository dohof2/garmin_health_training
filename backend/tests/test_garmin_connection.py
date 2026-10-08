from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

from garminconnect import GarminConnectAuthenticationError

from app.garmin_connection import (
    GarminConnectProvider,
    begin_login,
    complete_mfa,
    connection_state,
    disconnect,
    garmin_token_file,
    load_client,
    read_only_probe,
)
from app.sync import SyncConnectionRequired


class _FakeTokenClient:
    def __init__(self, owner: "FakeGarmin"):
        self.owner = owner

    def dump(self, path: str) -> None:
        target = Path(path) / "garmin_tokens.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"test": "token"}), encoding="utf-8")
        target.chmod(0o600)


class FakeGarmin:
    require_mfa = False
    fail_login = False
    fail_saved_login = False
    instances: list["FakeGarmin"] = []

    def __init__(self, email=None, password=None, **kwargs):
        self.email = email
        self.password = password
        self.return_on_mfa = kwargs.get("return_on_mfa", False)
        self.client = _FakeTokenClient(self)
        self.__class__.instances.append(self)

    def login(self, tokenstore: str):
        if self.fail_login:
            raise GarminConnectAuthenticationError("secret response")
        if self.fail_saved_login and not self.email:
            raise GarminConnectAuthenticationError("expired saved token")
        if self.require_mfa and self.email:
            return "needs_mfa", None
        if not self.email and not (Path(tokenstore) / "garmin_tokens.json").is_file():
            raise GarminConnectAuthenticationError("missing token")
        return None, None

    def resume_login(self, _state, code: str):
        if code != "123456":
            raise GarminConnectAuthenticationError("bad code")
        return None, None

    def logout(self, tokenstore: str):
        (Path(tokenstore) / "garmin_tokens.json").unlink(missing_ok=True)

    def get_user_summary(self, calendar_date: str):
        return {
            "calendarDate": calendar_date,
            "totalSteps": 8000,
            "totalKilocalories": 2200,
            "restingHeartRate": 52,
        }

    def get_activities_by_date(self, start: str, end: str):
        return [
            {
                "activityId": 42,
                "activityName": "Morning Ride",
                "activityType": {"typeKey": "cycling"},
                "startTimeGMT": f"{start} 06:00:00",
                "duration": 3600,
                "distance": 24000,
                "calories": 650,
                "elevationGain": 320,
                "lastUpdated": f"{end} 09:00:00",
            }
        ]


@contextmanager
def _local_data(root: Path):
    FakeGarmin.require_mfa = False
    FakeGarmin.fail_login = False
    FakeGarmin.fail_saved_login = False
    FakeGarmin.instances.clear()
    with patch.dict(os.environ, {"HT_APP_DATA_DIR": str(root.resolve())}):
        yield
        disconnect(client_factory=FakeGarmin)


class GarminConnectionTests(unittest.TestCase):
    def test_password_is_not_saved_and_tokens_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _local_data(Path(temporary)):
            result = begin_login(
                "person@example.com",
                "private-password",
                client_factory=FakeGarmin,
            )

            self.assertEqual(result["status"], "connected")
            self.assertIsNone(FakeGarmin.instances[-1].password)
            self.assertTrue(garmin_token_file().is_file())
            self.assertEqual(garmin_token_file().stat().st_mode & 0o777, 0o600)
            self.assertNotIn("private-password", garmin_token_file().read_text())

    def test_mfa_resumes_the_pending_login(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _local_data(Path(temporary)):
            FakeGarmin.require_mfa = True
            first = begin_login("person@example.com", "password", client_factory=FakeGarmin)
            self.assertEqual(first["status"], "mfa_required")
            self.assertTrue(connection_state()["mfa_pending"])

            completed = complete_mfa("123456")
            self.assertEqual(completed["status"], "connected")
            self.assertFalse(connection_state()["mfa_pending"])
            self.assertTrue(garmin_token_file().is_file())

    def test_read_only_probe_returns_counts_not_private_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _local_data(Path(temporary)):
            begin_login("person@example.com", "password", client_factory=FakeGarmin)
            result = read_only_probe(client_factory=FakeGarmin)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["writes_performed"], 0)
            self.assertEqual(result["activities_today"], 1)
            self.assertNotIn("summary", result)

    def test_saved_session_reuse_expiry_sign_out_and_reconnect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _local_data(Path(temporary)):
            begin_login("person@example.com", "password", client_factory=FakeGarmin)

            restored = load_client(client_factory=FakeGarmin)
            self.assertIsNone(restored.email)
            self.assertEqual(connection_state()["status"], "connected")

            FakeGarmin.fail_saved_login = True
            with self.assertRaises(SyncConnectionRequired):
                load_client(client_factory=FakeGarmin)
            self.assertEqual(connection_state()["status"], "reconnect_required")

            FakeGarmin.fail_saved_login = False
            signed_out = disconnect(client_factory=FakeGarmin)
            self.assertEqual(signed_out["status"], "not_connected")
            self.assertFalse(garmin_token_file().exists())

            reconnected = begin_login(
                "person@example.com", "new-password", client_factory=FakeGarmin
            )
            self.assertEqual(reconnected["status"], "connected")
            self.assertTrue(garmin_token_file().is_file())

    def test_live_provider_normalises_activity_and_daily_metrics(self) -> None:
        client = FakeGarmin()
        provider = GarminConnectProvider(client)
        activities = provider.fetch("activities", date(2026, 10, 8), date(2026, 10, 8))
        metrics = provider.fetch("daily_metrics", date(2026, 10, 8), date(2026, 10, 8))

        self.assertEqual(activities[0]["source_record_id"], "42")
        self.assertEqual(activities[0]["started_at"], "2026-10-08T06:00:00Z")
        self.assertEqual(
            {metric["metric_type"] for metric in metrics},
            {"steps", "total_calories", "resting_heart_rate"},
        )

    def test_authentication_errors_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _local_data(Path(temporary)):
            FakeGarmin.fail_login = True
            with self.assertRaises(SyncConnectionRequired) as raised:
                begin_login(
                    "person@example.com",
                    "private-password",
                    client_factory=FakeGarmin,
                )
            self.assertNotIn("private-password", str(raised.exception))
            self.assertNotIn("secret response", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
