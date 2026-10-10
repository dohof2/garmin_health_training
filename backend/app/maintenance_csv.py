"""Versioned, spreadsheet-safe CSV snapshots and reviewable imports."""
from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path

from .database import connect, migrate
from .maintenance import (EVENT_FIELDS, _begin, _event, _finish, _write, json_text,
                          list_maintenance, text, validate_event)

CSV_COLUMNS = ('format', 'id', *EVENT_FIELDS)
CSV_FORMAT = 'maintenance-v1'
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 2000
ALIASES = {'equipment': 'equipment_label', 'item': 'equipment_label', 'date': 'event_date',
           'work': 'action', 'cost': 'cost_amount', 'currency': 'cost_currency', 'notes': 'details'}


def safe_cell(value: object) -> str:
    result = '' if value is None else str(value)
    if result.startswith("'") or result.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) or result.startswith(('\t', '\r', '\n')):
        return "'" + result
    return result


def export_maintenance_csv(path: Path | None = None, **filters) -> str:
    # Up to 1000 per service query; export reads all current records explicitly.
    migrate(path)
    from .maintenance import _event
    with connect(path) as connection:
        ids = [row['id'] for row in connection.execute('SELECT id FROM maintenance_events WHERE deleted_at IS NULL ORDER BY event_date DESC, id')]
        events = [_event(connection, identifier) for identifier in ids]
    if filters:
        allowed = {event['id'] for event in list_maintenance(path, limit=1000, **filters)['events']}
        if len(ids) > 1000:
            raise ValueError('Use a smaller date range for filtered CSV export')
        events = [event for event in events if event['id'] in allowed]
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator='\r\n')
    writer.writeheader()
    for event in events:
        writer.writerow({column: safe_cell(CSV_FORMAT if column == 'format' else event.get(column)) for column in CSV_COLUMNS})
    return output.getvalue()


