"""Telegram adapter over the same single skill agent used by the browser."""
import json
import uuid
from datetime import datetime, timezone

from .ai_chat import chat_stream, _validated_messages
from .chat_access import questions_only, nutrition_writes


def _reply(message, history, timezone_name, path, *, operation_id, conversation_id, context=None,
           sent=None, allow_nutrition=False, authorizer=None):
    text, history = _validated_messages(message, history)
    chunks, nutrition, complete = [], dict((context or {}).get('nutrition') or {}), False
    with questions_only(allow_nutrition=allow_nutrition), nutrition_writes(authorizer):
        for line in chat_stream(text, history, timezone_name, path, operation_id=operation_id,
                conversation_id=conversation_id, nutrition_context=nutrition,
                nutrition_allow_target_save=False, message_time=sent or datetime.now(timezone.utc)):
            event = json.loads(line)
            if event['type'] == 'delta':
                chunks.append(event['text'])
            elif event['type'] == 'tool' and event.get('evidence', {}).get('nutrition'):
                result = event['evidence']['nutrition']
                if result.get('context_date'):
                    nutrition['day'] = result['context_date']
                if result.get('logged'):
                    nutrition['pending_foods'] = []
                    nutrition.pop('pending_correction', None)
                elif result.get('ingredients') or result.get('pending_foods_replaced'):
                    nutrition['pending_foods'] = result.get('ingredients', [])
                for key in ('saved_meals', 'pending_correction', 'pending_drafts'):
                    if key in result:
                        nutrition[key] = result[key]
                if result.get('target_proposal'):
                    nutrition['pending_target'] = result['target_proposal'].get('request')
            elif event['type'] == 'complete':
                complete = True
            elif event['type'] == 'error':
                raise RuntimeError(event['message'])
    if not complete or not ''.join(chunks).strip():
        raise RuntimeError('The assistant did not finish. Inspect saved results before retrying.')
    return ''.join(chunks)[:12000], nutrition


def conversation_reply(message, history, timezone_name, path=None, *, operation_id, context=None, sent_at=None, authorizer=None):
    state = dict(context or {})
    state.pop('role', None)
    state.setdefault('assistant_conversation_id', 'telegram-' + str(uuid.uuid4()))
    sent = datetime.fromtimestamp(sent_at, timezone.utc) if sent_at is not None else datetime.now(timezone.utc)
    reply, nutrition = _reply(message, history, timezone_name, path, operation_id=operation_id,
        conversation_id=state['assistant_conversation_id'], context=state, sent=sent,
        allow_nutrition=True, authorizer=authorizer)
    return {'reply': reply, 'context': {**state, 'nutrition': nutrition}}


def answer(message, history, timezone_name, path=None, *, conversation_id=None, operation_id=None):
    reply, _ = _reply(message, history, timezone_name, path, conversation_id=conversation_id,
                      operation_id=operation_id or str(uuid.uuid4()))
    return reply
