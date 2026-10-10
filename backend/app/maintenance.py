"""Local maintenance records, revisions, and atomic idempotent actions."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from .database import connect, migrate
from .time_utils import timezone_info

EVENT_FIELDS = ('equipment_label', 'action', 'event_date', 'category', 'part', 'quantity',
                'cost_amount', 'cost_currency', 'provider', 'usage_value', 'usage_unit', 'details')
CATEGORIES = ('general', 'replacement', 'service', 'repair', 'inspection')
MAX_EVENTS = 25


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def text(value: object, field: str, maximum: int = 1000, required: bool = False) -> str | None:
    if value is None or value == '':
        if required:
            raise ValueError(f'{field} is required')
        return None
    if not isinstance(value, str):
        raise ValueError(f'{field} must be text')
    value = value.strip()
    if not value or len(value) > maximum or '\x00' in value:
        raise ValueError(f'{field} must contain 1 to {maximum} characters without NUL')
    return value


def number(value: object, field: str, maximum: float, positive: bool = False) -> float | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a finite number')
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{field} must be a number') from error
    if not math.isfinite(result) or result < 0 or result > maximum or (positive and result == 0):
        raise ValueError(f'{field} is outside its allowed range')
    return result


def resolve_date(value: object, timezone_name: str | None = None, today: date | None = None) -> str:
    today = today or datetime.now(timezone_info(timezone_name)).date()
    if value == 'today':
        return today.isoformat()
    if value == 'yesterday':
        return (today - timedelta(days=1)).isoformat()
    try:
        result = date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError('event_date is required and must be YYYY-MM-DD, today, or yesterday') from error
    if result > today:
        raise ValueError('Completed maintenance cannot have a future event date')
    return result.isoformat()


def validate_event(values: dict[str, object], timezone_name: str | None = None) -> dict[str, object]:
    if not isinstance(values, dict) or set(values) - set(EVENT_FIELDS):
        raise ValueError('Unsupported maintenance fields')
    result = {field: values.get(field) for field in EVENT_FIELDS}
    result['equipment_label'] = text(result['equipment_label'], 'equipment_label', 120, True)
    result['action'] = text(result['action'], 'action', 240, True)
    result['event_date'] = resolve_date(result['event_date'], timezone_name)
    result['category'] = result['category'] or 'general'
    if result['category'] not in CATEGORIES:
        raise ValueError('Invalid maintenance category')
    for field, limit in (('part', 160), ('provider', 160), ('usage_unit', 30), ('details', 2000)):
        result[field] = text(result[field], field, limit)
    for field, maximum, positive in (('quantity', 10000, True), ('cost_amount', 100000000, False), ('usage_value', 100000000, False)):
        result[field] = number(result[field], field, maximum, positive)
    currency = text(result['cost_currency'], 'cost_currency', 3)
    if currency and not re.fullmatch('[A-Za-z]{3}', currency):
        raise ValueError('cost_currency must be a three-letter currency code')
    result['cost_currency'] = currency.upper() if currency else None
    if result['cost_currency'] and result['cost_amount'] is None:
        raise ValueError('A currency requires an amount')
    if result['usage_unit'] and result['usage_value'] is None:
        raise ValueError('A usage unit requires a value')
    return result


def _event(connection: sqlite3.Connection, identifier: str) -> dict[str, object]:
    row = connection.execute('''SELECT m.*, e.label AS equipment_label,
        (SELECT MAX(revision_number) FROM maintenance_event_revisions r WHERE r.maintenance_event_id = m.id) AS revision
        FROM maintenance_events m JOIN equipment e ON e.id = m.equipment_id WHERE m.id = ?''', (identifier,)).fetchone()
    if row is None:
        raise ValueError('Maintenance event was not found')
    return dict(row)


def _equipment(connection: sqlite3.Connection, label: str) -> str:
    existing = connection.execute('SELECT id FROM equipment WHERE label = ? COLLATE NOCASE', (label,)).fetchone()
    if existing:
        return str(existing['id'])
    identifier = f'equipment-{uuid.uuid4()}'
    connection.execute('INSERT INTO equipment(id, label) VALUES (?, ?)', (identifier, label))
    return identifier


def _write(connection: sqlite3.Connection, identifier: str, values: dict[str, object], operation_id: str,
           deleted_at: str | None = None) -> dict[str, object]:
    equipment_id = _equipment(connection, str(values['equipment_label']))
    columns = [field for field in EVENT_FIELDS if field != 'equipment_label']
    connection.execute(f'''INSERT INTO maintenance_events(id, equipment_id, operation_id, {', '.join(columns)}, deleted_at)
        VALUES ({', '.join('?' for _ in range(len(columns) + 4))})
        ON CONFLICT(id) DO UPDATE SET equipment_id = excluded.equipment_id,
        {', '.join(f'{field} = excluded.{field}' for field in columns)},
        deleted_at = excluded.deleted_at, updated_at = CURRENT_TIMESTAMP''',
        (identifier, equipment_id, operation_id, *[values[field] for field in columns], deleted_at))
    revision = connection.execute('SELECT COALESCE(MAX(revision_number), 0) + 1 FROM maintenance_event_revisions WHERE maintenance_event_id = ?', (identifier,)).fetchone()[0]
    snapshot = _event(connection, identifier)
    snapshot['revision'] = revision
    connection.execute('INSERT INTO maintenance_event_revisions(maintenance_event_id, revision_number, snapshot_json) VALUES (?, ?, ?)',
                       (identifier, revision, json_text(snapshot)))
    return snapshot


def list_maintenance(path: Path | None = None, *, equipment: str | None = None, query: str | None = None,
                     category: str | None = None, start_date: str | None = None, end_date: str | None = None,
                     include_deleted: bool = False, limit: int = 100) -> dict[str, object]:
    migrate(path)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('limit must be between 1 and 1000')
    if category and category not in CATEGORIES:
        raise ValueError('Invalid maintenance category')
    for value in (start_date, end_date):
        if value:
            date.fromisoformat(value)
    if start_date and end_date and start_date > end_date:
        raise ValueError('start_date must be on or before end_date')
    filters = []
    parameters = []
    if not include_deleted:
        filters.append('m.deleted_at IS NULL')
    if equipment:
        text(equipment, 'equipment', 120)
        filters.append('e.label = ? COLLATE NOCASE')
        parameters.append(equipment.strip())
    if query:
        text(query, 'query', 240)
        # Literal substring matching: wildcard characters in names are not SQL patterns.
        filters.append("instr(replace(lower(m.action || ' ' || COALESCE(m.part, '') || ' ' || COALESCE(m.details, '') || ' ' || e.label), 'tyre', 'tire'), replace(lower(?), 'tyre', 'tire')) > 0")
        parameters.append(query.strip())
    if category:
        filters.append('m.category = ?')
        parameters.append(category)
    for field, op, value in (('event_date', '>=', start_date), ('event_date', '<=', end_date)):
        if value:
            filters.append(f'm.{field} {op} ?')
            parameters.append(value)
    where = ' WHERE ' + ' AND '.join(filters) if filters else ''
    with connect(path) as connection:
        rows = connection.execute('SELECT m.id FROM maintenance_events m JOIN equipment e ON e.id = m.equipment_id' + where + ' ORDER BY m.event_date DESC, m.rowid DESC', parameters).fetchall()
        events = [_event(connection, row['id']) for row in rows[:limit]]
        totals = connection.execute("SELECT m.cost_currency AS currency, SUM(m.cost_amount) AS amount, COUNT(*) AS event_count FROM maintenance_events m JOIN equipment e ON e.id = m.equipment_id" + where + (' AND ' if where else ' WHERE ') + "m.deleted_at IS NULL AND m.cost_amount IS NOT NULL GROUP BY m.cost_currency", parameters).fetchall()
        labels = [dict(row) for row in connection.execute('SELECT id, label FROM equipment ORDER BY label COLLATE NOCASE')]
    return {'tool': 'list_maintenance', 'events': events, 'total_matches': len(rows), 'truncated': len(rows) > limit,
            'cost_totals': [dict(row) for row in totals], 'equipment': labels,
            'filters': {'equipment': equipment, 'query': query, 'category': category, 'start_date': start_date, 'end_date': end_date},
            'limitations': ['Costs without a recorded currency are kept in a separate unspecified-currency total.', 'Manual usage values are user-entered; Garmin equipment mileage is not calculated.']}


def event_history(identifier: str, path: Path | None = None) -> dict[str, object]:
    migrate(path)
    with connect(path) as connection:
        event = _event(connection, identifier)
        revisions = [json.loads(row['snapshot_json']) for row in connection.execute('SELECT snapshot_json FROM maintenance_event_revisions WHERE maintenance_event_id = ? ORDER BY revision_number DESC', (identifier,))]
    return {'event': event, 'revisions': revisions}


def _begin(connection: sqlite3.Connection, operation_id: str, request: object) -> dict[str, object] | None:
    text(operation_id, 'operation_id', 160, True)
    connection.execute('BEGIN IMMEDIATE')
    previous = connection.execute('SELECT request_json, result_json FROM maintenance_operations WHERE id = ?', (operation_id,)).fetchone()
    if previous:
        if previous['request_json'] != json_text(request):
            raise ValueError('Operation ID was already used for a different action')
        return json.loads(previous['result_json'])
    return None


def _finish(connection: sqlite3.Connection, operation_id: str, request: object, before: list, after: list,
            kind: str) -> dict[str, object]:
    result = {'tool': kind, 'events': after, 'operation_id': operation_id, 'saved': True,
              'message': 'Saved locally. You can edit or undo this action.', 'undo_available': True}
    connection.execute('INSERT INTO maintenance_operations(id, request_json, result_json, before_json, after_json) VALUES (?, ?, ?, ?, ?)',
                       (operation_id, json_text(request), json_text(result), json_text(before), json_text(after)))
    return result


def log_maintenance(events: list[dict[str, object]], operation_id: str, path: Path | None = None,
                    timezone_name: str | None = None) -> dict[str, object]:
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError(f'events must contain 1 to {MAX_EVENTS} entries')
    normalized = [validate_event(event, timezone_name) for event in events]
    migrate(path)
    request = {'kind': 'log', 'events': events, 'timezone': timezone_name}
    with connect(path) as connection:
        previous = _begin(connection, operation_id, request)
        if previous:
            return previous
        after = [_write(connection, f'maintenance-{uuid.uuid4()}', event, f'{operation_id}:{index}') for index, event in enumerate(normalized)]
        return _finish(connection, operation_id, request, [], after, 'log_maintenance')


def update_maintenance(identifier: str, changes: dict[str, object], expected_revision: int, operation_id: str,
                       path: Path | None = None, timezone_name: str | None = None,
                       deleted: bool | None = None) -> dict[str, object]:
    if not isinstance(changes, dict) or set(changes) - set(EVENT_FIELDS):
        raise ValueError('Unsupported maintenance fields')
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
        raise ValueError('expected_revision must be a positive integer')
    if deleted is not None and not isinstance(deleted, bool):
        raise ValueError('deleted must be boolean')
    migrate(path)
    request = {'kind': 'update', 'id': identifier, 'changes': changes, 'revision': expected_revision, 'deleted': deleted, 'timezone': timezone_name}
    with connect(path) as connection:
        previous = _begin(connection, operation_id, request)
        if previous:
            return previous
        before = _event(connection, identifier)
        if before['revision'] != expected_revision:
            raise ValueError('This event changed. Refresh it before editing.')
        values = validate_event({**{field: before[field] for field in EVENT_FIELDS}, **changes}, timezone_name)
        deleted_at = before['deleted_at'] if deleted is None else datetime.now().isoformat() if deleted else None
        after = _write(connection, identifier, values, before['operation_id'], deleted_at)
        return _finish(connection, operation_id, request, [before], [after], 'update_maintenance')


def undo_maintenance(target_operation_id: str, operation_id: str, path: Path | None = None) -> dict[str, object]:
    migrate(path)
    request = {'kind': 'undo', 'target': target_operation_id}
    with connect(path) as connection:
        previous = _begin(connection, operation_id, request)
        if previous:
            return previous
        target = connection.execute('SELECT * FROM maintenance_operations WHERE id = ?', (target_operation_id,)).fetchone()
        if not target:
            raise ValueError('Saved maintenance action was not found')
        if target['undone_by']:
            raise ValueError('This action was already undone')
        originals = json.loads(target['before_json'])
        changed = json.loads(target['after_json'])
        current = [_event(connection, event['id']) for event in changed]
        if any(any(now[field] != then[field] for field in (*EVENT_FIELDS, 'deleted_at')) for now, then in zip(current, changed)):
            raise ValueError('A later edit exists. Undo the latest action first or edit the event.')
        after = []
        originals_by_id = {event['id']: event for event in originals}
        for event in current:
            original = originals_by_id.get(event['id'])
            values = {field: (original or event)[field] for field in EVENT_FIELDS}
            deleted_at = original['deleted_at'] if original else datetime.now().isoformat()
            after.append(_write(connection, event['id'], values, event['operation_id'], deleted_at))
        connection.execute('UPDATE maintenance_operations SET undone_by = ? WHERE id = ?', (operation_id, target_operation_id))
        result = _finish(connection, operation_id, request, current, after, 'undo_maintenance')
        result['message'] = 'Action undone locally. The revision history is retained.'
        # Keep the exact retry response, including the undo wording.
        connection.execute('UPDATE maintenance_operations SET result_json = ? WHERE id = ?', (json_text(result), operation_id))
        return result