def preview_maintenance_csv(content: str, mapping: dict[str, str] | None = None, path: Path | None = None) -> dict[str, object]:
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_CSV_BYTES or '\x00' in content:
        raise ValueError('CSV must be UTF-8 text without NUL and no more than 2 MiB')
    try:
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff'), newline=''), strict=True)
        headers = reader.fieldnames or []
        if not headers or len(headers) > 40 or len(headers) != len(set(headers)):
            raise ValueError('CSV requires unique column headers (at most 40)')
        records = []
        for index, row in enumerate(reader):
            if index >= MAX_CSV_ROWS:
                raise ValueError(f'CSV cannot exceed {MAX_CSV_ROWS} rows')
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Every CSV row must have the same number of columns as the header')
            records.append(row)
    except csv.Error as error:
        raise ValueError(f'Invalid CSV: {error}') from error
    if mapping is None:
        mapping = {field: next((header for header in headers if header.strip().lower() == field or ALIASES.get(header.strip().lower()) == field), '') for field in ('id', *EVENT_FIELDS)}
        mapping = {field: header for field, header in mapping.items() if header}
    if not isinstance(mapping, dict) or set(mapping) - {'id', *EVENT_FIELDS}:
        raise ValueError('Invalid CSV field mapping')
    if any(header not in headers for header in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise ValueError('Each mapped field must use a different existing CSV column')
    for required in ('equipment_label', 'action', 'event_date'):
        if required not in mapping:
            return {'columns': headers, 'mapping': mapping, 'required_mapping': ['equipment_label', 'action', 'event_date'],
                    'rows': [], 'errors': [f'Map the {required} column before previewing'], 'preview_id': None}
    migrate(path)
    plans = []
    errors = []
    seen_ids = {}
    seen_values = set()
    with connect(path) as connection:
        existing_rows = connection.execute('SELECT id FROM maintenance_events').fetchall()
        existing = {row['id']: _event(connection, row['id']) for row in existing_rows}
        fingerprints = {json_text({field: event[field] for field in EVENT_FIELDS}): event['id'] for event in existing.values() if event['deleted_at'] is None}
        for index, row in enumerate(records, start=2):
            try:
                def decode(value):
                    return value[1:] if row.get('format') == CSV_FORMAT and value.startswith("'") else value
                values = {field: decode(row[header]) or None for field, header in mapping.items()}
                identifier = text(values.pop('id', None), 'id', 160)
                normalized = validate_event(values)
                fingerprint = json_text(normalized)
                if identifier and identifier in seen_ids and seen_ids[identifier] != fingerprint:
                    raise ValueError('This ID has conflicting rows within the CSV')
                before = existing.get(identifier) if identifier else None
                if (identifier and identifier in seen_ids) or (not identifier and fingerprint in seen_values):
                    status = 'duplicate'
                elif before:
                    status = 'unchanged' if all(before[field] == normalized[field] for field in EVENT_FIELDS) and before['deleted_at'] is None else 'conflict'
                elif not identifier and fingerprint in fingerprints:
                    identifier = fingerprints[fingerprint]
                    status = 'unchanged'
                else:
                    status = 'new'
                if identifier:
                    seen_ids[identifier] = fingerprint
                seen_values.add(fingerprint)
                plans.append({'row': index, 'id': identifier or f'maintenance-{uuid.uuid4()}', 'status': status,
                              'values': normalized, 'before': before})
            except ValueError as error:
                errors.append(f'Row {index}: {error}')
        preview_id = str(uuid.uuid4())
        plan = {'rows': plans, 'errors': errors}
        connection.execute('INSERT INTO maintenance_csv_previews(id, plan_json) VALUES (?, ?)', (preview_id, json_text(plan)))
    return {'preview_id': preview_id, 'columns': headers, 'mapping': mapping, 'rows': plans, 'errors': errors,
            'counts': {status: sum(row['status'] == status for row in plans) for status in ('new', 'unchanged', 'duplicate', 'conflict')}}


def apply_maintenance_csv(preview_id: str, decisions: dict[str, str], operation_id: str, path: Path | None = None) -> dict[str, object]:
    if not isinstance(decisions, dict) or any(value not in ('skip', 'update', 'create') for value in decisions.values()):
        raise ValueError('CSV decisions must be skip, update, or create')
    migrate(path)
    request = {'kind': 'csv_import', 'preview_id': preview_id, 'decisions': decisions}
    with connect(path) as connection:
        previous = _begin(connection, operation_id, request)
        if previous:
            return previous
        preview = connection.execute('SELECT * FROM maintenance_csv_previews WHERE id = ?', (preview_id,)).fetchone()
        if not preview:
            raise ValueError('CSV preview was not found')
        if preview['applied_operation_id']:
            raise ValueError('This preview was already imported. Preview the file again if needed.')
        plan = json.loads(preview['plan_json'])
        if plan['errors']:
            raise ValueError('Fix invalid CSV rows before importing')
        if set(decisions) - {str(row['row']) for row in plan['rows']}:
            raise ValueError('Unknown CSV row decision')
        before = []
        after = []
        for row in plan['rows']:
            decision = decisions.get(str(row['row']), 'create' if row['status'] == 'new' else 'skip')
            if decision == 'skip':
                continue
            if (row['status'], decision) not in (('new', 'create'), ('conflict', 'update')):
                raise ValueError('Only new rows can be created and conflicting rows explicitly updated')
            current = connection.execute('SELECT id FROM maintenance_events WHERE id = ?', (row['id'],)).fetchone()
            if row['before']:
                event = _event(connection, row['id'])
                if event['revision'] != row['before']['revision']:
                    raise ValueError('A CSV conflict changed since preview. Preview the file again.')
                before.append(event)
                source_operation = event['operation_id']
            else:
                if current:
                    raise ValueError('A CSV event was added since preview. Preview the file again.')
                source_operation = f'{operation_id}:{row["row"]}'
            values = validate_event(row['values'])
            after.append(_write(connection, row['id'], values, source_operation))
        connection.execute('UPDATE maintenance_csv_previews SET applied_operation_id = ? WHERE id = ?', (operation_id, preview_id))
        return _finish(connection, operation_id, request, before, after, 'import_maintenance_csv')
