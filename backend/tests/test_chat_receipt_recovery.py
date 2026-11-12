"""A refresh recovers the saved response without executing the request again."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.database import migrate, connect
from app.skill_agent import read_turn


class ChatReceiptRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        migrate(self.path)
        self.events = [
            {'type': 'tool', 'evidence': {'tool': 'lookup_workouts'}},
            {'type': 'delta', 'text': 'Your calf-raise proposal is ready.'},
            {'type': 'complete', 'workflow': 'skills'},
        ]
        with connect(self.path) as c:
            c.execute("INSERT INTO assistant_skill_sessions(conversation_id) VALUES(?)", ('conversation',))
            c.execute("INSERT INTO assistant_skill_turns(operation_id,conversation_id,request_hash,status,events_json) VALUES(?,?,?,?,?)",
                      ('operation', 'conversation', 'hash', 'review', json.dumps(self.events)))

    def test_reads_finished_answer_without_provider_or_tool_execution(self):
        with patch('app.skill_agent.active_provider') as provider, patch('app.skill_agent.execute') as execute:
            self.assertEqual(read_turn('operation', 'conversation', self.path),
                             {'status': 'review', 'events': self.events})
        provider.assert_not_called()
        execute.assert_not_called()

    def test_receipt_is_scoped_to_conversation(self):
        with self.assertRaises(KeyError):
            read_turn('operation', 'other-conversation', self.path)

    def test_running_receipt_stays_running(self):
        with connect(self.path) as c:
            c.execute("UPDATE assistant_skill_turns SET status='running',events_json='[]'")
        self.assertEqual(read_turn('operation', 'conversation', self.path), {'status': 'running', 'events': []})
