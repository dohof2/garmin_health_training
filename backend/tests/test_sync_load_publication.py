"""Fast source commits and daily publication windows; all provider calls are fake."""
import json,tempfile,unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.sync import SimulatedGarminProvider,run_sync,sync_status,ensure_sync_checkpoints
from app.training_load_charts import daily_rows
from app.rolling_publication import window,DailyPublicationWorker
from app.training_volume import estimates
from app.active_training import _observed_cycling_minutes
from test_sync import _seed
from test_long_ride_allocation import preferences

DAY=date(2026,10,28);NOW=datetime(2026,10,28,8,tzinfo=timezone.utc)

def payload(day,acute=511):
 return {'calendarDate':day.isoformat(),'timestamp':1793170000000,'acuteTrainingLoadDTO':{'dailyTrainingLoadAcute':acute,'dailyTrainingLoadChronic':363,'minTrainingLoadChronic':290,'maxTrainingLoadChronic':544}}

class FastLoadSyncTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';_seed(self.path,(DAY-timedelta(days=1)).isoformat())
 def provider(self,fail=False):
  owner=self
  class Provider(SimulatedGarminProvider):
   def fetch_training_load(self,day):
    self.order.append('load:'+day.isoformat())
    if fail:raise RuntimeError('private URL/token must not escape')
    return payload(day)
   def fetch(self,kind,start,end):
    self.order.append(kind)
    if kind=='weight_metrics':
     assert daily_rows(owner.path)[-1]['acute']==511
     state=sync_status(owner.path)['last_job']
     assert state['status']=='running' and state['checkpoint']['data_revision']>=2
    return super().fetch(kind,start,end)
  p=Provider({'activities':[{'source_record_id':'new','activity_type':'cycling','started_at':DAY.isoformat()+'T05:00:00Z','duration_seconds':3600}]});p.order=[]
  return p
 def test_load_is_visible_before_other_sync_families_finish(self):
  p=self.provider();r=run_sync(p,DAY,self.path,data_types=('activities','daily_metrics','weight_metrics'),overlap_days=0)
  self.assertEqual(p.order[:4],['daily_metrics','activities','load:'+DAY.isoformat(),'weight_metrics'])
  self.assertEqual(r['status'],'completed');self.assertEqual(r['training_load_refresh']['fetched_dates'],[DAY.isoformat()])
  self.assertGreater(sync_status(self.path)['last_job']['checkpoint']['data_revision'],2)
 def test_load_failure_keeps_committed_activity_and_is_retried_when_unchanged(self):
  r=run_sync(self.provider(True),DAY,self.path,data_types=('activities',),overlap_days=0)
  self.assertEqual(r['status'],'failed');self.assertNotIn('private',json.dumps(r))
  with connect(self.path) as c:self.assertIsNotNone(c.execute("SELECT id FROM activities WHERE source_record_id='new'").fetchone())
  self.assertEqual(daily_rows(self.path),[])
  self.assertIn('Retry',sync_status(self.path)['next_action'])
  r=run_sync(self.provider(),DAY,self.path,data_types=('activities',),overlap_days=1)
  self.assertEqual(r['status'],'completed');self.assertEqual(daily_rows(self.path)[-1]['acute'],511)

class DailyWindowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  with connect(self.path) as c:c.execute("INSERT INTO training_plans(id,name,status) VALUES('root','Fictional plan','active')")
 def test_window_is_seven_workouts_not_seven_days_and_keeps_removals(self):
  with connect(self.path) as c:
   for i in range(9):
    day=(DAY+timedelta(days=i*3)).isoformat()
    c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,'root','cycling','Ride',?,'{}')",(str(i),day+'T12:00:00Z'))
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,completion_status,publish_status,garmin_workout_id) VALUES('remove','root','cycling','Canceled',?,'{}','cancelled','update_needed','remote')",(DAY.isoformat()+'T12:00:00Z',))
   self.assertEqual(window(c,'root','UTC',NOW,False),[str(i) for i in range(7)])
   self.assertEqual(window(c,'root','UTC',NOW),[str(i) for i in range(7)]+['remove'])
 def test_daily_worker_requires_opt_in_fresh_core_data_and_new_local_day(self):
  worker=DailyPublicationWorker(self.path)
  with patch('app.rolling_publication.sync') as publish:
   worker.tick(NOW);publish.assert_not_called()
   with connect(self.path) as c:c.execute("INSERT INTO garmin_rolling_publication(id,enabled,account_key,root_plan_id,timezone) VALUES(1,1,'fake','root','UTC')")
   ensure_sync_checkpoints(self.path);worker.tick(NOW);publish.assert_not_called()
   with connect(self.path) as c:c.execute("UPDATE sync_checkpoints SET status='synced',coverage_end=?",(DAY.isoformat(),))
   worker.tick(NOW);publish.assert_called_once();publish.reset_mock()
   with connect(self.path) as c:c.execute('UPDATE garmin_rolling_publication SET detail_json=?',(json.dumps({'last_success_date':DAY.isoformat()}),))
   worker.tick(NOW);publish.assert_not_called()
   worker.tick(NOW+timedelta(days=1));publish.assert_not_called()
   with connect(self.path) as c:c.execute("UPDATE sync_checkpoints SET coverage_end=?",((DAY+timedelta(days=1)).isoformat(),))
   worker.tick(NOW+timedelta(days=1));publish.assert_called_once()
 def test_two_long_rides_in_distinct_weeks_use_shorter_duration_not_outlier_average(self):
  ensure_sync_checkpoints(self.path)
  with connect(self.path) as c:
   c.execute("UPDATE sync_checkpoints SET coverage_start='2026-01-01',coverage_end=? WHERE data_type='activities'",(DAY.isoformat(),))
   for i,(ago,minutes) in enumerate([(19,310),(14,99),(7,55),(6,58),(3,60),(1,65)]):
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_connect','cycling',?,?)",(str(i),(DAY-timedelta(days=ago)).isoformat()+'T05:00:00Z',minutes*60))
   e=estimates(c,preferences(),{},DAY,'UTC')['cycling']
   answers=preferences();answers['weekly_caps']={'cycling':{'max_minutes':330,'range_min_minutes':300}}
   raised=estimates(c,answers,{},DAY,'UTC')['cycling']
  self.assertEqual(e['long_session_minutes'],min(99,e['estimate_minutes']))
  self.assertLess(e['long_session_minutes'],(310+99)/2)
  self.assertEqual(raised['effective_ceiling_minutes'],330)
  self.assertEqual(raised['baseline_minutes'],e['baseline_minutes'])
 def test_observed_week_counts_unplanned_rides_without_double_counting_linked_completion(self):
  ensure_sync_checkpoints(self.path)
  with connect(self.path) as c:
   c.execute("UPDATE sync_checkpoints SET coverage_start='2026-01-01',coverage_end=?,status='synced' WHERE data_type='activities'",(DAY.isoformat(),))
   for identifier,day,minutes in [('actual',DAY,68),('unplanned',DAY-timedelta(days=1),69)]:
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_connect','cycling',?,?)",(identifier,day.isoformat()+'T05:00:00Z',minutes*60))
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,completion_status) VALUES('completed','root','cycling','Ride',?,?,'completed')",(DAY.isoformat()+'T12:00:00Z',json.dumps({'duration_minutes':60})))
   c.execute("INSERT INTO training_feedback(workout_id,pain_or_illness,activity_id) VALUES('completed',0,'actual')")
   rows=[dict(r) for r in c.execute('SELECT * FROM planned_workouts')]
   self.assertEqual(_observed_cycling_minutes(c,rows,DAY-timedelta(days=2),DAY,'UTC'),137)
   c.execute("UPDATE sync_checkpoints SET status='syncing' WHERE data_type='activities'")
   self.assertIsNone(_observed_cycling_minutes(c,rows,DAY-timedelta(days=2),DAY,'UTC'))
 def test_new_week_preview_preserves_two_hour_friday_with_explicit_allowance(self):
  from app.training_coach import preview,DEFAULT
  ensure_sync_checkpoints(self.path)
  with connect(self.path) as c:
   c.execute("UPDATE sync_checkpoints SET status='synced',coverage_start='2026-01-01',coverage_end=? WHERE data_type='activities'",(DAY.isoformat(),))
   for i,(ago,minutes) in enumerate([(19,99),(14,95),(7,55),(3,60)]):
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_connect','cycling',?,?)",(str(i),(DAY-timedelta(days=ago)).isoformat()+'T05:00:00Z',minutes*60))
  answers=preferences();answers['weekly_caps']={'cycling':{'range_min_minutes':300,'max_minutes':330}}
  answers['week_schedule'][4]['activities'][0]['min_minutes']=120
  start=DAY-timedelta(days=DAY.weekday())
  b={**DEFAULT,'goal':'general','program_start':start.isoformat(),'duration_confirmed':True}
  result=preview(b,start,'UTC',self.path,NOW,candidate_answers=answers)
  self.assertEqual(result['status'],'ready',result.get('questions'))
  friday=next(s for s in result['sessions'] if s['scheduled_for'][:10]=='2026-10-30')
  self.assertGreaterEqual(friday['definition']['duration_minutes'],120)
  self.assertEqual(friday['definition']['workout_kind'],'long_endurance')

if __name__=='__main__':unittest.main()
