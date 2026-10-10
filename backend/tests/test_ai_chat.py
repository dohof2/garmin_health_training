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
    def test_matching_followups_preserve_user_reference_and_handle_actual_typos(self):
        history = [{'role':'user','content':'What rides match my ride on September 27th?'},
                   {'role':'assistant','content':'There are no rides on October 9th.'}]
        with patch('app.ai_chat._today', return_value=date(2026,10,10)):
            followup = ai_chat._matching_followup('and for the ride on OC 6th?',history,'Asia/Jerusalem')
            self.assertEqual(ai_chat._forced_tool_name(followup),'find_same_course_rides')
            self.assertEqual(ai_chat._ride_reference_date(followup),'2026-10-06')
            gps = ai_chat._matching_followup('match using GPS',history,'Asia/Jerusalem')
            self.assertEqual(ai_chat._ride_reference_date(gps),'2026-09-27')
            for message in ('is ther mathced ride fir the oct 6th ride?', 'is there mathced ride for the ride on oct 6th ?'):
                self.assertEqual(ai_chat._forced_tool_name(message),'find_same_course_rides')
                self.assertEqual(ai_chat._ride_reference_date(message),'2026-10-06')
            unrelated = 'What maintenance did I do on October 6th?'
            self.assertEqual(ai_chat._matching_followup(unrelated,history,'Asia/Jerusalem'), unrelated)

    def test_named_ride_dates_and_typos_select_reference_not_candidate_period(self):
        with patch('app.ai_chat._today', return_value=date(2026,10,10)):
            for phrase in ('September 27th', 'Sep 27', 'Sept 27 th', '27th of September', 'septmeber 27th', '2026-09-27'):
                message = f'what re the rides maching my ride on {phrase}?'
                self.assertEqual(ai_chat._forced_tool_name(message), 'find_same_course_rides')
                args = ai_chat._normalize_tool_arguments('find_similar_rides', {
                    'reference_activity_id':'invented', 'reference_date':'2026-10-09',
                    'candidate_start_date':'2026-09-27','candidate_end_date':'2026-09-27'}, message, 'Asia/Jerusalem')
                self.assertEqual(args, {'reference_date':'2026-09-27'})
            self.assertEqual(ai_chat._ride_reference_date('December 27th'), '2025-12-27')
            self.assertEqual(ai_chat._ride_reference_date('September 27th 2024'), '2024-09-27')

    def test_date_matching_stream_is_grounded_without_model_inference(self):
        from app.database import connect, migrate
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'rides.sqlite3'
            migrate(db)
            with connect(db) as c:
                for ident, day in (('reference','2026-09-27'),('match','2026-09-01'),('latest','2026-10-09')):
                    c.execute("INSERT INTO activities(id,source_name,name,activity_type,started_at,duration_seconds,distance_meters,elevation_gain_meters) VALUES(?,'synthetic',?,'cycling',?,3600,20000,100)", (ident,ident,day+'T06:00:00Z'))
                    c.executemany("INSERT INTO activity_samples(activity_id, recorded_at, latitude, longitude) VALUES(?,?,?,?)", [(ident,day+f'T06:00:{i:02d}Z',32+i*.001+(1 if ident=='latest' else 0),34+i*.001) for i in range(12)])
                c.execute("UPDATE activities SET distance_meters=80000,duration_seconds=14000 WHERE id='match'")
            with patch('app.ai_chat._today', return_value=date(2026,10,10)), patch('app.ai_chat._ollama_request') as model:
                events = [json.loads(line) for line in chat_stream('and for the ride on Sep 27th?', history=[{'role':'user','content':'Find matching rides for my latest ride'}], timezone_name='Asia/Jerusalem',path=db)]
            model.assert_not_called()
            self.assertFalse(any(e['type']=='error' for e in events), events)
            evidence = next(e['evidence'] for e in events if e['type']=='tool')
            self.assertEqual(evidence['reference_record']['id'], 'reference')
            self.assertEqual(evidence['total_matches'], 1)
            self.assertEqual(evidence['records'][0]['id'], 'match')
            answer = next(e['text'] for e in events if e['type']=='delta')
            self.assertIn('2026-09-27',answer)
            self.assertIn('1 other course attempts',answer)
            self.assertEqual(evidence['tool'], 'find_same_course_rides')
            self.assertIn('full stored history',answer)
            with connect(db) as c:
                c.execute("UPDATE activities SET started_at='2026-10-06T06:00:00Z' WHERE id='reference'")
            previous = [{'role':'user','content':'What rides match my ride on September 27th?'}]
            with patch('app.ai_chat._today', return_value=date(2026,10,10)), patch('app.ai_chat._ollama_request') as model, patch('app.ai_chat.maintenance_chat') as maintenance:
                for question in ('and for the ride on OC 6th?', 'is ther mathced ride fir the oct 6th ride?', 'is there mathced ride for the ride on oct 6th ?'):
                    events = [json.loads(line) for line in chat_stream(question, history=previous, timezone_name='Asia/Jerusalem',path=db)]
                    self.assertFalse(any(e['type']=='error' for e in events), events)
                    evidence = next(e['evidence'] for e in events if e['type']=='tool')
                    self.assertEqual(evidence['tool'],'find_same_course_rides')
                    self.assertEqual(evidence['reference_record']['local_date'],'2026-10-06')
                    self.assertEqual(evidence['total_matches'],1)
            model.assert_not_called()
            maintenance.assert_not_called()


    def test_similar_ride_questions_force_the_scoped_matcher(self) -> None:
        self.assertEqual(
            ai_chat._forced_tool_name("Find rides similar to my latest ride"),
            "find_same_course_rides",
        )
        self.assertIsNone(ai_chat._forced_tool_name("List my latest rides"))
        self.assertEqual(
            ai_chat._forced_tool_name("How have I improved on this GPS course?"),
            "find_same_course_rides",
        )
        self.assertIn(
            "candidate_pool_count",
            ai_chat._answer_guardrail("Find rides similar to my latest ride by distance"),
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
