"""Reviewed one-time replacement of a local strength session with an easy ride."""
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


def propose(base, rows, program, sessions, context, policy, capacity, today, text, illness, fatigue, source_id=None):
    from .training_constraints import optional_cap
    from .training_prescriptions import cycling_dose, endurance, validate_workout

    def answer(message, status='needs_input'):
        return {**base, 'status': status, 'message': message}

    if re.search(r"\b(don't|do not|never)\s+(remove|replace|delete)\b", text):
        return answer('The strength session is unchanged. What change would you like instead?')
    if len(rows) != 1:
        return answer('Choose one strength session to replace with an endurance ride.')
    row = rows[0]
    old = row['definition']
    day = row.get('scheduled_date', row['scheduled_for'][:10])
    if row['publish_status'] != 'local' or row.get('garmin_workout_id'):
        return answer('This strength session has been sent to Garmin. Remove its Garmin calendar entry before replacing its sport.', 'not_recommended')
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
            source, definition = sources[0]
            if minutes is not None and minutes != definition['duration_minutes']:
                source = None
            else:
                minutes = definition['duration_minutes']
        elif source_id:
            return answer('The source must be an endurance or recovery ride in this active program. Read the intended source session again.')
    if minutes is None:
        return answer(f'I have the strength session on {day}. How many minutes should the replacement endurance ride be?')
    if not 10 <= minutes <= 180:
        return answer(f'I have the strength session on {day}. Choose a ride duration between 10 and 180 minutes.')
    dose = cycling_dose(180, capacity, context['recent_feedback'], today)
    cap, _ = optional_cap(answers, 'cycling')
    ceiling = min(dose['weekly_cap_minutes'], cap) if cap is not None else dose['weekly_cap_minutes']
    from datetime import date
    target = date.fromisoformat(day)
    monday = target - timedelta(days=target.weekday())
    reserved = sum(json.loads(w['definition_json'])['duration_minutes'] for w in sessions
                   if w['sport'] == 'cycling' and w['completion_status'] in ('planned', 'completed')
                   and monday.isoformat() <= w['scheduled_for'][:10] < (monday + timedelta(days=7)).isoformat())
    remaining = max(0, ceiling - reserved)
    if minutes > remaining:
        return answer(f'The strength session on {day} is selected. The cycling week has {remaining} minutes available; choose a shorter ride or redistribute another planned ride.', 'not_recommended')
    if minutes > dose['minutes'] or (fatigue or policy['level'] == 'recovery') and minutes > 30:
        return answer(f'The strength session on {day} is selected. Current duration and recovery guidance supports at most {min(dose["minutes"], 30) if fatigue or policy["level"] == "recovery" else dose["minutes"]} minutes for this ride.', 'not_recommended')
    if minutes >= 90:
        from datetime import date
        for peer in sessions:
            if peer['id'] == row['id'] or peer['completion_status'] not in ('planned', 'completed'):
                continue
            definition = json.loads(peer['definition_json'])
            demanding = definition['duration_minutes'] >= 90 or definition.get('workout_kind') in ('tempo', 'threshold', 'vo2', 'short_efforts', 'sprint', 'anaerobic', 'long_tempo')
            if demanding and abs((date.fromisoformat(peer['scheduled_for'][:10]) - target).days) <= 1:
                return answer(f'The strength session on {day} is selected. Choose a ride shorter than 90 minutes to keep recovery space around the nearby demanding session.', 'not_recommended')

    replacement = copy.deepcopy(definition) if source else endurance('endurance', minutes, program['state']['brief'], today=today)
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
    proposal['fingerprint'] = hashlib.sha256(encoded({k: proposal[k] for k in ('root_plan_id', 'program_revision', 'adjustments')}).encode()).hexdigest()
    return proposal
