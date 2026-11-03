from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from os import environ
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.database import connect, migrate
from app.exports import create_backup, export_json, restore_backup
from app.maintenance import (event_history, list_maintenance, log_maintenance, resolve_date,
                             undo_maintenance, update_maintenance, validate_event)
from app.maintenance_csv import apply_maintenance_csv, export_maintenance_csv, preview_maintenance_csv


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / 'maintenance.sqlite3'
        migrate(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def event(self, **updates):
        return {'equipment_label': 'road bike', 'action': 'Replaced chain', 'event_date': '2026-01-02', 'category': 'replacement', **updates}

    def log(self, operation='log', **updates):
        return log_maintenance([self.event(**updates)], operation, self.path)


    def test_validated_optional_fields_and_case_insensitive_labels(self):
        first = self.log(part='chain', quantity=1, cost_amount=45, cost_currency='eur', provider='Bike shop', usage_value=1200, usage_unit='km', details='Quoted, multiline\nnotes')
        second = self.log('second', equipment_label='ROAD BIKE')
        self.assertEqual(first['events'][0]['cost_currency'], 'EUR')
        self.assertEqual(first['events'][0]['equipment_id'], second['events'][0]['equipment_id'])
        self.assertEqual(len(event_history(first['events'][0]['id'], self.path)['revisions']), 1)

    def test_validation_atomic_batch_and_nonfinite_values(self):
        for changes in ({'event_date': 'bad'}, {'equipment_label': ''}, {'cost_amount': -1}, {'quantity': 0},
                        {'cost_amount': float('nan')}, {'usage_value': float('inf')}, {'cost_amount': True},
                        {'cost_currency': 'EURO'}, {'category': 'invented'}, {'event_date': '2099-01-01'}, {'shell': 'write'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_event(self.event(**changes))
        with self.assertRaises(ValueError):
            log_maintenance([self.event(), self.event(action='')], 'batch', self.path)
        self.assertEqual(list_maintenance(self.path)['total_matches'], 0)

    def test_idempotent_actions_but_genuine_identical_events_remain_distinct(self):
        first = self.log()
        self.assertEqual(first, self.log())
        self.log('different-operation')
        self.assertEqual(list_maintenance(self.path)['total_matches'], 2)
        with self.assertRaisesRegex(ValueError, 'different action'):
            self.log(action='Repaired brakes')

    def test_concurrent_retry_creates_one_event(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.log(), range(8)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(list_maintenance(self.path)['total_matches'], 1)

    def test_edit_stale_rejection_revisions_undo_and_sequential_undo(self):
        logged = self.log()
        event = logged['events'][0]
        updated = update_maintenance(event['id'], {'cost_amount': 45, 'cost_currency': 'EUR'}, 1, 'edit', self.path)
        self.assertEqual(updated, update_maintenance(event['id'], {'cost_amount': 45, 'cost_currency': 'EUR'}, 1, 'edit', self.path))
        with self.assertRaisesRegex(ValueError, 'changed'):
            update_maintenance(event['id'], {'action': 'Other'}, 1, 'stale', self.path)
        with self.assertRaisesRegex(ValueError, 'later edit'):
            undo_maintenance('log', 'bad-undo', self.path)
        undone = undo_maintenance('edit', 'undo-edit', self.path)
        self.assertIsNone(undone['events'][0]['cost_amount'])
        self.assertEqual(undone, undo_maintenance('edit', 'undo-edit', self.path))
        undo_maintenance('log', 'undo-log', self.path)
        self.assertEqual(list_maintenance(self.path)['total_matches'], 0)
        self.assertEqual(len(event_history(event['id'], self.path)['revisions']), 4)

    def test_remove_restore_and_undo_preserve_history(self):
        event = self.log()['events'][0]
        removed = update_maintenance(event['id'], {}, 1, 'remove', self.path, deleted=True)
        self.assertEqual(list_maintenance(self.path)['total_matches'], 0)
        self.assertEqual(list_maintenance(self.path, include_deleted=True)['total_matches'], 1)
        restored = update_maintenance(event['id'], {}, removed['events'][0]['revision'], 'restore', self.path, deleted=False)
        self.assertEqual(list_maintenance(self.path)['total_matches'], 1)
        self.assertEqual(restored['events'][0]['revision'], 3)

    def test_filters_and_separate_currency_totals_are_not_limited_to_display(self):
        self.log(cost_amount=45, cost_currency='EUR')
        self.log('usd', cost_amount=50, cost_currency='USD')
        self.log('unknown', cost_amount=10)
        self.log('different', equipment_label='mountain bike', action='Serviced brakes', category='service', event_date='2026-02-01')
        filtered = list_maintenance(self.path, equipment='road bike', query='chain', start_date='2026-01-01', end_date='2026-01-31', limit=1)
        self.assertEqual(filtered['total_matches'], 3)
        self.assertTrue(filtered['truncated'])
        self.assertEqual({total['currency']: total['amount'] for total in filtered['cost_totals']}, {'EUR': 45, 'USD': 50, None: 10})
        self.assertEqual(list_maintenance(self.path, category='service')['total_matches'], 1)

    def test_relative_dates_use_calendar_and_timezone(self):
        self.assertEqual(resolve_date('yesterday', today=date(2026, 1, 1)), '2025-12-31')
        self.assertEqual(resolve_date('today', today=date(2026, 10, 10)), '2026-10-10')
        with patch('app.maintenance.datetime') as clock:
            clock.now.side_effect = lambda zone: datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc).astimezone(zone)
            self.assertEqual(resolve_date('today', 'Asia/Jerusalem'), '2026-01-02')


    def test_csv_round_trip_quote_unicode_formula_safety_and_no_duplicates(self):
        self.log(equipment_label='=dangerous', action='\t=SUM(1,2)', details="'quoted,\nשלום")
        exported = export_maintenance_csv(self.path)
        row = next(csv.DictReader(io.StringIO(exported)))
        self.assertTrue(row['equipment_label'].startswith("'="))
        self.assertTrue(row['action'].startswith("'="))
        self.assertTrue(row['details'].startswith("''"))
        preview = preview_maintenance_csv(exported, path=self.path)
        self.assertEqual(preview['counts']['unchanged'], 1)
        apply_maintenance_csv(preview['preview_id'], {}, 'csv-same', self.path)
        other = self.path.parent / 'other.sqlite3'
        imported = preview_maintenance_csv(exported, path=other)
        apply_maintenance_csv(imported['preview_id'], {}, 'csv-other', other)
        event = list_maintenance(other)['events'][0]
        self.assertEqual(event['equipment_label'], '=dangerous')
        self.assertEqual(event['details'], "'quoted,\nשלום")
        repeated = preview_maintenance_csv(exported, path=other)
        self.assertEqual(repeated['counts']['unchanged'], 1)
        self.assertEqual(list_maintenance(other)['total_matches'], 1)


    def test_api_log_edit_stale_undo_and_csv_round_trip(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with patch.dict(environ, {'HT_APP_DATA_DIR': str(self.path.parent)}), TestClient(app) as client:
            body = {'events': [self.event()], 'operation_id': 'api-log'}
            logged = client.post('/api/maintenance', json=body)
            self.assertEqual(logged.status_code, 200)
            self.assertEqual(logged.json(), client.post('/api/maintenance', json=body).json())
            identifier = logged.json()['events'][0]['id']
            url = f'/api/maintenance/events/{identifier}'
            correction = {'changes': {'cost_amount': 45, 'cost_currency': 'EUR'}, 'expected_revision': 1, 'operation_id': 'api-edit'}
            self.assertEqual(client.patch(url, json=correction).status_code, 200)
            self.assertEqual(client.patch(url, json={**correction, 'operation_id': 'stale'}).status_code, 409)
            self.assertEqual(client.patch(url, json={**correction, 'expected_revision': True}).status_code, 422)
            self.assertEqual(len(client.get(url).json()['revisions']), 2)
            exported = client.get('/api/maintenance/export.csv')
            self.assertIn('text/csv', exported.headers['content-type'])
            self.assertIn('attachment', exported.headers['content-disposition'])
            preview = client.post('/api/maintenance/csv/preview', json={'content': exported.text}).json()
            self.assertEqual(preview['counts']['unchanged'], 1)
            applied = client.post('/api/maintenance/csv/apply', json={'preview_id': preview['preview_id'], 'operation_id': 'csv-api'})
            self.assertEqual(applied.status_code, 200)
            self.assertEqual(client.get('/api/maintenance').json()['total_matches'], 1)
            self.assertEqual(client.post('/api/maintenance/operations/api-edit/undo', json={'operation_id': 'api-undo'}).status_code, 200)
            self.assertIsNone(client.get(url).json()['event']['cost_amount'])
            self.assertEqual(client.post('/api/maintenance', json={'events': [self.event()]}).status_code, 422)

    def test_csv_mapping_invalid_rows_duplicates_and_distinct_dates(self):
        content = 'Bike,Work,When\nroad bike,Replaced chain,2026-01-02\nroad bike,Replaced chain,2026-01-02\nroad bike,Replaced chain,2026-01-03\n'
        missing = preview_maintenance_csv(content, path=self.path)
        self.assertIsNone(missing['preview_id'])
        mapped = preview_maintenance_csv(content, {'equipment_label': 'Bike', 'action': 'Work', 'event_date': 'When'}, self.path)
        self.assertEqual(mapped['counts']['new'], 2)
        self.assertEqual(mapped['counts']['duplicate'], 1)
        apply_maintenance_csv(mapped['preview_id'], {}, 'mapped', self.path)
        self.assertEqual(list_maintenance(self.path)['total_matches'], 2)
        invalid = preview_maintenance_csv('equipment,action,date\nroad bike,Work,bad\n', path=self.path)
        self.assertTrue(invalid['errors'])
        with self.assertRaises(ValueError):
            apply_maintenance_csv(invalid['preview_id'], {}, 'bad-csv', self.path)

    def test_csv_conflict_requires_choice_stale_preview_rejects_and_import_is_undoable(self):
        event = self.log()['events'][0]
        output = io.StringIO()
        rows = list(csv.DictReader(io.StringIO(export_maintenance_csv(self.path))))
        rows[0]['cost_amount'] = '45'
        rows[0]['cost_currency'] = 'EUR'
        writer = csv.DictWriter(output, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
        content = output.getvalue()
        preview = preview_maintenance_csv(content, path=self.path)
        self.assertEqual(preview['counts']['conflict'], 1)
        skipped = apply_maintenance_csv(preview['preview_id'], {}, 'skip-conflict', self.path)
        self.assertEqual(skipped['events'], [])
        preview = preview_maintenance_csv(content, path=self.path)
        result = apply_maintenance_csv(preview['preview_id'], {'2': 'update'}, 'apply-conflict', self.path)
        self.assertEqual(result['events'][0]['cost_amount'], 45)
        self.assertEqual(result, apply_maintenance_csv(preview['preview_id'], {'2': 'update'}, 'apply-conflict', self.path))
        undo_maintenance('apply-conflict', 'undo-csv', self.path)
        self.assertIsNone(list_maintenance(self.path)['events'][0]['cost_amount'])
        stale = preview_maintenance_csv(content, path=self.path)
        current = list_maintenance(self.path)['events'][0]
        update_maintenance(event['id'], {'details': 'new edit'}, current['revision'], 'new-edit', self.path)
        with self.assertRaisesRegex(ValueError, 'since preview'):
            apply_maintenance_csv(stale['preview_id'], {'2': 'update'}, 'stale-csv', self.path)

    def test_json_and_backup_restore_preserve_events_revisions_actions(self):
        event = self.log()['events'][0]
        update_maintenance(event['id'], {'details': 'corrected'}, 1, 'edit', self.path)
        output = self.path.parent / 'export.json'
        export_json(output, path=self.path)
        exported = json.loads(output.read_text())['tables']
        self.assertEqual(len(exported['maintenance_events']), 1)
        self.assertEqual(len(exported['maintenance_event_revisions']), 2)
        backup = self.path.parent / 'backup.zip'; restored = self.path.parent / 'restored.sqlite3'
        create_backup(backup, self.path); restore_backup(backup, restored)
        self.assertEqual(len(event_history(event['id'], restored)['revisions']), 2)
        undo_maintenance('edit', 'undo-restored', restored)
        self.assertIsNone(list_maintenance(restored)['events'][0]['details'])


if __name__ == '__main__':
    unittest.main()
