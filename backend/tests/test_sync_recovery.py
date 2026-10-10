from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.activity_metrics import normalize_activity_metrics, preserve_fit_summary
from app.database import connect, migrate
from app.exports import create_backup, export_json, restore_backup
from app.garmin_connection import GarminConnectProvider, _normalise_activity, _normalise_hrv
from app.history import get_activity
from app.sync import (SimulatedGarminProvider, SyncError, SyncInterrupted, run_sync,
                      sync_plan, _upsert_activity)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        migrate(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def activity(self, **values):
        return {'source_record_id': '42', 'activity_type': 'cycling',
                'started_at': '2026-01-02T06:00:00Z', 'duration_seconds': 60,
                'source_payload': {'activityTrainingLoad': 140}, **values}

    def seed_sleep(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(id,source_name,source_record_id,metric_type,recorded_at,value,unit) VALUES ('sleep','garmin_export','sleep:2026-01-01','sleep_duration','2026-01-01',28000,'s')")

    def test_live_activity_keeps_training_fields_and_redacts_identity(self):
        record = _normalise_activity({'activityId':42, 'userProfileId':123,
            'activityTypeDTO':{'typeKey':'cycling'}, 'summaryDTO':{
                'startTimeGMT':'2026-01-02 06:00:00', 'activityTrainingLoad':140,
                'duration':60, 'normalizedPower':230, 'trainingEffect':3.2}})
        self.assertEqual(record['activity_type'], 'cycling')
        self.assertNotIn('userProfileId', record['source_payload'])
        provider = SimulatedGarminProvider({'activities':[record]})
        run_sync(provider,date(2026,1,2),self.path,data_types=('activities',))
        with connect(self.path) as c:
            identifier=c.execute('SELECT id FROM activities').fetchone()[0]
            values={r['metric_type']:r['value'] for r in c.execute('SELECT * FROM activity_metrics')}
        self.assertEqual(values['exercise_load'],140)
        self.assertEqual(values['normalized_power'],230)
        self.assertTrue(get_activity(identifier,self.path)['activity_metrics'])

    def test_filtered_export_limits_activity_metrics_to_parent_dates(self):
        with connect(self.path) as c:
            for identifier, started in [('42', '2026-01-02'), ('43', '2025-12-01')]:
                record = self.activity(source_record_id=identifier, started_at=started)
                _upsert_activity(c, record)
                activity_id = c.execute('SELECT id FROM activities WHERE source_record_id=?', (identifier,)).fetchone()[0]
                normalize_activity_metrics(c, activity_id, record['source_payload'])
        output = Path(self.temp.name) / 'filtered.json'
        export_json(output, start_date=date(2026,1,1), path=self.path)
        tables = json.loads(output.read_text())['tables']
        self.assertEqual(len(tables['activity_metrics']), 1)
        self.assertEqual(tables['activity_metrics'][0]['activity_id'], tables['activities'][0]['id'])

    def test_imported_recent_hrv_does_not_skip_older_sleep_history(self):
        self.seed_sleep()
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(id,source_name,source_record_id,metric_type,recorded_at,value,unit) VALUES ('hrv','garmin_connect','hrv:2026-01-05:average','hrv_last_night_average','2026-01-05',40,'ms')")
        plan = sync_plan(date(2026,1,6), self.path)
        hrv = next(item for item in plan['data_types'] if item['data_type']=='hrv_metrics')
        self.assertEqual(hrv['start_date'], '2026-01-01')
        self.assertEqual(hrv['kind'], 'history_backfill')

    def test_summary_refresh_preserves_archive_and_fit_fields(self):
        with connect(self.path) as c:
            _upsert_activity(c,self.activity())
            identifier=c.execute('SELECT id FROM activities').fetchone()[0]
            preserve_fit_summary(c,identifier,{'session_mesgs':[{'training_load_peak':99}]})
            _upsert_activity(c,self.activity(source_payload={'activityName':'Corrected'}))
            stored=json.loads(c.execute('SELECT raw_json FROM activities').fetchone()[0])
        self.assertEqual(stored['activityTrainingLoad'],140)
        self.assertEqual(stored['fit_sessions'][0]['training_load_peak'],99)

    def test_fit_recovery_runs_even_when_samples_already_exist_and_does_not_repeat(self):
        with connect(self.path) as c:
            _upsert_activity(c,self.activity())
            identifier=c.execute('SELECT id FROM activities').fetchone()[0]
            c.execute('INSERT INTO activity_samples(activity_id,recorded_at,heart_rate_bpm) VALUES (?, ?, 140)',(identifier,'2026-01-02T06:00:01Z'))
        class Provider(SimulatedGarminProvider):
            calls=0
            def fetch_activity_detail(self,identifier):
                self.calls+=1
                return b'FIT'
        p=Provider({'activities':[self.activity()]})
        decoded={'session_mesgs':[{'training_load_peak':99,'total_training_effect':3}], 'record_mesgs':[]}
        with patch('app.sync._decode_fit',return_value=(decoded,[])):
            run_sync(p,date(2026,1,2),self.path,data_types=('activities',))
            run_sync(p,date(2026,1,2),self.path,data_types=('activities',))
        self.assertEqual(p.calls,1)
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM activity_samples').fetchone()[0],1)
            load=c.execute("SELECT value,source_method FROM activity_metrics WHERE metric_type='exercise_load'").fetchone()
            self.assertEqual(tuple(load),(140,'garmin_summary'))
            self.assertEqual(c.execute('SELECT fit_detail_version FROM activities').fetchone()[0],1)

    def test_fit_only_fields_are_normalized_without_inventing_missing_load(self):
        with connect(self.path) as c:
            _upsert_activity(c,self.activity(source_payload={}))
            identifier=c.execute('SELECT id FROM activities').fetchone()[0]
            preserve_fit_summary(c,identifier,{'session_mesgs':[{'total_training_effect':2.5}]})
            self.assertEqual(c.execute("SELECT COUNT(*) FROM activity_metrics WHERE metric_type='exercise_load'").fetchone()[0],0)
            preserve_fit_summary(c,identifier,{'session_mesgs':[{'training_load_peak':87,'total_anaerobic_training_effect':1.2}]})
            self.assertEqual(c.execute("SELECT value FROM activity_metrics WHERE metric_type='exercise_load'").fetchone()[0],87)

    def test_multisport_fit_preserves_sessions_without_assigning_first_session_load(self):
        with connect(self.path) as c:
            _upsert_activity(c,self.activity(source_payload={}))
            identifier=c.execute('SELECT id FROM activities').fetchone()[0]
            preserve_fit_summary(c,identifier,{'session_mesgs':[{'training_load_peak':87},{'training_load_peak':100}]})
            self.assertEqual(c.execute('SELECT COUNT(*) FROM activity_metrics').fetchone()[0],0)
            self.assertEqual(len(json.loads(c.execute('SELECT raw_json FROM activities').fetchone()[0])['fit_sessions']),2)

    def test_nonfinite_and_negative_activity_metrics_are_not_saved(self):
        with connect(self.path) as c:
            _upsert_activity(c,self.activity())
            identifier=c.execute('SELECT id FROM activities').fetchone()[0]
            for value in [float('nan'),float('inf'),-1,True,None]:
                normalize_activity_metrics(c,identifier,{'activityTrainingLoad':value})
            self.assertEqual(c.execute('SELECT COUNT(*) FROM activity_metrics').fetchone()[0],0)

    def test_hrv_bootstrap_resumes_interruption_with_existing_recent_checkpoint(self):
        self.seed_sleep()
        sync_plan(date(2026,1,5),self.path)
        with connect(self.path) as c:
            c.execute("UPDATE sync_checkpoints SET coverage_end='2026-01-05' WHERE data_type='hrv_metrics'")
        provider=SimulatedGarminProvider({'hrv_metrics':[{'source_record_id':'hrv:2026-01-01','metric_type':'hrv_last_night_average','recorded_at':'2026-01-01','value':45,'unit':'ms'}]})
        with self.assertRaises(SyncInterrupted):
            run_sync(provider,date(2026,1,5),self.path,data_types=('hrv_metrics',),interrupt_after=2)
        plan=next(p for p in sync_plan(date(2026,1,5),self.path)['data_types'] if p['data_type']=='hrv_metrics')
        self.assertEqual(plan['start_date'],'2026-01-03')
        result=run_sync(provider,date(2026,1,5),self.path,data_types=('hrv_metrics',))
        self.assertEqual(result['status'],'completed')
        with connect(self.path) as c:
            row=c.execute("SELECT coverage_start,history_backfill_next FROM sync_checkpoints WHERE data_type='hrv_metrics'").fetchone()
            self.assertEqual(tuple(row),('2026-01-01',None))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM metric_readings WHERE metric_type='hrv_last_night_average'").fetchone()[0],1)

    def test_hrv_range_cache_covers_empty_days_and_fresh_daily_requests(self):
        class Client:
            range_calls=0
            daily_calls=0
            def get_hrv_data_range(self,start,end):
                self.range_calls+=1
                return {'hrvSummaries':[{'calendarDate':start,'lastNightAvg':45}]}
            def get_hrv_data(self,day):
                self.daily_calls+=1
                return {'hrvSummary':{'calendarDate':day,'lastNightAvg':50}}
        client=Client(); provider=GarminConnectProvider(client)
        provider.prepare_intervals('hrv_metrics',date(2026,1,1),date(2026,2,10))
        self.assertEqual(len(provider.fetch('hrv_metrics',date(2026,1,1),date(2026,1,1))),1)
        self.assertEqual(provider.fetch('hrv_metrics',date(2026,1,2),date(2026,1,2)),[])
        self.assertEqual(client.daily_calls,0)
        provider.prepare_intervals('hrv_metrics',date(2026,1,1),date(2026,1,1))
        self.assertEqual(provider.fetch('hrv_metrics',date(2026,1,1),date(2026,1,1))[0]['value'],50)
        self.assertEqual(client.daily_calls,1)

    def test_malformed_hrv_range_does_not_advance_coverage(self):
        self.seed_sleep()
        class Client:
            def get_hrv_data_range(self,start,end): return {'error':'unavailable'}
        result=run_sync(GarminConnectProvider(Client()),date(2026,2,10),self.path,data_types=('hrv_metrics',))
        self.assertEqual(result['status'],'failed')
        with connect(self.path) as c:
            self.assertIsNone(c.execute("SELECT coverage_end FROM sync_checkpoints WHERE data_type='hrv_metrics'").fetchone()[0])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM garmin_sync_payloads').fetchone()[0],0)

    def test_hrv_range_accepts_explicit_empty_server_shapes(self):
        for payload in [{}, None, {'hrvSummaries':None}, {'hrvSummaries':[]}]:
            with self.subTest(payload=payload):
                class Client:
                    def get_hrv_data_range(self,start,end): return payload
                provider=GarminConnectProvider(Client())
                provider.prepare_intervals('hrv_metrics',date(2018,8,6),date(2018,11,3))
                self.assertEqual(provider.fetch('hrv_metrics',date(2018,8,6),date(2018,8,6)),[])

    def test_hrv_full_response_persists_baseline_and_readings_and_backup(self):
        class Client:
            def get_hrv_data(self,day): return {'userProfilePk':123,'hrvSummary':{'calendarDate':day,'lastNightAvg':45,'baseline':{'balancedLow':40}},'hrvReadings':[{'hrvValue':47,'readingTimeGMT':'2026-01-02T01:00:00Z'}]}
        result=run_sync(GarminConnectProvider(Client()),date(2026,1,2),self.path,data_types=('hrv_metrics',))
        self.assertEqual(result['status'],'completed')
        run_sync(GarminConnectProvider(Client()),date(2026,1,2),self.path,data_types=('hrv_metrics',))
        with connect(self.path) as c:
            payload=json.loads(c.execute('SELECT payload_json FROM garmin_sync_payloads').fetchone()[0])
            self.assertNotIn('userProfilePk',payload)
            self.assertEqual(payload['hrvReadings'][0]['hrvValue'],47)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM metric_readings').fetchone()[0],1)
        output=Path(self.temp.name)/'data.json'; export_json(output,path=self.path)
        self.assertIn('garmin_sync_payloads',json.loads(output.read_text())['tables'])
        backup=Path(self.temp.name)/'backup.zip'; restored=Path(self.temp.name)/'restore.sqlite3'
        create_backup(backup,self.path); restore_backup(backup,restored)
        with connect(restored) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM garmin_sync_payloads').fetchone()[0],1)

    def test_hrv_mismatched_date_is_rejected(self):
        with self.assertRaises(SyncError):
            _normalise_hrv({'hrvSummary':{'calendarDate':'2026-01-01','lastNightAvg':45}},'2026-01-02')

    def test_activity_summary_mismatched_id_is_rejected(self):
        class Client:
            def get_activities_by_date(self,start,end): return [{'activityId':42}]
            def get_activity(self,identifier): return {'activityId':99,'summaryDTO':{}}
        with self.assertRaises(SyncError):
            GarminConnectProvider(Client()).fetch('activities',date(2026,1,2),date(2026,1,2))
