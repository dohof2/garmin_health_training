"""Keep date-only intent separate from a timestamp used for internal storage."""
import json

TIME_FIELDS = ('scheduled_date', 'time_unspecified', 'schedule_timezone')


def preserve_timing(replacement, original):
    for key in TIME_FIELDS:
        if key in original and (key not in replacement or replacement[key] is None):
            replacement[key] = original[key]
    return replacement


def recover_timing(c, row):
    """Use explicit history only; noon alone is never evidence of date-only intent."""
    definition = json.loads(row['definition_json'])
    if definition.get('fixed_commitment') or type(definition.get('time_unspecified')) is bool:
        return definition
    for revision in c.execute('SELECT snapshot_json FROM training_workout_revisions WHERE workout_id=? AND revision<? ORDER BY revision DESC', (row['id'], row['revision'])):
        old = json.loads(revision['snapshot_json'])
        # An actual schedule change is a boundary. Never carry an older timing
        # choice across a move to another time or day.
        if old.get('scheduled_for') != row['scheduled_for']:
            break
        source = json.loads(old.get('definition_json') or '{}')
        if source.get('fixed_commitment'):
            break
        if type(source.get('time_unspecified')) is bool:
            return preserve_timing(definition, source)
    return definition


def preserve_saved_timing(c, row):
    definition = recover_timing(c, row)
    if definition != json.loads(row['definition_json']):
        from .training import encoded
        row['definition_json'] = encoded(definition)
        c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?', (row['definition_json'], row['id']))


def repair_saved_timing(c):
    """Restore provably lost flags, without moving workouts or changing clocks."""
    from .training import encoded, _revision, _snapshot
    changed = []
    for record in c.execute('SELECT * FROM planned_workouts').fetchall():
        row = dict(record)
        repaired = recover_timing(c, row)
        if repaired == json.loads(row['definition_json']):
            continue
        c.execute('UPDATE planned_workouts SET definition_json=?,revision=revision+1 WHERE id=?', (encoded(repaired), row['id']))
        _revision(c, _snapshot(c, row['id']))
        changed.append(row['id'])
    return changed
