"""Reviewed duration settings shared by scheduled and future workouts."""
import copy
import hashlib
import json
import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .database import connect
from .training import encoded, _preferences, _revision, _snapshot

PREFIX = '@duration:'


def validate_schedule_fit(sessions, targets, tz, today):
    from datetime import timedelta
    days = {}; timed = []
    for row in sessions:
        definition = json.loads(row['definition_json'])
        start = datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz))
        day = definition.get('scheduled_date') or start.date().isoformat()
        if row['completion_status']!='planned' or day<today:continue
        minutes=targets.get(row['id'],definition['duration_minutes'])
        days[day]=days.get(day,0)+minutes
        if definition.get('time_unspecified'):continue
        end=start+timedelta(minutes=minutes)
        if row['id'] in targets and end.date()!=start.date():raise ValueError('The longer workout crosses midnight. Move its start time before changing duration.')
        timed.append((row['id'],start,end))
    for day,total in days.items():
        if total>1440:raise ValueError(f'The requested workouts exceed the time available on {day}.')
    for index,(identifier,start,end) in enumerate(timed):
        for peer,peer_start,peer_end in timed[index+1:]:
            if (identifier in targets or peer in targets) and start<peer_end and peer_start<end:
                raise ValueError('The longer workout overlaps another scheduled workout. Move its start time first.')


def matches(rule, definition):
    kind = definition.get('workout_kind') or definition.get('strength_purpose') or 'all'
    return (rule.get('sport', 'all') in ('all', definition['sport'])
            and rule.get('workout_type', 'all') in ('all', kind)
            and (not rule.get('slot_id') or rule['slot_id'] == definition.get('schedule_slot_id')))


def resize(old, minutes, answers):
    """Keep prescribed intensity and interval blocks; change the time budget."""
    from .training import workout_definition
    from .training_notes import apply_definition
    result = copy.deepcopy(old)
    if old['sport'] == 'strength':
        if minutes < 20:
            raise ValueError('Strength needs at least 20 minutes.')
        # Retain existing exercises and their settings. Extra time admits more
        # supported movements, without inferring heavier loads or extra sets.
        base = workout_definition('strength_foundation', minutes, answers)
        if old.get('strength_purpose'):base['strength_purpose']=old['strength_purpose']
        candidates = apply_definition(base, answers.get('_training_notes', []))['exercises']
        exercises = copy.deepcopy(old.get('exercises', []))
        used = old.get('warmup_minutes', 5) * 60 + sum(e['sets'] * (120 + e.get('rest_seconds', 90)) for e in exercises)
        if minutes < old['duration_minutes'] and used > minutes * 60:
            raise ValueError('The saved strength exercises and rests do not fit that duration. Review sets or exercises explicitly.')
        for exercise in candidates:
            cost = exercise['sets'] * (120 + exercise.get('rest_seconds', 90))
            if exercise['id'] not in {e['id'] for e in exercises} and used + cost <= minutes * 60:
                exercises.append(copy.deepcopy(exercise)); used += cost
        result['exercises'] = exercises
        result['strength_duration_allowance_minutes'] = minutes
        result.pop('strength_timing', None)
        result['duration_estimated'] = True
    else:
        steps = result.get('steps', [])
        candidates = [s for s in steps if 'steady' in str(s.get('name') or s.get('type')).lower()]
        if not candidates and len(steps) == 1:
            candidates = steps
        if not candidates:
            raise ValueError('This workout has no steady timed block to resize while preserving its intervals. Review its structure first.')
        block = max(candidates, key=lambda s: s.get('duration_seconds', 0))
        if block.get('termination', 'time') != 'time' or block.get('repetitions', 1) != 1:
            raise ValueError('The steady block must use a single timed duration.')
        block['duration_seconds'] += (minutes - old['duration_minutes']) * 60
        if block['duration_seconds'] <= 0:
            raise ValueError('That duration leaves no steady time after the saved intervals, warm-up and recovery.')
        if any(s.get('target') for s in steps):
            from .training_prescriptions import validate_workout
            result['duration_minutes'] = minutes
            validate_workout(result)
        result.pop('duration_guidance', None)
    result.update(duration_minutes=minutes, user_adjusted=True)
    result.pop('daily_base_definition', None)
    return result


