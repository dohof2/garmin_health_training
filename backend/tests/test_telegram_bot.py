import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import connect, migrate
from app import telegram_bot as bot
from app.chat_access import questions_only, READ_ONLY, QUESTION_TOOLS
from app.ai_tools import execute_tool, tool_definitions
from app.telegram_routes import router


class FakeTelegram:
    def __init__(self, bot_id=99):
        self.bot_id = bot_id
        self.sent = []

    def call(self, method, **payload):
        if method == 'getMe':
            return {'id': self.bot_id, 'username': 'fictional_garmin_test_bot', 'is_bot': True}
        if method == 'getWebhookInfo':
            return {'url': ''}
        if method == 'sendMessage':
            self.sent.append(payload)
            return {'message_id': 1000+len(self.sent)}
        return []


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'test.sqlite3'
        migrate(self.path)
        self.client = FakeTelegram()

    def configure(self):
        result = bot.configure('Asia/Jerusalem', self.path, self.client)
        return parse_qs(urlsplit(result['url']).query)['start'][0]

    def update(self, number, text, user=10, chat=10, kind='private', **extra):
        return {'update_id': number, 'message': {'message_id': number, 'date': time.time(),
                'chat': {'id': chat, 'type': kind}, 'from': {'id': user}, 'text': text, **extra}}

    def pair(self):
        code = self.configure()
        bot.intake([self.update(1, '/start '+code)], 99, self.path)
        bot.process_one(self.path)
        bot.deliver_one(self.client, self.path)
        return code

    def rows(self, table):
        with connect(self.path) as c:
            return [dict(r) for r in c.execute('SELECT * FROM '+table)]


    def test_questions_only_denies_writes_exports_and_unadvertised_tools(self):
        with questions_only():
            self.assertEqual({d['name'] for d in tool_definitions()}, QUESTION_TOOLS)
            for name in ('log_maintenance', 'propose_settings_change', 'export_maintenance', 'create_plots'):
                with self.assertRaisesRegex(ValueError, 'questions only'):
                    execute_tool(name, {}, self.path)
            with self.assertRaises(sqlite3.OperationalError):
                with connect(self.path) as c:
                    c.execute("UPDATE telegram_settings SET enabled=1")
            self.assertEqual(migrate(self.path), [])
        self.assertFalse(READ_ONLY.get())

    def test_shared_read_tools_still_work_in_questions_only_scope(self):
        with questions_only():
            result = execute_tool('get_health_summary', {'start_date':'2026-01-01', 'end_date':'2026-01-02'}, self.path)
            self.assertIsInstance(result, dict)
            execute_tool('query_app_data', {'dataset':'profile','start_date':'2026-01-01','end_date':'2026-01-02'}, self.path)
            execute_tool('query_app_data', {'dataset':'nutrition','start_date':'2026-01-01','end_date':'2026-01-01'}, self.path)
            execute_tool('get_active_training_plan', {}, self.path)
            execute_tool('get_training_readiness', {'timezone':'Asia/Jerusalem'}, self.path)
            execute_tool('get_projected_training_readiness', {'timezone':'Asia/Jerusalem'}, self.path)
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM readiness_settings').fetchone()[0], 0)


    def test_keychain_failures_never_include_output(self):
        result = type('Result', (), {'returncode':1, 'stdout':b'fake-secret', 'stderr':b'fake-secret'})()
        with patch('app.telegram_bot.subprocess.run', return_value=result):
            with self.assertRaises(bot.TelegramError) as caught:
                bot.load_token()
        self.assertNotIn('fake-secret', str(caught.exception))


    def test_webhook_is_not_silently_removed(self):
        def call(method, **payload):
            return {'id':99,'is_bot':True,'username':'test'} if method=='getMe' else {'url':'https://example.com'}
        with patch.object(self.client, 'call', side_effect=call):
            with self.assertRaisesRegex(bot.TelegramError, 'webhook'):
                bot.configure('UTC', self.path, self.client)
        self.assertFalse(bot.status(self.path)['enabled'])

    def test_local_routes_reject_remote_origins_and_host_rebinding(self):
        app = FastAPI()
        app.include_router(router)
        with patch('app.telegram_bot.configuration', return_value=bot.configuration(self.path)), patch('app.telegram_bot.status', return_value={'enabled':False}):
            with TestClient(app, client=('127.0.0.1', 40000), base_url='http://127.0.0.1:8765') as client:
                self.assertEqual(client.get('/api/telegram/status').status_code, 200)
                for headers in ({'origin':'https://evil.example'}, {'host':'evil.example:8765'}, {'sec-fetch-site':'cross-site'}):
                    self.assertEqual(client.get('/api/telegram/status', headers=headers).status_code, 403)
                self.assertEqual(client.post('/api/telegram/disable').status_code, 403)
                with patch('app.telegram_bot.disable', return_value={'enabled':False}):
                    self.assertEqual(client.post('/api/telegram/disable', headers={'x-garmin-local-action':'telegram-setup','origin':'http://127.0.0.1:8765'}).status_code, 200)


    def test_disabled_worker_never_reads_keychain(self):
        worker = bot.TelegramWorker(self.path)
        with patch('app.telegram_bot.load_token') as credential:
            worker.start()
            worker.stop()
        credential.assert_not_called()
        self.assertFalse(worker.thread.is_alive())

    def test_reply_to_previous_answer_is_retained(self):
        self.pair()
        bot.intake([self.update(2, 'first')], 99, self.path)
        bot.process_one(self.path, lambda *args: 'answer about recorded ride')
        bot.deliver_one(self.client, self.path)
        bot.intake([self.update(3, 'that ride?', reply_to_message={'message_id': 1002})], 99, self.path)
        seen = []
        bot.process_one(self.path, lambda text, history, *args: seen.extend(history) or 'follow-up')
        self.assertTrue(any('Reply refers' in row['content'] for row in seen))

    def test_duplicate_updates_process_and_deliver_once(self):
        self.pair()
        update = self.update(2, 'How did I sleep?')
        bot.intake([update, update], 99, self.path)
        calls = []
        def answer(*args):
            calls.append(args)
            return 'Fictional grounded answer'
        self.assertTrue(bot.process_one(self.path, answer))
        self.assertFalse(bot.process_one(self.path, answer))
        bot.deliver_one(self.client, self.path)
        self.assertFalse(bot.deliver_one(self.client, self.path))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.client.sent), 2)

    def test_groups_wrong_sender_wrong_chat_and_edits_are_ignored(self):
        self.pair()
        bot.intake([self.update(2, 'private data', user=11), self.update(3, 'data', chat=11),
                    self.update(4, 'data', kind='group'), {'update_id': 5, 'edited_message': self.update(5, 'data')['message']}], 99, self.path)
        self.assertEqual(len(self.rows('telegram_updates')), 1)
        self.assertEqual(bot.configuration(self.path)['next_offset'], 6)

    def test_different_bot_cannot_ingest_and_has_separate_offset(self):
        self.configure()
        bot.intake([self.update(100, 'text')], 100, self.path)
        self.assertEqual(bot.configuration(self.path)['next_offset'], 0)
        bot.disable(self.path)
        self.client.bot_id = 101
        self.configure()
        self.assertEqual(bot.configuration(self.path)['bot_id'], 101)

    def test_long_emoji_answer_chunks_fit_utf16_limit(self):
        self.pair()
        bot.intake([self.update(2, 'question')], 99, self.path)
        bot.process_one(self.path, lambda *args: '😀'*4000)
        parts = [r['text'] for r in self.rows('telegram_outbox') if r['update_id']==2]
        self.assertEqual(''.join(parts), '😀'*4000)
        self.assertTrue(all(len(p.encode('utf-16-le'))//2 <= 3500 for p in parts))

    def test_pairing_stores_hash_only_and_is_single_use(self):
        code = self.pair()
        self.assertTrue(bot.status(self.path)['paired'])
        self.assertIsNone(bot.configuration(self.path)['pairing_hash'])
        bot.intake([self.update(2, '/start '+code, user=20, chat=20)], 99, self.path)
        self.assertEqual(len(self.rows('telegram_updates')), 1)
        self.assertNotIn(code, json.dumps(self.rows('telegram_updates')))
        self.assertEqual(bot.configuration(self.path)['owner_user_id'], 10)

    def test_worker_pairs_and_replies_using_fake_transport_then_stops(self):
        code = self.configure()
        delivered = threading.Event()
        original = self.client.call
        pending = [self.update(1, '/start '+code)]
        def transport(method, **payload):
            if method == 'getUpdates':
                batch = pending[:]
                pending.clear()
                return batch
            result = original(method, **payload)
            if method == 'sendMessage':
                delivered.set()
            return result
        worker = bot.TelegramWorker(self.path)
        with patch('app.telegram_bot.load_token', return_value='fictional:token'), patch('app.telegram_bot.TelegramAPI', return_value=self.client), patch.object(self.client, 'call', side_effect=transport):
            worker.start()
            try:
                self.assertTrue(delivered.wait(3))
            finally:
                worker.stop()
        self.assertFalse(worker.thread.is_alive())
        self.assertTrue(bot.status(self.path)['paired'])

    def test_pair_hash_and_expiration(self):
        code = self.configure()
        settings = bot.configuration(self.path)
        self.assertEqual(settings['pairing_hash'], hashlib.sha256(code.encode()).hexdigest())
        bot.intake([self.update(1, '/start '+code)], 99, self.path, now=time.time()+601)
        self.assertFalse(bot.status(self.path)['paired'])

    def test_bad_pair_attempts_are_bounded(self):
        code = self.configure()
        bot.intake([self.update(n, '/start wrong') for n in range(1, 22)], 99, self.path)
        bot.intake([self.update(22, '/start '+code)], 99, self.path)
        self.assertFalse(bot.status(self.path)['paired'])
        self.assertEqual(bot.configuration(self.path)['pairing_attempts'], 20)

    def test_disable_cancels_queued_work_and_pair_can_be_replaced(self):
        self.pair()
        bot.intake([self.update(2, 'question')], 99, self.path)
        bot.disable(self.path)
        self.assertFalse(bot.process_one(self.path))
        self.assertFalse(bot.deliver_one(self.client, self.path))
        self.assertFalse(bot.status(self.path)['paired'])
        self.configure()

    def test_unlink_during_inference_discards_response(self):
        self.pair()
        bot.intake([self.update(2, 'question')], 99, self.path)
        def answer(*args):
            bot.disable(self.path)
            return 'sensitive answer'
        bot.process_one(self.path, answer)
        self.assertFalse(bot.deliver_one(self.client, self.path))
        self.assertNotIn('sensitive answer', json.dumps(self.rows('telegram_outbox')))

    def test_late_messages_and_unsupported_media_do_not_invoke_model(self):
        self.pair()
        bot.intake([self.update(2, 'old', date=time.time()-901), self.update(3, None)], 99, self.path)
        def forbidden(*args):
            self.fail('Model must not be invoked')
        bot.process_one(self.path, forbidden)
        bot.process_one(self.path, forbidden)
        replies = [r['reply'] for r in self.rows('telegram_updates')]
        self.assertTrue(any('arrived late' in r for r in replies))
        self.assertTrue(any('not connected' in r for r in replies))

    def test_history_survives_restart_and_new_clears_context(self):
        self.pair()
        bot.intake([self.update(2, 'first')], 99, self.path)
        bot.process_one(self.path, lambda *args: 'first answer')
        bot.recover(self.path)
        seen = []
        bot.intake([self.update(3, 'second')], 99, self.path)
        bot.process_one(self.path, lambda text, history, *args: seen.extend(history) or 'second answer')
        self.assertIn({'role': 'assistant', 'content': 'first answer'}, seen)
        bot.intake([self.update(4, '/new'), self.update(5, 'third')], 99, self.path)
        bot.process_one(self.path)
        seen.clear()
        bot.process_one(self.path, lambda text, history, *args: seen.extend(history) or 'third answer')
        self.assertNotIn({'role': 'assistant', 'content': 'first answer'}, seen)

    def test_restart_never_resends_ambiguous_send(self):
        self.pair()
        bot.intake([self.update(2, 'question')], 99, self.path)
        bot.process_one(self.path, lambda *args: 'answer')
        with connect(self.path) as c:
            c.execute("UPDATE telegram_outbox SET state='sending' WHERE update_id=2")
        bot.recover(self.path)
        self.assertEqual(bot.status(self.path)['ambiguous_replies'], 1)
        self.assertFalse(bot.deliver_one(self.client, self.path))

    def test_rate_limit_retries_but_network_send_uncertainty_does_not(self):
        self.pair()
        bot.intake([self.update(2, 'question')], 99, self.path)
        bot.process_one(self.path, lambda *args: 'answer')
        with patch.object(self.client, 'call', side_effect=bot.TelegramError('limited', retry_after=3)):
            with self.assertRaises(bot.TelegramError):
                bot.deliver_one(self.client, self.path)
        self.assertEqual(self.rows('telegram_outbox')[-1]['state'], 'queued')
        with patch.object(self.client, 'call', side_effect=bot.TelegramError('network', ambiguous=True)):
            with self.assertRaises(bot.TelegramError):
                bot.deliver_one(self.client, self.path)
        self.assertEqual(self.rows('telegram_outbox')[-1]['state'], 'ambiguous')


if __name__ == '__main__':
    unittest.main()
