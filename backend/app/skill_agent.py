"""One model-directed conversation with progressive skill and tool loading."""
import hashlib
import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from . import skill_catalog
from .agent_runtime import CURRENT, Runtime, BudgetExceeded
from .ai_budget import bounded_history, compact_json
from .ai_providers import active_provider, get_ai_settings, shared_allowance_message, tool_result_message
from .database import connect, migrate
from .skill_tools import definition, available_definitions, execute, canonical_call, STRING, OBJECT
from .time_utils import timezone_info

CONTROL = [
    definition('find_skills', 'Search the complete hierarchy for a few relevant capability cards. No skill bodies are loaded.', {'query': STRING}, ('query',)),
    definition('list_skill_children', 'Browse one catalog branch. Empty path lists roots; direct skill search is usually faster.', {'path': STRING}),
    definition('load_skill', 'Load one skill and its focused tools. Replaces previous skills by default; keep_current=true only for a distinct additional capability.', {'skill_id': STRING, 'keep_current': {'type': 'boolean'}}, ('skill_id',)),
    definition('replace_skills', 'Choose the relevant active skill IDs or an empty list for general conversation. Removes other skill instructions/tools; task memory remains.', {'skill_ids': {'type': 'array', 'items': STRING, 'maxItems': 4}}, ('skill_ids',)),
    definition('update_task', 'Persist a compact planning brief, resolved IDs/absolute dates, decisions, draft or question under a task key. Replace that key with the complete updated value.', {'key': STRING, 'value': OBJECT}, ('key', 'value')),
    definition('read_task', 'Resume a retained task by key when its catalog summary is relevant. Loads its full brief without other tasks.', {'key': STRING}, ('key',)),
]
CONTROL_BY_NAME = {d['name']: d for d in CONTROL}


@contextmanager
def bookkeeping(path):
    # Conversation/receipt persistence is separate from domain-write permissions.
    from .chat_access import READ_ONLY
    token = READ_ONLY.set(False)
    try:
        with connect(path) as c:
            yield c
    finally:
        READ_ONLY.reset(token)


def _save(context):
    with bookkeeping(context['path']) as c:
        c.execute('UPDATE assistant_skill_sessions SET state_json=?,updated_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND active_operation=?',
                  (compact_json(context['state']), context['conversation_id'], context['operation_id']))


def _prepare(context, request_hash):
    with bookkeeping(context['path']) as c:
        c.execute('BEGIN IMMEDIATE')
        receipt = c.execute('SELECT * FROM assistant_skill_turns WHERE operation_id=?', (context['operation_id'],)).fetchone()
        if receipt:
            if receipt['conversation_id'] != context['conversation_id'] or receipt['request_hash'] != request_hash:
                raise ValueError('This operation ID belongs to a different request')
            events = json.loads(receipt['events_json'])
            return events or [{'type': 'delta', 'text': 'This request was already started. No duplicate operation was run. Inspect its saved results before retrying.'}, {'type': 'complete', 'evidence': [], 'workflow': 'skills'}]
        row = c.execute('SELECT *, julianday(updated_at) AS updated FROM assistant_skill_sessions WHERE conversation_id=?', (context['conversation_id'],)).fetchone()
        if row and row['active_operation']:
            now = c.execute('SELECT julianday(CURRENT_TIMESTAMP)').fetchone()[0]
            if (now - row['updated']) * 86400 < 600:
                return [{'type': 'delta', 'text': 'The previous request is still in progress. No second operation was started.'}, {'type': 'complete', 'evidence': [], 'workflow': 'skills'}]
        context['state'] = json.loads(row['state_json']) if row else {}
        if row:
            c.execute('UPDATE assistant_skill_sessions SET active_operation=?,updated_at=CURRENT_TIMESTAMP WHERE conversation_id=?',
                      (context['operation_id'], context['conversation_id']))
        else:
            c.execute('INSERT INTO assistant_skill_sessions(conversation_id,active_operation) VALUES(?,?)',
                      (context['conversation_id'], context['operation_id']))
        c.execute('INSERT INTO assistant_skill_turns(operation_id,conversation_id,request_hash) VALUES(?,?,?)',
                  (context['operation_id'], context['conversation_id'], request_hash))
    return None


