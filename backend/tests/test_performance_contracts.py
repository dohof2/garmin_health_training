import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.charts import catalog,chart_data
from app.history import weekly_calories_summary
from app.read_cache import versioned_read


class PerformanceContracts(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'qc.sqlite';migrate(self.path)

    def test_cache_reuses_but_invalidates_same_count_corrections_deletions_and_other_connections(self):
        calls=[]
        @versioned_read
        def load(path):
            calls.append(1)
            with connect(path) as c:return [dict(r) for r in c.execute('SELECT id,value FROM metric_readings')]
        self.assertEqual(load(self.path),[]);load(self.path);self.assertEqual(len(calls),1)
        with connect(self.path) as c:c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('x','manual','weight','2026-10-21',70,'kg')")
        self.assertEqual(load(self.path)[0]['value'],70)
        altered=load(self.path);altered[0]['value']=999
        self.assertEqual(load(self.path)[0]['value'],70)
        with connect(self.path) as c:c.execute("UPDATE metric_readings SET value=71 WHERE id='x'")
        self.assertEqual(load(self.path)[0]['value'],71)
        with connect(self.path) as c:c.execute("DELETE FROM metric_readings WHERE id='x'")
        self.assertEqual(load(self.path),[]);self.assertEqual(len(calls),4)

    def test_standard_plot_does_not_build_all_archive_and_fit_catalogs(self):
        with patch('app.charts.catalog',side_effect=AssertionError('Expensive catalog called')):
            result=chart_data({'metric':'weight','kind':'line'},self.path)
        self.assertEqual(result['count'],0)

    def test_live_week_overrides_archive_without_doubling_and_future_days_are_not_gaps(self):
        with connect(self.path) as c:
            for key,source,day,value in [('old','garmin_export','2026-10-04',2000),('export','garmin_export','2026-10-19',9000),('live','garmin_connect','2026-10-19',2100),('tue','garmin_connect','2026-10-20',2200),('wed','garmin_connect','2026-10-21',700),('future','garmin_connect','2026-10-25',9999)]:
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,?,'total_calories',?,?,'kcal')",(key,source,day,value))
        r=weekly_calories_summary(self.path,'Asia/Jerusalem',datetime(2026,10,21,8,tzinfo=timezone.utc))
        self.assertEqual(r['week_start'],'2026-10-19');self.assertEqual(r['total_kcal'],5000)
        self.assertEqual(r['missing_dates'],[]);self.assertEqual(r['days_elapsed'],3)
        self.assertEqual(r['period_status'],'week_to_date');self.assertTrue(r['today_in_progress'])
        with connect(self.path) as c:c.execute("DELETE FROM metric_readings WHERE id='tue'")
        r=weekly_calories_summary(self.path,'Asia/Jerusalem',datetime(2026,10,21,8,tzinfo=timezone.utc))
        self.assertEqual(r['missing_dates'],['2026-10-20']);self.assertEqual(r['period_status'],'partial')

    def test_speed_chart_preserves_recorded_summary_and_single_fit_session_fallback(self):
        with connect(self.path) as c:
            for index,payload in enumerate(({'averageSpeed':2},{'summaryDTO':{'averageSpeed':3},'averageSpeed':100},{'fit_sessions':[{'enhanced_avg_speed':4}]},{'fit_sessions':[{'avg_speed':5}]},{'fit_sessions':[{'avg_speed':10},{'avg_speed':20}]})):
                c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,raw_json) VALUES(?,'garmin_connect','cycling',?,?)",(str(index),f'2026-10-{index+1:02d}T08:00:00Z',json.dumps(payload)))
        r=chart_data({'metric':'activity_speed','kind':'line','timezone':'UTC'},self.path)
        self.assertEqual([p['y'] for p in r['points']],[7.2,10.8,14.4,18])
        self.assertEqual(r['excluded'],1)

    def test_repeated_sync_summary_skips_parsing_large_preserved_fit_payload(self):
        from app.sync import _upsert_activity
        record={'source_record_id':'123','activity_type':'cycling','started_at':'2026-10-21T08:00:00Z','source_payload':{'averagePower':150}}
        with connect(self.path) as c:
            self.assertEqual(_upsert_activity(c,record),'created')
            row=c.execute("SELECT id,raw_json FROM activities WHERE source_record_id='123'").fetchone()
            raw=json.loads(row['raw_json']);raw['fit_messages']={'record_mesgs':[{'power':123}]*1000}
            c.execute('UPDATE activities SET raw_json=? WHERE id=?',(json.dumps(raw),row['id']))
            with patch('app.sync.json.loads',side_effect=AssertionError('Repeated FIT parsing')):
                self.assertEqual(_upsert_activity(c,record),'unchanged')
            changed={**record,'source_payload':{'averagePower':160}}
            self.assertEqual(_upsert_activity(c,changed),'updated')
            saved=json.loads(c.execute('SELECT raw_json FROM activities WHERE id=?',(row['id'],)).fetchone()[0])
            self.assertEqual(saved['averagePower'],160);self.assertIn('fit_messages',saved)

    def test_compact_training_keeps_editable_sessions_and_saved_provenance(self):
        from test_training_adjustments import fixture
        from app.training import list_training
        fixture(self.path)
        complete=list_training(self.path);compact=list_training(self.path,compact=True)
        self.assertEqual([w['id'] for w in compact['workouts']],[w['id'] for w in complete['workouts']])
        for small,full in zip(compact['workouts'],complete['workouts']):
            self.assertEqual(small['definition'],full['definition']);self.assertEqual(small['revision'],full['revision'])
            self.assertNotIn('definition_json',small)
        self.assertLess(len(json.dumps(compact)),len(json.dumps(complete)))
        self.assertEqual(list_training(self.path),complete)
