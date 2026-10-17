import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from app.database import connect,migrate
from app.training_questionnaire import turn,read
from app.training_coach import approve,save_setup,read_brief
from app.training import list_training,training_context

NOW=datetime(2026,10,16,10,tzinfo=timezone.utc)
OPENING=('I want a 16 weeks FTP/endurance plan with occasional sprints. Cycling Sunday Monday Wednesday Friday, strength Tuesday Thursday. Saturday mostly off. Weekdays 60–90 minutes and Friday up to 5 hours. I have a bike, bodyweight, dip and pull-up bars. Beginner strength. I have an HR sensor and power indoors and outdoors. No pain.')

class QuestionnaireTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'db';migrate(self.path)
  with connect(self.path) as c:
   for index in range(16):
    day=NOW-timedelta(days=index*3)
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,7200)",(str(index),day.isoformat()))
   c.execute("INSERT INTO garmin_sync_payloads(data_type,calendar_date,payload_json) VALUES('supplementary_metrics','2026-10-16',?)",(json.dumps({'endpoints':{'get_cycling_ftp':{'functionalThresholdPower':225,'calendarDate':'2026-06-11','sport':'CYCLING','isStale':False}}}),))
 def say(self,text,history=None):return turn(text,history,'Asia/Jerusalem',self.path,NOW)
 def test_full_conversation_retains_user_facts_to_review_and_explicit_activation(self):
  initial=self.say(OPENING)
  self.assertEqual(initial['brief']['horizon_weeks'],16)
  self.assertEqual(initial['questionnaire']['partial']['sport_days'],{'cycling':[0,2,4,6],'strength':[1,3]})
  self.assertEqual(initial['questionnaire']['partial']['weekday_minutes_range'],[60,90])
  self.assertTrue(all(slot['start_time'] is None for slot in initial['candidate_answers']['availability']));self.assertNotIn('weekly_minutes',initial['candidate_answers'])
  self.assertEqual(initial['candidate_answers']['experience'],{'strength':'new','cycling':'experienced'})
  self.assertIn('225 W',initial['questions'][0])
  self.say('Use 60 minutes')
  time=self.say('All sessions at 08:00')
  self.assertEqual(time['candidate_answers']['availability'][0]['start_time'],'08:00')
  self.assertIn('225 W',time['questions'][0])
  authorized=self.say('yes')
  self.assertEqual(authorized['brief']['ftp_authorization']['authorized_on'],'2026-10-16')
  self.assertEqual(authorized['brief']['calibration']['ftp_confirmed_on'],'2026-06-11')
  self.say('Weekly budget cycling 480 minutes and strength 120 minutes. No restrictions. Secondary strength for cycling support. I can do 4 pull-ups and 6 dips.')
  ready=self.say('Please review my plan')
  self.assertEqual(ready['status'],'ready',ready['questions']);self.assertEqual(len(ready['roadmap']),16);self.assertTrue(ready['sessions'])
  self.assertEqual(list_training(self.path)['plans'],[])
  # Save setup remains separate from approval, and a fresh canonical read retains all facts.
  saved=save_setup(ready['candidate_answers'],ready['brief'],0,0,self.path)
  self.assertFalse(saved['schedule_activated']);self.assertEqual(list_training(self.path)['plans'],[])
  fresh=self.say('Is it active?')
  self.assertEqual(fresh['status'],'ready',fresh['questions'])
  for session in fresh['sessions']:
   weekday=date.fromisoformat(session['scheduled_for'][:10]).weekday()
   self.assertIn(weekday,fresh['brief']['sport_days'][session['sport']])
   for lap in session['definition'].get('steps',[]):self.assertNotEqual(lap.get('target',{}).get('type'),'power')
  history=approve(fresh['brief'],date.fromisoformat(fresh['week_start']),'Asia/Jerusalem',fresh['fingerprint'],self.path,NOW,candidate_answers=fresh['candidate_answers'])
  self.assertEqual(len(history['plans']),1);self.assertEqual(history['plans'][0]['status'],'active')
 def test_semantic_structured_paraphrase_and_conflict_are_retained(self):
  message='I am a novice lifter and free to pedal on Mondays and Wednesdays.'
  facts=[{'path':'answers.experience','value':{'strength':'new'},'quote':'I am a novice lifter'}, {'path':'partial.sport_days','value':{'cycling':[0,2]},'quote':'free to pedal on Mondays and Wednesdays'}]
  result=turn(message,[], 'UTC',self.path,NOW,structured_facts=facts)
  self.assertEqual(result['candidate_answers']['experience']['strength'],'new')
  self.assertEqual(result['questionnaire']['partial']['sport_days'],{'cycling':[0,2]})
  revised=turn('I now lift regularly',[],'UTC',self.path,NOW,structured_facts=[{'path':'answers.experience','value':{'strength':'regular'},'quote':'I now lift regularly'}])
  self.assertEqual(revised['candidate_answers']['experience']['strength'],'regular')
  self.assertTrue(any(change['field']=='experience' for change in revised['questionnaire']['changes']))
 def test_unquoted_structured_claims_do_not_enter_candidate(self):
  result=turn('Hello',[],'UTC',self.path,NOW,structured_facts=[{'path':'answers.weekly_minutes','value':{'cycling':900},'quote':'I can ride 900 minutes'}])
  self.assertNotIn('weekly_minutes',result['candidate_answers'])
 def test_authorization_never_creates_measurement_date(self):
  result=turn('Use my stored FTP',[],'UTC',self.path,NOW,structured_facts=[{'path':'brief.calibration','value':{'ftp_confirmed_on':'2026-10-16'},'quote':'Use my stored FTP'}])
  self.assertNotEqual(result['brief']['calibration']['ftp_confirmed_on'],'2026-10-16')
 def test_beginner_zero_capacity_uses_supported_alternatives_and_can_activate(self):
  from app.training import save_preferences
  from app.training_coach import DEFAULT,preview
  from app.training_prescriptions import validate_workout
  answers={'sports':['strength'],'priority':'strength','availability':[{'weekday':0,'start_time':'08:00','minutes':60},{'weekday':3,'start_time':'08:00','minutes':60}],'experience':{'strength':'new'},'equipment':['bodyweight','dip_bars','pull_up_bar'],'weekly_minutes':{'strength':120},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
  brief={**DEFAULT,'goal':'general','duration_confirmed':True,'strength_role':'secondary','strength_purpose':'cycling_support','strength_capacity':{'pull_up_reps':0,'dip_reps':0}}
  result=preview(brief,date(2026,10,19),'UTC',self.path,NOW,candidate_answers=answers)
  self.assertEqual(result['status'],'ready',result['questions'])
  self.assertTrue(result['sessions'])
  definition=result['sessions'][0]['definition']
  self.assertGreaterEqual(len(definition['exercises']),2)
  self.assertFalse(any(exercise['equipment'] in ('pull_up_bar','dip_bars') for exercise in definition['exercises']))
  self.assertTrue(any(exercise['id']=='wall_pushup' for exercise in definition['exercises']))
  changed=preview(brief,date(2026,10,19),'UTC',self.path,NOW,candidate_answers=answers,session_changes=[{'index':0,'duration_minutes':45,'exercises':[{'id':definition['exercises'][0]['id'],'sets':2,'repetitions':8,'rest_seconds':60,'load_target_kg':0}]}])
  self.assertEqual(changed['sessions'][0]['definition']['duration_minutes'],45)
  result=approve(brief,date(2026,10,19),'UTC',changed['fingerprint'],self.path,NOW+timedelta(seconds=10),candidate_answers=answers,session_changes=[{'index':0,'duration_minutes':45,'exercises':[{'id':definition['exercises'][0]['id'],'sets':2,'repetitions':8,'rest_seconds':60,'load_target_kg':0}]}])
  self.assertEqual(result['plans'][0]['status'],'active')
 def test_running_duration_edit_regenerates_exact_laps(self):
  from app.training_coach import DEFAULT,preview
  answers={'sports':['running'],'priority':'endurance','availability':[{'weekday':0,'start_time':'08:00','minutes':60}],'experience':{'running':'regular'},'equipment':[],'weekly_minutes':{'running':60},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
  brief={**DEFAULT,'goal':'endurance','goal_sport':'running','duration_confirmed':True}
  result=preview(brief,date(2026,10,19),'UTC',self.path,NOW,candidate_answers=answers,session_changes=[{'index':0,'duration_minutes':45}])
  definition=result['sessions'][0]['definition']
  self.assertEqual(definition['sport'],'running');self.assertEqual(sum(lap['duration_seconds'] for lap in definition['steps']),2700)
 def test_exact_opening_then_tomorrow_preserves_days_and_start_through_activation_review(self):
  from app.training_questionnaire import candidate_snapshot
  from app.active_training import review
  first=self.say(OPENING)
  following=self.say('you can start tomorrow')
  self.assertEqual(following['week_start'],'2026-10-17')
  self.assertEqual(following['brief']['program_start'],'2026-10-17')
  self.assertIn('2026-10-17',following['questions'][0])
  self.assertEqual(following['questionnaire']['partial']['sport_days'],first['questionnaire']['partial']['sport_days'])
  self.assertNotIn('start_time',following['questionnaire']['partial'])
  self.assertEqual(len(following['questions']),1)
  self.say('Use 60 minutes');clock=self.say('All sessions at 08:00');self.say('yes')
  self.say('Weekly budget cycling 480 minutes and strength 120 minutes. No restrictions. Secondary strength for cycling support. I can do 0 pull-ups and 0 dips.')
  ready=self.say('Show the full preview')
  self.assertEqual(ready['status'],'ready',ready['questions']);self.assertEqual(ready['roadmap'][0]['starts_on'],'2026-10-17')
  self.assertEqual(candidate_snapshot(self.path,'Asia/Jerusalem',NOW)['week_start'],'2026-10-17')
  self.assertEqual(candidate_snapshot(self.path,'Asia/Jerusalem',NOW)['next_question'],ready['questions'][0] if ready['questions'] else None)
  dates=[row['scheduled_for'][:10] for row in ready['sessions']]
  self.assertNotIn('2026-10-17',dates);self.assertIn('2026-10-18',dates);self.assertIn('2026-10-23',dates)
  self.assertTrue(all('2026-10-17'<=day<='2026-10-23' for day in dates))
  saved=save_setup(ready['candidate_answers'],ready['brief'],0,0,self.path)
  self.assertEqual(saved['brief']['program_start'],'2026-10-17')
  from app.training_coach import preview
  fresh=preview(saved['brief'],date(2026,10,17),'Asia/Jerusalem',self.path,NOW)
  approved=approve(fresh['brief'],date(2026,10,17),'Asia/Jerusalem',fresh['fingerprint'],self.path,NOW)
  self.assertEqual(approved['plans'][0]['starts_on'],'2026-10-17')
  result=review(self.path,'Asia/Jerusalem',NOW+timedelta(days=9))
  self.assertEqual(result['program']['starts_on'],'2026-10-17');self.assertEqual(result['program']['ends_on'],'2027-02-05')
  self.assertTrue(result['workouts'])
  for row in result['workouts']:
   self.assertNotEqual(date.fromisoformat(row['scheduled_for'][:10]).weekday(),5)
   self.assertGreaterEqual(row['scheduled_for'][:10],'2026-10-25')
 def test_tomorrow_uses_local_date_once_and_never_reanchors_on_reload(self):
  from app.training_questionnaire import candidate_snapshot
  local_now=datetime(2026,10,16,22,30,tzinfo=timezone.utc)
  result=turn('Build endurance for 16 weeks. Start tomorrow',[],'Asia/Jerusalem',self.path,local_now)
  self.assertEqual(result['week_start'],'2026-10-18')
  later=candidate_snapshot(self.path,'Asia/Jerusalem',local_now+timedelta(days=1))
  self.assertEqual(later['week_start'],'2026-10-18')
 def test_named_start_dates_are_supported_and_retained(self):
  from app.training_questionnaire import candidate_snapshot
  self.say(OPENING)
  for text in ('start in oct 19','Start on October 19','begin October 19th, 2026','starting 19 October 2026','start Oct. 19, 2026'):
   with self.subTest(text=text):
    result=self.say(text)
    self.assertEqual(result['brief']['program_start'],'2026-10-19')
    self.assertEqual(candidate_snapshot(self.path,'Asia/Jerusalem',NOW)['week_start'],'2026-10-19')
 def test_strength_preview_without_equipment_or_weekly_budget_returns_questions(self):
  from app.training_coach import preview,DEFAULT
  result=preview({**DEFAULT,'goal':'ftp','horizon_weeks':16,'duration_confirmed':True},date(2026,10,19),'UTC',self.path,NOW,candidate_answers={'sports':['cycling','strength']})
  self.assertEqual(result['status'],'needs_input')
  self.assertTrue(result['questions'])
 def test_user_range_and_friday_exception_are_independent(self):
  message=('Make me a 16 week training plan mostly for FTP and endurance improvement.\n'
   'ride days ar e all days apart from tuesday, thursday and saturday (in these day strength is possible)\n'
   'the long ride (up to 5 hours) can be on friday\n'
   'during the week ride should be 60-90 minutes. I have a power meter and indoor trainer.')
  result=self.say(message)
  partial=result['questionnaire']['partial']
  self.assertEqual(partial['sport_days']['cycling'],[0,2,4,6])
  self.assertEqual(partial['sport_days']['strength'],[1,3,5])
  self.assertEqual(partial['friday_minutes'],300)
  self.assertEqual(partial['weekday_minutes_range'],[60,90])
  self.assertNotIn('session length',result['questions'][0])
  result=self.say('All sessions at 08:00')
  slots={slot['weekday']:slot['minutes'] for slot in result['candidate_answers']['availability']}
  self.assertEqual(slots[4],300)
  self.assertEqual(slots[0],90)
  result=self.say('Use 60 minutes')
  slots={slot['weekday']:slot['minutes'] for slot in result['candidate_answers']['availability']}
  self.assertEqual(slots[4],300);self.assertEqual(slots[0],60)
 def test_named_dates_validate_calendar_and_do_not_roll_past_dates_forward(self):
  from app.training_questionnaire import _start_date
  self.assertEqual(_start_date('start January 2, 2027',date(2026,10,16)),date(2027,1,2))
  self.assertEqual(_start_date('start on February 29th 2028',date(2026,10,16)),date(2028,2,29))
  self.say(OPENING)
  invalid=self.say('start February 30')
  self.assertTrue(any('invalid' in q.lower() for q in read(self.path)['state']['clarifications']))
  past=self.say('start October 1')
  self.assertTrue(any('past' in q.lower() for q in read(self.path)['state']['clarifications']))
 def test_only_user_messages_supply_durable_facts(self):
  self.say('Build endurance for 16 weeks',[{'role':'assistant','content':'Weekly budget cycling 900 minutes. I have no restrictions.'}])
  state=read(self.path)['state']
  self.assertNotIn('weekly_minutes',state['answers']);self.assertNotIn('restrictions_notes',state['answers'])
 def test_no_history_does_not_imply_beginner(self):
  with connect(self.path) as c:c.execute('DELETE FROM activities')
  result=self.say(OPENING)
  self.assertNotIn('cycling',result['candidate_answers']['experience'])
 def test_natural_replies_advance_without_clock_or_repeated_summaries(self):
  from app.training_coach import assistant_answer
  first=self.say(OPENING)
  self.assertEqual(assistant_answer(first),first['questions'][0])
  self.assertEqual(first['questionnaire']['awaiting'],'ftp_authorization')
  self.say('yes')
  role=self.say('Mainly cycling and core support')
  self.assertEqual(role['questionnaire']['awaiting'],'pull_up_reps',role['questions'])
  pull=self.say('about 5')
  self.assertEqual(pull['brief']['strength_capacity']['pull_up_reps'],5)
  self.assertTrue(pull['questionnaire']['provenance']['pull_up_reps']['approximate'])
  self.assertEqual(pull['questionnaire']['awaiting'],'dip_reps')
  dips=self.say('about 5')
  self.assertEqual(dips['brief']['strength_capacity']['dip_reps'],5)
  self.assertEqual(dips['questionnaire']['awaiting'],'weekly_minutes:cycling',dips['questions'])
  cycling=self.say('about 5 hours')
  self.assertEqual(cycling['candidate_answers']['weekly_minutes']['cycling'],300)
  self.assertEqual(cycling['questionnaire']['awaiting'],'weekly_minutes:strength')
  strength=self.say('about 60 minutes')
  self.assertEqual(strength['candidate_answers']['weekly_minutes'],{'cycling':300,'strength':60})
  ready=self.say('none')
  self.assertEqual(ready['status'],'ready',ready['questions'])
  self.assertEqual(len(ready['roadmap']),16);self.assertTrue(ready['sessions'])
  self.assertTrue(all(slot['start_time'] is None for slot in ready['candidate_answers']['availability']))
  self.assertTrue(all(session['definition']['time_unspecified'] for session in ready['sessions']))
  self.assertFalse(list_training(self.path)['plans'])
  result=approve(ready['brief'],date.fromisoformat(ready['week_start']),'Asia/Jerusalem',ready['fingerprint'],self.path,NOW,candidate_answers=ready['candidate_answers'])
  self.assertEqual(result['plans'][0]['status'],'active')
 def test_broad_time_is_optional_and_no_capacity_answer_is_invented(self):
  self.say(OPENING)
  result=self.say('morning')
  self.assertEqual(result['questionnaire']['partial']['time_preference'],'morning')
  self.assertTrue(all(slot['start_time'] is None for slot in result['candidate_answers']['availability']))
  self.assertNotIn('time of day',result['questions'][0])
  self.assertEqual(result['brief']['strength_capacity'],{})
 def test_structured_date_only_availability_accepts_explicit_duration_without_clock(self):
  message='I have 90 minutes on Monday.'
  result=turn(message,[],'UTC',self.path,NOW,structured_facts=[{'path':'answers.availability','value':[{'weekday':0,'start_time':None,'minutes':90}],'quote':message}])
  self.assertEqual(result['candidate_answers']['availability'],[{'weekday':0,'start_time':None,'minutes':90}])
 def test_weekly_ranges_inherit_question_units_and_preserve_bounds(self):
  from app.training_questionnaire import _contextual_reply
  from app.training_coach import DEFAULT
  for reply,unit,bounds in [('6-7','hours',[360,420]),('6–7','hours',[360,420]),('6 to 7 hours','hours',[360,420]),('90–120 minutes','hours',[90,120]),('6-7','minutes',[6,7]),('about six to seven hours','hours',[360,420]),('1.5–2 hours','hours',[90,120])]:
   with self.subTest(reply=reply,unit=unit):
    state={'awaiting':'weekly_minutes:cycling','awaiting_unit':unit,'next_question':f'How many {unit} per week for cycling?','answers':{},'brief':json.loads(json.dumps(DEFAULT)),'partial':{},'provenance':{},'clarifications':[]}
    _contextual_reply(state,reply)
    self.assertEqual(state['answers']['weekly_minutes']['cycling'],bounds[1])
    self.assertEqual(state['brief']['weekly_time_ranges']['cycling'],bounds)
    self.assertFalse(state['clarifications'])
 def test_invalid_weekly_answers_explain_expected_format_without_filling(self):
  from app.training_questionnaire import _contextual_reply
  from app.training_coach import DEFAULT
  for reply,expected in [('7-6','smaller'),('a lot','number or range'),('6-7-8','number or range'),('-5 hours','number or range'),('100 hours','21 hours')]:
   with self.subTest(reply=reply):
    state={'awaiting':'weekly_minutes:cycling','awaiting_unit':'hours','answers':{},'brief':json.loads(json.dumps(DEFAULT)),'partial':{},'provenance':{},'clarifications':[]}
    _contextual_reply(state,reply)
    self.assertNotIn('weekly_minutes',state['answers'])
    self.assertIn(expected,state['clarifications'][0])
    self.assertIn('6–7 hours',state['clarifications'][0])
 def test_weekly_range_conversation_advances_and_survives_activation(self):
  self.say(OPENING);self.say('yes');self.say('Mainly cycling and core support');self.say('about 5');self.say('about 5')
  result=self.say('6-7')
  self.assertEqual(result['brief']['weekly_time_ranges']['cycling'],[360,420])
  self.assertIn('6–7 hours',result['recognized'][0])
  self.assertIn('not a required training volume',result['recognized'][0])
  self.assertEqual(result['questionnaire']['awaiting'],'weekly_minutes:strength')
  bad=self.say('a lot')
  self.assertIn('could not interpret',bad['questions'][0].lower())
  self.assertIn('90 minutes',bad['questions'][0])
  self.say('90 minutes');ready=self.say('none')
  self.assertEqual(ready['status'],'ready',ready['questions'])
  result=approve(ready['brief'],date.fromisoformat(ready['week_start']),'Asia/Jerusalem',ready['fingerprint'],self.path,NOW,candidate_answers=ready['candidate_answers'])
  self.assertEqual(result['plans'][0]['context']['brief']['weekly_time_ranges']['cycling'],[360,420])