def _control(name, args, context):
    from .skill_tools import validate
    validate(CONTROL_BY_NAME[name], args)
    state = context['state']
    if name == 'find_skills':
        return skill_catalog.find(args['query'])
    if name == 'list_skill_children':
        return skill_catalog.children(args.get('path', ''))
    if name == 'read_task':
        value = state.get('memory', {}).get(args['key'])
        if value is None:
            raise ValueError('Unknown retained task')
        state['focus_task'] = args['key']
        return {'task': value}
    if name in ('load_skill', 'replace_skills'):
        ids = (state.get('skills', []) if args.get('keep_current') else []) + [args['skill_id']] if name == 'load_skill' else args['skill_ids']
        ids = list(dict.fromkeys(ids))
        if len(ids) > 4:
            raise ValueError('Keep at most four relevant skills. Replace irrelevant skills first.')
        skills = [skill_catalog.load_skill(identifier) for identifier in ids]
        state['skills'] = ids
        state['skill_versions'] = {s['id']: s['version'] for s in skills}
        focused = state.get('focus_task')
        if focused and not set(state.get('task_skills', {}).get(focused, [])) & set(ids):
            state.pop('focus_task', None)
        from .ai_budget import compact_training_proposal
        references = {k: compact_training_proposal(state[k]) if k == 'last_training_proposal' else state[k] for k in ('last_training_proposal','planning_preview') if k in state and any(s.startswith('training.') for s in ids)}
        return {'active_skills': [skill_catalog.card(s) for s in skills], 'task_memory': _memory(state),
                'retained_references': references,
                **({'nutrition_context': state.get('nutrition', {})} if any(s.startswith('nutrition.') for s in ids) else {}),
                'note': 'Instructions and native tools are available on your next step.'}
    key = args['key']
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', key):
        raise ValueError('Use a short task key')
    memory = {**state.get('memory', {}), key: args['value']}
    if len(memory) > 12 or len(compact_json(memory)) > 48000:
        raise ValueError('Keep task memory compact: at most twelve task briefs and 48,000 characters total.')
    state['memory'] = memory
    state.setdefault('task_skills', {})[key] = list(state.get('skills', []))
    state['focus_task'] = key
    return {'retained_task': key}


def _memory(state):
    active = set(state.get('skills', []))
    values, index = {}, []
    for key, value in state.get('memory', {}).items():
        skills = state.get('task_skills', {}).get(key, [])
        index.append({'key': key, 'skills': skills, 'summary': str(value.get('title') or value.get('request') or value.get('goal') or value.get('stage') or '')[:200]})
        if key == state.get('focus_task') or (not state.get('focus_task') and active.intersection(skills)):
            values[key] = value
    return {'index': index, 'selected_briefs': values}


def _instructions(context):
    state = context['state']
    instructions = (skill_catalog.ROOT / 'core.md').read_text()
    instructions += '\nCurrent user-local date: ' + context['today'] + '; timezone: ' + context['timezone']
    if any(s.startswith('training.') for s in state.get('skills',[])):
        from .training_notes import read
        notes=read(context['path'])['notes']
        instructions+='\nSaved training note branches (user preference data): '+compact_json([f"{n['activity']}/{n['workout_type']}/{n['topic']}" for n in notes])+'. Read relevant notes before planning or revising sessions.'
    if not state.get('skills'):
        instructions += '\nCatalog branches: ' + compact_json(skill_catalog.branches())
    available = available_definitions()
    tools = dict(CONTROL_BY_NAME)
    for identifier in state.get('skills', []):
        skill = skill_catalog.load_skill(identifier)
        if state.get('skill_versions', {}).get(identifier) != skill['version']:
            instructions += '\nSkill version changed; re-read current records and refresh any pending proposal before applying it.'
        instructions += '\n\n' + skill['instructions']
        tools.update({name: available[name] for name in skill['tools'] if name in available})
        if identifier in ('training.programs.build', 'training.programs.revise'):
            context['runtime'].planning()
    from .chat_access import READ_ONLY, QUESTION_INSTRUCTIONS, ALLOW_NUTRITION
    if READ_ONLY.get():
        instructions += '\n' + QUESTION_INSTRUCTIONS
        if ALLOW_NUTRITION.get():
            instructions += '\nChannel exception: explicitly reported foods/corrections may use nutrition_conversation to save meals. Nutrition targets still require browser review; training/settings/publication writes remain unavailable.'
    return instructions, tools


def _tool(name, args, context):
    signature = hashlib.sha256(canonical_call(name, args).encode()).hexdigest()
    with bookkeeping(context['path']) as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT result_json FROM assistant_skill_calls WHERE operation_id=? AND signature=?', (context['operation_id'], signature)).fetchone()
        if row:
            return json.loads(row[0]) if row[0] else {'result': {'error': 'This operation was interrupted after starting; inspect current records before another write.'}, 'evidence': None}
        c.execute('INSERT INTO assistant_skill_calls(operation_id,signature) VALUES(?,?)', (context['operation_id'], signature))
    try:
        if name in CONTROL_BY_NAME:
            result, evidence = _control(name, args, context), None
        else:
            result, evidence = execute(name, args, context)
        output = {'result': result, 'evidence': evidence}
    except (ValueError, KeyError, TypeError) as error:
        output = {'result': {'error': str(error), 'status': 'not_applied'}, 'evidence': None}
    # Save result and context together before another model call or public yield.
    with bookkeeping(context['path']) as c:
        c.execute('UPDATE assistant_skill_calls SET result_json=? WHERE operation_id=? AND signature=?',
                  (compact_json(output), context['operation_id'], signature))
        c.execute('UPDATE assistant_skill_sessions SET state_json=?,updated_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND active_operation=?',
                  (compact_json(context['state']), context['conversation_id'], context['operation_id']))
    return output