def apply_generated(definition, state, answers):
    rule = next((r for r in reversed(state.get('duration_settings', [])) if matches(r, definition)), None)
    if not rule or definition.get('fixed_commitment') or definition.get('event_id'):
        return definition
    result = resize(definition, rule['minutes'], answers)
    result['duration_setting'] = rule
    return result


def preview(arguments, path=None, now=None):
    from .active_training import _program_workouts
    from .training import _context
    now = now or datetime.now(timezone.utc)
    if set(arguments) - {'scope', 'minutes', 'sport', 'workout_type', 'workout_id', 'date'}:
        raise ValueError('Unsupported duration setting fields')
    scope = arguments.get('scope'); minutes = arguments.get('minutes')
    if scope not in ('once', 'plan') or type(minutes) is not int or not 10 <= minutes <= 720:
        raise ValueError('Choose once or plan, and 10–720 whole minutes.')
    sport = arguments.get('sport', 'all'); kind = arguments.get('workout_type', 'all')
    from .training_constraints import SPORTS
    from .training_prescriptions import KINDS
    if sport not in ('all', *SPORTS) or kind not in ('all', *KINDS, 'cycling_support', 'general_fitness', 'strength_development'):
        raise ValueError('Choose a supported activity and workout type.')
    if scope == 'once' and not (arguments.get('workout_id') or arguments.get('date')):
        raise ValueError('Choose a workout ID or date for a one-time duration change.')
    if scope == 'plan' and (arguments.get('workout_id') or arguments.get('date')):
        raise ValueError('Plan duration settings use activity/workout type; omit one-time selectors.')
    if arguments.get('date'):date.fromisoformat(arguments['date'])
    with connect(path) as c:
        program = c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if not program:raise ValueError('Activate a plan before changing its workout durations.')
        state = json.loads(program['state_json']); tz = state['timezone']
        today = now.astimezone(ZoneInfo(tz)).date().isoformat()
        context = _context(c, now, brief=state['brief'], timezone_name=tz)
        if context['blockers']:
            raise ValueError('Review saved training restrictions before changing duration. '+' '.join(context['blockers']))
        if context['answers'].get('pain_or_illness') or any(f.get('pain_or_illness') for f in context['recent_feedback']):
            raise ValueError('Review reported pain or illness before changing training duration.')
        rule = {'sport': sport, 'workout_type': kind, 'minutes': minutes}
        changes = []
        from .training_notes import rows as note_rows
        answers = {**context['answers'], '_training_notes': note_rows(c)}
        sessions = _program_workouts(c, program['plan_id'])
        for row in sessions:
            old = json.loads(row['definition_json'])
            day = old.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()
            if row['completion_status'] != 'planned' or day < today:continue
            if scope == 'once' and (arguments.get('workout_id') and row['id'] != arguments['workout_id'] or arguments.get('date') and day != arguments['date']):continue
            if not matches(rule, old) or old.get('fixed_commitment') or old.get('event_id'):continue
            if old.get('review_hold'):raise ValueError('Resolve the matching workout’s review hold before changing its duration.')
            managed = c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=? AND verified_hash IS NOT NULL', (row['id'], row['garmin_workout_id'])).fetchone()
            if row['publish_status'] not in ('local', 'published', 'update_needed') or (row['publish_status'] != 'local' or row['garmin_workout_id']) and not managed:
                raise ValueError('Reconcile a matching workout’s Garmin publication before changing duration.')
            new = resize(old, minutes, answers)
            new['duration_setting'] = {**rule, 'scope': scope}
            changes.append({'workout_id': row['id'], 'expected_revision': row['revision'], 'title': row['title'], 'date': day,
                            'summary': [f'Duration allowance: {old["duration_minutes"]:g} → {minutes} minutes. Intensity targets are preserved.'], 'changes': {'definition': new}})
        if scope == 'once' and not changes:raise ValueError('No matching upcoming workout was found for this one-time change.')
        validate_schedule_fit(sessions,{item['workout_id']:minutes for item in changes},tz,today)
        proposal = {'tool': 'propose_training_adjustment', 'kind': 'adaptation', 'status': 'proposal',
                    'changes': {},
                    'request': PREFIX + encoded(arguments), 'root_plan_id': program['plan_id'], 'program_revision': program['revision'],
                    'preference_revision': context['revision'], 'adjustments': changes, 'duration_update': {**rule, 'scope': scope},
                    'message': f'Review {len(changes)} scheduled workout(s) with a {minutes}-minute duration allowance. '
                    + ('Save updates the plan duration setting, matching scheduled workouts and future workouts for the rest of this plan. ' if scope == 'plan' else 'Save updates only the selected workout(s) and their dated duration settings. ')
                    + 'Strength uses the time as a budget, with no requirement to fill it. Published workouts need a Garmin update. Recovery and restrictions still apply.'}
        proposal['fingerprint'] = hashlib.sha256(encoded({k: proposal[k] for k in ('root_plan_id', 'program_revision', 'preference_revision', 'adjustments', 'duration_update')}).encode()).hexdigest()
        return proposal


