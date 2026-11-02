"""No real Keychain, Telegram transport, credentials or user database access."""
import fcntl
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import telegram_bot as bot
from app.database import migrate
from app.telegram_routes import router
from test_telegram_bot import FakeTelegram


class CredentialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  self.store=bot.CredentialSession()
  self.credential_patch=patch.object(bot,'_credentials',self.store);self.credential_patch.start();self.addCleanup(self.credential_patch.stop)
  self.client=FakeTelegram()
 def enable(self):
  bot.configure('UTC',self.path,self.client)
 def run_paused(self,worker,until=4,on_wait=None):
  waits=[]
  def wait(seconds):
   waits.append(seconds)
   if on_wait:on_wait(len(waits))
   if len(waits)>=until:worker.stop_event.set()
  with patch.object(worker.stop_event,'wait',side_effect=wait):worker.run()
  return waits
 def test_success_cached_and_explicit_retry_reads_again(self):
  with patch.object(bot,'_read_keychain_token',return_value='fictional:token') as read:
   self.assertEqual(bot.load_token(),bot.load_token());self.assertEqual(read.call_count,1)
   self.store.reset();bot.load_token();self.assertEqual(read.call_count,2)
 def test_denied_access_is_latched_without_secret_output(self):
  result=type('Result',(),dict(returncode=1,stdout=b'private-value',stderr=b'private-value'))()
  with patch.object(bot.subprocess,'run',return_value=result) as read:
   for _ in range(3):
    with self.assertRaises(bot.TelegramCredentialError) as error:bot.load_token()
    self.assertNotIn('private-value',str(error.exception))
   self.assertEqual(read.call_count,1);self.assertEqual(self.store.snapshot()[1],'blocked')
 def test_simultaneous_reads_share_one_interactive_read_and_status_stays_available(self):
  entered=threading.Event();release=threading.Event()
  def read():
   entered.set();release.wait(2);return 'fictional:token'
  with patch.object(bot,'_read_keychain_token',side_effect=read) as secret,ThreadPoolExecutor(max_workers=2) as pool:
   first=pool.submit(bot.load_token);self.assertTrue(entered.wait(1));second=pool.submit(bot.load_token)
   try:self.assertEqual(bot.status(self.path)['credential_access'],'pending')
   finally:release.set()
   self.assertEqual(first.result(),second.result());self.assertEqual(secret.call_count,1)
 def test_setup_and_worker_share_successful_read(self):
  worker=bot.TelegramWorker(self.path)
  original=self.client.call
  def call(method,**payload):
   if method=='getUpdates':worker.stop_event.set()
   return original(method,**payload)
  with patch.object(bot,'_read_keychain_token',return_value='fictional:token') as read,patch.object(bot,'TelegramAPI',return_value=self.client),patch.object(self.client,'call',side_effect=call):
   bot.configure('UTC',self.path);worker.run()
   self.assertEqual(read.call_count,1);self.assertEqual(self.client.sent,[])
 def test_worker_does_not_retry_denial_until_explicit_action(self):
  self.enable();worker=bot.TelegramWorker(self.path)
  with patch.object(bot,'_read_keychain_token',side_effect=bot.TelegramCredentialError('Access paused')) as read:
   self.run_paused(worker)
   self.assertEqual(read.call_count,1)
  result=bot.status(self.path);self.assertEqual(result['credential_access'],'blocked');self.assertTrue(result['enabled'])
 def test_explicit_retry_resumes_same_pairing_and_reads_once_more(self):
  self.enable();before=bot.configuration(self.path);worker=bot.TelegramWorker(self.path)
  original=self.client.call
  def call(method,**payload):
   if method=='getUpdates':worker.stop_event.set()
   return original(method,**payload)
  with patch.object(bot,'_read_keychain_token',side_effect=[bot.TelegramCredentialError('Access paused'),'fictional:token']) as read,patch.object(bot,'TelegramAPI',return_value=self.client),patch.object(self.client,'call',side_effect=call):
   self.run_paused(worker,on_wait=lambda count:bot.retry_credentials(self.path) if count==2 else None)
   self.assertEqual(read.call_count,2)
  after=bot.configuration(self.path)
  self.assertEqual(after['pairing_hash'],before['pairing_hash']);self.assertEqual(after['conversation_id'],before['conversation_id'])
  self.assertEqual(bot.status(self.path)['credential_access'],'ready');self.assertEqual(self.client.sent,[])
 def test_rejected_token_pauses_instead_of_polling_or_reading_again(self):
  self.enable();worker=bot.TelegramWorker(self.path)
  with patch.object(bot,'_read_keychain_token',return_value='fictional:token') as read,patch.object(bot,'TelegramAPI',return_value=self.client),patch.object(self.client,'call',side_effect=bot.TelegramCredentialError('Token rejected')) as call:
   self.run_paused(worker);self.assertEqual(read.call_count,1);self.assertEqual(call.call_count,1)
  self.assertEqual(bot.status(self.path)['credential_access'],'blocked')
 def test_other_process_lock_prevents_any_credential_read(self):
  self.enable();worker=bot.TelegramWorker(self.path)
  with self.path.with_suffix('.telegram.lock').open('a') as lock,patch.object(bot,'_read_keychain_token') as read:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);self.run_paused(worker,until=2);read.assert_not_called()
 def test_stale_failure_cannot_override_explicit_retry(self):
  old=self.store.snapshot()[0];self.store.reset()
  self.assertIsNone(self.store.reject('Old rejected token',old));self.assertEqual(self.store.snapshot()[1],'pending')
 def test_retry_requires_enabled_bot_and_local_explicit_post(self):
  with self.assertRaises(ValueError):bot.retry_credentials(self.path)
  app=FastAPI();app.include_router(router)
  with patch.object(bot,'retry_credentials',return_value={'credential_access':'pending'}) as retry,TestClient(app,client=('127.0.0.1',40000),base_url='http://127.0.0.1:8765') as client:
   self.assertEqual(client.get('/api/telegram/retry-credentials').status_code,405)
   self.assertEqual(client.post('/api/telegram/retry-credentials').status_code,403)
   self.assertEqual(client.post('/api/telegram/retry-credentials',headers={'x-garmin-local-action':'telegram-setup','origin':'https://elsewhere.example'}).status_code,403)
   retry.assert_not_called()
   self.assertEqual(client.post('/api/telegram/retry-credentials',headers={'x-garmin-local-action':'telegram-setup'}).status_code,200);retry.assert_called_once()


if __name__=='__main__':unittest.main()
