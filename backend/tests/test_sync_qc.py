import json,tempfile,unittest
from pathlib import Path
from datetime import date,timedelta
from app.database import connect,migrate
from app.sync import run_sync,SimulatedGarminProvider,SyncInterrupted,sync_status
from test_sync import _seed

DAY=date(2026,10,29)
def sleep(day,seconds=25200):
 return {'source_record_id':'sleep:'+day.isoformat(),'metric_type':'sleep_duration','recorded_at':day.isoformat(),'value':seconds,'unit':'s','period_start':(day-timedelta(days=1)).isoformat()+'T21:00:00Z','period_end':day.isoformat()+'T05:00:00Z'}

class SyncQCTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';_seed(self.path,(DAY-timedelta(days=1)).isoformat())
  with connect(self.path) as c:
   r=sleep(DAY-timedelta(days=1));c.execute("INSERT INTO metric_readings(id,source_name,source_record_id,metric_type,recorded_at,value,unit,period_start,period_end,raw_json) VALUES('sleep-old','garmin_connect',?,'sleep_duration',?,?,'s',?,?,'{}')",(r['source_record_id'],r['recorded_at'],r['value'],r['period_start'],r['period_end']))
 def test_empty_supported_sleep_retries_once_then_reports_gap(self):
  class Provider(SimulatedGarminProvider):
   calls=0
   def fetch(self,kind,start,end):self.calls+=1;return []
  p=Provider({});r=run_sync(p,DAY,self.path,data_types=('sleep_metrics',),overlap_days=0)
  self.assertEqual(p.calls,2);self.assertEqual(r['qc']['status'],'attention')
  self.assertEqual(r['qc']['issues'][0]['missing'],['sleep_duration'])
  self.assertIn('QC',sync_status(self.path)['next_action'])
  with connect(self.path) as c:self.assertIsNone(c.execute("SELECT 1 FROM metric_readings WHERE source_record_id=?",('sleep:'+DAY.isoformat(),)).fetchone())
 def test_retry_recovers_sleep_and_updates_revision(self):
  class Provider(SimulatedGarminProvider):
   calls=0
   def fetch(self,kind,start,end):
    self.calls+=1;return [] if self.calls==1 else [sleep(DAY)]
  r=run_sync(Provider({}),DAY,self.path,data_types=('sleep_metrics',),overlap_days=0)
  self.assertEqual(r['qc']['status'],'passed');self.assertEqual(r['qc']['retry_attempted'],['sleep_metrics'])
  self.assertEqual(sync_status(self.path)['last_job']['progress_current'],2)
 def test_empty_intermittent_feeds_are_not_missing_daily_measurements(self):
  r=run_sync(SimulatedGarminProvider({}),DAY,self.path,data_types=('weight_metrics','vo2_metrics','activities'),overlap_days=0)
  self.assertEqual(r['qc']['status'],'passed');self.assertTrue(all(c['status']=='source_empty' for c in r['qc']['checks']))
 def test_source_failure_is_not_retried_as_empty_or_leaked(self):
  class Provider(SimulatedGarminProvider):
   calls=0
   def fetch(self,kind,start,end):self.calls+=1;raise RuntimeError('Unavailable')
  p=Provider({});r=run_sync(p,DAY,self.path,data_types=('sleep_metrics',),overlap_days=0)
  self.assertEqual(r['status'],'failed');self.assertEqual(p.calls,1)
  self.assertEqual(r['qc']['issues'][0]['status'],'failed')
 def test_sleep_and_recovery_feeds_precede_activity_load_history(self):
  class Provider(SimulatedGarminProvider):
   order=[]
   def fetch(self,kind,start,end):self.order.append(kind);return [sleep(DAY)] if kind=='sleep_metrics' else []
  p=Provider({});run_sync(p,DAY,self.path,data_types=('activities','sleep_metrics','hrv_metrics'),overlap_days=0)
  self.assertLess(p.order.index('sleep_metrics'),p.order.index('hrv_metrics'))
  self.assertLess(p.order.index('hrv_metrics'),p.order.index('activities'))
 def test_interruption_retains_audit_and_does_not_trigger_retry(self):
  with self.assertRaises(SyncInterrupted):run_sync(SimulatedGarminProvider({'sleep_metrics':[sleep(DAY)]}),DAY,self.path,data_types=('sleep_metrics','activities'),overlap_days=0,interrupt_after=1)
  q=sync_status(self.path)['last_job']['checkpoint']['qc']
  self.assertTrue(any(c['status']=='missing_interval' for c in q['issues']));self.assertEqual(q['retry_attempted'],[])

 def test_empty_reconciliation_retry_uses_a_distinct_durable_interval(self):
  result=run_sync(SimulatedGarminProvider({}),DAY,self.path,data_types=('sleep_metrics',),reconcile_from=DAY)
  self.assertEqual(result['qc']['retry_attempted'],['sleep_metrics'])
  self.assertEqual(result['qc']['retry_failed'],[])
  with connect(self.path) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM sync_intervals WHERE job_id=?',(result['job_id'],)).fetchone()[0],2)
