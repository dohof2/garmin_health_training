"""Optional foreground Telegram text worker. Credentials never enter SQLite or logs."""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import secrets
import ssl
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

import certifi

from .database import connect
from .time_utils import timezone_info

SERVICE = 'garmin-app.telegram'
ACCOUNT = 'bot-token'
HELP = ('Text questions, coaching advice and meal logging through the app nutrition chat are available. '
        'Tell me what you ate and the amounts; I will save the understood foods to your app meal log. '
        'Changing plans or nutrition targets, charts, photos and voice still require the browser app. '
        '/new starts a fresh conversation. /status shows connection status. /help shows this message.')


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class TelegramError(RuntimeError):
    def __init__(self, message, *, retry_after=5, ambiguous=False):
        super().__init__(message)
        self.retry_after = min(300, max(1, retry_after))
        self.ambiguous = ambiguous


class TelegramCredentialError(TelegramError):
    """Credential failures require a deliberate retry, not polling Keychain."""


def _read_keychain_token():
    # Capture stdout in this process only. Never return it through an API or exception.
    try:
        result = subprocess.run(
            ['/usr/bin/security', 'find-generic-password', '-a', ACCOUNT, '-s', SERVICE, '-w'],
            capture_output=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise TelegramCredentialError('Telegram credential access paused. Check macOS Keychain, then use Retry credential access in Telegram settings.') from None
    token = result.stdout.decode('utf-8', errors='replace').strip()
    if result.returncode or not token or ':' not in token or any(c.isspace() for c in token):
        raise TelegramCredentialError('Telegram credential access paused. Check the garmin-app.telegram / bot-token Keychain entry, then use Retry credential access in Telegram settings.')
    return token


class CredentialSession:
    """One serialized secret read per process/retry, never persisted or returned."""
    def __init__(self):
        self.lock = threading.Lock()
        self.token = None
        self.error = None
        self.revision = 0
        self._state = (0, 'pending')

    def load(self):
        with self.lock:
            if self.error:
                raise TelegramCredentialError(self.error)
            if self.token is None:
                try:
                    self.token = _read_keychain_token()
                    self._state = (self.revision, 'ready')
                except TelegramCredentialError as error:
                    self.error = str(error)
                    self._state = (self.revision, 'blocked')
                    raise
            return self.token

    def reset(self, failed_only=False):
        with self.lock:
            if failed_only and not self.error:
                return
            self.token = self.error = None
            self.revision += 1
            self._state = (self.revision, 'pending')

    def reject(self, message, revision=None):
        with self.lock:
            if revision is not None and revision != self.revision:
                return None
            self.token = None
            self.error = message
            self._state = (self.revision, 'blocked')
            return self.revision

    def snapshot(self):
        # Publish only a nonsecret immutable state; status requests must not
        # wait behind a macOS dialog while the read lock is held.
        return self._state


_credentials = CredentialSession()


def load_token():
    return _credentials.load()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TelegramAPI:
    def __init__(self, token):
        self._token = token
        self._opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def call(self, method, **payload):
        if method not in {'getMe', 'getWebhookInfo', 'getUpdates', 'sendMessage'}:
            raise ValueError('Unsupported Telegram operation')
        request = Request(
            f'https://api.telegram.org/bot{self._token}/{method}',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST',
        )
        try:
            with self._opener.open(request, timeout=20) as response:
                result = json.loads(response.read(2_000_000))
        except HTTPError as error:
            delay = 5
            if error.code == 429:
                try:
                    delay = int(json.loads(error.read(4096)).get('parameters', {}).get('retry_after', 5))
                except (ValueError, TypeError):
                    pass
            message = {401: 'Telegram rejected the token. Check BotFather and Keychain.',
                       403: 'Telegram cannot deliver replies. Open the bot and unblock it.',
                       409: 'Another Telegram consumer is active. Stop it before reconnecting.',
                       429: 'Telegram rate limit reached; the worker will wait.'}.get(error.code, 'Telegram request failed; check the connection.')
            if error.code == 401:
                raise TelegramCredentialError(message+' Use Retry credential access in Telegram settings after updating Keychain.') from None
            raise TelegramError(message, retry_after=delay, ambiguous=method == 'sendMessage' and error.code >= 500) from None
        except (URLError, OSError, ValueError):
            raise TelegramError('Telegram is unreachable; check the internet connection.', ambiguous=method == 'sendMessage') from None
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise TelegramError('Telegram did not confirm the request.', ambiguous=method == 'sendMessage')
        return result['result']


def configuration(path=None):
    with connect(path) as c:
        return dict(c.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone())


def status(path=None):
    settings = configuration(path)
    with connect(path) as c:
        pending = c.execute("SELECT COUNT(*) FROM telegram_updates WHERE bot_id=? AND state='queued'", (settings['bot_id'],)).fetchone()[0]
        ambiguous = c.execute("SELECT COUNT(*) FROM telegram_outbox WHERE bot_id=? AND state='ambiguous'", (settings['bot_id'],)).fetchone()[0]
    return {key: settings[key] for key in ('enabled', 'bot_username', 'timezone', 'last_poll_at', 'last_error')} | {
        'enabled': bool(settings['enabled']),
        'paired': settings['owner_user_id'] is not None, 'pending': pending,
        'ambiguous_replies': ambiguous, 'capabilities': 'text_questions_and_meal_logging',
        'pairing_pending': bool(settings['pairing_hash'] and (settings['pairing_expires'] or 0) > time.time()),
        'credential_access': _credentials.snapshot()[1],
    }


def configure(timezone_name, path=None, client=None):
    timezone_info(timezone_name)
    revision = _credentials.snapshot()[0]
    if client is None:
        # An explicit setup attempt can retry a previously denied read. A
        # successful setup/worker share the existing in-memory credential.
        _credentials.reset(failed_only=True)
        revision = _credentials.snapshot()[0]
        client = TelegramAPI(load_token())
    try:
        bot = client.call('getMe')
        webhook = client.call('getWebhookInfo')
    except TelegramCredentialError as error:
        _credentials.reject(str(error), revision)
        raise
    if not bot.get('is_bot') or not isinstance(bot.get('id'), int) or not bot.get('username'):
        raise TelegramError('The saved credential did not identify a Telegram bot.')
    if webhook.get('url'):
        raise TelegramError('This bot already has a webhook. Remove it from its existing integration before connecting here.')
    code = secrets.token_urlsafe(24)
    expires = time.time() + 600
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone()
        if old['owner_user_id'] is not None:
            raise ValueError('Unlink the paired account before creating another pairing code.')
        if old['bot_id'] != bot['id']:
            c.execute('UPDATE telegram_settings SET next_offset=0 WHERE id=1')
        c.execute('''UPDATE telegram_settings SET enabled=1,bot_id=?,bot_username=?,timezone=?,
            pairing_hash=?,pairing_expires=?,pairing_attempts=0,last_error=NULL,conversation_id=? WHERE id=1''',
            (bot['id'], bot['username'], timezone_name, hashlib.sha256(code.encode()).hexdigest(), expires, str(uuid.uuid4())))
    return {'url': f"https://t.me/{bot['username']}?start={code}", 'expires_at': datetime.fromtimestamp(expires, timezone.utc).isoformat()}


def disable(path=None):
    with connect(path) as c:
        c.execute('''UPDATE telegram_settings SET enabled=0,owner_user_id=NULL,owner_chat_id=NULL,
            pairing_hash=NULL,pairing_expires=NULL,last_error=NULL,conversation_id=? WHERE id=1''', (str(uuid.uuid4()),))
        c.execute("UPDATE telegram_updates SET state='cancelled' WHERE state IN ('queued','processing')")
        c.execute("UPDATE telegram_outbox SET state='cancelled' WHERE state='queued'")
    _credentials.reset()
    return status(path)


def retry_credentials(path=None):
    """Explicit local action: let the enabled worker resume after a failed read."""
    if not configuration(path)['enabled']:
        raise ValueError('Connect Telegram before retrying credential access.')
    _credentials.reset()
    with connect(path) as c:
        c.execute('UPDATE telegram_settings SET last_error=NULL WHERE id=1')
    return status(path)


def intake(updates, bot_id, path=None, now=None):
    """Commit authorized intake and offset together, before acknowledging to Telegram."""
    now = time.time() if now is None else now
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        settings = dict(c.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone())
        if not settings['enabled'] or settings['bot_id'] != bot_id:
            return
        for update in updates:
            update_id = update.get('update_id')
            if type(update_id) is not int or update_id < settings['next_offset']:
                continue
            c.execute('UPDATE telegram_settings SET next_offset=MAX(next_offset,?) WHERE id=1', (update_id+1,))
            msg = update.get('message')  # Edits/callbacks never replay the original action.
            if not isinstance(msg, dict):
                continue
            chat, sender = msg.get('chat', {}), msg.get('from', {})
            user_id, chat_id = sender.get('id'), chat.get('id')
            if chat.get('type') != 'private' or type(user_id) is not int or type(chat_id) is not int or sender.get('is_bot'):
                continue
            text = msg.get('text')
            if not isinstance(text, str):
                text = '/unsupported'
            if settings['owner_user_id'] is None:
                if not text.startswith('/start ') or not settings['pairing_hash'] or (settings['pairing_expires'] or 0) < now or settings['pairing_attempts'] >= 20:
                    continue
                code = text.partition(' ')[2].strip()
                settings['pairing_attempts'] += 1
                c.execute('UPDATE telegram_settings SET pairing_attempts=pairing_attempts+1 WHERE id=1')
                if len(code) > 128 or not hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(), settings['pairing_hash']):
                    continue
                settings['owner_user_id'], settings['owner_chat_id'] = user_id, chat_id
                settings['pairing_hash'] = None
                c.execute('''UPDATE telegram_settings SET owner_user_id=?,owner_chat_id=?,pairing_hash=NULL,pairing_expires=NULL WHERE id=1''', (user_id, chat_id))
                text = '/paired'  # Never retain the pairing code in message history.
            if (settings['owner_user_id'], settings['owner_chat_id']) != (user_id, chat_id):
                continue
            if type(msg.get('message_id')) is not int or type(msg.get('date')) not in (int, float):
                continue
            queued = c.execute("SELECT COUNT(*) FROM telegram_updates WHERE bot_id=? AND state='queued'", (bot_id,)).fetchone()[0]
            if queued >= 100:
                c.execute("UPDATE telegram_settings SET last_error='Incoming queue is full. Retry your latest message later.' WHERE id=1")
                continue
            reply_to = (msg.get('reply_to_message') or {}).get('message_id')
            c.execute('''INSERT OR IGNORE INTO telegram_updates(bot_id,update_id,user_id,chat_id,message_id,sent_at,text,reply_to)
                VALUES(?,?,?,?,?,?,?,?)''', (bot_id, update_id, user_id, chat_id, msg['message_id'], msg['date'], text[:4001], reply_to if type(reply_to) is int else None))
        c.execute('UPDATE telegram_settings SET last_poll_at=? WHERE id=1', (utcnow(),))


