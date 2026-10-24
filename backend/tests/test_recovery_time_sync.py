import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.database import connect, migrate
from app.supplementary_sync import normalized_metrics
from app.sync import SimulatedGarminProvider, run_sync


class RecoveryTimeSyncTests(unittest.TestCase):
    day = '2026-10-24'

    def snapshot(self, **changes):
        return {'calendarDate': self.day, 'timestamp': self.day+'T06:00:00Z',
                'recoveryTime': 120, **changes}

    def metrics(self, *rows):
        return normalized_metrics({'endpoints': {'get_training_readiness': list(rows)}}, self.day)

    def test_latest_snapshot_and_units(self):
        records = self.metrics(self.snapshot(timestamp=self.day+'T09:00:00Z', recoveryTime=60),
                               self.snapshot())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['value'], 60)
        self.assertEqual(records[0]['unit'], 'min')
        self.assertEqual(records[0]['recorded_at'], self.day+'T09:00:00+00:00')

    def test_reached_zero_overrides_retained_minutes_and_keeps_evidence(self):
        record = self.metrics(self.snapshot(recoveryTime=1846, recoveryTimeChangePhrase='REACHED_ZERO'))[0]
        self.assertEqual(record['value'], 0)
        self.assertEqual(record['source_recovery_time_minutes'], 1846)

    def test_unavailable_is_not_zero(self):
        self.assertEqual(self.metrics(), [])
        self.assertEqual(self.metrics(self.snapshot(recoveryTime=None)), [])
        self.assertEqual(self.metrics(self.snapshot(recoveryTime=0))[0]['value'], 0)

    def test_invalid_and_undated_evidence_is_not_imported(self):
        for changes in ({'recoveryTime': True}, {'recoveryTime': -1}, {'recoveryTime': '120'},
                        {'recoveryTime': float('nan')}, {'recoveryTime': float('inf')},
                        {'calendarDate': '2026-10-23'}, {'timestamp': None},
                        {'timestamp': 'invalid'}, {'timestamp': self.day+'T06:00:00'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.metrics(self.snapshot(**changes)), [])

    def test_morning_fallback_is_labeled(self):
        records = normalized_metrics({'endpoints': {'get_training_readiness': [],
            'get_morning_training_readiness': self.snapshot()}}, self.day)
        self.assertEqual(records[0]['source_endpoint'], 'get_morning_training_readiness')

    def test_sync_is_idempotent_and_updates_daily_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.sqlite3'
            migrate(path)
            provider = SimulatedGarminProvider({'supplementary_metrics': self.metrics(self.snapshot())})
            for _ in range(2):
                run_sync(provider, date.fromisoformat(self.day), path, data_types=('supplementary_metrics',))
            provider.records['supplementary_metrics'] = self.metrics(
                self.snapshot(timestamp=self.day+'T10:00:00Z', recoveryTime=30))
            run_sync(provider, date.fromisoformat(self.day), path, data_types=('supplementary_metrics',))
            with connect(path) as c:
                rows = c.execute("SELECT * FROM metric_readings WHERE metric_type='recovery_time'").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['value'], 30)
            self.assertEqual(json.loads(rows[0]['raw_json'])['source_endpoint'], 'get_training_readiness')
