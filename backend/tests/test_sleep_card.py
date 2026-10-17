import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from app.database import migrate,connect
from app.sleep_card import night

class SleepCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        with connect(self.path) as c:
            for day,score,source in [('2026-01-01',80,'garmin_export'),('2026-01-02',42,'garmin_connect'),('2026-01-03',99,'synthetic_fixture')]:
                c.execute("INSERT INTO metric_readings(id,metric_type,value,unit,recorded_at,source_name) VALUES(?,'sleep_score',?,'score',?,?)",(day,score,day,source))
    def store(self,kind,payload,day='2026-01-02'):
        with connect(self.path) as c:c.execute('INSERT INTO garmin_sync_payloads(data_type,calendar_date,payload_json) VALUES(?,?,?)',(kind,day,json.dumps(payload)))
    def test_recorded_hrv_times_gap_and_sleep_components(self):
        self.store('sleep_metrics',{'dailySleepDTO':{'calendarDate':'2026-01-02','sleepStartTimestampGMT':'2026-01-01T23:00:00Z','sleepEndTimestampGMT':'2026-01-02T07:00:00Z','sleepScores':{'overall':{'value':42,'qualifierKey':'POOR'},'remPercentage':{'value':9,'qualifierKey':'POOR'}}}})
        self.store('hrv_metrics',{'hrvSummary':{'calendarDate':'2026-01-02'},'hrvReadings':[{'hrvValue':20,'readingTimeGMT':'2026-01-01T23:00:00.0'},{'hrvValue':30,'readingTimeGMT':'2026-01-02T00:00:00.0'},{'hrvValue':99,'readingTimeGMT':'2026-01-02T08:00:00.0'}]})
        r=night('2026-01-02',path=self.path)
        self.assertEqual(r['date'],'2026-01-02');self.assertEqual(r['score'],42)
        self.assertEqual([p['y'] for p in r['plot']['points']],[20,30]);self.assertEqual([p['segment'] for p in r['plot']['points']],[0,1])
        self.assertTrue(r['plot']['points'][0]['x'].endswith('+00:00'));self.assertEqual(r['components'][0]['label'],'REM sleep')
    def test_daily_average_is_not_a_trace_and_missing_dates_remain_empty(self):
        r=night('2026-01-01',self.path);self.assertEqual(r['score'],80);self.assertEqual(r['plot']['points'],[])
        r=night('2025-12-31',self.path);self.assertIsNone(r['score']);self.assertEqual(r['available_dates'],['2026-01-02','2026-01-01'])
    def test_sleep_payload_hrv_fallback_and_actual_date_validation(self):
        self.store('sleep_metrics',{'dailySleepDTO':{'calendarDate':'2026-01-02'},'hrvData':[{'startGMT':1767312000000,'value':25},{'startGMT':1767312300000,'value':0}]})
        self.assertEqual(night('2026-01-02',path=self.path)['plot']['count'],1)
        self.store('hrv_metrics',{'hrvSummary':{'calendarDate':'2026-01-01'},'hrvReadings':[{'hrvValue':99,'readingTimeGMT':'2026-01-02T00:00:00Z'}]})
        self.assertEqual(night('2026-01-02',path=self.path)['plot']['points'][0]['y'],25)
    def test_default_is_current_local_waking_date_not_latest_stored_night(self):
        now=datetime(2026,1,3,23,30,tzinfo=timezone.utc)
        result=night(path=self.path,timezone_name='Asia/Jerusalem',now=now)
        self.assertEqual(result['date'],'2026-01-04');self.assertEqual(result['latest_date'],'2026-01-02')
        self.assertIsNone(result['score']);self.assertIsNone(result['overnight_hrv'])
        self.assertEqual(result['score_status'],'missing')
    def test_night_average_without_trace_is_exposed_without_inventing_samples(self):
        self.store('hrv_metrics',{'hrvSummary':{'calendarDate':'2026-01-02','lastNightAvg':44}})
        result=night('2026-01-02',self.path)
        self.assertEqual(result['overnight_hrv'],44);self.assertEqual(result['plot']['points'],[])
        self.assertEqual(result['hrv_trace_status'],'missing');self.assertEqual(result['hrv_status'],'available')
    def test_normalized_average_precedence_and_invalid_units(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(id,metric_type,value,unit,recorded_at,source_name) VALUES('hrv','sleep_hrv_average',48,'ms','2026-01-02','garmin_connect')")
        self.store('hrv_metrics',{'hrvSummary':{'calendarDate':'2026-01-02','lastNightAvg':44}})
        self.assertEqual(night('2026-01-02',self.path)['overnight_hrv'],48)
        with connect(self.path) as c:c.execute("UPDATE metric_readings SET unit='bpm' WHERE id='hrv'")
        self.assertEqual(night('2026-01-02',self.path)['overnight_hrv'],44)
    def test_invalid_date_is_rejected(self):
        with self.assertRaises(ValueError):night('bad',self.path)