def recover(path=None):
    with connect(path) as c:
        # Reads can be retried; sending is ambiguous after process death and is never replayed automatically.
        c.execute("UPDATE telegram_updates SET state='queued' WHERE state='processing'")
        c.execute("UPDATE telegram_outbox SET state='ambiguous' WHERE state='sending'")


def process_one(path=None, responder=None, now=None):
    from .telegram_chat import conversation_reply
    now = time.time() if now is None else now
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        settings = dict(c.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone())
        if not settings['enabled'] or settings['owner_user_id'] is None:
            return False
        row = c.execute("SELECT * FROM telegram_updates WHERE bot_id=? AND state='queued' ORDER BY update_id LIMIT 1", (settings['bot_id'],)).fetchone()
        if row is None:
            return False
        row = dict(row)
        if (row['user_id'], row['chat_id']) != (settings['owner_user_id'], settings['owner_chat_id']):
            c.execute("UPDATE telegram_updates SET state='cancelled' WHERE bot_id=? AND update_id=?", (row['bot_id'], row['update_id']))
            return True
        c.execute("UPDATE telegram_updates SET state='processing' WHERE bot_id=? AND update_id=?", (row['bot_id'], row['update_id']))
        saved_state = c.execute('SELECT context_json FROM telegram_conversation_state WHERE bot_id=? AND conversation_id=?',
            (settings['bot_id'],settings['conversation_id'])).fetchone()
        context = json.loads(saved_state['context_json']) if saved_state else {}
        operation_id = f"telegram:{row['bot_id']}:{row['update_id']}"
        saved_operation = c.execute('SELECT 1 FROM nutrition_chat_operations WHERE operation_id=?',(operation_id,)).fetchone()
        if not saved_operation:
            saved_operation = c.execute("SELECT 1 FROM assistant_skill_turns WHERE operation_id=? AND status IN ('completed','review','awaiting_information') UNION SELECT 1 FROM assistant_skill_calls WHERE operation_id=? AND json_extract(result_json,'$.evidence.nutrition.logged')=1 LIMIT 1", (operation_id,operation_id)).fetchone()
        local_sent=datetime.fromtimestamp(row['sent_at'],timezone.utc).astimezone(ZoneInfo(settings['timezone']))
        day_start=local_sent.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        history = [dict(r) for r in c.execute('''SELECT role,content FROM (SELECT t.id,t.role,t.content FROM telegram_turns t JOIN telegram_updates u ON u.bot_id=t.bot_id AND u.update_id=t.update_id
            WHERE t.bot_id=? AND t.conversation_id=? AND u.sent_at>=? AND u.sent_at<=? ORDER BY t.id DESC LIMIT 18) ORDER BY id''', (settings['bot_id'],settings['conversation_id'],day_start,row['sent_at']))]
        if row['reply_to']:
            reference = c.execute('''SELECT t.content FROM telegram_outbox o JOIN telegram_turns t ON
                t.bot_id=o.bot_id AND t.update_id=o.update_id AND t.role='assistant'
                WHERE o.bot_id=? AND o.telegram_message_id=? AND t.conversation_id=? LIMIT 1''',
                (row['bot_id'], row['reply_to'], settings['conversation_id'])).fetchone()
            if reference:
                history.append({'role': 'assistant', 'content': 'Reply refers to this earlier answer: ' + reference['content'][:3900]})
    text = row['text']
    conversation = settings['conversation_id']
    if text == '/paired':
        reply = 'Your account is paired with Garmin Health & Training. ' + HELP
    elif text == '/new':
        conversation = str(uuid.uuid4())
        context = {}
        reply = 'Started a new Telegram conversation. ' + HELP
    elif text == '/status':
        reply = f"Connected to @{settings['bot_username']}. Timezone: {settings['timezone']}. Text questions and meal logging are available; the Mac must stay awake with the app open."
    elif text in {'/help', '/start'}:
        reply = HELP
    elif text == '/unsupported':
        reply = 'Photos, files and voice are not connected yet. Please send a text question.'
    elif text.startswith('/'):
        reply = 'Available commands: /new, /status, /help. Trainer, nutrition and data questions share this conversation.'
    elif not saved_operation and not 0 <= now-row['sent_at'] <= 900:
        reply = 'This message arrived late. Please send it again so the answer uses your current context.'
    elif len(text) > 4000:
        reply = 'Please send a shorter question (up to 4,000 characters).'
    else:
        try:
            def authorize(connection):
                current = connection.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone()
                if not current['enabled'] or (current['bot_id'],current['owner_user_id'],current['owner_chat_id'],current['conversation_id']) != (settings['bot_id'],row['user_id'],row['chat_id'],settings['conversation_id']):
                    raise ValueError('Telegram access was disabled or changed. No new meal was saved.')
            if responder is not None:
                reply = responder(text,history,settings['timezone'],path)
            else:
                result = conversation_reply(text,history,settings['timezone'],path,operation_id=operation_id,
                    context=context,sent_at=row['sent_at'],authorizer=authorize)
                reply,context = result['reply'],result['context']
        except Exception:
            reply = 'The assistant could not finish this answer. Check the meal log and the selected AI provider in Settings before retrying; a saved meal may already be present.'
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        current = c.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone()
        if not current['enabled'] or (current['bot_id'], current['owner_user_id'], current['owner_chat_id'], current['conversation_id']) != (settings['bot_id'], row['user_id'], row['chat_id'], settings['conversation_id']):
            c.execute("UPDATE telegram_updates SET state='cancelled' WHERE bot_id=? AND update_id=?", (row['bot_id'], row['update_id']))
            return True
        c.execute('UPDATE telegram_settings SET conversation_id=? WHERE id=1', (conversation,))
        c.execute('''INSERT INTO telegram_conversation_state(bot_id,conversation_id,context_json) VALUES(?,?,?)
            ON CONFLICT(bot_id,conversation_id) DO UPDATE SET context_json=excluded.context_json,updated_at=CURRENT_TIMESTAMP''',
            (row['bot_id'],conversation,json.dumps(context)))
        for role, content in [('user', text), ('assistant', reply)]:
            c.execute('''INSERT OR IGNORE INTO telegram_turns(bot_id,conversation_id,update_id,role,content) VALUES(?,?,?,?,?)''', (row['bot_id'], conversation, row['update_id'], role, content[:4000]))
        # Plain text, bounded below Telegram's UTF-16 character limit, including emoji.
        parts, part, size = [], '', 0
        for char in reply[:12000]:
            width = 2 if ord(char) > 0xFFFF else 1
            if size + width > 3500:
                parts.append(part); part, size = '', 0
            part += char; size += width
        if part:
            parts.append(part)
        for index, part in enumerate(parts):
            c.execute('''INSERT OR IGNORE INTO telegram_outbox(bot_id,update_id,part,chat_id,text) VALUES(?,?,?,?,?)''', (row['bot_id'], row['update_id'], index, row['chat_id'], part))
        c.execute("UPDATE telegram_updates SET state='done',reply=?,conversation_id=? WHERE bot_id=? AND update_id=?", (reply[:12000], conversation, row['bot_id'], row['update_id']))
    return True


