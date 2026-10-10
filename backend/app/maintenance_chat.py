"""Grounded maintenance commands shared by both providers.

Common clear commands are resolved locally, including dates and write authorization.
The same services are exposed as scoped tools; imported text never authorizes writes.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta
from .time_utils import timezone_info
from pathlib import Path

from .database import connect, migrate
from .maintenance import (EVENT_FIELDS, json_text, list_maintenance, log_maintenance,
                          resolve_date, text, undo_maintenance, update_maintenance)

SUBJECTS = r'\b(maintenance|replacement|chain|tires?|tyres?|brakes?|service|serviced|replace|replaced|repaired|installed|equipment|accessor(?:y|ies))\b'
PAST = r'\b(replaced|serviced|repaired|installed|inspected|lubricated|cleaned)\b'
FUTURE = r"\b(should|will|would|might|planning|plan to|need to|going to|hypothetically|did not|have not|haven't|didn't|never)\b"


def request_kind(message: str) -> str | None:
    note = re.search(r'\bnotes?\s*:|\bnotes?\b[^:]*?\bto\s+', message, re.I)
    if note:
        message = message[:note.end()] if ':' not in note.group() else message[:note.start()]
    if re.search(r'\b(goal|profile)\b', message, re.I):
        return None
    if not re.search(SUBJECTS, message, re.I):
        return None
    if re.search(FUTURE, message, re.I):
        return 'future'
    if re.search(r'\bundo\b', message, re.I):
        return 'undo'
    if re.search(r'\bexport\b', message, re.I):
        return 'export'
    if re.search(r'\b(change|correct|update|delete|remove|restore)\b', message, re.I):
        return 'update'
    if re.search(r'^\s*(when|what|which|how much|have I|did I|show|list|find)\b', message, re.I) or '?' in message:
        # "Can you log that I replaced ...?" is still an explicit logging command.
        if not re.search(r'\b(log|record|save)\b', message, re.I):
            return 'list'
    if re.search(PAST, message, re.I) or re.search(r'\b(log|record|save)\b', message, re.I):
        return 'log'
    return 'list'


def _date(message: str, timezone_name: str | None) -> str | None:
    found = re.search(r'\b(today|yesterday|\d{4}-\d{2}-\d{2})\b', message, re.I)
    return resolve_date(found.group(1).lower(), timezone_name) if found else None


def _equipment(message: str, path: Path | None) -> str | None:
    labels = list_maintenance(path)['equipment']
    matches = [item['label'] for item in labels if re.search(r'(?<!\w)' + re.escape(item['label']) + r'(?!\w)', message, re.I)]
    if matches:
        return max(matches, key=len)
    found = re.search(r'\b(?:on|for)\s+(?:(?:my|the)\s+)?(.+?)(?=\s+(?:today|yesterday|on \d{4}-|and I|at \d|cost|paid|quantity|provider|notes?)|[.,;]|$)', message, re.I)
    if found:
        return found.group(1).strip()
    found = re.search(r'\bmy\s+((?:(?:road|mountain|gravel|commuter|indoor)\s+)?bike|bicycle|running shoes|treadmill)\b', message, re.I)
    return found.group(1).strip() if found else None


def _cost(message: str) -> dict[str, object]:
    match = re.search(r'\b(?:cost(?:\s+me)?|cost\s+to|to|paid)\s+(\d+(?:\.\d+)?)\s*(euros?|EUR|USD|GBP|ILS|shekels?|pounds?)\b', message, re.I)
    if not match:
        match = re.search(r'\b(?:cost(?:\s+me)?|paid)\s+(\d+(?:\.\d+)?)\b', message, re.I)
        return {'cost_amount': float(match.group(1))} if match else {}
    unit = match.group(2).lower()
    currency = 'EUR' if unit.startswith('euro') else 'ILS' if unit.startswith('shekel') else 'GBP' if unit.startswith('pound') else unit.upper()
    return {'cost_amount': float(match.group(1)), 'cost_currency': currency}


def _query(message: str) -> str | None:
    match = re.search(r'\b(rear\s+t(?:ire|yre)|front\s+t(?:ire|yre)|chain|brakes?|tires?|tyres?)\b', message, re.I)
    if not match:
        match = re.search(r'\b(?:replace|replaced)\s+(?:(?:my|the|a|an)\s+)?(.+?)(?=\s+(?:on|for|today|yesterday)\b|[?.;]|$)', message, re.I)
    return match.group(1).lower().replace('tyre', 'tire') if match else None


def _drafts(message: str, path: Path | None, timezone_name: str | None) -> list[dict[str, object]]:
    # Notes are data, even when they contain verbs or additional instructions.
    note_parts = re.split(r'\bnotes?\s*:', message, maxsplit=1, flags=re.I)
    message = note_parts[0]
    note = note_parts[1].strip() if len(note_parts) == 2 else None
    common_equipment = _equipment(message, path)
    common_date = _date(message, timezone_name)
    clauses = re.split(r'\s+and\s+(?=(?:I\s+)?(?:replaced|serviced|repaired|installed|inspected|cleaned|lubricated)\b)|;\s*|\.\s+(?=I\s+)', message, flags=re.I)
    drafts = []
    for clause in clauses:
        match = re.search(PAST + r'\s+(.+?)(?=\s+(?:on|for)\s+(?:my|the)?|\s+(?:today|yesterday|quantity|provider\s*:|at\s+\d|cost|paid)|\s+on\s+\d{4}-|[.,;]|$)', clause, re.I)
        if not match:
            # Explicit "log a tire replacement yesterday" is a completed event request.
            replacement = re.search(r'\b(?:log|record|save)\s+(?:an?\s+)?(.+?\breplacement)\b', clause, re.I)
            action = replacement.group(1).strip() if replacement else None
            category = 'replacement' if replacement else 'general'
            objects = [action]
            verb = None
        else:
            verb = match.group(1).capitalize()
            obj = re.sub(r'^(?:the|my|a|an)\s+', '', match.group(2).strip(), flags=re.I)
            objects = [obj] if _cost(clause) or re.search(r'\bquantity\b', clause, re.I) else re.split(r'\s+and\s+', obj)
            category = 'replacement' if verb.lower() in ('replaced', 'installed') else 'repair' if verb.lower() == 'repaired' else 'inspection' if verb.lower() == 'inspected' else 'service'
        for obj in objects:
            values = {'equipment_label': _equipment(clause, path) or common_equipment,
                      'event_date': _date(clause, timezone_name) or common_date,
                      'action': f'{verb} {obj}' if verb and obj else obj, 'category': category}
            values.update(_cost(clause))
            if verb and obj:
                values['part'] = obj
            quantity = re.search(r'\bquantity\s+(\d+(?:\.\d+)?)\b', clause, re.I)
            usage = re.search(r'\bat\s+(\d+(?:\.\d+)?)\s*(km|mi|hours?)\b', clause, re.I)
            provider = re.search(r'\bprovider\s*:\s*([^.;]+)', clause, re.I)
            if quantity:
                values['quantity'] = float(quantity.group(1))
            if usage:
                values.update(usage_value=float(usage.group(1)), usage_unit=usage.group(2).lower())
            if provider:
                values['provider'] = provider.group(1).strip()
            if note:
                values['details'] = note
            drafts.append(values)
    return drafts


def _pending(draft: dict[str, object], missing: str, path: Path | None) -> dict[str, object]:
    identifier = str(uuid.uuid4())
    with connect(path) as connection:
        connection.execute('INSERT INTO maintenance_pending(id, draft_json, missing_field) VALUES (?, ?, ?)', (identifier, json_text(draft), missing))
    questions = {'equipment_label': 'Which equipment or item was this for? For example: road bike.',
                 'event_date': 'On which date was the work completed? Use today, yesterday, or YYYY-MM-DD.',
                 'action': 'What work was completed?', 'event_id': 'Which maintenance event should I change? Give its event ID from Maintenance history.'}
    return {'tool': 'maintenance_clarification', 'clarification_id': identifier, 'question': questions[missing], 'saved': False}


def _save_drafts(drafts: list[dict[str, object]], operation_id: str, path: Path | None, timezone_name: str | None):
    for event in drafts:
        for field in ('equipment_label', 'action', 'event_date'):
            if not event.get(field):
                return _pending({'kind': 'log', 'events': drafts, 'operation_id': operation_id}, field, path)
    return log_maintenance(drafts, operation_id, path, timezone_name)


def _update(message: str, operation_id: str, path: Path | None, timezone_name: str | None,
            equipment: str | None = None, event_id: str | None = None):
    original_message = message
    note = re.search(r'\bnotes?\b[^:]*?\bto\s+(.+)$', message, re.I)
    if note:
        message = message[:note.start(1)]
    equipment = equipment or _equipment(message, path)
    query = _query(message)
    events = list_maintenance(path, equipment=equipment, query=query, category='replacement' if re.search(r'\breplacement\b', message, re.I) else None, include_deleted=bool(re.search(r'\brestore\b', message, re.I)))['events']
    if event_id:
        events = [event for event in events if event['id'] == event_id]
    if not events:
        return {'tool': 'list_maintenance', 'events': [], 'message': 'No matching maintenance event is recorded.', 'cost_totals': []}
    if not equipment and len({event['equipment_id'] for event in events}) > 1:
        return _pending({'kind': 'update', 'message': original_message, 'operation_id': operation_id}, 'equipment_label', path)
    if len(events) > 1 and not re.search(r'\b(last|latest|most recent)\b', message, re.I) and not event_id:
        return _pending({'kind': 'update', 'message': original_message, 'operation_id': operation_id, 'equipment': equipment}, 'event_id', path)
    event = events[0]
    changes = _cost(message)
    event_date = _date(message, timezone_name)
    if event_date:
        changes['event_date'] = event_date
    title = re.search(r'\b(?:action|work)\s+to\s+(.+)$', message, re.I)
    if title:
        changes['action'] = title.group(1).strip().rstrip('.')
    if note:
        changes['details'] = note.group(1).strip()
    deleted = True if re.search(r'\b(delete|remove)\b', message, re.I) else False if re.search(r'\brestore\b', message, re.I) else None
    if not changes and deleted is None:
        return {'tool': 'maintenance_clarification', 'saved': False, 'question': 'Specify the field and new value, or edit the event in Maintenance history.'}
    return update_maintenance(event['id'], changes, event['revision'], operation_id, path, timezone_name, deleted)


def _maintenance_chat(message: str, operation_id: str, path: Path | None = None,
                     timezone_name: str | None = None, clarification_id: str | None = None) -> dict[str, object] | None:
    kind = request_kind(message)
    if clarification_id and not re.search(PAST + '|' + FUTURE + r'|\b(log|record|save|update|change|correct|delete|remove|restore|undo|export|when|show|list|find|what)\b', message, re.I) and '?' not in message:
        kind = None
    if not kind and not clarification_id:
        return None
    migrate(path)
    if clarification_id and kind == 'log' and not re.search(r'\b(log|record|save)\b', message, re.I):
        with connect(path) as connection:
            missing = connection.execute('SELECT missing_field FROM maintenance_pending WHERE id = ?', (clarification_id,)).fetchone()
        if missing and missing['missing_field'] == 'action':
            kind = None
    if kind == 'future':
        return {'tool': 'maintenance_clarification', 'saved': False,
                'question': 'That describes planned or hypothetical work. No completed maintenance event was saved.'}
    if clarification_id and not kind:
        with connect(path) as connection:
            pending = connection.execute('SELECT * FROM maintenance_pending WHERE id = ?', (clarification_id,)).fetchone()
        if not pending:
            raise ValueError('This clarification was not found. Repeat the original logging request.')
        draft = json.loads(pending['draft_json'])
        field = pending['missing_field']
        if draft['kind'] == 'update':
            return _update(draft['message'], draft['operation_id'], path, timezone_name,
                           equipment=message.strip() if field == 'equipment_label' else draft.get('equipment'),
                           event_id=message.strip() if field == 'event_id' else None)
        value = resolve_date(message.strip().lower(), timezone_name) if field == 'event_date' else text(re.sub(r'^my\s+', '', message.strip(), flags=re.I), field, 120 if field == 'equipment_label' else 240, True)
        for event in draft['events']:
            if not event.get(field):
                event[field] = value
                if field == 'action' and re.search(PAST, value, re.I):
                    parsed = _drafts(value, path, timezone_name)
                    if len(parsed) == 1:
                        event['category'] = parsed[0]['category']
                        if parsed[0].get('part'):
                            event['part'] = parsed[0]['part']
        return _save_drafts(draft['events'], draft['operation_id'], path, timezone_name)
    if kind == 'log':
        return _save_drafts(_drafts(message, path, timezone_name), operation_id, path, timezone_name)
    if kind == 'update':
        return _update(message, operation_id, path, timezone_name)
    if kind == 'undo':
        with connect(path) as connection:
            latest = connection.execute("SELECT id FROM maintenance_operations WHERE undone_by IS NULL AND json_extract(request_json, '$.kind') != 'undo' ORDER BY rowid DESC LIMIT 1").fetchone()
        if not latest:
            return {'tool': 'maintenance_clarification', 'saved': False, 'question': 'No maintenance action is available to undo.'}
        return undo_maintenance(latest['id'], operation_id, path)
    if kind == 'export':
        return {'tool': 'export_maintenance', 'download_url': '/api/maintenance/export.csv',
                'message': 'Download the current maintenance history as a UTF-8 CSV snapshot.'}
    equipment = _equipment(message, path)
    query = _query(message)
    start = end = None
    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', message)
    today = datetime.now(timezone_info(timezone_name)).date()
    if len(dates) == 2:
        start, end = dates
    elif _date(message, timezone_name):
        start = end = _date(message, timezone_name)
    elif re.search(r'\blast month\b', message, re.I):
        end_day = today.replace(day=1) - timedelta(days=1)
        start, end = end_day.replace(day=1).isoformat(), end_day.isoformat()
    else:
        match = re.search(r'\b(?:last|past)\s+(\d+|one|two|three|seven|eight|ten|thirty)\s+(days?|weeks?)\b', message, re.I)
        if match:
            words = {'one': 1, 'two': 2, 'three': 3, 'seven': 7, 'eight': 8, 'ten': 10, 'thirty': 30}
            count = int(match.group(1)) if match.group(1).isdigit() else words[match.group(1).lower()]
            if not 1 <= count <= 365:
                raise ValueError('Requested maintenance period is too large')
            days = count * (7 if match.group(2).lower().startswith('week') else 1)
            start, end = (today - timedelta(days=days - 1)).isoformat(), today.isoformat()
    result = list_maintenance(path, equipment=equipment, query=query, start_date=start, end_date=end,
                              category='replacement' if re.search(r'\b(replace|replaced|replacement)\b', message, re.I) else None)
    if re.search(r'\b(last|latest|most recent)\b', message, re.I):
        result['events'] = result['events'][:1]
    return result



def maintenance_chat(message: str, operation_id: str, path: Path | None = None,
                     timezone_name: str | None = None, clarification_id: str | None = None) -> dict[str, object] | None:
    if not request_kind(message) and not clarification_id:
        return None
    migrate(path)
    request = json_text({'message': message, 'timezone': timezone_name, 'clarification_id': clarification_id})
    with connect(path) as connection:
        previous = connection.execute('SELECT * FROM maintenance_chat_requests WHERE id = ?', (operation_id,)).fetchone()
    if previous:
        if previous['request_json'] != request:
            raise ValueError('Chat operation ID was reused for a different request')
        return json.loads(previous['result_json'])
    result = _maintenance_chat(message, operation_id, path, timezone_name, clarification_id)
    if result is not None:
        with connect(path) as connection:
            connection.execute('INSERT INTO maintenance_chat_requests(id, request_json, result_json) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING',
                               (operation_id, request, json_text(result)))
    return result


def maintenance_answer(result: dict[str, object]) -> str:
    if result.get('question'):
        return str(result['question'])
    if result.get('download_url'):
        return str(result['message'])
    events = result.get('events') or []
    lines = [str(result.get('message') or 'Recorded maintenance history:')]
    if not events:
        lines.append('No matching maintenance records were found.')
    for event in events[:25]:
        line = f"{event['event_date']} · {event['equipment_label']} · {event['action']}"
        if event.get('deleted_at'):
            line += ' · removed (recoverable)'
        if event.get('cost_amount') is not None:
            line += f" · {event['cost_amount']:g} {event.get('cost_currency') or '(currency not recorded)'}"
        lines.append(line)
    if len(events) > 25 or result.get('truncated'):
        lines.append('More matching records are available in Maintenance history.')
    for total in result.get('cost_totals') or []:
        lines.append(f"Recorded cost total: {total['amount']:g} {total['currency'] or '(currency not recorded)'} across {total['event_count']} events.")
    return '\n\n'.join(lines)
