import json
import tempfile
import unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import migrate,connect
from app.training import validate_answers,list_training
from app.training_coach import DEFAULT,preview,approve
from app.active_training import review,reschedule
from app.main import app

NOW=datetime(2026,10,17,10,tzinfo=timezone.utc)
START=date(2026,10,17)
TZ='Asia/Jerusalem'
ANSWERS={'sports':['cycling','strength'],'priority':'endurance','availability':[{'weekday':day,'start_time':None,'minutes':300 if day==4 else 60} for day in (0,1,2,3,4,6)],'experience':{'cycling':'regular','strength':'new'},'equipment':['bike','bodyweight'],'weekly_minutes':{'cycling':480,'strength':120},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
BRIEF={**DEFAULT,'goal':'endurance','duration_confirmed':True,'horizon_weeks':16,'program_start':'2026-10-17','sport_days':{'cycling':[0,2,4,6],'strength':[1,3]},'strength_role':'secondary','strength_purpose':'cycling_support'}

class DateOnlyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'db';migrate(self.path)
 def activate(self):
  candidate=preview(BRIEF,START,TZ,self.path,NOW,candidate_answers=ANSWERS)
  self.assertEqual(candidate['status'],'ready',candidate['questions'])
  return approve(candidate['brief'],START,TZ,candidate['fingerprint'],self.path,NOW,candidate_answers=ANSWERS)
 def test_sixteen_week_date_only_plan_activation_and_rolling_preserve_metadata(self):
  self.assertTrue(all(slot['start_time'] is None for slot in validate_answers(ANSWERS)['availability']))
  saved=self.activate()
  self.assertEqual(saved['plans'][0]['starts_on'],'2026-10-17')
  self.assertTrue(saved['workouts'])
  for workout in saved['workouts']:
   self.assertTrue(workout['time_unspecified']);self.assertEqual(workout['scheduled_date'],workout['definition']['scheduled_date'])
   self.assertNotEqual(date.fromisoformat(workout['scheduled_date']).weekday(),5)
  ready={'latest':{'date':'2026-10-25','score':80,'status':'complete','groups':[]}}
  with patch('app.readiness.readiness_history',return_value=ready):current=review(self.path,TZ,NOW+timedelta(days=8))
  self.assertEqual(current['program']['ends_on'],'2027-02-05')
  self.assertTrue(current['workouts'])
  self.assertTrue(all(workout['time_unspecified'] for workout in current['workouts']))
  self.assertTrue(all('2026-10-25'<=workout['scheduled_date']<='2026-10-31' for workout in current['workouts']))
 def test_date_only_preview_edit_and_schedule_patch_preserve_optional_clock(self):
  changed=preview(BRIEF,START,TZ,self.path,NOW,candidate_answers=ANSWERS,session_changes=[{'index':0,'scheduled_date':'2026-10-18','start_time':None,'duration_minutes':45}])
  self.assertTrue(changed['sessions'][0]['time_unspecified']);self.assertEqual(changed['sessions'][0]['definition']['duration_minutes'],45)
  saved=self.activate();workout=next(workout for workout in saved['workouts'] if workout['scheduled_date']=='2026-10-18')
  with patch('app.database.database_path',return_value=self.path),patch('app.active_training.datetime') as clock:
   clock.now.return_value=NOW;clock.fromisoformat.side_effect=datetime.fromisoformat
   # Route API schema exercised without production data.
   with TestClient(app) as client:
    result=client.patch('/api/training/workouts/'+workout['id']+'/schedule',json={'expected_revision':workout['revision'],'changes':{'scheduled_date':'2026-10-25','start_time':None,'timezone':TZ}})
    self.assertEqual(result.status_code,200,result.text)
  moved=next(row for row in list_training(self.path)['workouts'] if row['id']==workout['id'])
  self.assertTrue(moved['time_unspecified']);self.assertEqual(moved['scheduled_date'],'2026-10-25')
  reschedule(workout['id'],None,moved['revision'],self.path,NOW,scheduled_date='2026-10-25',start_time='08:00')
  timed=next(row for row in list_training(self.path)['workouts'] if row['id']==workout['id'])
  self.assertFalse(timed['time_unspecified']);self.assertIn('08:00',timed['scheduled_for'])
 def test_date_only_day_budget_conflict_does_not_pretend_clock_overlap(self):
  result=preview(BRIEF,START,TZ,self.path,NOW,candidate_answers=ANSWERS,session_changes=[{'index':0,'scheduled_date':'2026-10-19','start_time':None}])
  self.assertEqual(result['status'],'needs_input')
  self.assertTrue(any('day budget' in question for question in result['questions']))
  self.assertFalse(any('overlap' in question and 'non-overlapping' not in question for question in result['questions']))
 def test_optional_time_today_is_not_discarded_because_internal_anchor_passed(self):
  late=datetime(2026,10,18,18,tzinfo=timezone.utc)
  brief={**BRIEF,'program_start':'2026-10-18'}
  result=preview(brief,date(2026,10,18),TZ,self.path,late,candidate_answers=ANSWERS)
  today=next(session for session in result['sessions'] if session['scheduled_date']=='2026-10-18')
  self.assertTrue(today['time_unspecified'])
 def test_explicit_timed_availability_retains_original_clock(self):
  answers={**ANSWERS,'availability':[{**slot,'start_time':'08:00'} for slot in ANSWERS['availability']]}
  result=preview(BRIEF,START,TZ,self.path,NOW,candidate_answers=answers)
  self.assertTrue(result['sessions'])
  self.assertTrue(all(not session['time_unspecified'] and '08:00' in session['scheduled_for'] for session in result['sessions']))
