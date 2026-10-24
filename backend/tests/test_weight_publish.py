import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.charts import add_weight
from app.database import migrate
from app.sync import SyncConnectionRequired
from app.weight_publish import publish


class WeightPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        migrate(self.path)
        self.saved = add_weight('2026-10-23', 176, 'lb', self.path)
        self.transport = Mock()
        self.transport.post.return_value = Mock(status_code=200)
        self.client = SimpleNamespace(client=self.transport, garmin_connect_weight_url='/weight-service')
        self.factory = lambda path: self.client
        self.now = datetime(2026, 10, 24, 5, tzinfo=UTC)

    def send(self, reading=None, **kwargs):
        return publish(reading or self.saved['id'], 'Asia/Jerusalem', self.path, kwargs.get('factory', self.factory), self.now)

    def test_converts_pounds_preserves_date_and_only_sends_once(self):
        self.assertEqual(self.send()['status'], 'sent')
        payload = self.transport.post.call_args.kwargs['json']
        self.assertAlmostEqual(payload['value'], 79.83225712)
        self.assertEqual(payload['unitKey'], 'kg')
        self.assertEqual(payload['dateTimestamp'], '2026-10-23T12:00:00.000')
        self.assertEqual(payload['gmtTimestamp'], '2026-10-23T09:00:00.000')
        self.assertEqual(self.send()['status'], 'sent')
        self.assertEqual(self.transport.post.call_count, 1)

    def test_lost_response_never_retries(self):
        self.transport.post.side_effect = TimeoutError('private response')
        answer = self.send()
        self.assertEqual(answer['status'], 'unknown')
        self.assertNotIn('private', answer['message'])
        self.assertEqual(self.send()['status'], 'unknown')
        self.assertEqual(self.transport.post.call_count, 1)

    def test_not_signed_in_can_send_later_without_resaving(self):
        def disconnected(path):
            raise SyncConnectionRequired('private')
        self.assertEqual(self.send(factory=disconnected)['status'], 'not_connected')
        self.transport.post.assert_not_called()
        self.assertEqual(self.send()['status'], 'sent')

    def test_invalid_reading_timezone_and_future_do_not_send(self):
        with self.assertRaises(ValueError):
            self.send('missing')
        with self.assertRaises(ValueError):
            publish(self.saved['id'], 'invalid', self.path, self.factory, self.now)
        future = add_weight('2026-10-25', 80, 'kg', self.path)
        with self.assertRaises(ValueError):
            self.send(future['id'])
        self.transport.post.assert_not_called()

    def test_today_uses_actual_time_and_empty_response_is_uncertain(self):
        today = add_weight('2026-10-24', 80, 'kg', self.path)
        self.transport.post.return_value = None
        self.assertEqual(self.send(today['id'])['status'], 'unknown')
        self.assertEqual(self.transport.post.call_args.kwargs['json']['dateTimestamp'], '2026-10-24T08:00:00.000')
