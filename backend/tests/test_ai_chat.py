from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from os import environ
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import ai_chat
from app.ai_chat import chat_stream
from app.ai_providers import save_ai_settings


def _health_result() -> dict[str, object]:
    return {
        "tool": "get_health_summary",
        "period": {"start": "2026-10-01", "end": "2026-10-08"},
        "metrics": [],
        "requested_metric_types": ["steps"],
        "missing_metric_types": [],
        "freshness": {
            "latest_recorded_at": "2026-10-08",
            "sources": ["garmin_export"],
        },
        "evidence": {
            "record_count": 8,
            "record_endpoint": "/api/metrics",
            "period": {"start": "2026-10-01", "end": "2026-10-08"},
        },
    }


class FakeResponse:
    def __init__(self, payload: dict[str, object] | None = None, lines: list[bytes] | None = None) -> None:
        self.payload = payload or {}
        self.lines = lines or []

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __iter__(self):
        return iter(self.lines)


class AIChatTests(unittest.TestCase):
    def test_similar_ride_questions_force_the_scoped_matcher(self) -> None:
        self.assertEqual(
            ai_chat._forced_tool_name("Find rides similar to my latest ride"),
            "find_similar_rides",
        )
        self.assertIsNone(ai_chat._forced_tool_name("List my latest rides"))
        self.assertEqual(
            ai_chat._forced_tool_name("How have I improved on this GPS course?"),
            "find_same_course_rides",
        )
        self.assertIn(
            "candidate_pool_count",
            ai_chat._answer_guardrail("Find rides similar to my latest ride"),
        )
        self.assertIn(
            "raw GPS coordinates were not provided",
            ai_chat._answer_guardrail("How have I improved on this GPS course?"),
        )
        self.assertEqual(
            ai_chat._normalize_tool_arguments(
                "find_similar_rides",
                {"reference_activity_id": "invented", "limit": 5},
                "Find rides similar to my latest ride",
            ),
            {"limit": 5},
        )

    def test_relative_period_resolves_last_days_deterministically(self) -> None:
        with patch("app.ai_chat.date") as mocked_date:
            mocked_date.today.return_value = date(2026, 10, 8)
            self.assertEqual(
                ai_chat._relative_period("Summarize the last seven days"),
                ("2026-10-02", "2026-10-08"),
            )

    def test_same_course_answer_uses_only_computed_progress(self) -> None:
        answer = ai_chat._same_course_answer(
            {
                "reference_ride": {"name": "Loop", "local_date": "2026-10-06"},
                "total_matches": 3,
                "course_progress": {
                    "attempt_count": 4,
                    "earliest": {"local_date": "2025-01-01"},
                    "latest": {"local_date": "2026-10-06"},
                    "changes_latest_minus_earliest": [
                        {
                            "metric": "duration",
                            "earliest": 1.0,
                            "latest": 0.9,
                            "unit": "hours",
                            "percent": -10.0,
                        }
                    ],
                },
            }
        )
        self.assertIn("3 other course attempts", answer)
        self.assertIn("4 matched attempts", answer)
        self.assertIn("latest attempt was faster", answer)
        self.assertIn("not proof of improved fitness", answer)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "chat.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @patch("app.ai_chat.execute_tool", return_value=_health_result())
    @patch("app.ai_chat.OpenAI")
    def test_openai_executes_registered_tool_then_streams_grounded_answer(
        self,
        openai_class: MagicMock,
        execute_tool: MagicMock,
    ) -> None:
        save_ai_settings(
            {
                "active_provider": "openai",
                "ollama_model": "qwen3.5:2b",
                "openai_model": "gpt-6-astra",
            },
            self.database,
        )
        planning = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call-1",
                    name="get_health_summary",
                    arguments=json.dumps(
                        {
                            "start_date": "2026-10-01",
                            "end_date": "2026-10-08",
                            "metric_types": ["steps"],
                        }
                    ),
                )
            ],
            output_text="",
        )
        streamed = [
            SimpleNamespace(type="response.output_text.delta", delta="Grounded "),
            SimpleNamespace(type="response.output_text.delta", delta="answer."),
        ]
        openai_class.return_value.responses.create.side_effect = [planning, streamed]

        with patch.dict(environ, {"OPENAI_API_KEY": "secret-test-key"}):
            events = [json.loads(line) for line in chat_stream(
                "How were my steps?",
                timezone_name="Asia/Jerusalem",
                path=self.database,
            )]

        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[1]["type"], "tool")
        self.assertEqual(events[1]["evidence"]["record_count"], 8)
        self.assertEqual("".join(item.get("text", "") for item in events), "Grounded answer.")
        self.assertEqual(events[-1]["type"], "complete")
        execute_tool.assert_called_once()
        calls = openai_class.return_value.responses.create.call_args_list
        self.assertFalse(calls[0].kwargs["store"])
        self.assertEqual(calls[1].kwargs["tool_choice"], "none")
        self.assertTrue(calls[1].kwargs["stream"])
        self.assertNotIn("secret-test-key", str(events))

    @patch("app.ai_chat.execute_tool", return_value=_health_result())
    @patch("app.ai_chat._ollama_request")
    def test_ollama_uses_same_tool_and_stream_event_contract(
        self,
        ollama_request: MagicMock,
        execute_tool: MagicMock,
    ) -> None:
        save_ai_settings(
            {
                "active_provider": "ollama",
                "ollama_model": "qwen3.5:2b",
                "openai_model": "gpt-6-astra",
            },
            self.database,
        )
        planner = FakeResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_health_summary",
                                "arguments": {
                                    "start_date": "2026-10-01",
                                    "end_date": "2026-10-08",
                                    "metric_types": ["steps"],
                                },
                            }
                        }
                    ],
                }
            }
        )
        stream = FakeResponse(
            lines=[
                b'{"message":{"content":"Local "},"done":false}\n',
                b'{"message":{"content":"answer."},"done":true}\n',
            ]
        )
        ollama_request.side_effect = [planner, stream]

        events = [json.loads(line) for line in chat_stream(
            "How were my steps?",
            timezone_name="Asia/Jerusalem",
            path=self.database,
        )]

        self.assertEqual(events[0]["provider"], "ollama")
        self.assertEqual(events[1]["type"], "tool")
        self.assertEqual("".join(item.get("text", "") for item in events), "Local answer.")
        self.assertEqual(events[-1]["type"], "complete")
        execute_tool.assert_called_once()
        self.assertEqual(ollama_request.call_count, 2)
        final_payload = ollama_request.call_args_list[1].args[0]
        self.assertTrue(final_payload["stream"])
        self.assertFalse(final_payload["think"])
        self.assertNotIn("tools", final_payload)

    def test_missing_openai_key_returns_safe_error_event(self) -> None:
        save_ai_settings(
            {
                "active_provider": "openai",
                "ollama_model": "qwen3.5:2b",
                "openai_model": "gpt-6-astra",
            },
            self.database,
        )
        with patch.dict(environ, {}, clear=True):
            events = [json.loads(line) for line in chat_stream(
                "Hello", path=self.database
            )]
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(
            events[-1]["message"],
            "OpenAI is selected but OPENAI_API_KEY is not configured.",
        )

    def test_rejects_invalid_or_oversized_history(self) -> None:
        with self.assertRaisesRegex(ValueError, "message is required"):
            list(chat_stream("", path=self.database))
        with self.assertRaisesRegex(ValueError, "at most 20"):
            list(
                chat_stream(
                    "Question",
                    history=[{"role": "user", "content": "x"}] * 21,
                    path=self.database,
                )
            )


if __name__ == "__main__":
    unittest.main()
