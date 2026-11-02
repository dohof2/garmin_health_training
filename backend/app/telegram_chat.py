"""Text-question adapter over the browser's provider and grounded tool services."""
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .ai_chat import _validated_messages, _chatgpt_stream, _openai_stream, _ollama_stream
from .ai_providers import get_ai_settings
from .chat_access import questions_only


def conversation_reply(message, history, timezone_name, path=None, *, operation_id, context=None, sent_at=None, authorizer=None):
    """Route meal reports through the same shared chat entry point as the app."""
    from .ai_chat import chat_stream
    from .chat_routing import route
    from .chat_access import nutrition_writes
    text, history = _validated_messages(message, history)
    state = dict(context or {})
    sent = datetime.fromtimestamp(sent_at, timezone.utc) if sent_at is not None else datetime.now(timezone.utc)
    today=sent.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    if (state.get('chat_day') or state.get('nutrition',{}).get('day')) and (state.get('chat_day') or state['nutrition']['day'])!=today:
        from .nutrition_drafts import new_day
        state={'nutrition':new_day(state.get('nutrition') or {},today)};history=[]
    state['chat_day']=today
    selected = route(text, previous=state.get('role'))
    if selected != 'nutrition':
        return {'reply':answer(text,history,timezone_name,path),'context':{**state,'role':selected}}
    sent = datetime.fromtimestamp(sent_at, timezone.utc) if sent_at is not None else datetime.now(timezone.utc)
    nutrition = dict(state.get('nutrition') or {})
    day = sent.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    nutrition.setdefault('day',day)
    chunks = []
    complete = False
    target_proposal = False
    with nutrition_writes(authorizer):
        for line in chat_stream(text,history,timezone_name,path,operation_id=operation_id,
                chat_role='nutrition',nutrition_context=nutrition,nutrition_allow_target_save=False,message_time=sent):
            event = json.loads(line)
            if event['type'] == 'delta':
                chunks.append(event['text'])
            elif event['type'] == 'tool' and event.get('evidence',{}).get('nutrition'):
                result = event['evidence']['nutrition']
                if result.get('context_date') and result['context_date']!=nutrition.get('day'):
                    from .nutrition_drafts import new_day
                    nutrition=new_day(nutrition,result['context_date'])
                nutrition['day'] = result.get('context_date') or day
                nutrition['chat_day']=result.get('chat_day') or today
                if result.get('logged'):nutrition.pop('pending_correction',None)
                elif 'pending_correction' in result:nutrition['pending_correction']=result['pending_correction']
                if 'pending_drafts' in result:nutrition['pending_drafts']=result['pending_drafts']
                if result.get('logged'):
                    nutrition['pending_foods'] = []
                elif result.get('ingredients') or result.get('pending_foods_replaced'):
                    nutrition['pending_foods'] = [
                        {key:food[key] for key in ('name','grams_low','grams_high','grams_proposed','question','meal_type','nutrients_per_100g','estimate_assumptions') if key in food}
                        for food in result['ingredients']]
                if result.get('saved_meals'):
                    nutrition['saved_meals'] = result['saved_meals']
                if result.get('target_proposal'):
                    target_proposal = True
                    nutrition['pending_target'] = result['target_proposal'].get('request')
            elif event['type'] == 'complete':
                complete = True
            elif event['type'] == 'error':
                raise RuntimeError('The nutrition assistant could not finish. Check the meal log before retrying.')
    if not complete or not ''.join(chunks).strip():
        raise RuntimeError('The nutrition assistant did not finish its reply.')
    if target_proposal:
        chunks.append('\nשינוי יעד התזונה דורש שמירה באפליקציה; היעד לא נשמר דרך טלגרם.' if re.search('[\u0590-\u05ff]',text) else '\nSave nutrition target changes in the browser app; this target was not saved through Telegram.')
    return {'reply':''.join(chunks)[:12000],'context':{**state,'role':'nutrition','nutrition':nutrition}}


def answer(message, history, timezone_name, path=None):
    text, history = _validated_messages(message, history)
    settings = get_ai_settings(path)
    provider = settings['active_provider']
    model = settings[f'{provider}_model']
    chunks = []
    complete = False
    with questions_only():
        if provider == 'chatgpt':
            stream = _chatgpt_stream(model, text, history, timezone_name, path)
        elif provider == 'openai':
            stream = _openai_stream(model, text, history, timezone_name, path)
        else:
            stream = _ollama_stream(model, text, history, timezone_name, path)
        for line in stream:
            event = json.loads(line)
            if event['type'] == 'delta':
                chunks.append(event['text'])
            elif event['type'] == 'complete':
                complete = True
            elif event['type'] == 'error':
                raise RuntimeError('The selected assistant could not answer. Check Assistant settings.')
    if not complete or not ''.join(chunks).strip():
        raise RuntimeError('The assistant did not finish its answer. Please try again.')
    return ''.join(chunks)[:12000]
