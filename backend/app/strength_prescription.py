"""Reviewed sets/rest edits to exact dated sessions; publication snapshots stay immutable."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .training import _context, encoded

PREFIX = '@strength_prescription:'


def preview(arguments, path=None, now=None):
    from .active_training import _program_workouts
    from .training_accounting import session_day, counts_toward_plan
    from .training_constraints import assign_slot, day_limit, optional_cap
    from .training_notes import strength_timing
    from .training_prescriptions import validate_workout
    now = now or datetime.now(timezone.utc)
    if set(arguments) - {'workouts', 'sets', 'rest_seconds'}:
        raise ValueError('Unsupported strength prescription fields')
    targets = arguments.get('workouts')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 7:
        raise ValueError('Choose 1–7 dated strength sessions')
    if not {'sets', 'rest_seconds'} & arguments.keys():
        raise ValueError('Specify sets or rest_seconds')
    for key, low, high in (('sets', 1, 5), ('rest_seconds', 0, 600)):
        if key in arguments and (type(arguments[key]) is not int or not low <= arguments[key] <= high):
            raise ValueError('Use 1–5 sets and 0–600 seconds of rest')
    for target in targets:
        if not isinstance(target, dict) or set(target) != {'workout_id', 'expected_revision'} or not isinstance(target['workout_id'], str) or type(target['expected_revision']) is not int:
            raise ValueError('Supply each workout ID and current revision')
    if len({t['workout_id'] for t in targets}) != len(targets):
        raise ValueError('Choose distinct workouts')
    with connect(path) as c:
        program = c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if not program:
            raise ValueError('Activate a plan before editing its strength workouts')
        state = json.loads(program['state_json']); tz = state['timezone']
        today = now.astimezone(ZoneInfo(tz)).date()
        context = _context(c, now, timezone_name=tz)
        if context['blockers'] or context['answers'].get('pain_or_illness'):
            raise ValueError('Review saved restrictions or pain/illness before changing strength prescriptions')
        sessions = _program_workouts(c, program['plan_id'])
        by_id = {w['id']: w for w in sessions}; updated = {}; changes = []; warnings = []
        for target in targets:
            row = by_id.get(target['workout_id'])
            if not row or row['revision'] != target['expected_revision']:
                raise ValueError('A selected workout changed. Read its current revision before editing')
            day = session_day(row, tz); old = json.loads(row['definition_json'])
            if row['sport'] != 'strength' or row['completion_status'] != 'planned' or day < today:
                raise ValueError('Choose upcoming planned strength sessions; completed workouts are preserved')
            if any(old.get(k) for k in ('fixed_commitment', 'event_id', 'review_hold')) or old.get('template_id') == 'fixed_commitment':
                raise ValueError('Review the selected session’s fixed commitment or hold before editing')
            if row['publish_status'] not in ('local', 'published', 'update_needed', 'publishing'):
                raise ValueError('Review this session’s publication state before editing')
            if not old.get('exercises'):
                raise ValueError('The selected strength workout has no exercises')
            new = copy.deepcopy(old)
            for exercise in new['exercises']:
                for key in ('sets', 'rest_seconds'):
                    if key in arguments: exercise[key] = arguments[key]
            new.pop('strength_set_policy', None)
            strength_timing(new, state.get('strength_set_policy'))
            new['user_adjusted'] = True
            validate_workout(new)
            assign_slot(context['answers']['week_schedule'], day.weekday(), 'strength', new['duration_minutes'], old.get('schedule_slot_id'))
            updated[row['id']] = new
            changes.append({'workout_id': row['id'], 'expected_revision': row['revision'], 'title': row['title'], 'date': day.isoformat(),
                'changes': {'definition': new}, 'summary': [f"{e['name']}: {e['sets']} total sets, {e['rest_seconds']}s rest" for e in new['exercises']] + [f"Estimated duration: {new['duration_minutes']} minutes. Repetitions and loads retained."]})
            if row['publish_status'] == 'publishing':
                item = c.execute("SELECT state,error FROM garmin_publication_items WHERE workout_id=? AND state NOT IN ('verified','superseded') ORDER BY rowid DESC LIMIT 1", (row['id'],)).fetchone()
                warnings.append(f"{day}: local edit only. Existing Garmin publication remains unresolved" + (': ' + item['error'] if item and item['error'] else '.') + ' Saving does not resolve or retry that send.')
            if old.get('training_block', {}).get('phase') == 'Recovery / review':
                warnings.append(f'{day}: explicit prescription also changes a recovery-week workout; review the added work before Save.')
        cap, _ = optional_cap(context.get('raw_answers', context['answers']), 'strength')
        for item in changes:
            day = datetime.fromisoformat(item['date']).date()
            peers = [p for p in sessions if counts_toward_plan(p, today, tz)]
            total = sum(updated.get(p['id'], json.loads(p['definition_json']))['duration_minutes'] for p in peers if session_day(p, tz) == day)
            if total > day_limit(context['answers']['week_schedule'], day.weekday()):
                raise ValueError(f'{day}: requested prescription exceeds the shared day limit')
            anchor = datetime.fromisoformat(state['starts_on']).date()
            week = anchor.toordinal() + ((day-anchor).days//7)*7
            weekly = sum(updated.get(p['id'], json.loads(p['definition_json']))['duration_minutes'] for p in peers if p['sport']=='strength' and week <= session_day(p,tz).toordinal() < week+7)
            if cap is not None and weekly > cap:
                raise ValueError('Requested prescription exceeds the explicit weekly strength cap')
    result = {'tool': 'propose_training_adjustment', 'kind': 'adaptation', 'status': 'proposal',
        'request': PREFIX + encoded(arguments), 'root_plan_id': program['plan_id'], 'program_revision': program['revision'],
        'changes': {}, 'adjustments': changes, 'local_prescription_edit': True, 'warnings': warnings,
        'message': 'Review these sets/rest changes together. Save applies them locally. Garmin instructions need a separate publication review. Existing Garmin conflicts remain for publication review. ' + ' '.join(warnings)}
    result['fingerprint'] = hashlib.sha256(encoded({k:result[k] for k in ('root_plan_id','program_revision','adjustments')}).encode()).hexdigest()
    return result
