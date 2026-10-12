import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from app.database import connect,migrate
from app.charts import chart_data,validate_spec
from app.training_load_charts import daily_rows,refresh_history
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
