"""Preview extra steady riding while preserving every other saved block."""
import copy
import hashlib
import re
from datetime import date, timedelta

from .database import connect
from .training import _context, encoded


def requested(text):
    from .workout_edits import interval_edit_requested
    if interval_edit_requested(text):return False
    return bool(re.search(r'\b(?:endurance|edurance|steady)\b', text) and
                re.search(r'\b(?:add|extend|lengthen|extra|additional)\b', text))


def propose(base, rows, program, sessions, context, policy, capacity, today, text, illness, fatigue, path, now):
    from .training_accounting import counts_toward_plan, session_day, completed_minutes
    from .training_constraints import assign_slot, day_limit
    from .training_prescriptions import cycling_dose, validate_workout

    def answer(message, status='needs_input'):
        return {**base, 'status':status, 'message':message}

    if len(rows) != 1 or rows[0]['sport'] != 'cycling':
        return answer('Choose one cycling session whose steady endurance block should be extended.')
    row = rows[0]
    old = row['definition']
    if re.search(r"\b(?:do not|don't|never)\s+(?:add|extend|lengthen)\b", text):
        return answer('The session is unchanged.')
    if illness or fatigue or context['blockers'] or context['answers'].get('pain_or_illness') or policy['level'] != 'normal':
        return answer('Current recovery or saved restrictions do not support adding endurance time.', 'not_recommended')
    if any(old.get(k) for k in ('fixed_commitment','event_id','review_hold')):
        return answer('Resolve this session’s commitment or review hold before extending it.', 'not_recommended')
    with connect(path) as c:
        managed = c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=? AND verified_hash IS NOT NULL',
                            (row['id'], row.get('garmin_workout_id'))).fetchone()
    if row['publish_status'] not in ('local','published','update_needed') or (row['publish_status'] != 'local' or row.get('garmin_workout_id')) and not managed:
        return answer('Reconcile the unfinished or unverified Garmin publication before extending this ride.', 'not_recommended')
    steady = [s for s in old.get('steps', []) if s.get('name') == 'Steady endurance']
    if len(steady) != 1 or steady[0].get('repetitions',1) != 1 or steady[0].get('termination','time') != 'time':
        return answer('This needs one explicitly timed steady endurance block; review the saved structure first.')
    addition = re.search(r'\b(?:add(?:\s+another)?|another|extra|additional|by)\s+(\d+)\s*(?:minutes?|mins?|m)\b', text)
    change = re.search(r'\bfrom\s+(\d+)(?::00)?\s*(?:minutes?|mins?)?\s*(?:to|→)\s*(\d+)(?::00)?\s*(?:minutes?|mins?)?', text)
    if addition:
        extra = int(addition[1])
    elif change:
        if int(change[1])*60 != steady[0]['duration_seconds']:
            return answer('The saved endurance duration differs from that request. Read the current session and review the intended extension.')
        extra = int(change[2]) - int(change[1])
    else:
        return answer('Specify the extra steady riding in minutes, for example: add 15 minutes to the endurance section.')
    if not 1 <= extra <= 60:
        return answer('Choose 1–60 extra minutes of steady endurance.')
    if re.search(r'\b(?:change|set|increase|reduce)\b.{0,30}\b(?:targets?|watts?|reps?|intervals?|recoveries)\b', text):
        return answer('Review changes to intervals or targets separately from this endurance extension.')
    tz = program['state']['timezone']
    day = session_day(row, tz)
    minutes = old['duration_minutes'] + extra
    try:
        assign_slot(context['answers']['week_schedule'], day.weekday(), 'cycling', minutes, old.get('schedule_slot_id'))
    except ValueError as error:
        return answer(str(error), 'not_recommended')
    peers = [s for s in sessions if s['id'] != row['id'] and counts_toward_plan(s,today,tz)]
    if minutes + sum(s['definition']['duration_minutes'] for s in peers if session_day(s,tz) == day) > day_limit(context['answers']['week_schedule'], day.weekday()):
        return answer('The extended ride exceeds the shared day limit.', 'not_recommended')
    dose = cycling_dose(720, capacity, context['recent_feedback'], today)
    if minutes > dose['minutes']:
        return answer(f"Current single-session duration guidance supports at most {dose['minutes']:g} minutes. Review a shorter extension.", 'not_recommended')
    anchor = date.fromisoformat(program['state']['starts_on'])
    week = anchor + timedelta(weeks=(day-anchor).days//7)
    with connect(path) as c:
        weekly = _context(c,now,brief={**program['state']['brief'],'_planning_day':week.isoformat()},timezone_name=tz)
        ceiling = weekly['volume_estimates'].get('cycling',{}).get('effective_ceiling_minutes',0)
        performed = completed_minutes(c,sessions,week,today,tz)
    reserved = sum(s['definition']['duration_minutes'] for s in peers if s['sport']=='cycling' and s['completion_status']=='planned' and week <= session_day(s,tz) < week+timedelta(days=7))
    if performed + reserved + minutes > ceiling:
        return answer('The extension exceeds the cycling week’s remaining allowance. Redistribute another ride or review a shorter extension.', 'not_recommended')
    replacement = copy.deepcopy(old)
    index = old['steps'].index(steady[0])
    replacement['steps'][index]['duration_seconds'] += extra*60
    replacement.update(duration_minutes=minutes,user_adjusted=True)
    validate_workout(replacement)
    summary = [f'Add {extra} minutes to steady endurance; total {old["duration_minutes"]:g} → {minutes:g} minutes. All other blocks and targets are preserved.']
    replacement['edit_summary'] = summary
    result = {**base,'status':'proposal','root_plan_id':program['plan_id'],'program_revision':program['revision'],
        'adjustments':[{'workout_id':row['id'],'expected_revision':row['revision'],'title':row['title'],'date':day.isoformat(),
                        'summary':summary,'changes':{'definition':replacement}}],
        'message':'Review the endurance extension. Nothing is saved yet. Save applies it locally; then use Send to Garmin to update a published workout.', 'policy':policy}
    result['fingerprint'] = hashlib.sha256(encoded({k:result[k] for k in ('root_plan_id','program_revision','adjustments')}).encode()).hexdigest()
    return result
