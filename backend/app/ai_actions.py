"""AI can propose settings changes; only the explicit UI save endpoint applies them."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from .database import connect, migrate
from .settings import get_settings, normalize_goals, normalize_profile, save_goals, save_profile, _profile_row

PROFILE_FIELDS = ('display_name', 'timezone', 'preferred_distance_unit', 'preferred_weight_unit',
                  'birth_date', 'sex', 'height_cm', 'weight_kg')
GOAL_FIELDS = ('id', 'goal_type', 'title', 'target_value', 'target_unit', 'target_date', 'status', 'notes')


def _snapshot(target, connection):
    if target == 'profile':
        profile = _profile_row(connection)
        return {key: profile[key] for key in PROFILE_FIELDS}
    return [{key: row[key] for key in GOAL_FIELDS} for row in connection.execute(
        "SELECT * FROM goals WHERE status != 'archived' ORDER BY id")]


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def propose_settings_change(arguments: dict[str, object], path: Path | None = None):
    target = arguments.get('target')
    if target not in ('profile', 'goals'):
        raise ValueError('target must be profile or goals')
    patch = arguments.get('changes')
    if not isinstance(patch, dict) or not patch:
        raise ValueError('changes must be a nonempty object')
    allowed = PROFILE_FIELDS if target == 'profile' else GOAL_FIELDS
    if set(patch) - set(allowed):
        raise ValueError('Unsupported settings fields')
    migrate(path)
    with connect(path) as connection:
        before = _snapshot(target, connection)
        if target == 'profile':
            after = dict(zip(PROFILE_FIELDS, normalize_profile({**before, **patch})))
        else:
            goals = [dict(item) for item in before]
            identifier = patch.get('id')
            if identifier:
                index = next((i for i, item in enumerate(goals) if item['id'] == identifier), None)
                if index is None:
                    raise ValueError('Goal was not found; read saved goals before updating')
                goals[index].update(patch)
            else:
                if patch.get('status') == 'archived':
                    raise ValueError('Archiving requires an existing goal id')
                goals.append(dict(patch))
            after = sorted(normalize_goals(goals), key=lambda item: item['id'])
        identifier = str(uuid.uuid4())
        connection.execute('INSERT INTO ai_settings_actions(id, target, before_json, after_json) VALUES (?, ?, ?, ?)',
                           (identifier, target, _json(before), _json(after)))
    return {'tool': 'propose_settings_change', 'proposal': {
        'id': identifier, 'target': target, 'before': before, 'after': after, 'status': 'pending'},
        'instruction': 'Nothing has been saved. Review the displayed changes, then use Save change. Corrections can be made in Settings or proposed again in chat.'}


def confirm_settings_change(identifier: str, path: Path | None = None):
    migrate(path)
    with connect(path) as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT * FROM ai_settings_actions WHERE id = ?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Change proposal was not found')
        if row['status'] != 'saved':
            if _json(_snapshot(row['target'], connection)) != row['before_json']:
                raise ValueError('Settings changed since this proposal. Ask for a new proposal to preserve your edits.')
            after = json.loads(row['after_json'])
            if row['target'] == 'profile':
                save_profile(after, path, connection=connection)
            else:
                save_goals(after, path, connection=connection)
            connection.execute("UPDATE ai_settings_actions SET status = 'saved', saved_at = CURRENT_TIMESTAMP WHERE id = ?", (identifier,))
    return get_settings(path)


def get_training_context(arguments: dict[str, object], path: Path | None = None):
    from .training import training_context
    settings = get_settings(path)
    return {'tool': 'get_training_context', 'profile': settings['profile'], 'goals': settings['goals'],
            'training': training_context(path),
            'limitations': ['User goals are context, not evidence of the intent of a particular session. Draft and save training preferences in the Training screen; the assistant does not change the schedule.']}
