import copy
import json
import tempfile
import unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from app.database import migrate,connect
from app.training import save_preferences,accept_plan,list_training,update_workout,training_context
from app.training_coach import DEFAULT,preview,create_draft
from app.active_training import review,read_active,set_status,reschedule,request_change,suggest_today,capability

NOW=datetime(2026,10,12,7,tzinfo=timezone.utc)
WEEK=date(2026,10,12)
ANSWERS={'sports':['cycling'],'priority':'endurance','availability':[{'weekday':i,'start_time':'18:00','minutes':120} for i in (0,2,4,6)],'experience':{'cycling':'regular'},'equipment':['bike'],'weekly_minutes':{'cycling':360},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
READY={'latest':{'date':'2026-10-12','score':80,'status':'complete','groups':[]}}
class ActiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite';migrate(self.path)
  save_preferences(copy.deepcopy(ANSWERS),0,self.path,NOW)
  self.brief={**copy.deepcopy(DEFAULT),'goal':'endurance','horizon_weeks':4,'duration_confirmed':True}
  p=preview(self.brief,WEEK,'Asia/Jerusalem',self.path,NOW)
  h=create_draft(self.brief,WEEK,'Asia/Jerusalem',p['fingerprint'],self.path,NOW)
  self.identifier=h['plans'][0]['id']
  with patch('app.training._context',return_value=training_context(self.path,NOW)):accept_plan(self.identifier,self.path)
 def tearDown(self):self.tmp.cleanup()
 def long_session_fixture(self):
  # Isolate move/approval behavior from the separately tested history-based
  # volume allocator, which correctly limits this no-history fixture.
  from app.training_prescriptions import endurance
  with connect(self.path) as c:
   row=c.execute('SELECT * FROM planned_workouts ORDER BY scheduled_for LIMIT 1').fetchone()
   old=json.loads(row['definition_json']);definition=endurance('long_endurance',90,self.brief,today=NOW.date())
   definition.update({k:v for k,v in old.items() if k.startswith('schedule_') or k in ('scheduled_date','time_unspecified')})
   c.execute('UPDATE planned_workouts SET definition_json=?,title=? WHERE id=?',(json.dumps(definition),definition['title'],row['id']))
 def run_review(self,now=NOW,score=80):
  with patch('app.readiness.readiness_history',return_value={'latest':{**READY['latest'],'score':score}}):return review(self.path,'Asia/Jerusalem',now)
 def test_persistent_goal_blocks_and_next_seven_days(self):
  result=self.run_review();self.assertEqual(result['program']['id'],self.identifier);self.assertEqual(len(result['program']['blocks']),4)
  self.assertTrue(result['workouts']);self.assertTrue(all(w['completion_status']=='planned' for w in result['workouts']))
  self.assertEqual(read_active({},self.path)['program']['plan_id'],self.identifier)
 def test_repeated_open_no_duplicate_workouts(self):
  first=self.run_review();second=self.run_review();self.assertEqual([(w['id'],w['revision']) for w in first['workouts']],[(w['id'],w['revision']) for w in second['workouts']])
 def test_low_readiness_alone_does_not_force_automatic_recovery(self):
  first=self.run_review(score=20);self.assertFalse(any(ch['action']=='Changed to easy recovery' for ch in first['review']['changes']))
  second=self.run_review(score=20)
  self.assertEqual([(w['id'],w['revision']) for w in first['workouts']],[(w['id'],w['revision']) for w in second['workouts']])
 def test_pause_stops_auto_changes(self):
  set_status('paused',self.path);r=self.run_review(score=20);self.assertEqual(r['program']['status'],'paused');self.assertIsNone(r['review'])
 def test_feedback_note_changes_recovery_review(self):
  r=self.run_review();w=r['workouts'][0];update_workout(w['id'],w['revision'],{'notes':'That was too hard','completion_status':'completed'},self.path)
  r=self.run_review();self.assertTrue(any('notes' in reason for reason in r['review']['reasons']))
 def test_next_week_is_filled_and_original_goal_retained(self):
  self.run_review();r=self.run_review(NOW+timedelta(days=7));self.assertTrue(r['workouts']);self.assertEqual(r['program']['brief']['goal'],'endurance')
  r2=self.run_review(NOW+timedelta(days=7));self.assertEqual(len(r['workouts']),len(r2['workouts']))
 def test_expired_program_does_not_generate(self):
  r=self.run_review(NOW+timedelta(days=29));self.assertEqual(r['program']['status'],'completed');self.assertEqual(r['workouts'],[])
 def test_move_requested_long_ride_to_today_and_stale_edit(self):
  self.long_session_fixture();w=list_training(self.path)['workouts'][0]
  result=request_change('Move my long ride to today at 18:00','Asia/Jerusalem',self.path,NOW)
  self.assertIn('2026-10-12 18:00',result['message'])
  with self.assertRaisesRegex(ValueError,'changed'):reschedule(w['id'],'2026-10-13T18:00:00+03:00',w['revision'],self.path,NOW)
 def test_assistant_proposal_does_not_write_until_saved(self):
  self.long_session_fixture()
  before=list_training(self.path)
  p=request_change('Move my long ride to tomorrow at 18:00','Asia/Jerusalem',self.path,NOW,apply=False)
  self.assertEqual(p['status'],'proposal');self.assertEqual(before,list_training(self.path))
 def test_replacing_active_plan_does_not_cancel_new_sessions(self):
  b={**self.brief,'goal':'general'};week=WEEK+timedelta(days=7)
  p=preview(b,week,'Asia/Jerusalem',self.path,NOW);h=create_draft(b,week,'Asia/Jerusalem',p['fingerprint'],self.path,NOW)
  new=h['plans'][0]['id']
  with patch('app.training._context',return_value=training_context(self.path,NOW)):accept_plan(new,self.path)
  h=list_training(self.path)
  self.assertTrue(all(w['completion_status']=='planned' for w in h['workouts'] if w['training_plan_id']==new))
  self.assertTrue(all(w['completion_status']=='cancelled' for w in h['workouts'] if w['training_plan_id']==self.identifier))
 def test_free_text_feedback_persists_and_informs_review(self):
  w=list_training(self.path)['workouts'][0]
  later=NOW+timedelta(days=1)
  p=request_change('The ride was too hard','Asia/Jerusalem',self.path,later)
  self.assertEqual(p['kind'],'feedback')
  r=self.run_review(later)
  self.assertTrue(any('notes' in reason for reason in r['review']['reasons']))
 def test_available_minutes_use_active_session_without_writes(self):
  before=list_training(self.path)
  with patch('app.readiness.readiness_history',return_value=READY):r=suggest_today({'minutes':60,'timezone':'Asia/Jerusalem','mode':'plan'},self.path,NOW)
  self.assertEqual(r['session']['duration_minutes'],60);self.assertEqual(sum(s['duration_seconds'] for s in r['session']['steps']),3600)
  self.assertEqual(before,list_training(self.path));self.assertEqual(r['active_plan_id'],self.identifier)
 def test_available_minutes_without_plan_and_low_readiness(self):
  set_status('completed',self.path)
  with patch('app.readiness.readiness_history',return_value={'latest':{**READY['latest'],'score':45}}):r=suggest_today({'minutes':60,'timezone':'Asia/Jerusalem','sport':'cycling'},self.path,NOW)
  self.assertIsNone(r['active_plan_id']);self.assertLessEqual(r['session']['duration_minutes'],60)
 def test_training_mix_uses_labels_not_effect_scores(self):
  with connect(self.path) as c:
   for i,label in enumerate(('AEROBIC_BASE','AEROBIC_BASE','SPRINT')):
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,raw_json) VALUES(?,'garmin_export','cycling',?,3600,?)",('ride-'+str(i),(NOW-timedelta(days=i+1)).isoformat(),json.dumps({'trainingEffectLabel':label})))
  mix=capability(self.path,WEEK,'Asia/Jerusalem')['training_mix']
  self.assertEqual(mix['gaps'],['tempo']);self.assertEqual(mix['coverage'],'usable')
  set_status('completed',self.path)
  with patch('app.readiness.readiness_history',return_value=READY):r=suggest_today({'minutes':60,'timezone':'Asia/Jerusalem','sport':'cycling'},self.path,NOW)
  self.assertIn('tempo',r['session']['title'].lower());self.assertEqual(sum(s['duration_seconds'] for s in r['session']['steps']),3600)
 def test_unclassified_history_is_not_a_training_gap(self):
  self.assertEqual(capability(self.path,WEEK,'Asia/Jerusalem')['training_mix']['gaps'],[])
 def test_low_readiness_alone_keeps_conservative_independent_option(self):
  with patch('app.readiness.readiness_history',return_value={'latest':{**READY['latest'],'score':20}}):r=suggest_today({'minutes':60,'timezone':'Asia/Jerusalem','sport':'cycling'},self.path,NOW)
  self.assertEqual(r['session']['sport'],'cycling');self.assertLessEqual(r['session']['duration_minutes'],60);self.assertEqual(r['readiness']['score'],20)
 def test_moderate_recovery_signal_recommends_gentle_ride(self):
  with patch('app.readiness.readiness_history',return_value={'latest':{**READY['latest'],'score':45}}):r=suggest_today({'minutes':60,'timezone':'Asia/Jerusalem','sport':'cycling'},self.path,NOW)
  self.assertEqual(r['session']['sport'],'cycling');self.assertLessEqual(r['session']['duration_minutes'],60);self.assertEqual(r['readiness']['score'],45)
 def test_planned_rest_day_stays_rest_with_optional_easy_spin(self):
  with patch('app.readiness.readiness_history',return_value=READY):r=suggest_today({'minutes':60,'timezone':'Asia/Jerusalem','sport':'cycling','mode':'plan'},self.path,NOW+timedelta(days=1))
  self.assertEqual(r['session']['sport'],'rest');self.assertFalse(r['saved'])
 def test_missing_readiness_is_explicit(self):
  r=self.run_review(score=None);self.assertTrue(any('unavailable' in text for text in r['review']['warnings']))
