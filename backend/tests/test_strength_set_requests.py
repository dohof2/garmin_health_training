import copy,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.training_adjustments import propose,save
from app.strength_adjustments import apply_policy

NOW=datetime(2026,10,30,10,tzinfo=timezone.utc)
REQUEST='in the training plan the strength feel abut too easy I think we can do 2 sets from each strating from next workout'
class StrengthSetRequestTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  self.state={'timezone':'Asia/Jerusalem','starts_on':'2026-10-19','ends_on':'2027-02-07','blocks':[]}
  self.program={'plan_id':'root','revision':1,'status':'active','state':self.state}
  days=[{'weekday':day,'mode':'training','total_limit_minutes':60,'activities':[{'slot_id':f's{day}','sport':'strength','max_minutes':60}]} for day in range(7)]
  self.context={'answers':{'pain_or_illness':False,'week_schedule':days},'blockers':[]}
  self.definition={'sport':'strength','title':'Support strength','duration_minutes':30,'template_id':'strength_foundation','exercises':[{'id':name,'name':name,'sets':1,'repetitions':10,'rest_seconds':90,'load':'Bodyweight'} for name in ['air_squat','hip_raise','dead_bug','pull_up','dip']]}
  with connect(self.path) as c:
   c.execute("INSERT INTO training_plans(id,name,status) VALUES('root','Plan','active')")
   c.execute("INSERT INTO active_training_program(id,plan_id,status,state_json) VALUES(1,'root','active',?)",(json.dumps(self.state),))
   for identifier,day,status in [('done','2026-10-29','completed'),('next','2026-11-03','planned'),('later','2026-11-05','planned')]:
    c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,completion_status) VALUES(?,'root','strength','Support strength',?,?,?)",(identifier,day+'T12:00:00+02:00',json.dumps(self.definition),status))
   c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('recorded','garmin_connect','strength_training','2026-10-29T18:58:00Z',739.062)")
   c.execute("INSERT INTO training_feedback(workout_id,pain_or_illness,activity_id) VALUES('done',0,'recorded')")
  self.addCleanup(patch.stopall)
  patch('app.active_training.read_active',return_value={'program':self.program}).start()
  patch('app.strength_adjustments._context',return_value=self.context).start()
  patch('app.strength_adjustments._preferences',return_value={'answers':{'weekly_minutes':{'strength':120}}}).start()
 def test_verbatim_request_prepares_all_exercises_without_new_plan(self):
  result=propose(REQUEST,self.path,NOW)
  self.assertEqual(result['status'],'proposal');self.assertEqual(len(result['adjustments']),2)
  for adjustment in result['adjustments']:
   d=adjustment['changes']['definition'];self.assertEqual(d['duration_minutes'],25)
   for exercise,old in zip(d['exercises'],self.definition['exercises']):
    self.assertEqual(exercise['sets'],2);self.assertEqual({k:v for k,v in exercise.items() if k!='sets'},{k:v for k,v in old.items() if k!='sets'})
  with connect(self.path) as c:self.assertEqual(json.loads(c.execute("SELECT definition_json FROM planned_workouts WHERE id='next'").fetchone()[0])['exercises'][0]['sets'],1)
 def test_save_is_reviewed_and_persists_continuation_policy(self):
  proposal=propose(REQUEST,self.path,NOW)
  result=save({'message':REQUEST,'fingerprint':proposal['fingerprint']},self.path,NOW)
  self.assertEqual(result['count'],2)
  with connect(self.path) as c:
   state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0]);policy=state['strength_set_policy']
   self.assertEqual(policy['weekly_allowance_minutes'],50)
   completed=json.loads(c.execute("SELECT definition_json FROM planned_workouts WHERE id='done'").fetchone()[0]);self.assertEqual(completed['exercises'][0]['sets'],1)
  continued=apply_policy(self.definition,policy,'Build specificity');self.assertEqual(continued['duration_minutes'],25);self.assertEqual(continued['exercises'][0]['sets'],2)
  recovery=apply_policy(self.definition,policy,'Recovery / review');self.assertEqual(recovery['exercises'][0]['sets'],1)
 def test_selected_session_set_edit_does_not_create_program_progression(self):
  proposal=propose(REQUEST,self.path,NOW,selected_id='next')
  self.assertEqual([row['workout_id'] for row in proposal['adjustments']],['next'])
  self.assertNotIn('strength_set_policy',proposal['adjustments'][0]['changes']['definition'])
 def test_continuation_fill_passes_preferences_by_name_and_uses_duration_limit(self):
  from app.active_training import _fill
  from app.training_coach import DEFAULT
  proposal=propose(REQUEST,self.path,NOW)
  policy=proposal['adjustments'][0]['changes']['definition']['strength_set_policy']
  state={**self.state,'starts_on':'2026-10-26','ends_on':'2026-11-01','brief':copy.deepcopy(DEFAULT),'strength_set_policy':policy,'blocks':[{'starts_on':'2026-10-26','phase':'Build specificity'}]}
  context={**self.context,'ready':True,'missing':[],'stale':[]}
  def preview(c,brief,monday,tz,now,replace_plan_id,**kwargs):
   self.assertIsNone(replace_plan_id)
   self.assertEqual(kwargs['candidate_answers']['weekly_caps']['strength']['range_min_minutes'],50)
   return {'status':'ready','sessions':[{'sport':'strength','scheduled_for':'2026-10-31T12:00:00+02:00','definition':copy.deepcopy(self.definition)}]}
  with connect(self.path) as c,patch('app.active_training._context',return_value=context),patch('app.training_coach._preview',side_effect=preview):
   _fill(c,'root',state,NOW.date(),NOW)
   row=c.execute("SELECT definition_json FROM planned_workouts WHERE substr(scheduled_for,1,10)='2026-10-31'").fetchone()
   self.assertIsNotNone(row);definition=json.loads(row[0]);self.assertEqual(definition['exercises'][0]['sets'],2);self.assertEqual(definition['duration_minutes'],25)
 def test_explicit_cap_and_availability_still_apply(self):
  with patch('app.strength_adjustments._preferences',return_value={'answers':{'weekly_minutes':{'strength':40}}}):self.assertIn('explicit 40-minute cap',propose(REQUEST,self.path,NOW)['message'])
  for day in self.context['answers']['week_schedule']:day['total_limit_minutes']=15
  self.assertIn('availability',propose(REQUEST,self.path,NOW)['message'])
 def test_no_recorded_baseline_or_pain_does_not_invent_progression(self):
  self.context['answers']['pain_or_illness']=True
  self.assertIn('pain or illness',propose(REQUEST,self.path,NOW)['message'])
  self.context['answers']['pain_or_illness']=False
  with connect(self.path) as c:c.execute('DELETE FROM training_feedback')
  self.assertIn('completed strength session',propose(REQUEST,self.path,NOW)['message'])