def read_turn(operation_id, conversation_id, path=None):
    """Read a saved receipt without repeating model calls or tool operations."""
    with connect(path) as c:
        row = c.execute('SELECT status,events_json FROM assistant_skill_turns WHERE operation_id=? AND conversation_id=?',
                        (operation_id, conversation_id)).fetchone()
    if row is None:
        raise KeyError('Chat response not found')
    return {'status': row['status'], 'events': json.loads(row['events_json'])}


def _receipts(results):
    """Carry confirmed outcomes across allowance failures without full prescriptions."""
    receipts = []
    for entry in results[-8:]:
        value = entry.get('result') or {}
        if not isinstance(value, dict):
            continue
        receipt = {k: value[k] for k in ('status', 'message', 'error', 'request', 'revision', 'activity', 'workout_type', 'topic', 'fingerprint') if k in value}
        if receipt:
            receipts.append({'tool': entry.get('tool'), 'result': receipt})
    return receipts


def _result_status(results):
    for result in reversed(results):
        value = result.get('result') or {}
        proposal = value.get('target_proposal') or value
        if proposal.get('status') == 'proposal':
            return 'review'
        if proposal.get('status') == 'needs_input':
            return 'awaiting_information'
    return 'completed'


def stream(message, history, timezone_name, path, *, conversation_id=None, settings=None, **options):
    from .ai_chat import _validated_messages
    text, history = _validated_messages(message, history)
    tz = timezone_name or 'UTC'
    now = options.get('message_time') or datetime.now(timezone.utc)
    today = now.astimezone(timezone_info(tz)).date().isoformat()
    conversation_id = conversation_id or 'request-' + str(uuid.uuid4())
    operation = options.get('operation_id') or str(uuid.uuid4())
    if not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 120 or not isinstance(operation, str) or not 1 <= len(operation) <= 120:
        raise ValueError('Invalid conversation or operation ID')
    with bookkeeping(path):
        migrate(path)
    settings = settings or get_ai_settings(path)
    provider = settings['active_provider']
    model = settings[provider + '_model']
    context = {'message': text, 'history': history, 'timezone': tz, 'today': today, 'now': now,
               'path': path, 'conversation_id': conversation_id, 'operation_id': operation, 'options': options}
    request_hash = hashlib.sha256(json.dumps([text, tz, options.get('nutrition_context')], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    replay = _prepare(context, request_hash)
    if replay is not None:
        for event in replay:
            yield compact_json(event) + '\n'
        return
    state = context['state']
    # Nutrition UI context is only a reference, not an instruction or a write authorization.
    if options.get('nutrition_context'):
        allowed = {'day', 'meal_type', 'pending_foods', 'pending_target', 'saved_meals', 'pending_correction', 'draft_items'}
        state['nutrition'] = {**state.get('nutrition', {}), **{k: v for k, v in options['nutrition_context'].items() if k in allowed}}
    history = state.get('history') or history
    context['history'] = history
    runtime = Runtime()
    context['runtime'] = runtime
    events, evidence, results, messages = [], [], [], []
    status, reply = 'blocked', ''
    stage = 'starting'
    def emit(event):
        events.append(event)
        return compact_json(event) + '\n'
    try:
        state['current_turn'] = {'message': text, 'date': today}
        _save(context)
        yield emit({'type': 'start', 'provider': provider, 'model': model, 'workflow': 'skills', 'conversation_id': conversation_id})
        for _ in range(24):
            instructions, tools = _instructions(context)
            training = any(s.startswith('training.') for s in state.get('skills', []))
            nutrition = any(s.startswith('nutrition.') for s in state.get('skills', []))
            from .ai_budget import compact_app_context, compact_training_proposal
            payload = {'message': text, 'recent_exchange': bounded_history(history, 8000, 6),
                'task_memory': _memory(state), 'active_skills': state.get('skills', []),
                'previous_turn_results': state.get('last_turn_results', []),
                'retained_references': {k: compact_training_proposal(state[k]) if k == 'last_training_proposal' else state[k]
                    for k in ('last_training_proposal', 'planning_preview') if training and k in state},
                'nutrition_context': state.get('nutrition', {}) if nutrition else None,
                'ui_references': compact_app_context({'ride': options.get('ride_context'), 'sections': options.get('section_context'),
                    'plots': options.get('plot_context'), 'coaching': options.get('coaching_context') if training else None})}
            current_input = {'role': 'user', 'content': compact_json(payload)}
            if messages:
                messages[0] = current_input
            else:
                messages.append(current_input)
            token = CURRENT.set(runtime)
            try:
                stage = 'model_response'
                decision = active_provider(path).respond(messages, instructions, list(tools.values()), timeout_seconds=180)
            finally:
                CURRENT.reset(token)
            stage = 'native_response'
            messages.extend(decision.get('messages', []))
            calls = decision.get('calls') or []
            if not calls:
                reply = decision.get('reply')
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError('The assistant returned no answer. The current task is retained.')
                status = decision.get('status') or _result_status(results)
                if status not in ('completed', 'awaiting_information', 'review'):
                    status = 'completed'
                break
            if not isinstance(calls, list):
                raise ValueError('The provider returned invalid native tool calls')
            step_results = []
            for call in calls:
                name, args = call.get('name'), call.get('arguments', {})
                if name not in tools:
                    output = {'result': {'error': 'Load the appropriate skill before using this tool.'}, 'evidence': None}
                else:
                    token = CURRENT.set(runtime)
                    try:
                        stage = 'tool:' + name
                        output = _tool(name, args, context)
                    finally:
                        CURRENT.reset(token)
                messages.append(tool_result_message(call, output['result'], decision.get('transport', 'responses')))
                step_results.append({'tool': name, 'arguments': args, 'result': output['result']})
                if output['evidence']:
                    evidence.append(output['evidence'])
                    yield emit({'type': 'tool', 'evidence': output['evidence']})
            results.extend(step_results)
            # Keep native function-call/output pairs and opaque reasoning items in
            # their original order. Skill instructions/schemas are replaced above.
            if len(compact_json(results)) > 64000:
                results = results[-4:]
                results.insert(0, {'note': 'Older results omitted from this step; record references and task memory remain. Re-query narrowly if needed.'})
        else:
            raise BudgetExceeded('This investigation reached its step allowance. The task and planning draft are retained; continue with a focused next step.')
        state['history'] = bounded_history([*history, {'role': 'user', 'content': text, 'local_date': today},
            {'role': 'assistant', 'content': reply, 'local_date': today}], 24000, 20)
        state['status'] = status
        yield emit({'type': 'delta', 'text': reply})
        yield emit({'type': 'complete', 'provider': provider, 'model': model, 'workflow': 'skills',
                    'evidence': evidence, 'skills': state.get('skills', []), 'task_status': status, 'usage': runtime.summary()})
    except Exception as error:
        public = shared_allowance_message(error)
        if public is None:
            public = str(error) if isinstance(error, BudgetExceeded) else 'The assistant could not finish this turn. Its task context and confirmed results are retained. Check saved results before retrying.'
        state['status'] = 'blocked'
        state['last_error'] = public
        state['last_failure'] = {'stage': stage, 'type': type(error).__name__, 'operation_id': operation}
        state['history'] = bounded_history([*history, {'role': 'user', 'content': text, 'local_date': today},
            {'role': 'assistant', 'content': public, 'local_date': today}], 24000, 20)
        yield emit({'type': 'error', 'message': public})
        yield emit({'type': 'complete', 'provider': provider, 'model': model, 'workflow': 'skills',
                    'evidence': evidence, 'skills': state.get('skills', []), 'task_status': 'blocked', 'usage': runtime.summary()})
        logging.getLogger('uvicorn.error').warning('skill_agent_turn_failed %s', compact_json(state['last_failure']))
    finally:
        if results:
            state['last_turn_results'] = _receipts(results)
        if not events or events[-1]['type'] != 'complete':
            state['status'] = 'interrupted'
            events.extend([{'type': 'error', 'message': 'The turn was interrupted. Inspect confirmed results before retrying.'},
                           {'type': 'complete', 'workflow': 'skills', 'evidence': evidence, 'usage': runtime.summary()}])
        with bookkeeping(path) as c:
            c.execute('UPDATE assistant_skill_sessions SET state_json=?,active_operation=NULL,updated_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND active_operation=?',
                      (compact_json(state), conversation_id, operation))
            c.execute('UPDATE assistant_skill_turns SET events_json=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE operation_id=?',
                      (compact_json(events), state.get('status', 'blocked'), operation))
        logging.getLogger('uvicorn.error').info('skill_agent_usage %s', compact_json({'operation_id': operation,
            'skills': state.get('skills', []), 'status': state.get('status'), **runtime.summary()}))
