"""Read APIs must observe newly committed/corrected data without process reload."""
import json,tempfile,unittest
from pathlib import Path
from app.database import connect,migrate
from app.charts import catalog,chart_data
from app.history import history_summary,list_activities
from app.training_load_charts import daily_rows,store_daily_status

class SyncedViewFreshnessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
 def activity(self,identifier,started):
  with connect(self.path) as c:c.execute("INSERT INTO activities(id,source_name,name,activity_type,started_at) VALUES(?,'garmin_connect',?,'cycling',?)",(identifier,identifier,started))
 def test_last_activity_tracks_new_upload_and_corrected_time_in_actual_time_order(self):
  self.activity('previous','2026-10-29T18:00:00Z')
  self.assertEqual(history_summary(self.path,'Asia/Jerusalem')['latest_activity']['id'],'previous')
  self.activity('latest','2026-10-30T05:49:19Z')
  self.assertEqual(history_summary(self.path,'Asia/Jerusalem')['latest_activity']['id'],'latest')
  self.activity('offset','2026-10-30T07:30:00+03:00')
  self.assertEqual(history_summary(self.path,'Asia/Jerusalem')['latest_activity']['id'],'latest')
  self.assertEqual(list_activities(path=self.path)[0]['id'],'latest')
  with connect(self.path) as c:c.execute("UPDATE activities SET started_at='2026-10-30T06:00:00Z' WHERE id='offset'")
  self.assertEqual(history_summary(self.path,'Asia/Jerusalem')['latest_activity']['id'],'offset')
 def test_metric_catalog_and_chart_observe_commits_and_corrections(self):
  self.assertFalse(any(m['id']=='resting_heart_rate' for m in catalog(self.path)['metrics']))
  with connect(self.path) as c:c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('rhr','garmin_connect','resting_heart_rate','2026-10-30',52,'bpm')")
  self.assertTrue(any(m['id']=='resting_heart_rate' for m in catalog(self.path)['metrics']))
  spec={'metric':'resting_heart_rate','kind':'line','timezone':'Asia/Jerusalem'}
  self.assertEqual(chart_data(spec,self.path)['points'][0]['y'],52)
  with connect(self.path) as c:c.execute("UPDATE metric_readings SET value=58 WHERE id='rhr'")
  self.assertEqual(chart_data(spec,self.path)['points'][0]['y'],58)
  self.assertEqual(history_summary(self.path,'Asia/Jerusalem')['metric_count'],1)
 def test_training_load_cache_tracks_source_corrections_without_restart(self):
  self.assertEqual(daily_rows(self.path),[])
  def payload(acute):return {'calendarDate':'2026-10-30','acuteTrainingLoadDTO':{'dailyTrainingLoadAcute':acute,'dailyTrainingLoadChronic':352,'minTrainingLoadChronic':300,'maxTrainingLoadChronic':500}}
  store_daily_status('2026-10-30',payload(511),self.path)
  self.assertEqual(daily_rows(self.path)[-1]['acute'],511)
  store_daily_status('2026-10-30',payload(572),self.path)
  self.assertEqual(daily_rows(self.path)[-1]['acute'],572)