def deliver_one(client, path=None):
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        settings = c.execute('SELECT * FROM telegram_settings WHERE id=1').fetchone()
        if not settings['enabled'] or settings['owner_user_id'] is None:
            return False
        row = c.execute("SELECT * FROM telegram_outbox WHERE bot_id=? AND chat_id=? AND state='queued' ORDER BY id LIMIT 1", (settings['bot_id'], settings['owner_chat_id'])).fetchone()
        if row is None:
            return False
        row = dict(row)
        c.execute("UPDATE telegram_outbox SET state='sending' WHERE id=?", (row['id'],))
    try:
        result = client.call('sendMessage', chat_id=row['chat_id'], text=row['text'], protect_content=True)
    except TelegramError as error:
        with connect(path) as c:
            c.execute('UPDATE telegram_outbox SET state=? WHERE id=?', ('ambiguous' if error.ambiguous else 'queued', row['id']))
        raise
    with connect(path) as c:
        c.execute("UPDATE telegram_outbox SET state='sent',telegram_message_id=? WHERE id=?", (result['message_id'], row['id']))
    return True


class TelegramWorker:
    def __init__(self, path=None):
        from . import database
        self.path = path or database.database_path()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name='telegram-text', daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=1)

    def run(self):
        lock = None
        client = None
        active_bot = None
        credential_revision = None
        paused_revision = None
        while not self.stop_event.is_set():
            try:
                settings = configuration(self.path)
                if not settings['enabled']:
                    if lock:
                        lock.close(); lock = None
                    client = None
                    self.stop_event.wait(1)
                    continue
                if lock is None:
                    lock = self.path.with_suffix('.telegram.lock').open('a')
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        lock.close(); lock = None
                        raise TelegramError('Telegram is already running in another app process.', retry_after=15)
                    recover(self.path)
                revision, _ = _credentials.snapshot()
                if paused_revision == revision:
                    self.stop_event.wait(1)
                    continue
                if client is None or active_bot != settings['bot_id'] or credential_revision != revision:
                    client = TelegramAPI(load_token())
                    if client.call('getMe')['id'] != settings['bot_id']:
                        client = None
                        raise TelegramCredentialError('Keychain now identifies a different bot. Restore the paired bot credential and retry, or unlink and reconnect in settings.')
                    active_bot = settings['bot_id']
                    credential_revision = revision
                if deliver_one(client, self.path):
                    self.stop_event.wait(1)
                    continue
                if process_one(self.path):
                    continue
                updates = client.call('getUpdates', offset=settings['next_offset'], timeout=10, limit=25, allowed_updates=['message'])
                intake(updates, settings['bot_id'], self.path)
                with connect(self.path) as c:
                    c.execute('UPDATE telegram_settings SET last_error=NULL WHERE id=1')
            except TelegramCredentialError as error:
                paused_revision = _credentials.reject(str(error), revision)
                client = None
                with connect(self.path) as c:
                    c.execute('UPDATE telegram_settings SET last_error=? WHERE id=1', (str(error),))
                self.stop_event.wait(1)
            except TelegramError as error:
                with connect(self.path) as c:
                    c.execute('UPDATE telegram_settings SET last_error=? WHERE id=1', (str(error),))
                self.stop_event.wait(error.retry_after)
            except Exception:
                with connect(self.path) as c:
                    c.execute("UPDATE telegram_settings SET last_error='Telegram worker paused after an internal error. Restart the app or reconnect.' WHERE id=1")
                self.stop_event.wait(10)
        if lock:
            lock.close()
