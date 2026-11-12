"""Shared distinction between performed training and remaining commitments."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def session_day(row, tz):
    definition = row.get('definition') or json.loads(row['definition_json'])
    return (datetime.fromisoformat(definition['scheduled_date']).date() if definition.get('scheduled_date')
            else datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date())


def counts_toward_plan(row, today, tz):
    """Past intentions are history, never performed load or future reservations."""
    return row['completion_status'] == 'completed' or (
        row['completion_status'] == 'planned' and session_day(row, tz) >= today)


def completed_minutes(c, rows, window, today, tz, sport='cycling'):
    """Actual activities plus deduplicated explicit completions, even with partial sync."""
    from .training_volume import sport_of
    recorded = []
    end = min(today, window + timedelta(days=6))
    for activity in c.execute("SELECT id,activity_type,started_at,duration_seconds FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND started_at>=?", ((window-timedelta(days=1)).isoformat(),)):
        day = datetime.fromisoformat(activity['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date()
        if sport_of(activity['activity_type']) == sport and window <= day <= end and activity['duration_seconds']:
            recorded.append((activity['id'], day, activity['duration_seconds']/60))
    total = sum(r[2] for r in recorded)
    identifiers = {r[0] for r in recorded}
    for row in rows:
        if row['sport'] != sport or row['completion_status'] != 'completed':
            continue
        day = session_day(row, tz)
        if not window <= day <= end:
            continue
        feedback = c.execute('SELECT activity_id FROM training_feedback WHERE workout_id=?', (row['id'],)).fetchone()
        if feedback and feedback['activity_id'] in identifiers:
            continue
        definition = row.get('definition') or json.loads(row['definition_json'])
        minutes = definition['duration_minutes']
        if not any(r[1] == day and abs(r[2]-minutes) <= max(10, minutes*.15) for r in recorded):
            total += minutes
    return total
