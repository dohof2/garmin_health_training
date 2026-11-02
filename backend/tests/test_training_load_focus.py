import copy,json,tempfile,unittest
from datetime import date
from pathlib import Path
from app.database import connect,migrate
from app.training_load_focus import normalize,read_load_focus

DAY=date(2026,10,27)
def record(day='2026-10-27'):
 return {'calendarDate':day,'monthlyLoadAerobicHigh':110,'monthlyLoadAerobicHighTargetMin':50,'monthlyLoadAerobicHighTargetMax':100,
  'monthlyLoadAerobicLow':40,'monthlyLoadAerobicLowTargetMin':50,'monthlyLoadAerobicLowTargetMax':100,
  'monthlyLoadAnaerobic':75,'monthlyLoadAnaerobicTargetMin':50,'monthlyLoadAnaerobicTargetMax':100}
def payload(records=None):return {'endpoints':{'get_training_four_week_load_balance':{'metricsTrainingLoadBalanceDTOMap':records or {'fictional-device':record()}}}}
class LoadFocusTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
 def store(self,p,day='2026-10-27'):
  with connect(self.path) as c:
   c.execute("INSERT INTO garmin_sync_payloads(data_type,calendar_date,payload_json) VALUES('supplementary_metrics',?,?)",(day,json.dumps(p)))
 def read(self):
  with connect(self.path) as c:return read_load_focus(c,DAY)
 def test_source_ranges_keep_units_provenance_and_all_three_positions(self):
  self.store(payload());result=self.read()
  self.assertEqual(result['status'],'current')
  self.assertEqual({k:v['position'] for k,v in result['categories'].items()},{'high_aerobic':'above','low_aerobic':'below','anaerobic':'within'})
  self.assertEqual(result['window_days'],28)
  self.assertIn('cycling-only scope is not established',result['sport_scope'])
  self.assertNotIn('fictional-device',json.dumps(result))
 def test_nested_training_status_fallback(self):
  body=payload()['endpoints']['get_training_four_week_load_balance']
  self.store({'endpoints':{'get_training_status':{'mostRecentTrainingLoadBalance':body}}})
  self.assertEqual(self.read()['source_endpoint'],'get_training_status')
 def test_missing_stale_future_and_malformed_are_not_zero(self):
  self.assertEqual(self.read()['status'],'unavailable')
  future=payload({'device':record('2026-10-28')});self.assertEqual(normalize(future,DAY),[])
  self.store(payload({'device':record('2026-10-23')}))
  self.assertEqual(self.read()['status'],'stale')
  self.assertEqual(self.read()['age_days'],4)
 def test_invalid_ranges_and_booleans_are_not_fabricated(self):
  for value in (-1,True,float('nan'),float('inf'),'110'):
   r=record();r['monthlyLoadAerobicHigh']=value
   values=normalize(payload({'device':r}),DAY)[0]['categories']
   self.assertNotIn('high_aerobic',values)
  r=record();r['monthlyLoadAerobicHighTargetMin']=150
  self.assertNotIn('high_aerobic',normalize(payload({'device':r}),DAY)[0]['categories'])
 def test_conflicting_devices_are_explicit_not_summed(self):
  a,b=record(),record();b['monthlyLoadAerobicHigh']=210
  self.store(payload({'one':a,'two':b}))
  self.assertEqual(self.read()['status'],'ambiguous');self.assertEqual(self.read()['categories'],{})
 def test_duplicate_endpoints_are_one_observation_and_read_only(self):
  p=payload();p['endpoints']['get_training_status']={'mostRecentTrainingLoadBalance':copy.deepcopy(p['endpoints']['get_training_four_week_load_balance'])}
  p['endpoints']['get_user_profile']={'private':'must not leave this source'}
  self.store(p)
  with connect(self.path) as c:
   before=list(c.iterdump());result=read_load_focus(c,DAY);self.assertEqual(before,list(c.iterdump()))
  self.assertEqual(result['status'],'current');self.assertEqual(result['categories']['high_aerobic']['value'],110)
  self.assertNotIn('private',json.dumps(result))

 def test_above_range_changes_dose_without_dropping_goal_or_cutting_recovery(self):
  from app.training_load_focus import adjust_workout
  from app.training_prescriptions import endurance
  from test_advanced_cycling import BRIEF
  self.store(payload());focus=self.read()
  workout=endurance('threshold',60,BRIEF,today=DAY,variant='split_threshold')
  changed=adjust_workout(workout,focus)
  self.assertEqual(changed['workout_kind'],'threshold')
  self.assertLess(changed['load_focus_adjustment']['work_seconds'],changed['load_focus_adjustment']['original_work_seconds'])
  self.assertEqual(sum(s['duration_seconds'] for s in changed['steps']),3600)
  self.assertEqual([s for s in changed['steps'] if s['name'].startswith('Recovery')],[s for s in workout['steps'] if s['name'].startswith('Recovery')])
  self.assertEqual([s['target'] for s in changed['steps'] if s['name'].startswith('Work lap')],[s['target'] for s in workout['steps'] if s['name'].startswith('Work lap')])
  self.assertNotEqual(changed['variant_label'],workout['variant_label'])
  self.assertEqual(sum(s['duration_seconds'] for s in workout['steps'] if s['name'].startswith('Work lap')),960)

 def test_below_within_stale_ambiguous_and_missing_never_force_more_work(self):
  from app.training_load_focus import adjust_workout
  from app.training_prescriptions import endurance
  from test_advanced_cycling import BRIEF
  self.store(payload());focus=self.read();workout=endurance('threshold',60,BRIEF,today=DAY)
  for status,position in [('current','below'),('current','within'),('stale','above'),('ambiguous','above'),('unavailable','above')]:
   evidence=copy.deepcopy(focus);evidence['status']=status;evidence['categories']['high_aerobic']['position']=position
   self.assertIs(adjust_workout(workout,evidence),workout)
