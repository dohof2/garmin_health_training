import json
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from pathlib import Path

from app.charts import add_weight, chart_data, read_layout, save_layout
from app.database import connect, migrate
from app.assistant_evidence import tool_evidence as _tool_evidence
from app.ai_tools import execute_tool


class ChartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'charts.sqlite3'
        migrate(self.path)
        with connect(self.path) as c:
            for i, day in enumerate(('2026-09-01', '2026-09-03')):
                payload = json.dumps({'sport': 'CYCLING', 'vo2MaxValue': 44+i, 'calendarDate': day})
                c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES(?, 'garmin_export','max_met_fitness',?,?,?)", (str(i),str(i),day,payload))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('hr','garmin_export','resting_heart_rate','2026-09-01',52,'bpm')")

    def test_time_scatter_preserves_all_dates_and_regression(self):
        with connect(self.path) as c: c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES('third','garmin_export','max_met_fitness','third','2026-09-05',?)",(json.dumps({'sport':'CYCLING','vo2MaxValue':46}),))
        result=chart_data({'metric':'vo2_cycling','kind':'scatter','x_metric':'date','trend_line':True,'correlation':True},self.path)
        self.assertEqual(result['x_unit'],'Date')
        self.assertTrue(all(p['x']==p['date'] for p in result['points']))
        self.assertEqual(result['analysis']['sample_count'],len(result['points']))
        self.assertIsInstance(result['analysis']['trend']['x_start'],str)
        line=chart_data({'metric':'vo2_cycling','kind':'line','trend_line':True},self.path)
        self.assertEqual(result['analysis']['trend'],line['analysis']['trend'])


    def test_sparse_vo2_is_paired_only_on_real_dates(self):
        result = chart_data({'metric':'vo2_cycling','x_metric':'resting_heart_rate','kind':'scatter'},self.path)
        self.assertEqual(result['count'],1)
        self.assertEqual(result['unpaired'],1)
        self.assertEqual((result['points'][0]['x'],result['points'][0]['y']),(52,44))
        self.assertEqual(chart_data({'metric':'vo2_running','kind':'line'},self.path)['count'],0)

    def test_layout_replacement_removal_and_empty_layout_survive_reload(self):
        one = {'id':'a','metric':'vo2_cycling','kind':'dial'}
        save_layout([one],self.path)
        replacement = {**one,'metric':'vo2_running','kind':'line'}
        save_layout([replacement],self.path)
        self.assertEqual(read_layout(self.path),[replacement])
        save_layout([],self.path)
        self.assertEqual(read_layout(self.path),[])
        with self.assertRaises(ValueError):
            save_layout([one,one],self.path)

    def test_weight_conversion_preserves_garmin_and_filters_period(self):
        add_weight('2026-09-02',165,'lb',self.path)
        r=chart_data({'metric':'weight','kind':'line','start':'2026-09-02','end':'2026-09-02'},self.path)
        self.assertEqual(r['count'],1)
        self.assertAlmostEqual(r['points'][0]['y'],74.84274105)
        self.assertEqual(r['points'][0]['source'],'manual')

    def test_archived_weight_history_merges_converts_and_deduplicates(self):
        with connect(self.path) as c:
            samples = [
                ('old', '2025-01-02', {'weight': {'weight': 79000}}),
                ('scale', '2026-09-01', {'weight': {'weight': 82000, 'timestampGMT': '2026-08-31T22:30:00.0'}}),
                ('duplicate', '2026-09-01', {'weight': {'weight': 82000}}),
                ('null', '2026-09-02', {'weight': {'weight': 83000}, 'userSetNullForWeight': True}),
                ('missing', '2026-09-03', {'height': 170}),
                ('bad', '2026-09-04', {'weight': {'weight': '84000'}}),
            ]
            for ident, day, payload in samples:
                c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES(?,'garmin_export','biometrics_history',?,?,?)", (ident,ident,day,json.dumps(payload)))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('live','garmin_connect','weight','2026-09-01',82,'kg')")
        add_weight('2026-09-01',81.5,'kg',self.path)
        r = chart_data({'metric':'weight','kind':'line','timezone':'Asia/Jerusalem'},self.path)
        self.assertEqual(r['unit'],'kg')
        self.assertEqual([(p['date'],p['y']) for p in r['points']], [('2025-01-02',79),('2026-09-01',82),('2026-09-01',81.5)])
        self.assertEqual(r['latest']['source'],'manual')
        self.assertEqual(r['excluded'],1)
        filtered = chart_data({'metric':'weight','kind':'line','timezone':'Asia/Jerusalem','start':'2026-09-01'},self.path)
        self.assertEqual(filtered['count'],2)

    def test_activity_pairing_uses_recorded_mean_speed(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,distance_meters,raw_json) VALUES('ride','garmin_export','cycling','2026-09-01T23:00:00Z',3600,10000,?)",(json.dumps({'averageSpeed':8}),))
            c.execute("INSERT INTO activity_metrics(activity_id,metric_type,value,unit,source_method,source_field) VALUES('ride','average_power',200,'W','garmin_summary','averagePower')")
        r=chart_data({'metric':'activity_speed','x_metric':'activity_power','kind':'scatter','sport':'cycling','timezone':'Asia/Jerusalem','start':'2026-09-02'},self.path)
        self.assertEqual(r['count'],1)
        self.assertEqual(r['points'][0]['x'],200)
        self.assertAlmostEqual(r['points'][0]['y'],28.8)
