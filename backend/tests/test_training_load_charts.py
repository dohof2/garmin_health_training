import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from app.database import connect,migrate
from app.charts import chart_data,validate_spec
from app.training_load_charts import daily_rows,refresh_history,store_daily_status
from app.time_utils import timezone_info

class TrainingLoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        self.today=datetime.now(timezone_info('Asia/Jerusalem')).date().isoformat()
        self.spec={'metric':'acute_training_load','kind':'line','window_days':28,'show_chronic':True,'timezone':'Asia/Jerusalem'}
    def store(self,payload,day=None):
        with connect(self.path) as c:
            c.execute("INSERT INTO garmin_sync_payloads VALUES('training_load_history',?,?,CURRENT_TIMESTAMP)",(day or self.today,json.dumps(payload)))
    def payload(self,day=None):
        return {'calendarDate':day or self.today,'acuteTrainingLoadDTO':{'dailyTrainingLoadAcute':0,'dailyTrainingLoadChronic':100,'minTrainingLoadChronic':80,'maxTrainingLoadChronic':150}}
    def test_recorded_range_zero_and_overlay(self):
        self.store(self.payload());r=chart_data(self.spec,self.path)
        self.assertEqual([p['y'] for p in r['points']],[0,100]);self.assertEqual(r['range_band']['points'][0]['high'],150)
        self.assertEqual((datetime.fromisoformat(r['spec']['end'])-datetime.fromisoformat(r['spec']['start'])).days,27)
    def test_chronic_toggle_and_missing_boundaries(self):
        p=self.payload();p['acuteTrainingLoadDTO'].pop('minTrainingLoadChronic');self.store(p)
        r=chart_data({**self.spec,'show_chronic':False},self.path)
        self.assertEqual(len(r['points']),1);self.assertEqual(r['range_band']['points'],[])
    def test_actual_payload_date_overrides_request_date(self):
        self.store(self.payload('2020-01-01'));self.assertEqual(chart_data(self.spec,self.path)['points'],[])
        self.assertEqual(daily_rows(self.path)[0]['date'],'2020-01-01')
    def test_range_toggle_and_invalid_range(self):
        p=self.payload();p['acuteTrainingLoadDTO']['minTrainingLoadChronic']=200;self.store(p)
        self.assertEqual(chart_data(self.spec,self.path)['range_band']['points'],[])
    def test_invalid_options(self):
        for patch in ({'window_days':True},{'show_chronic':'yes'},{'kind':'scatter','x_metric':'date'},{'trend_line':True},{'metric':'weight'}):
            with self.assertRaises(ValueError):validate_spec({**self.spec,**patch},self.path)
    def test_refresh_preserves_full_payload_and_partial_errors(self):
        outer=self
        class Client:
            count=0
            def get_daily_training_status(self,day):
                self.count+=1
                if self.count==1:raise RuntimeError('private credential error')
                return {**outer.payload(day),'additionalRawField':{'everything':[1,2]}}
        r=refresh_history(self.path,days=2,timezone='Asia/Jerusalem',client=Client())
        self.assertEqual(r['fetched_days'],1);self.assertEqual(len(r['failed_dates']),1)
        with connect(self.path) as c:payload=json.loads(c.execute('SELECT payload_json FROM garmin_sync_payloads').fetchone()[0])
        self.assertIn('additionalRawField',payload['endpoints']['get_daily_training_status'])
    def test_gap_segments_and_invalid_values(self):
        self.store(self.payload())
        old=(datetime.fromisoformat(self.today)-timedelta(days=3)).date().isoformat();self.store(self.payload(old),old)
        r=chart_data(self.spec,self.path)
        self.assertEqual([p['segment'] for p in r['points'] if p['series_id']=='acute'],[0,1])
    def test_daily_endpoint_wins_equal_timestamp_regardless_of_json_order(self):
        daily=self.payload();daily['acuteTrainingLoadDTO']['dailyTrainingLoadAcute']=245
        summary=self.payload();summary['acuteTrainingLoadDTO']['dailyTrainingLoadAcute']=100
        for endpoints in ({'get_daily_training_status':daily,'get_training_status':summary},{'get_training_status':summary,'get_daily_training_status':daily}):
            with connect(self.path) as c:
                c.execute("INSERT OR REPLACE INTO garmin_sync_payloads VALUES('supplementary_metrics',?,?,?)",(self.today,json.dumps({'endpoints':endpoints}),'2026-10-27 10:00:00'))
            self.assertEqual(daily_rows(self.path)[0]['acute'],245)
    def test_new_commit_invalidates_cached_rows_and_old_history_cannot_replace_it(self):
        self.store(self.payload());self.assertEqual(daily_rows(self.path)[0]['acute'],0)
        fresh=self.payload();fresh['acuteTrainingLoadDTO']['dailyTrainingLoadAcute']=320
        with connect(self.path) as c:
            c.execute("UPDATE garmin_sync_payloads SET updated_at='2026-10-26 10:00:00'")
            c.execute("INSERT INTO garmin_sync_payloads VALUES('supplementary_metrics',?,?,?)",(self.today,json.dumps({'endpoints':{'get_daily_training_status':fresh}}),'2026-10-27 10:00:00'))
        self.assertEqual(daily_rows(self.path)[0]['acute'],320)
        with connect(self.path) as c:
            c.execute("UPDATE garmin_sync_payloads SET payload_json='broken' WHERE data_type='supplementary_metrics'")
        self.assertEqual(daily_rows(self.path)[0]['acute'],0)

    def test_later_fetch_of_older_garmin_observation_cannot_replace_new_value(self):
        fresh=self.payload();fresh['timestamp']=1793169000000;fresh['acuteTrainingLoadDTO']['dailyTrainingLoadAcute']=511
        old=self.payload();old['timestamp']=1793160000000;old['acuteTrainingLoadDTO']['dailyTrainingLoadAcute']=295
        self.store({'endpoints':{'get_daily_training_status':fresh}})
        with connect(self.path) as c:
            c.execute("UPDATE garmin_sync_payloads SET updated_at='2026-10-28 06:40:00'")
            c.execute("INSERT INTO garmin_sync_payloads VALUES('supplementary_metrics',?,?,?)",(self.today,json.dumps({'endpoints':{'get_daily_training_status':old}}),'2026-10-28 07:00:00'))
        self.assertEqual(daily_rows(self.path)[0]['acute'],511)

    def test_missing_wrong_day_and_malformed_source_preserve_last_record(self):
        self.store(self.payload())
        for payload in ({},self.payload('2000-01-01'),None,{'calendarDate':self.today,'acuteTrainingLoadDTO':{'dailyTrainingLoadAcute':True}}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):store_daily_status(self.today,payload,self.path)
        self.assertEqual(daily_rows(self.path)[0]['acute'],0)