def persist(c, program, proposal, now):
    """Save recurring settings in the same transaction as all workout revisions."""
    rule = proposal['duration_update']
    current = _preferences(c)
    if current['revision'] != proposal['preference_revision']:
        raise ValueError('Time settings changed. Review a fresh proposal.')
    state = json.loads(program['state_json'])
    from .active_training import _program_workouts
    today = now.astimezone(ZoneInfo(state['timezone'])).date().isoformat()
    selector = json.loads(proposal['request'][len(PREFIX):])
    matching = []
    for row in _program_workouts(c,program['plan_id']):
        definition = json.loads(row['definition_json'])
        day = definition.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(state['timezone'])).date().isoformat()
        if row['completion_status']!='planned' or day<today or definition.get('fixed_commitment') or definition.get('event_id') or not matches(rule,definition):continue
        if rule['scope']=='once' and (selector.get('workout_id') and row['id']!=selector['workout_id'] or selector.get('date') and day!=selector['date']):continue
        matching.append(row['id'])
    if set(matching)!={item['workout_id'] for item in proposal['adjustments']}:
        raise ValueError('Matching workouts changed. Review a fresh duration proposal.')
    validate_schedule_fit(_program_workouts(c,program['plan_id']),{item['workout_id']:rule['minutes'] for item in proposal['adjustments']},state['timezone'],today)
    if rule['scope'] == 'once':
        # Keep recurrence unchanged, but make the dated allowance available to
        # subsequent weekly planning instead of silently reclaiming that time.
        from .training_accounting import completed_minutes, session_day
        from datetime import timedelta
        sessions = _program_workouts(c,program['plan_id'])
        targets = {item['workout_id']:rule['minutes'] for item in proposal['adjustments']}
        anchor = date.fromisoformat(state['starts_on'])
        weeks = {(anchor+timedelta(weeks=(date.fromisoformat(item['date'])-anchor).days//7),item['changes']['definition']['sport']) for item in proposal['adjustments']}
        allowances = state.setdefault('duration_week_allowances',{})
        for week,sport in weeks:
            planned = sum(targets.get(row['id'],json.loads(row['definition_json'])['duration_minutes']) for row in sessions if row['sport']==sport and row['completion_status']=='planned' and week<=session_day(row,state['timezone'])<week+timedelta(days=7) and session_day(row,state['timezone']).isoformat()>=today)
            total = planned+completed_minutes(c,sessions,week,date.fromisoformat(today),state['timezone'],sport)
            key=week.isoformat()+':'+sport
            allowances[key]=max(allowances.get(key,0),total)
        c.execute('UPDATE active_training_program SET state_json=? WHERE id=1',(encoded(state),))
        return
    rules = state.get('duration_settings', [])
    rules = [r for r in rules if (r.get('sport'), r.get('workout_type')) != (rule['sport'], rule['workout_type'])]
    state['duration_settings'] = rules + [rule]
    answers = copy.deepcopy(current['answers'])
    from .training_constraints import resolve
    answers['week_schedule'] = resolve(answers, state['brief'])['days']
    # This explicit time increase grants matching slots enough room. Keep
    # unrelated activity limits; shared-day ceilings include those peers.
    for day in answers['week_schedule']:
        for slot in day['activities']:
            if rule['workout_type']=='all' and rule['sport'] in ('all', slot['sport']):
                slot['max_minutes'] = max(slot.get('max_minutes') or 0, rule['minutes'])
        if day.get('total_limit_minutes') is not None:
            day['total_limit_minutes'] = max(day['total_limit_minutes'], sum(s.get('max_minutes') or 0 for s in day['activities']))
    caps = answers.setdefault('weekly_caps', {})
    plan_allowances = state.setdefault('duration_plan_allowances',{})
    for sport in {s['sport'] for d in answers['week_schedule'] for s in d['activities'] if rule['sport'] in ('all', s['sport'])}:
        allowance = sum(s.get('max_minutes') or 0 for d in answers['week_schedule'] for s in d['activities'] if s['sport'] == sport)
        if rule['workout_type']!='all':
            # A type-specific exception does not enlarge every activity slot.
            # Grant its extra weekly room separately from the generic schedule.
            from datetime import timedelta
            anchor=date.fromisoformat(state['starts_on']); extra={}
            for item in proposal['adjustments']:
                if item['changes']['definition']['sport']!=sport:continue
                old=_snapshot(c,item['workout_id']);old_definition=json.loads(old['definition_json'])
                week=anchor+timedelta(weeks=(date.fromisoformat(item['date'])-anchor).days//7)
                extra[week]=extra.get(week,0)+max(0,rule['minutes']-old_definition['duration_minutes'])
            allowance+=math.ceil(max(extra.values(),default=rule['minutes']))
        old = caps.get(sport) or {}
        caps[sport] = {'max_minutes': max(old.get('max_minutes') or 0, allowance), 'range_min_minutes': max(old.get('range_min_minutes') or 0, allowance)}
        plan_allowances[sport]=caps[sport]['max_minutes']
    from .training import validate_answers
    answers = {**answers, **validate_answers({'week_schedule': answers['week_schedule'], 'weekly_caps': caps})}
    revision = current['revision'] + 1
    confirmed = {**current['confirmed_at'], 'week_schedule': now.isoformat(), 'weekly_caps': now.isoformat()}
    c.execute('UPDATE training_preferences SET revision=?,answers_json=?,confirmed_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=1', (revision, encoded(answers), encoded(confirmed)))
    c.execute('INSERT INTO training_preference_revisions(revision,answers_json,confirmed_json) VALUES(?,?,?)', (revision, encoded(answers), encoded(confirmed)))
    c.execute('UPDATE active_training_program SET state_json=? WHERE id=1', (encoded(state),))


def sync_schedule(c, previous, answers, now):
    """Changing an existing slot's time also updates this plan and continuation."""
    from .active_training import _program_workouts
    from .training_constraints import resolve
    from .training_notes import rows as note_rows
    program = c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
    if not program or 'week_schedule' not in previous or 'week_schedule' not in answers:return 0
    before = {s['slot_id']: s for d in previous['week_schedule'] for s in d['activities']}
    changed = [s for d in answers['week_schedule'] for s in d['activities']
               if s['slot_id'] in before and s.get('max_minutes') is not None and s.get('max_minutes') != before[s['slot_id']].get('max_minutes')]
    if not changed:return 0
    # Existing settings controls use this same propagation path. Keep the saved
    # allowance consistent with the new slot budgets and its revision history.
    touched = {s['sport'] for s in changed}
    for day in answers['week_schedule']:
        if day.get('total_limit_minutes') is not None and any(s['slot_id'] in {s['slot_id'] for s in changed} for s in day['activities']):
            day['total_limit_minutes'] = max(day['total_limit_minutes'],sum(s['max_minutes'] for s in day['activities']))
    caps = answers.setdefault('weekly_caps',{})
    for sport in touched:
        allowance = sum(s['max_minutes'] for day in answers['week_schedule'] for s in day['activities'] if s['sport']==sport)
        old = caps.get(sport) or {}
        caps[sport] = {'max_minutes':max(old.get('max_minutes') or 0,allowance),'range_min_minutes':max(old.get('range_min_minutes') or 0,allowance)}
    from .training import validate_answers
    validate_answers({'week_schedule':answers['week_schedule'],'weekly_caps':caps})
    current = _preferences(c)
    confirmed = {**current['confirmed_at'],'weekly_caps':now.isoformat()}
    c.execute('UPDATE training_preferences SET answers_json=?,confirmed_json=? WHERE id=1',(encoded(answers),encoded(confirmed)))
    c.execute('UPDATE training_preference_revisions SET answers_json=?,confirmed_json=? WHERE revision=?',(encoded(answers),encoded(confirmed),current['revision']))
    state = json.loads(program['state_json']); tz = state['timezone']
    today = now.astimezone(ZoneInfo(tz)).date().isoformat()
    rules = [{'sport': s['sport'], 'workout_type': 'all', 'slot_id': s['slot_id'], 'minutes': s['max_minutes'], 'scope': 'plan'} for s in changed]
    state['duration_settings'] = [r for r in state.get('duration_settings', []) if r.get('slot_id') not in {s['slot_id'] for s in changed}] + rules
    resolved = resolve(answers, state['brief'])['days']
    generation_answers = {**answers, 'sports': list(dict.fromkeys(answers.get('sports', []) + [s['sport'] for d in resolved for s in d['activities']])), '_training_notes': note_rows(c)}
    count = 0; targets={}
    for row in _program_workouts(c, program['plan_id']):
        old = json.loads(row['definition_json'])
        day = old.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()
        if row['completion_status'] != 'planned' or day < today or not any(matches(r, old) for r in rules):continue
        if old.get('fixed_commitment') or old.get('event_id'):continue
        if old.get('review_hold'):raise ValueError('Resolve a matching workout’s review hold before changing its time setting.')
        managed = c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=? AND verified_hash IS NOT NULL', (row['id'], row['garmin_workout_id'])).fetchone()
        if row['publish_status'] not in ('local', 'published', 'update_needed') or (row['publish_status'] != 'local' or row['garmin_workout_id']) and not managed:
            raise ValueError('Reconcile a matching workout’s Garmin publication before changing its time setting.')
        new = apply_generated(old, state, generation_answers)
        targets[row['id']]=new['duration_minutes']
        c.execute("UPDATE planned_workouts SET definition_json=?,revision=revision+1,publish_status=CASE WHEN publish_status='local' THEN 'local' ELSE 'update_needed' END WHERE id=?", (encoded(new), row['id']))
        _revision(c, _snapshot(c, row['id'])); count += 1
    validate_schedule_fit(_program_workouts(c,program['plan_id']),targets,tz,today)
    c.execute('UPDATE active_training_program SET state_json=?,revision=revision+1 WHERE id=1', (encoded(state),))
    from .training_lifecycle import invalidate
    invalidate(c, program['plan_id'])
    return count
