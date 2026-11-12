"""Reviewed one-time replacement of a strength session with an easy ride."""
import copy
import hashlib
import json
import re
from datetime import timedelta

from .training import encoded


def requested(text):
    return bool(re.search(r'\bstrength\b', text) and
                re.search(r'\b(remove|replace|delete|instead)\b', text) and
                re.search(r'\b(bike|ride|cycling|endurance)\b', text))


def propose(base, rows, program, sessions, context, policy, capacity, today, text, illness, fatigue, source_id=None, path=None, now=None):
    from .training_prescriptions import cycling_dose, endurance, validate_workout
    from .training_accounting import counts_toward_plan, session_day, completed_minutes

    def answer(message, status='needs_input'):
        return {**base, 'status': status, 'message': message}

    if re.search(r"\b(don't|do not|never)\s+(remove|replace|delete)\b", text):
        return answer('The strength session is unchanged. What change would you like instead?')
    if len(rows) != 1:
        return answer('Choose one strength session to replace with an endurance ride.')
    row = rows[0]
    old = row['definition']
    day = row.get('scheduled_date', row['scheduled_for'][:10])
    remote = row['publish_status'] != 'local' or bool(row.get('garmin_workout_id'))
    if remote:
        from .database import connect
        with connect(path) as c:
            managed = c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=? AND verified_hash IS NOT NULL',
                                (row['id'], row.get('garmin_workout_id'))).fetchone()
        if row['publish_status'] not in ('published', 'update_needed') or not managed:
            return answer('The Garmin publication for this session needs reconciliation. Open Send to Garmin and resolve its publication status before replacing it.', 'not_recommended')
    if any(old.get(key) for key in ('fixed_commitment', 'event_id', 'review_hold')):
        return answer('Resolve this session’s commitment or review hold before replacing it.', 'not_recommended')
    answers = context['answers']
    blockers = [b for b in context['blockers'] if b not in (
        'Equipment unavailable for strength.',
        'Equipment and exclusions leave fewer than two supported strength movements.')]
    if illness or policy['level'] == 'hold' or answers.get('pain_or_illness') or blockers:
        return answer('Review the reported pain, illness or saved restrictions before adding a ride.', 'not_recommended')
    if 'cycling' in answers.get('blocked_sports', []):
        return answer('Cycling is blocked in your saved preferences. Review that restriction first.', 'not_recommended')

    duration = re.search(r'\b(\d+)\s*(?:minutes?|mins?|m)\b', text)
    minutes = int(duration[1]) if duration else None
    if minutes is None:
        clock = re.search(r'\b(\d+):([0-5]\d):([0-5]\d)\b', text)
        if clock:
            seconds = int(clock[1])*3600 + int(clock[2])*60 + int(clock[3])
            if seconds % 60:
                return answer('Choose a replacement duration in whole minutes.')
            minutes = seconds // 60
        elif re.search(r'\b(?:an? hour|one hour)\b', text):
            minutes = 60
    source = None
    if source_id or minutes is None and 'yesterday' in text and 'supposed' in text:
        # Historical instructions are a reference, never a request to alter history.
        reference = re.search(r'yesterday \[reference (\d{4}-\d{2}-\d{2})\]', text)
        source_day = reference[1] if reference else (today - timedelta(days=1)).isoformat()
        sources = [(w, json.loads(w['definition_json'])) for w in sessions
                   if w['sport'] == 'cycling' and (w['id']==source_id if source_id else w['scheduled_for'][:10] == source_day)
                   and w['completion_status'] != 'cancelled']
        sources = [(w, d) for w, d in sources if d.get('workout_kind') in ('endurance', 'recovery')]
        if len(sources) == 1:
            source, source_definition = sources[0]
            if minutes is not None and minutes != source_definition['duration_minutes']:
                source = None
            else:
                minutes = source_definition['duration_minutes']
        elif source_id:
            return answer('The source must be an endurance or recovery ride in this active program. Read the intended source session again.')
    if minutes is None:
        return answer(f'I have the strength session on {day}. How many minutes should the replacement endurance ride be?')
    if not 10 <= minutes <= 180:
        return answer(f'I have the strength session on {day}. Choose a ride duration between 10 and 180 minutes.')
    dose = cycling_dose(180, capacity, context['recent_feedback'], today)
    from datetime import date
    target = date.fromisoformat(day)
    anchor = date.fromisoformat(program['state']['starts_on'])
    week = anchor + timedelta(weeks=(target-anchor).days//7)
    from .database import connect
    from .training import _context
    with connect(path) as c:
        week_context = _context(c, now,
            brief={**program['state']['brief'], '_planning_day': week.isoformat()}, timezone_name=program['state']['timezone'])
        ceiling = week_context['volume_estimates'].get('cycling', {}).get('effective_ceiling_minutes', 0)
        performed = completed_minutes(c, sessions, week, today, program['state']['timezone'])
    reserved = sum(json.loads(w['definition_json'])['duration_minutes'] for w in sessions
                   if w['sport'] == 'cycling' and w['completion_status'] == 'planned'
                   and counts_toward_plan(w, today, program['state']['timezone'])
                   and week <= session_day(w, program['state']['timezone']) < week + timedelta(days=7))
    remaining = max(0, ceiling - performed - reserved)
    if minutes > remaining:
        return answer(f'The strength session on {day} is selected. The cycling week has {remaining} minutes available; choose a shorter ride or redistribute another planned ride.', 'not_recommended')
    if minutes > dose['minutes'] or (fatigue or policy['level'] == 'recovery') and minutes > 30:
        return answer(f'The strength session on {day} is selected. Current duration and recovery guidance supports at most {min(dose["minutes"], 30) if fatigue or policy["level"] == "recovery" else dose["minutes"]} minutes for this ride.', 'not_recommended')
    if minutes >= 90:
        from datetime import date
        for peer in sessions:
            if peer['id'] == row['id'] or not counts_toward_plan(peer, today, program['state']['timezone']):
                continue
            definition = json.loads(peer['definition_json'])
            demanding = definition['duration_minutes'] >= 90 or definition.get('workout_kind') in ('tempo', 'threshold', 'vo2', 'short_efforts', 'sprint', 'anaerobic', 'long_tempo')
            if demanding and abs((date.fromisoformat(peer['scheduled_for'][:10]) - target).days) <= 1:
                return answer(f'The strength session on {day} is selected. Choose a ride shorter than 90 minutes to keep recovery space around the nearby demanding session.', 'not_recommended')

    replacement = copy.deepcopy(source_definition) if source else endurance('endurance', minutes, program['state']['brief'], today=today)
    # Formatting applies to the new ride, never to the strength session it replaces.
    from .workout_format import requested as format_requested, continuous_definition
    format_text = re.sub(r'\bstrength\b', '', text)
    if format_requested(format_text):
        replacement = continuous_definition(replacement)
    power = re.search(r'\b(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*(?:watts?|w)\b', text, re.I)
    if power:
        from .workout_edits import parse, EditError
        from .training_prescriptions import text as target_text
        try:
            target = parse(f'power target to {power[1]}-{power[2]} W')['target']
        except EditError as error:
            return answer(str(error))
        for step in replacement['steps']:
            if not re.search(r'warm|cool', step.get('name', ''), re.I):
                step.update(target=copy.deepcopy(target), effort=target_text(target), power_reference_fractions=None)
        replacement['effort_target'] = {'method':'power', 'description':'; '.join(f"{s['name']}: {s['effort']}" for s in replacement['steps'])}
    # Retain only the destination schedule; source dates and slots cannot leak.
    replacement = {k: v for k, v in replacement.items() if not k.startswith('schedule_') and k not in ('scheduled_date', 'time_unspecified')}
    replacement.update({k: v for k, v in old.items() if k.startswith('schedule_') or k in ('scheduled_date', 'time_unspecified')})
    replacement.update(sport='cycling', user_adjusted=True)
    replacement['schedule_override'] = {'date': day, 'replaced_slot_id': old.get('schedule_slot_id'),
        'destination_sport': 'strength', 'reason': 'Explicit one-time strength-to-ride replacement.'}
    validate_workout(replacement)
    adjustment = {'workout_id': row['id'], 'expected_revision': row['revision'], 'title': row['title'], 'date': day,
                  'changes': {'definition': replacement}, 'summary': ['Replace strength with an endurance ride.']}
    proposal = {**base, 'status': 'proposal', 'root_plan_id': program['plan_id'], 'program_revision': program['revision'],
                'adjustments': [adjustment], 'policy': policy,
                'message': f'Review replacing the strength session on {day} with a {minutes}-minute endurance ride. Nothing is saved yet. This is a one-time change; your recurring schedule stays unchanged.'}
    if remote:
        proposal['message'] += ' After saving, the Garmin workout needs updating through Send to Garmin; saving this proposal alone does not confirm a Garmin update. Manual calendar removal is not required for this app-managed workout.'
    proposal['fingerprint'] = hashlib.sha256(encoded({k: proposal[k] for k in ('root_plan_id', 'program_revision', 'adjustments')}).encode()).hexdigest()
    return proposal
