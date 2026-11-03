import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from app.database import connect,migrate
from app.training_questionnaire import read
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
 def test_strength_preview_without_equipment_or_weekly_budget_returns_questions(self):
  from app.training_coach import preview,DEFAULT
  result=preview({**DEFAULT,'goal':'ftp','horizon_weeks':16,'duration_confirmed':True},date(2026,10,19),'UTC',self.path,NOW,candidate_answers={'sports':['cycling','strength']})
  self.assertEqual(result['status'],'needs_input')
  self.assertTrue(result['questions'])
