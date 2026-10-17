import tempfile,unittest
from pathlib import Path
from app.database import migrate
from app.ai_tools import execute_tool,tool_definitions,TOOL_DEFINITIONS_BY_NAME,TOOL_HANDLERS
class RegistryTests(unittest.TestCase):
 def test_every_advertised_tool_is_executable(self):
  names={d['name'] for d in tool_definitions()}
  self.assertEqual(names,set(TOOL_DEFINITIONS_BY_NAME));self.assertEqual(names,set(TOOL_HANDLERS))
 def test_new_tools_dispatch_without_missing_registry_entries(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db.sqlite';migrate(p)
   self.assertIsNone(execute_tool('get_active_training_plan',{},p)['program'])
   self.assertIn('training_mix',execute_tool('get_recent_training_mix',{},p))
   self.assertIn('status',execute_tool('suggest_today_workout',{'minutes':60},p))
   with self.assertRaisesRegex(ValueError,'Accept a training plan'):execute_tool('propose_training_adjustment',{'message':'Move my ride tomorrow'},p)

import copy,json
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from app.training import save_preferences,training_context,accept_plan,list_training,update_workout
from app.training_coach import DEFAULT,preview,create_draft,approve,save_brief,read_brief,save_setup,propose_setup,validate_brief
from app.active_training import review,set_status
from app.training_prescriptions import endurance,validate_workout
NOW=datetime(2026,10,12,7,tzinfo=timezone.utc);WEEK=date(2026,10,12);TZ='Asia/Jerusalem'
ANS={'sports':['cycling'],'priority':'endurance','availability':[{'weekday':i,'start_time':'18:00','minutes':240} for i in (0,2,4,6)],'experience':{'cycling':'experienced'},'equipment':['bike'],'weekly_minutes':{'cycling':600},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
CAL={'power_access':'outdoor','ftp_confirmed_on':'2026-10-11','hr_sensor':False}
READY={'latest':{'date':WEEK.isoformat(),'score':80,'status':'complete','groups':[]}}
class PrescriptionTests(unittest.TestCase):
 def test_numeric_ftp_laps_and_exact_total(self):
  w=endurance('threshold',60,{**DEFAULT,'ftp_watts':250,'calibration':CAL},today=WEEK)
  work=[s for s in w['steps'] if s['name'].startswith('Work')]
  self.assertEqual(len(work),2);self.assertEqual(work[0]['target']['lower'],225);self.assertEqual(work[0]['target']['upper'],237.5)
  self.assertEqual(sum(s['duration_seconds'] for s in w['steps']),3600)
 def test_indoor_access_is_not_outdoor_access(self):
  b={**DEFAULT,'ftp_watts':250,'calibration':{**CAL,'power_access':'indoor'}}
  self.assertEqual(endurance('endurance',60,b,today=WEEK)['steps'][0]['target']['type'],'perceived_effort')
  self.assertEqual(endurance('endurance',60,b,indoor=True,today=WEEK)['steps'][0]['target']['type'],'power')
 def test_confirmed_hr_fallback_and_stale_calibration(self):
  b={**DEFAULT,'calibration':{'power_access':'none','hr_sensor':True,'hr_confirmed_on':'2026-10-11','hr_zones':{'endurance':[120,140]}}}
  w=endurance('endurance',60,b,today=WEEK);self.assertEqual(w['steps'][1]['target']['type'],'heart_rate');self.assertEqual(w['steps'][1]['target']['lower'],120)
  self.assertEqual(endurance('endurance',60,{**DEFAULT,'ftp_watts':250,'calibration':{**CAL,'ftp_confirmed_on':'2025-01-01'}},today=WEEK)['steps'][1]['target']['type'],'perceived_effort')
 def test_varied_long_types_preserve_time_and_targets(self):
  for kind in ('long_endurance','long_tempo','climbing_endurance'):
   w=endurance(kind,240,{**DEFAULT,'ftp_watts':250,'calibration':CAL},today=WEEK)
   self.assertEqual(w['duration_minutes'],240);self.assertEqual(sum(s['duration_seconds'] for s in w['steps']),14400)
   self.assertTrue(all(s['target']['type']=='power' for s in w['steps']))
 def test_invalid_lap_totals_are_rejected(self):
  w=endurance('endurance',60,DEFAULT,today=WEEK);w['steps'][0]['duration_seconds']+=1
  with self.assertRaises(ValueError):validate_workout(w)

class CoachWorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite';migrate(self.path);save_preferences(copy.deepcopy(ANS),0,self.path,NOW)
 def tearDown(self):self.tmp.cleanup()
 def brief(self,**patches):return {**copy.deepcopy(DEFAULT),'duration_confirmed':True,'goal':'endurance','calibration':CAL,**patches}
 def activate(self,b=None):
  b=b or self.brief();p=preview(b,WEEK,TZ,self.path,NOW);self.assertEqual(p['status'],'ready',p['questions']);h=create_draft(b,WEEK,TZ,p['fingerprint'],self.path,NOW)
  with patch('app.training._context',return_value=training_context(self.path,NOW)):accept_plan(h['plans'][0]['id'],self.path)
  return h['plans'][0]['id']
 def review(self,now=NOW):
  with patch('app.readiness.readiness_history',return_value=READY):return review(self.path,TZ,now)
 def approve_change(self,b):
  b={**b,"duration_confirmed":True};old=self.review()["program"]["id"];p=preview(b,WEEK,TZ,self.path,NOW,old)
  return approve(b,WEEK,TZ,p["fingerprint"],self.path,NOW,old)
 def test_recovery_adapts_dose_preserving_goal_and_block(self):
  self.activate(self.brief(goal='ftp',ftp_watts=250))
  healthy=self.review();self.assertEqual(healthy['review']['current_block']['phase'],'Establish consistency')
  low={'latest':{'date':WEEK.isoformat(),'score':30,'status':'complete','groups':[{'name':'autonomic','hrv_z':-2,'rhr_z':2}]}}
  with patch('app.readiness.readiness_history',return_value=low):poor=review(self.path,TZ,NOW)
  self.assertEqual(poor['program']['brief']['goal'],'ftp')
  self.assertEqual(poor['review']['current_block'],healthy['review']['current_block'])
  self.assertTrue(any('HRV' in reason for reason in poor['review']['reasons']))
  self.assertTrue(any(change['action']=='Changed to easy recovery' for change in poor['review']['changes']))
  self.assertEqual(poor['review']['ftp_progress']['approved_watts'],250)
  self.assertIsNone(poor['review']['ftp_progress']['latest_measurement'].get('measured_change_watts'))
 def test_active_direction_and_targets_update_together(self):
  self.activate();self.approve_change(self.brief(goal='ftp',ftp_watts=250));r=self.review()
  self.assertEqual(r['program']['brief']['goal'],'ftp');self.assertEqual(r['program']['brief']['ftp_watts'],250)
  self.assertTrue(any(s['target']['type']=='power' for w in r['workouts'] for s in w['definition'].get('steps',[])))
 def test_surprise_event_rebuilds_neighbors_and_budget(self):
  self.activate();self.review();b=self.brief(fixed_events=[{'date':'2026-10-13','title':'Surprise ride','sport':'cycling','start_time':'08:00','duration_minutes':180,'effort':'hard','distance_km':90,'elevation_gain_meters':1500}]);self.approve_change(b);r=self.review()
  self.assertTrue(any(w['title']=='Surprise ride' for w in r['workouts']))
  self.assertTrue(all(w['definition']['duration_minutes']<=30 for w in r['workouts'] if w['scheduled_for'][:10] in ('2026-10-12','2026-10-14')))
  self.assertLessEqual(sum(w['definition']['duration_minutes'] for w in r['workouts']),600)
 def test_fixed_event_is_not_shortened_when_budget_is_impossible(self):
  self.activate();before=list_training(self.path);b=self.brief(duration_confirmed=True,fixed_events=[{'date':'2026-10-13','title':'Long event','start_time':'06:00','duration_minutes':660,'effort':'hard'}]);old=self.review()['program']['id'];p=preview(b,WEEK,TZ,self.path,NOW,old)
  self.assertEqual(p['status'],'needs_input')
  with self.assertRaises(ValueError):approve(b,WEEK,TZ,p['fingerprint'],self.path,NOW,old)
  self.assertEqual(before,list_training(self.path))
 def test_stable_event_id_survives_manual_date_edit(self):
  b=validate_brief(self.brief(fixed_events=[{'date':'2026-10-14','title':'Named ride'}]));event=b['fixed_events'][0];identifier=event['id'];event['date']='2026-10-15'
  self.assertEqual(validate_brief(b)['fixed_events'][0]['id'],identifier)
 def test_multiple_events_need_distinct_times(self):
  b=self.brief(fixed_events=[{'date':'2026-10-14','title':'Morning ride','start_time':'08:00','duration_minutes':60,'effort':'easy'},{'date':'2026-10-14','title':'Other ride','start_time':'08:30','duration_minutes':60,'effort':'easy'}]);p=preview(b,WEEK,TZ,self.path,NOW)
  self.assertIn('overlap',' '.join(p['questions']))
 def test_power_meter_is_asked_before_ftp_prescription(self):
  b=self.brief(goal='ftp',ftp_watts=250,calibration={});p=preview(b,WEEK,TZ,self.path,NOW)
  self.assertEqual(p['status'],'needs_input');self.assertTrue(any('power meter' in q for q in p['questions']))
 def test_cancel_and_pause_are_idempotent_and_persist(self):
  self.activate();set_status('paused',self.path);first=list_training(self.path);self.review();self.assertEqual(first,list_training(self.path));set_status('cancelled',self.path)
  self.assertTrue(all(w['completion_status']=='cancelled' for w in list_training(self.path)['workouts']))
 def test_setup_is_atomic_on_invalid_or_stale_input(self):
  before=training_context(self.path,NOW)
  with self.assertRaises(ValueError):save_setup({'priority':'strength'},self.brief(),99,0,self.path)
  self.assertEqual(training_context(self.path,NOW),before)
 def test_agent_setup_proposal_is_read_only_then_saved(self):
  p=propose_setup({'answers':{'priority':'strength'},'brief_changes':{'strength_role':'primary','strength_purpose':'strength_development'}},self.path)
  self.assertEqual(training_context(self.path,NOW)['answers']['priority'],'endurance')
  save_setup(p['answers'],p['brief'],p['expected_preference_revision'],p['expected_brief_revision'],self.path)
  self.assertEqual(training_context(self.path,NOW)['answers']['priority'],'strength')
 def test_long_slots_generate_more_than_two_hours(self):
  p=preview(self.brief(),WEEK,TZ,self.path,NOW)
  self.assertGreater(max(s['definition']['duration_minutes'] for s in p['sessions']),120)
 def test_unique_activity_completion_is_linked(self):
  self.activate();r=self.review();w=r['workouts'][0]
  from app.database import connect
  with connect(self.path) as c:c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('actual','garmin_export','cycling',?,?)",(w['scheduled_for'],w['definition']['duration_minutes']*60))
  later=NOW+timedelta(days=1);self.review(later);updated=next(a for a in list_training(self.path)['workouts'] if a['id']==w['id'])
  self.assertEqual(updated['completion_status'],'completed');self.assertEqual(updated['feedback']['activity_id'],'actual')
 def test_primary_secondary_strength_are_different_and_bars_supported(self):
  a={**ANS,'sports':['cycling','strength'],'experience':{'cycling':'experienced','strength':'regular'},'equipment':['bike','pull_up_bar','dip_bars'],'weekly_minutes':{'cycling':240,'strength':120},'availability':[{'weekday':i,'start_time':'18:00','minutes':60} for i in range(7)]};save_preferences(a,1,self.path,NOW)
  outputs=[]
  for role,purpose in [('primary','strength_development'),('secondary','cycling_support')]:
   p=preview(self.brief(goal='general',strength_role=role,strength_purpose=purpose,strength_capacity={'pull_up_reps':5,'dip_reps':8}),WEEK,TZ,self.path,NOW)
   self.assertEqual(p['status'],'ready',p['questions']);outputs.append([(s['sport'],s['definition'].get('exercises')) for s in p['sessions']])
  self.assertNotEqual(outputs[0],outputs[1]);self.assertTrue(any(e['equipment']=='pull_up_bar' for sport,ex in outputs[0] if ex for e in ex))
 def test_actual_strength_sets_are_atomic_and_portable(self):
  a={**ANS,'sports':['strength'],'priority':'strength','experience':{'strength':'regular'},'equipment':['bodyweight','dumbbells'],'weekly_minutes':{'strength':120},'availability':[{'weekday':0,'start_time':'18:00','minutes':60},{'weekday':3,'start_time':'18:00','minutes':60}]};save_preferences(a,1,self.path,NOW)
  self.activate(self.brief(goal='general',strength_role='primary',strength_purpose='strength_development'))
  w=list_training(self.path)['workouts'][0];e=w['definition']['exercises'][0]
  actual={'exercise_id':e['id'],'set_index':1,'load_kg':10,'repetitions':6,'repetitions_in_reserve':3}
  h=update_workout(w['id'],w['revision'],{'completion_status':'completed','effort':6,'strength_sets':[actual]},self.path)
  saved=next(row for row in h['workouts'] if row['id']==w['id']);self.assertEqual(saved['strength_performance'][0]['load_kg'],10)
  from app.exports import create_backup,restore_backup
  backup=Path(self.tmp.name)/'backup.zip';restored=Path(self.tmp.name)/'restore.sqlite';create_backup(backup,self.path);restore_backup(backup,restored)
  self.assertEqual(list_training(restored),h)
  with self.assertRaises(ValueError):update_workout(w['id'],saved['revision'],{'notes':'Should roll back','strength_sets':[actual,{**actual,'exercise_id':'unknown'}]},self.path)
  self.assertEqual(list_training(self.path),h)
 def test_ambiguous_completion_requires_confirmation(self):
  self.activate();w=self.review()['workouts'][0]
  from app.database import connect
  with connect(self.path) as c:
   for identifier in ('one','two'):c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,?)",(identifier,w['scheduled_for'],w['definition']['duration_minutes']*60))
  r=self.review(NOW+timedelta(days=1));self.assertTrue(any('Several recordings' in text for text in r['review']['warnings']))
  self.assertEqual(next(row for row in list_training(self.path)['workouts'] if row['id']==w['id'])['completion_status'],'planned')
 def test_completion_matches_utc_to_local_schedule(self):
  self.activate();w=self.review()['workouts'][0];stamp=datetime.fromisoformat(w['scheduled_for']).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
  from app.database import connect
  with connect(self.path) as c:c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('utc','garmin_export','cycling',?,?)",(stamp,w['definition']['duration_minutes']*60))
  self.review(NOW+timedelta(days=1));self.assertEqual(next(row for row in list_training(self.path)['workouts'] if row['id']==w['id'])['completion_status'],'completed')

 def test_program_continues_after_its_target_event(self):
  self.activate(self.brief(goal='race',target_date='2026-10-12',event_name='Synthetic race',fixed_events=[{'date':'2026-10-12','title':'Race','start_time':'18:00','duration_minutes':180,'is_race':True,'effort':'hard'}]))
  r=self.review(NOW+timedelta(days=7));self.assertEqual(r['program']['status'],'active');self.assertTrue(r['workouts'])
  self.assertTrue(all(w['definition']['duration_minutes']<=30 for w in r['workouts']))

class CalibrationParsingTests(unittest.TestCase):
 def test_mentioning_ftp_does_not_refresh_a_stale_test(self):
  from app.training_coach import parse_request
  b={**DEFAULT,'ftp_watts':250,'calibration':{**CAL,'ftp_confirmed_on':'2025-01-01'}}
  parsed,_=parse_request('My FTP is 250 W',b,WEEK,WEEK)
  self.assertEqual(parsed['calibration']['ftp_confirmed_on'],'2025-01-01')
  changed,_=parse_request('My FTP is 260 W',b,WEEK,WEEK)
  self.assertIsNone(changed['calibration']['ftp_confirmed_on'])
  confirmed,_=parse_request('My FTP is 260 W measured on 2026-10-11',b,WEEK,WEEK)
  self.assertEqual(confirmed['calibration']['ftp_confirmed_on'],'2026-10-11')
