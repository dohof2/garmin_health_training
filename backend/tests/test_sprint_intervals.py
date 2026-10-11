import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,UTC,timedelta
from app.database import connect,migrate
from app.activity_metrics import preserve_fit_summary
from app.intervals import ride_efforts,weighted_power,power_segments,analyze_tool,stream
from app.charts import chart_data,validate_spec

class SprintIntervalsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        self.origin=datetime(2026,1,5,tzinfo=UTC)
    def tearDown(self):self.tmp.cleanup()
    def add_ride(self,identifier='ride',source='garmin_connect',deleted=False):
        with connect(self.path) as c:
            c.execute('INSERT INTO activities(id,source_name,activity_type,started_at,raw_json,deleted_at) VALUES(?,?,?,?,?,?)',(identifier,source,'cycling',self.origin.isoformat(),'{}','2026-01-06' if deleted else None))
            for second in range(121):
                watts=400 if 20<=second<30 or 60<=second<75 or 90<=second<100 else 100
                c.execute('INSERT INTO activity_samples(activity_id,recorded_at,power_watts) VALUES(?,?,?)',(identifier,(self.origin+timedelta(seconds=second)).isoformat(),watts))
    def test_repeated_bursts_duration_separation_and_refresh(self):
        self.add_ride();self.add_ride('fixture','synthetic_fixture');self.add_ride('deleted',deleted=True)
        result=analyze_tool({},self.path)
        self.assertEqual((result['rides_scanned'],result['matching_rides'],result['interval_count']),(1,1,3))
        self.assertEqual([p['spec']['sprint_seconds'] for p in result['plots']],[10,15])
        for plot in result['plots']:
            self.assertEqual(plot['points'][0]['y'],400)
            self.assertEqual(chart_data(plot['spec'],self.path)['points'],plot['points'])
    def test_laps_preserved_idempotently_and_not_double_counted(self):
        self.add_ride()
        messages={'session_mesgs':[],'lap_mesgs':[{'start_time':self.origin+timedelta(seconds=20),'timestamp':self.origin+timedelta(seconds=30),'total_timer_time':10,'avg_power':999}],'event_mesgs':[{'event':'timer'}],'record_mesgs':[{}]}
        with connect(self.path) as c:
            preserve_fit_summary(c,'ride',messages);preserve_fit_summary(c,'ride',messages)
            raw=json.loads(c.execute('SELECT raw_json FROM activities').fetchone()[0]);self.assertEqual(len(raw['fit_laps']),1)
        result=analyze_tool({},self.path)
        self.assertEqual(result['interval_count'],3)
        # Measured timestamp-weighted power, not a conflicting recorded summary.
        self.assertEqual(result['rides'][0]['groups'][0]['mean_power_watts'],400)
        detail=stream({'start_seconds':20,'end_seconds':30,'limit':10},self.path)
        self.assertEqual(len(detail['laps']),1);self.assertEqual(detail['sample_count'],11);self.assertTrue(detail['display_reduced'])
    def test_timestamp_weighted_average(self):
        segments=[(0,2,300),(2,3,500),(3,10,300)]
        self.assertEqual(weighted_power(segments,0,10),320)
        self.assertIsNone(weighted_power([(0,2,300),(3,10,300)],0,10))
    def test_missing_power_gap_and_long_efforts_are_not_sprints(self):
        samples=[{'t':i,'power_watts':400 if 10<=i<40 else 100} for i in range(60)]
        self.assertEqual(ride_efforts(samples,[],10,15,180)[0],[])
        broken=[{'t':i,'power_watts':400 if 10<=i<20 else 100} for i in range(40) if i not in range(14,18)]
        self.assertEqual(ride_efforts(broken,[],10,15,180)[0],[])
        null=[{'t':i,'power_watts':None if i==15 else 400 if 10<=i<20 else 100} for i in range(40)]
        self.assertEqual(ride_efforts(null,[],10,15,180)[0],[])
    def test_minimum_repetitions_and_periods(self):
        self.add_ride()
        self.assertEqual(analyze_tool({'min_repetitions':4},self.path)['matching_rides'],0)
        self.assertEqual(analyze_tool({'start_date':'2026-01-06'},self.path)['rides_scanned'],0)
        self.assertEqual(analyze_tool({'threshold_watts':500},self.path)['matching_rides'],0)
        with self.assertRaises(ValueError):analyze_tool({'min_seconds':15,'max_seconds':10},self.path)
        with self.assertRaises(ValueError):stream({'activity_id':'missing'},self.path)
    def test_chart_validation(self):
        self.add_ride()
        with self.assertRaises(ValueError):validate_spec({'metric':'activity_sprint_power','kind':'scatter','x_metric':'date'},self.path)
        with self.assertRaises(ValueError):validate_spec({'metric':'activity_sprint_power','kind':'scatter','x_metric':'activity_power','sprint_seconds':10},self.path)
    def test_more_than_one_hundred_rides_are_all_used(self):
        for i in range(101):self.add_ride(str(i))
        result=analyze_tool({},self.path)
        self.assertEqual(result['matching_rides'],101);self.assertEqual(result['plots'][0]['count'],101)
        self.assertEqual(result['returned_rides'],100);self.assertTrue(result['rides_truncated'])
