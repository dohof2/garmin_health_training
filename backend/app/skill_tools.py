"""Focused tool adapters over the app's domain services, without role routing."""
import json
import uuid
from datetime import date

from .ai_budget import compact_json, compact_active_plan, compact_training_context, bounded_history
from .assistant_evidence import tool_evidence
from .database import connect


def definition(name, description, properties, required=()):
    return {'name': name, 'description': description, 'input_schema': {
        'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}}


STRING = {'type': 'string'}
INTEGER = {'type': 'integer'}
OBJECT = {'type': 'object'}
LOCAL = [
    definition('preview_workout_duration','Preview an explicit duration/time allowance change. scope=once selects a workout ID or date; scope=plan updates settings, every matching scheduled workout and future generation for the remaining plan. Use sport/workout_type=all for all. Save applies atomically; no writes here.',
        {'scope':{'type':'string','enum':['once','plan']},'minutes':INTEGER,'sport':STRING,'workout_type':STRING,'workout_id':STRING,'date':STRING},('scope','minutes')),
    definition('get_training_notes','Read concise recurring preferences by activity and workout type. Omit filters to browse the small note tree.',
        {'activity':STRING,'workout_type':STRING}),
    definition('save_training_note','Save or delete an explicitly requested recurring training preference. Replace its existing topic; never append conversation history. One line, at most 160 characters. This saves a note, not a workout or Garmin update.',
        {'activity':STRING,'workout_type':STRING,'topic':STRING,'text':{'type':'string','maxLength':160},
         'settings':{'type':'object','properties':{'sets':INTEGER,'rest_seconds':INTEGER,'continuous_endurance':{'type':'boolean','enum':[True]}},'additionalProperties':False},
         'expected_revision':INTEGER,'operation':{'type':'string','enum':['upsert','delete']}},
        ('activity','workout_type','topic','expected_revision')),
    definition('lookup_workouts', 'Read scoped planned/completed workouts. Prefer IDs or dates. Full instructions for at most two results; never all history by default.',
        {'id': STRING, 'date': STRING, 'start_date': STRING, 'end_date': STRING, 'sport': STRING,
         'limit': {'type': 'integer', 'minimum': 1, 'maximum': 14}, 'details': {'type': 'boolean'}}),
    definition('lookup_program', 'Read the active program brief, dates and blocks, without full workout/history snapshots.', {}),
    definition('preview_session_change', 'Preview one selected workout. For interval count/work/recovery edits choose edit_intervals with intervals; total duration and other blocks/targets stay fixed. Otherwise adjust, skip, or replace_with_endurance.',
        {'workout_id': STRING, 'expected_revision': INTEGER, 'action': {'type': 'string', 'enum': ['adjust', 'edit_intervals', 'skip', 'replace_with_endurance']},
         'intervals':{'type':'object','properties':{'count':INTEGER,'work_seconds':INTEGER,'recovery_seconds':INTEGER},'additionalProperties':False},
         'manual_override': {'type': 'boolean', 'description': 'True for a concrete interval/block change explicitly requested by the user. Warn above 20% instead of rejecting; Save is required. Never use for automatic planning.'},
         'request': {'type': 'string', 'maxLength': 800}, 'source_workout_id': STRING, 'minutes': INTEGER},
        ('workout_id', 'expected_revision', 'action')),
    definition('preview_strength_prescription', 'Preview sets/rest on 1–7 exact strength workouts together. Sets means total sets. Preserve reps and loads; recalculate duration. Explicit edits may be saved locally while Garmin reconciliation remains separate. No save or send.',
        {'workouts':{'type':'array','maxItems':7,'items':{'type':'object','properties':{'workout_id':STRING,'expected_revision':INTEGER},'required':['workout_id','expected_revision'],'additionalProperties':False}}, 'sets':INTEGER,'rest_seconds':INTEGER}, ('workouts',)),
    definition('preview_strength_exercise_addition','Preview adding a reviewed bodyweight exercise to 1–7 exact strength sessions in one atomic proposal. Preserve existing exercises. Missing reps/rest use common values from each routine and are shown in the review. No save.',
        {'workouts':{'type':'array','maxItems':7,'items':{'type':'object','properties':{'workout_id':STRING,'expected_revision':INTEGER},'required':['workout_id','expected_revision'],'additionalProperties':False}},
         'exercise':{'type':'object','properties':{'id':STRING,'sets':INTEGER,'repetitions':INTEGER,'rest_seconds':INTEGER},'required':['id','sets'],'additionalProperties':False}},
        ('workouts','exercise')),
    definition('preview_schedule_change', 'Preview swapping two exact workouts or moving one to an ISO date; no save. Supply both revisions for a swap.',
        {'workout_id': STRING, 'expected_revision': INTEGER, 'other_workout_id': STRING, 'other_expected_revision': INTEGER,
         'date': STRING, 'start_time': STRING}, ('workout_id', 'expected_revision')),
    definition('preview_workout_feedback', 'Prepare completion/feedback for a selected workout; existing Save applies it.',
        {'workout_id': STRING, 'changes': OBJECT}, ('workout_id', 'changes')),
    definition('preview_strength_progression', 'Preview an explicitly requested set-count progression across upcoming strength sessions. Use only for a program-wide change, not an individual session.', {'sets': INTEGER}, ('sets',)),
    definition('preview_program_format', 'Preview explicitly removing warmup/cooldown from steady endurance rides throughout the program and remembering a continuous format. A single-session format change uses preview_session_change.', {}),
    definition('get_activity_detail', 'Read detailed recorded evidence for one activity ID.', {'activity_id': STRING}, ('activity_id',)),
    definition('nutrition_day', 'Read totals, target, missing nutrients, and saved meals for one local ISO date.', {'date': STRING}),
    definition('nutrition_conversation', 'Apply understood structured nutrition inputs. No second model call. log saves explicit consumed foods in grams with estimated per-100g nutrients or null. correct changes an exact meal/item quantity or date; targets prepares a reviewed calculation. Read actual saved flags.',
        {'intent': {'type': 'string', 'enum': ['log', 'correct', 'targets']}, 'date': STRING,
         'ingredients': {'type': 'array', 'maxItems': 30, 'items': {'type': 'object', 'properties': {
            'name': STRING, 'grams': {'type': 'number'}, 'meal_type': STRING, 'assumptions': STRING,
            'nutrients_per_100g': {'type': ['object', 'null'], 'properties': {k: {'type': ['number', 'null']} for k in ('calories_kcal', 'protein_grams', 'fat_grams', 'carbohydrate_grams')}}}}},
         'target_request': OBJECT, 'meal_id': STRING, 'expected_revision': INTEGER, 'item_id': STRING, 'quantity': {'type': 'number'},
         'replacement': {'type': 'object', 'properties': {'name': STRING, 'grams': {'type': 'number'}, 'food_id': STRING, 'nutrients_per_100g': OBJECT, 'assumptions': STRING}},
         'meal_type': {'type': 'string', 'enum': ['meal', 'breakfast', 'lunch', 'dinner', 'snack']}}, ('intent',)),
    definition('find_food', 'Search the local USDA catalog for public food names and per-100g composition. Use its exact food IDs for sourced corrections.', {'query': STRING}, ('query',)),
    definition('app_status', 'Read connection state, sync freshness, and publication status. No credentials.', {}),
    definition('open_app_workflow', 'Return the existing app review/control or a supported download link. This does not run, save, sync, or publish anything.',
        {'workflow': {'type': 'string', 'enum': ['sync', 'publication', 'import', 'export', 'backup', 'restore', 'dashboard', 'nutrition_library']},
         'dataset': {'type': 'string', 'enum': ['activities', 'metrics']}, 'workout_ids': {'type': 'array', 'items': STRING, 'maxItems': 14}}, ('workflow',)),
]
LOCAL_BY_NAME = {item['name']: item for item in LOCAL}
READ_TOOLS = {'get_training_notes','lookup_workouts', 'lookup_program', 'get_activity_detail', 'nutrition_day', 'find_food', 'app_status'}


def available_definitions():
    from .ai_tools import tool_definitions
    from .chat_access import READ_ONLY, ALLOW_NUTRITION
    definitions = {d['name']: d for d in tool_definitions()}
    definitions.update({d['name']: d for d in LOCAL if not READ_ONLY.get() or d['name'] in READ_TOOLS or d['name']=='nutrition_conversation' and ALLOW_NUTRITION.get()})
    # Never expose the obsolete free-text adjustment entry point to the agent.
    definitions.pop('propose_training_adjustment', None)
    for name in ('log_maintenance','update_maintenance','undo_maintenance'):
        if name in definitions:
            d = definitions[name]
            schema = d['input_schema']
            definitions[name] = {**d, 'input_schema': {**schema,
                'properties': {k:v for k,v in schema['properties'].items() if k!='operation_id'},
                'required': [k for k in schema.get('required',[]) if k!='operation_id']}}
    return definitions


def canonical_call(name, arguments):
    if isinstance(arguments, dict) and name in ('log_maintenance','update_maintenance','undo_maintenance'):
        arguments = {k:v for k,v in arguments.items() if k!='operation_id'}
    return json.dumps([name,arguments], ensure_ascii=False, sort_keys=True, separators=(',',':'))


def validate(defn, arguments):
    if not isinstance(arguments, dict):
        raise ValueError('Tool arguments must be an object')
    schema = defn['input_schema']
    if set(arguments) - set(schema['properties']):
        raise ValueError('Unsupported fields for ' + defn['name'])
    missing = set(schema.get('required', [])) - set(arguments)
    if missing:
        raise ValueError('Missing fields: ' + ', '.join(sorted(missing)))
    for key, value in arguments.items():
        field = schema['properties'][key]
        if 'enum' in field and value not in field['enum']:
            raise ValueError('Unsupported value for ' + key)
        typ = field.get('type')
        if typ == 'string' and not isinstance(value, str) or typ == 'integer' and type(value) is not int or typ == 'boolean' and type(value) is not bool or typ == 'object' and not isinstance(value, dict) or typ == 'array' and not isinstance(value, list):
            raise ValueError('Invalid type for ' + key)
        if isinstance(value, str) and len(value) > field.get('maxLength', 10000):
            raise ValueError('Too much text for ' + key)


def lookup_workouts(args, path, today):
    clauses = ["p.deleted_at IS NULL", "w.completion_status NOT IN ('cancelled','missed')"]
    values = []
    for key, column, operator in [('id', 'w.id', '='), ('date', 'substr(w.scheduled_for,1,10)', '='),
            ('start_date', 'substr(w.scheduled_for,1,10)', '>='), ('end_date', 'substr(w.scheduled_for,1,10)', '<='), ('sport', 'w.sport', '=')]:
        if args.get(key):
            if 'date' in key:
                date.fromisoformat(args[key])
            clauses.append(column + operator + '?')
            values.append(args[key])
    if not any(args.get(k) for k in ('id', 'date', 'start_date', 'end_date')):
        clauses.append('substr(w.scheduled_for,1,10)>=?')
        values.append(today)
    limit = args.get('limit', 7)
    if type(limit) is not int or not 1 <= limit <= 14:
        raise ValueError('Choose 1–14 workouts')
    with connect(path) as c:
        rows = c.execute('SELECT w.id,w.training_plan_id,w.title,w.sport,w.scheduled_for,w.revision,w.completion_status,w.publish_status,w.definition_json FROM planned_workouts w JOIN training_plans p ON p.id=w.training_plan_id WHERE ' + ' AND '.join(clauses) + ' ORDER BY w.scheduled_for,w.id LIMIT ?', (*values, limit + 1)).fetchall()
        result = []
        for row in rows[:limit]:
            item = dict(row)
            definition = json.loads(item.pop('definition_json'))
            item['definition'] = definition if args.get('details') and len(rows) <= 2 else {key: definition[key] for key in ('duration_minutes', 'scheduled_date', 'workout_kind', 'effort_target', 'review_hold') if key in definition}
            result.append(item)
    return {'workouts': result, 'truncated': len(rows) > limit, 'scope': args,
            'note': 'Full instructions require details=true and at most two selected results.'}


def lookup_program(path):
    with connect(path) as c:
        row = c.execute('SELECT plan_id,status,revision,state_json FROM active_training_program WHERE id=1').fetchone()
    if not row:
        return {'program': None}
    state = json.loads(row['state_json'])
    return {'program': {key: row[key] for key in ('plan_id', 'status', 'revision')},
        **{key: state[key] for key in ('timezone', 'starts_on', 'ends_on', 'brief', 'duration_settings', 'duration_week_allowances') if key in state},
        'blocks': [{k: b[k] for k in ('week', 'starts_on', 'phase', 'focus') if k in b} for b in state.get('blocks', [])]}


def compact_result(value):
    """Keep chart artifacts in UI; return explicit bounded model evidence."""
    if isinstance(value, list):
        return [compact_result(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in ('definition_json', 'state_json', 'context_json'):
            continue
        if key == 'points' and isinstance(item, list):
            numeric = [p['y'] for p in item if isinstance(p, dict) and type(p.get('y')) in (int, float)]
            result['point_summary'] = {'displayed_count': len(item), 'first': item[0] if item else None,
                'last': item[-1] if item else None, 'minimum': min(numeric) if numeric else None,
                'maximum': max(numeric) if numeric else None, 'full_points_available_in_app': True}
        else:
            result[key] = compact_result(item)
    return result


def execute(name, arguments, context):
    path, state, today, tz = (context[k] for k in ('path', 'state', 'today', 'timezone'))
    defns = available_definitions()
    if name not in defns:
        raise ValueError('This tool is not available in the current channel')
    args = dict(arguments)
    if name in ('log_maintenance','update_maintenance','undo_maintenance'):
        args.pop('operation_id', None)
    validate(defns[name], args)
    if 'timezone' in defns[name]['input_schema']['properties']:
        args['timezone'] = tz
    operation = str(uuid.uuid5(uuid.NAMESPACE_URL, context['operation_id'] + ':' + canonical_call(name, arguments)))
    evidence_name = name
    if name == 'get_training_notes':
        from .training_notes import read
        notes=read(path,**args)
        result={'notes':notes['notes']} if args.get('activity') else {'branches':{sport:{kind:[n['topic'] for n in entries] for kind,entries in kinds.items()} for sport,kinds in notes['tree'].items()},'limits':notes['limits']}
    elif name == 'save_training_note':
        from .training_notes import save
        result=save(args,path)
    elif name == 'lookup_workouts':
        result = lookup_workouts(args, path, today)
    elif name == 'lookup_program':
        result = lookup_program(path)
    elif name == 'get_training_context':
        from .settings import get_settings
        from .training import _preferences, training_context
        from .training_coach import read_brief
        settings = get_settings(path)
        result = {'tool': name, 'profile': settings['profile'], 'goals': settings['goals']}
        from .training_notes import read
        result['training_notes']=read(path)['notes']
        skills = state.get('skills', [])
        if any(s != 'profile.personal' for s in skills):
            if any(s.startswith('training.programs.') for s in skills):
                training = training_context(path, context['now'])
                result['training'] = {k: training[k] for k in ('revision','answers','missing','stale','questions','blockers','planning_limits','volume_estimates','recent_feedback') if k in training}
            else:
                with connect(path) as c:
                    result['training'] = _preferences(c)
            result['coaching_brief'] = read_brief(path)
    elif name == 'preview_workout_duration':
        from .workout_duration import preview
        result = preview(args, path, context['now'])
        evidence_name = 'propose_training_adjustment'
    elif name == 'preview_session_change':
        from .session_changes import preview
        # The model has already scoped this action to one workout. Appending the
        # whole turn can mix in a different day's edit or reclassify a skip.
        if args.get('action') != 'skip' and not args.get('request'):
            args['request'] = context['message'].strip()
        result = preview(args, path, context['now'])
        evidence_name = 'propose_training_adjustment'
    elif name == 'preview_strength_prescription':
        from .strength_prescription import preview
        result = preview(args, path, context['now'])
        evidence_name = 'propose_training_adjustment'
    elif name == 'preview_strength_exercise_addition':
        from .strength_exercise_edits import preview
        result=preview(args,path,context['now'])
        evidence_name='propose_training_adjustment'
    elif name == 'preview_schedule_change':
        from .session_changes import schedule
        result = schedule(args, path, context['now'])
        evidence_name = 'propose_training_adjustment'
    elif name == 'preview_workout_feedback':
        from .active_training import propose_adjustment
        result = propose_adjustment(args, path)
        evidence_name = 'propose_training_adjustment'
    elif name == 'preview_strength_progression':
        from .training_adjustments import propose
        if not 1 <= args['sets'] <= 5:
            raise ValueError('Choose 1–5 sets per exercise')
        result = propose(f"Use {args['sets']} sets for every strength exercise from the next workout", path, context['now'])
        evidence_name = 'propose_training_adjustment'
    elif name == 'preview_program_format':
        from .workout_format import propose
        result = propose('Remove warmup and cooldown from all steady endurance rides', path, context['now'])
        evidence_name = 'propose_training_adjustment'
    elif name == 'get_activity_detail':
        from .history import get_activity
        result = get_activity(args['activity_id'], path, tz)
        if result is None:
            raise ValueError('Recorded activity not found')
    elif name == 'nutrition_day':
        from .nutrition import daily_status
        result = daily_status(date.fromisoformat(args.get('date') or today), tz, path)
    elif name == 'nutrition_conversation':
        result = _nutrition(args, context, operation)
        return result, {'tool': name, 'nutrition': result}
    elif name == 'find_food':
        from .nutrition import food_search
        result = food_search(args['query'])
    elif name == 'app_status':
        from .garmin_connection import connection_state
        from .rolling_publication import status
        connection = connection_state(path)
        with connect(path) as c:
            checkpoints = [dict(r) for r in c.execute('SELECT data_type,status,coverage_start,coverage_end FROM sync_checkpoints')]
            job = c.execute("SELECT status,progress_current,progress_total,finished_at FROM jobs WHERE job_type='garmin_sync' ORDER BY created_at DESC,rowid DESC LIMIT 1").fetchone()
        result = {'connection': {k: connection[k] for k in ('status', 'detail', 'updated_at') if k in connection},
                  'sync': {'checkpoints': checkpoints, 'last_job': dict(job) if job else None}, 'publication': status(path)}
    elif name == 'open_app_workflow':
        links = {'sync': '#data', 'publication': '#training', 'import': '#data',
                 'export': '/api/exports/csv/' + args.get('dataset', 'activities'), 'backup': '/api/exports/backup.zip',
                 'restore': '#data', 'dashboard': '#dashboard', 'nutrition_library': '#nutrition'}
        result = {'status': 'review_required', 'workflow': args['workflow'], 'url': links[args['workflow']],
                  'workout_ids': args.get('workout_ids', []), 'message': 'Use this existing app control. No operation was executed.'}
    elif name == 'preview_training_plan':
        from .training_coach import preview, read_brief
        brief = args.get('brief') or read_brief(path)['brief']
        week = date.fromisoformat(args.get('week_start') or brief.get('program_start') or today)
        result = {'tool': name, **preview(brief, week, tz, path, context['now'], args.get('replace_plan_id'),
            candidate_answers=args.get('candidate_answers'), session_changes=args.get('session_changes'))}
    else:
        from .ai_tools import execute_tool
        if name in ('log_maintenance', 'update_maintenance', 'undo_maintenance'):
            args['operation_id'] = operation
        result = execute_tool(name, args, path)
    evidence = tool_evidence(evidence_name, result)
    if name == 'open_app_workflow':
        labels = {'sync':'Open Data & sync','publication':'Review in Training','import':'Open import controls',
                  'export':'Download CSV','backup':'Download backup','restore':'Open restore preview',
                  'dashboard':'Open dashboard','nutrition_library':'Open Nutrition library'}
        evidence['action_link'] = {'url': result['url'], 'label': labels[args['workflow']]}
    if name in ('log_maintenance', 'update_maintenance', 'undo_maintenance'):
        evidence['maintenance'] = result
    if name in ('preview_strength_prescription','preview_workout_duration','preview_session_change', 'preview_strength_exercise_addition','preview_schedule_change', 'preview_workout_feedback', 'preview_strength_progression', 'preview_program_format'):
        state['last_training_proposal'] = result
    model_result = compact_result(result)
    if isinstance(result, dict) and result.get('tool') == 'propose_training_adjustment':
        from .ai_budget import compact_training_proposal
        model_result = compact_training_proposal(result)
    if name == 'get_training_context':
        model_result = compact_training_context(result, context['message'], today)
    elif name == 'preview_training_plan':
        state['planning_preview'] = {k: result[k] for k in ('status', 'brief', 'candidate_answers', 'week_start', 'fingerprint', 'questions') if k in result}
        model_result = {k: model_result[k] for k in model_result if k not in ('evidence', 'capability', 'context', 'raw_answers')}
    return model_result, evidence


def _nutrition(args, context, operation):
    from .nutrition_operations import execute as nutrition_operation
    from .chat_access import READ_ONLY, ALLOW_NUTRITION
    access_token = READ_ONLY.set(False) if READ_ONLY.get() and ALLOW_NUTRITION.get() else None
    try:
        return nutrition_operation(args, context, operation)
    finally:
        if access_token is not None:
            READ_ONLY.reset(access_token)
