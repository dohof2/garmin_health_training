"""Structured session selection around existing prescription/save validators."""
import hashlib
import json
from datetime import datetime, timezone

from .database import connect
from .training import encoded

PREFIX = '@session:'


def preview(arguments, path=None, now=None):
    allowed = {'workout_id', 'expected_revision', 'action', 'request', 'source_workout_id', 'minutes'}
    if set(arguments) - allowed:
        raise ValueError('Unsupported session-change fields')
    request = PREFIX + encoded(arguments)
    if len(request) > 1500:
        raise ValueError('Describe this session edit in fewer than 800 characters')
    result = build(arguments, path, now)
    result['request'] = request
    return result


def build(arguments, path=None, now=None):
    from .training_adjustments import propose
    now = now or datetime.now(timezone.utc)
    with connect(path) as c:
        row = c.execute('SELECT id,sport,revision,scheduled_for FROM planned_workouts WHERE id=?', (arguments.get('workout_id'),)).fetchone()
    if not row:
        raise ValueError('The selected workout was not found')
    if type(arguments.get('expected_revision')) is not int or row['revision'] != arguments['expected_revision']:
        raise ValueError('The selected workout changed. Read it again before preparing an edit.')
    action = arguments.get('action')
    message = arguments.get('request') or ''
    if action == 'replace_with_endurance':
        if row['sport'] != 'strength':
            raise ValueError('This replacement supports a planned strength session as its target')
        minutes = arguments.get('minutes')
        if minutes is not None and (type(minutes) is not int or not 10 <= minutes <= 180):
            raise ValueError('Choose a ride duration between 10 and 180 minutes')
        message = 'Replace strength with an endurance ride' + (f' for {minutes} minutes' if minutes else '')
    elif action == 'skip':
        message = 'Skip this session'
    elif action != 'adjust' or not isinstance(message, str) or not message.strip():
        raise ValueError('Choose adjust, skip, or replace_with_endurance and describe the intended change')
    if action != 'adjust' and arguments.get('request'):
        message += '\n' + arguments['request']
    result = propose(message, path, now, selected_id=row['id'], source_id=arguments.get('source_workout_id'))
    result['request'] = PREFIX + encoded(arguments)
    return result


def schedule(arguments, path=None, now=None):
    from .active_training import swap_workouts, reschedule
    now = now or datetime.now(timezone.utc)
    with connect(path) as c:
        first = c.execute('SELECT * FROM planned_workouts WHERE id=?', (arguments['workout_id'],)).fetchone()
        if not first or first['revision'] != arguments['expected_revision']:
            raise ValueError('The selected workout changed. Read it again.')
        if arguments.get('other_workout_id'):
            second = c.execute('SELECT * FROM planned_workouts WHERE id=?', (arguments['other_workout_id'],)).fetchone()
            if not second or second['revision'] != arguments.get('other_expected_revision'):
                raise ValueError('The other workout changed. Read it again.')
            swap_workouts(first['id'], second['id'], first['revision'], second['revision'], path, now, preview=True)
            program = c.execute('SELECT plan_id,revision FROM active_training_program WHERE id=1').fetchone()
            adjustments = [{'workout_id': a['id'], 'expected_revision': a['revision'], 'title': a['title'],
                'date': a['scheduled_for'][:10], 'changes': {'scheduled_for': b['scheduled_for']}}
                for a, b in ((first, second), (second, first))]
            result = {'tool': 'propose_training_adjustment', 'kind': 'adaptation', 'status': 'proposal',
                'root_plan_id': program['plan_id'], 'program_revision': program['revision'], 'changes': {},
                'adjustments': adjustments, 'request': '@schedule:' + encoded(arguments),
                'message': 'Review swapping these two sessions. Save changes both dates together.'}
            result['fingerprint'] = hashlib.sha256(encoded({k: result[k] for k in ('root_plan_id', 'program_revision', 'adjustments')}).encode()).hexdigest()
            return result
    # Validate a move in a rolled-back transaction using the actual scheduler.
    from .database import rollback_preview
    with rollback_preview(path):
        reschedule(first['id'], None, first['revision'], path, now,
                   scheduled_date=arguments.get('date'), start_time=arguments.get('start_time'))
    return {'tool': 'propose_training_adjustment', 'kind': 'schedule', 'status': 'proposal',
        'workout_id': first['id'], 'expected_revision': first['revision'],
        'changes': {'scheduled_date': arguments['date'], 'start_time': arguments.get('start_time')},
        'message': 'Review moving ' + first['title'] + ' to ' + arguments['date'] + '. Nothing is saved yet.'}
