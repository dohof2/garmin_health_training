from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.database import connect,migrate
from app.exports import create_backup,export_json,restore_backup
from app.main import app
from app.training import training_context,save_preferences,workout_definition,draft_week,accept_plan,update_workout,list_training,validate_answers,progression_proposal

NOW=datetime(2026,10,10,12,tzinfo=timezone.utc)
class FrozenClock(datetime):
 @classmethod
 def now(cls,tz=None):return NOW if tz else NOW.replace(tzinfo=None)

WEEK=date(2026,10,12)
ANSWERS={'sports':['cycling','running','strength'],'priority':'mixed','availability':[{'weekday':0,'start_time':'18:00','minutes':45},{'weekday':2,'start_time':'18:00','minutes':45},{'weekday':4,'start_time':'18:00','minutes':45}],
 'experience':{'cycling':'regular','running':'new','strength':'new'},'equipment':['bike','bodyweight'],'weekly_minutes':{'cycling':120,'running':60,'strength':60},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}


class TrainingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'db.sqlite3';migrate(self.path)
 def tearDown(self):self.temp.cleanup()
 def save(self,answers=None,now=NOW):return save_preferences(answers or copy.deepcopy(ANSWERS),training_context(self.path,now)['revision'],self.path,now)
 def draft(self,**kwargs):return draft_week(WEEK,'Asia/Jerusalem',training_context(self.path,NOW)['revision'],self.path,now=NOW,**kwargs)
 def test_partial_answers_reused_and_only_missing_or_stale_asked(self):
  self.assertEqual(len(training_context(self.path,NOW)['missing']),10)
  save_preferences({'sports':['cycling']},0,self.path,NOW)
  context=training_context(self.path,NOW)
  self.assertNotIn('sports',context['missing']);self.assertIn('experience',context['missing'])
  self.save()
  self.assertTrue(training_context(self.path,NOW)['ready'])
  old=training_context(self.path,NOW+timedelta(days=31))
  self.assertIn('availability',old['stale']);self.assertNotIn('experience',old['stale'])
  save_preferences({'availability':ANSWERS['availability']},old['revision'],self.path,NOW+timedelta(days=31))
  self.assertIn('pain_or_illness',training_context(self.path,NOW+timedelta(days=31))['stale'])
 def test_invalid_answers_atomic_and_stale_revision_rejected(self):
  self.save()
  for value in [{'availability':[ANSWERS['availability'][0]]*2},{'weekly_minutes':{'running':float('nan')}},{'sports':['swimming']},{'pain_or_illness':'no'},{'availability':[{'weekday':0,'start_time':'23:45','minutes':60}]}]:
   with self.assertRaises(ValueError):save_preferences(value,1,self.path,NOW)
  with self.assertRaises(ValueError):save_preferences({'priority':'general'},0,self.path,NOW)
  self.assertEqual(training_context(self.path,NOW)['revision'],1)
 def test_changed_sports_requires_experience_and_volume_for_new_sport(self):
  answers=copy.deepcopy(ANSWERS);answers.update(sports=['cycling'],experience={'cycling':'regular'},weekly_minutes={'cycling':90})
  self.save(answers);save_preferences({'sports':['cycling','running']},1,self.path,NOW)
  context=training_context(self.path,NOW)
  self.assertIn('experience',context['missing']);self.assertIn('weekly_minutes',context['missing'])
 def test_incompatible_restrictions_and_pain_block_generation(self):
  for patch in [{'blocked_sports':['running']},{'equipment':['bodyweight']},{'pain_or_illness':True},{'restrictions_notes':'Clinician instructed no strenuous exercise'}]:
   self.save({**copy.deepcopy(ANSWERS),**patch})
   self.assertFalse(training_context(self.path,NOW)['ready'])
   with self.assertRaises(ValueError):self.draft()
  self.assertEqual(list_training(self.path)['plans'],[])
 def test_templates_have_exact_endurance_time_and_strength_targets(self):
  for template in ['cycling_easy','running_easy']:
   definition=workout_definition(template,30,ANSWERS)
   self.assertEqual(sum(s['duration_seconds'] for s in definition['steps']),1800)
  definition=workout_definition('strength_foundation',30,ANSWERS)
  self.assertTrue(all(e['sets']==1 and e['rest_seconds']==90 for e in definition['exercises']))
  blocked={**ANSWERS,'blocked_movements':['squat','push']}
  definition=workout_definition('strength_foundation',30,blocked)
  self.assertFalse(any(e['movement'] in ['squat','push'] for e in definition['exercises']))
 def test_draft_balances_sports_obeys_time_and_needs_explicit_accept(self):
  self.save();history=self.draft();plan=history['plans'][0]
  self.assertEqual(plan['status'],'draft')
  self.assertEqual(len(history['workouts']),3)
  self.assertEqual({s['sport'] for s in history['workouts']},set(ANSWERS['sports']))
  self.assertTrue(all(s['definition']['duration_minutes']<=45 for s in history['workouts']))
  with patch('app.training.datetime',FrozenClock):
   accepted=accept_plan(plan['id'],self.path)
  self.assertEqual(accepted['plans'][0]['status'],'active')
 def test_repeat_draft_conflict_rolls_back_and_existing_profile_not_required(self):
  self.save();self.draft()
  with self.assertRaisesRegex(ValueError,'conflict'):self.draft()
  self.assertEqual(len(list_training(self.path)['plans']),1)
  with connect(self.path) as c:self.assertEqual(c.execute('select count(*) from user_profile').fetchone()[0],0)
 def test_zero_minutes_never_gets_invented_as_volume(self):
  self.save({**ANSWERS,'weekly_minutes':{'cycling':0,'running':0,'strength':0}})
  with self.assertRaisesRegex(ValueError,'No supported'):self.draft()
 def test_strength_has_recovery_day_and_draft_dates_validated(self):
  answers=copy.deepcopy(ANSWERS);answers.update(sports=['strength'],availability=[{'weekday':i,'start_time':'18:00','minutes':30} for i in range(5)],weekly_minutes={'strength':150})
  self.save(answers);history=self.draft();dates=[date.fromisoformat(w['scheduled_for'][:10]) for w in history['workouts']]
  self.assertTrue(all((b-a).days>=2 for a,b in zip(dates,dates[1:])))
  with self.assertRaises(ValueError):draft_week(date(2026,10,13),'UTC',1,self.path,now=NOW)
  with self.assertRaises(ValueError):draft_week(date(2026,10,5),'UTC',1,self.path,now=NOW)
 def test_stale_profile_blocks_draft_and_accept_after_changed_preferences(self):
  self.save();history=self.draft();self.save({**ANSWERS,'priority':'general'})
  with self.assertRaises(ValueError):accept_plan(history['plans'][0]['id'],self.path)
  with self.assertRaises(ValueError):draft_week(WEEK,'UTC',2,self.path,now=NOW+timedelta(days=31))
 def test_priority_and_recovery_across_week_boundaries(self):
  self.save({**ANSWERS,'priority':'strength'})
  first=self.draft()['workouts'][0]
  self.assertEqual(first['sport'],'strength')
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET scheduled_for='2026-10-18T18:00:00+03:00' WHERE id=?",(first['id'],))
  next_week=draft_week(date(2026,10,19),'Asia/Jerusalem',1,self.path,now=NOW)
  fresh=[w for w in next_week['workouts'] if w['scheduled_for'][:10]>='2026-10-19']
  self.assertNotEqual(fresh[0]['sport'],'strength')
  self.assertTrue(any(w['sport']=='strength' for w in fresh))
 def test_full_availability_reserves_a_day_and_restore_checks_conflicts(self):
  answers={**ANSWERS,'sports':['running'],'availability':[{'weekday':i,'start_time':'18:00','minutes':30} for i in range(7)],'weekly_minutes':{'running':210}}
  self.save(answers);history=self.draft()
  self.assertEqual(len(history['workouts']),6)
  first=history['workouts'][0]
  update_workout(first['id'],1,{'completion_status':'skipped'},self.path)
  with connect(self.path) as c:
   c.execute('UPDATE planned_workouts SET scheduled_for=? WHERE id=?',(first['scheduled_for'],history['workouts'][1]['id']))
  with patch('app.training.datetime',FrozenClock):
   with self.assertRaisesRegex(ValueError,'conflicts'):update_workout(first['id'],2,{'completion_status':'planned'},self.path)
 def test_feedback_preserved_revisions_without_silent_rewrite(self):
  self.save();history=self.draft();workout=history['workouts'][0]
  updated=update_workout(workout['id'],1,{'completion_status':'completed','effort':9,'soreness':6,'pain_or_illness':True,'notes':'Review required'},self.path)
  changed=next(w for w in updated['workouts'] if w['id']==workout['id'])
  self.assertEqual(changed['revision'],2);self.assertIsNotNone(changed['suggested_revision'])
  self.assertEqual([w['scheduled_for'] for w in history['workouts']],[w['scheduled_for'] for w in updated['workouts']])
  with connect(self.path) as c:self.assertEqual(c.execute('select count(*) from training_workout_revisions where workout_id=?',(workout['id'],)).fetchone()[0],2)
  with self.assertRaises(ValueError):update_workout(workout['id'],1,{'completion_status':'skipped'},self.path)
 def test_session_edits_cannot_exceed_constraints_or_missing_equipment(self):
  self.save();history=self.draft();workout=history['workouts'][0]
  with patch('app.training.datetime',FrozenClock):
   with self.assertRaises(ValueError):update_workout(workout['id'],1,{'duration_minutes':120},self.path)
   with self.assertRaises(ValueError):update_workout(workout['id'],1,{'template_id':'unknown'},self.path)
  with self.assertRaises(ValueError):update_workout(workout['id'],1,{'effort':11},self.path)
  with self.assertRaises(ValueError):update_workout(workout['id'],1,{'activity_id':'unknown'},self.path)
 def test_portability_preserves_preferences_sessions_and_feedback(self):
  self.save();history=self.draft();update_workout(history['workouts'][0]['id'],1,{'completion_status':'skipped'},self.path)
  out=Path(self.temp.name)/'export.json';export_json(out,path=self.path)
  tables=json.loads(out.read_text())['tables'];self.assertEqual(len(tables['training_preferences']),1);self.assertEqual(len(tables['training_feedback']),1)
  backup=Path(self.temp.name)/'backup.zip';restored=Path(self.temp.name)/'restored.sqlite3';create_backup(backup,self.path);restore_backup(backup,restored)
  self.assertEqual(training_context(restored,NOW)['answers'],ANSWERS)
  self.assertEqual(list_training(restored),list_training(self.path))
 def test_api_requires_review_and_validates_preferences(self):
  with patch('app.database.database_path',return_value=self.path):
   with TestClient(app) as client:
    self.assertEqual(client.get('/api/training/context').status_code,200)
    self.assertEqual(client.put('/api/training/preferences',json={'answers':ANSWERS,'expected_revision':0}).status_code,200)
    self.assertEqual(client.put('/api/training/preferences',json={'answers':ANSWERS,'expected_revision':0}).status_code,400)
    self.assertEqual(client.post('/api/training/draft',json={'week_start':'2026-10-12','timezone':'UTC','expected_preference_revision':1}).status_code,200)
    self.assertEqual(client.get('/api/training').json()['plans'][0]['status'],'draft')

 def test_progression_needs_two_complete_weeks_and_explicit_review(self):
  answers=copy.deepcopy(ANSWERS);answers.update(sports=['running'],availability=[{'weekday':0,'start_time':'18:00','minutes':45},{'weekday':2,'start_time':'18:00','minutes':45}],weekly_minutes={'running':40})
  self.save(answers)
  for start in [date(2026,9,21),date(2026,9,28)]:
   cnow=datetime.combine(start-timedelta(days=1),datetime.min.time(),timezone.utc)
   # The fixture confirms a still-current profile before each historical test week.
   save_preferences(answers,training_context(self.path,cnow)['revision'],self.path,cnow)
   history=draft_week(start,'UTC',training_context(self.path,cnow)['revision'],self.path,now=cnow)
   with connect(self.path) as c:
    c.execute("UPDATE training_plans SET status='active'")
    for workout in history['workouts']:
     c.execute("UPDATE planned_workouts SET completion_status='completed' WHERE id=?",(workout['id'],))
     c.execute("INSERT OR REPLACE INTO training_feedback(workout_id,effort,soreness,pain_or_illness) VALUES (?,5,2,0)",(workout['id'],))
  self.save(answers)
  proposal=progression_proposal(self.path,NOW)
  self.assertEqual(proposal['changes']['weekly_minutes']['running'],42)
  self.assertEqual(training_context(self.path,NOW)['answers']['weekly_minutes']['running'],40)
  self.assertTrue(all(w['definition']['duration_minutes']<=30 for w in list_training(self.path)['workouts']))
  with connect(self.path) as c:c.execute("UPDATE planned_workouts SET completion_status='skipped' WHERE id=(SELECT id FROM planned_workouts LIMIT 1)")
  proposal=progression_proposal(self.path,NOW)
  self.assertEqual(proposal['changes']['weekly_minutes']['running'],32)
 def test_recent_pain_feedback_needs_explicit_reconfirmation(self):
  self.save();history=self.draft();workout=history['workouts'][0]
  update_workout(workout['id'],1,{'pain_or_illness':True},self.path)
  with connect(self.path) as c:c.execute("UPDATE training_feedback SET updated_at='2026-10-10T13:00:00+00:00'")
  later=NOW+timedelta(hours=2)
  self.assertFalse(training_context(self.path,later)['ready'])
  save_preferences({'pain_or_illness':False},1,self.path,later)
  self.assertTrue(training_context(self.path,later)['ready'])
 def test_date_filtered_exports_limit_feedback_and_workout_revisions(self):
  self.save();history=self.draft();update_workout(history['workouts'][0]['id'],1,{'effort':5},self.path)
  output=Path(self.temp.name)/'filtered.json';export_json(output,end_date=date(2026,10,1),path=self.path)
  tables=json.loads(output.read_text())['tables']
  self.assertEqual(tables['planned_workouts'],[]);self.assertEqual(tables['training_feedback'],[]);self.assertEqual(tables['training_workout_revisions'],[])
 def test_dst_ambiguous_schedule_is_not_guessed(self):
  answers=copy.deepcopy(ANSWERS);answers.update(sports=['running'],availability=[{'weekday':6,'start_time':'02:30','minutes':30}])
  self.save(answers)
  with self.assertRaisesRegex(ValueError,'clock change'):draft_week(date(2026,10,19),'Europe/Berlin',1,self.path,now=NOW)
