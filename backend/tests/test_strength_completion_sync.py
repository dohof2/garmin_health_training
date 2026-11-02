"""A strength completion must be visible before unrelated sync families finish."""
import json
import tempfile
import unittest
from datetime import date,datetime,timezone
from pathlib import Path
from unittest.mock import patch
from app.database import connect
from app.sync import _commit_interval,ensure_sync_checkpoints
from app.training_completion import reconcile_active
from test_sync import _seed

DAY=date(2026,10,29)
NOW=datetime(2026,10,29,20,tzinfo=timezone.utc)

class StrengthCompletionSyncTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'test.sqlite';_seed(self.path,'2026-10-28');ensure_sync_checkpoints(self.path)
  with connect(self.path) as c:
   c.execute("INSERT INTO training_plans(id,name,status) VALUES('root','Test','active')")
   c.execute("INSERT INTO active_training_program(id,plan_id,status,state_json) VALUES(1,'root','active',?)",(json.dumps({'timezone':'Asia/Jerusalem'}),))
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES('strength','root','strength','Cycling-support strength','2026-10-29T12:00:00+02:00',?)",(json.dumps({'duration_minutes':30,'scheduled_date':'2026-10-29','time_unspecified':True}),))
   c.execute("INSERT INTO jobs(id,job_type,status,checkpoint_json) VALUES('job','garmin_sync','running','{}')")
  self.activity={'source_record_id':'recorded-strength','name':'Cycling-support strength','activity_type':'strength_training','started_at':'2026-10-29T18:58:19Z','duration_seconds':739.062}
 def commit(self,records,job_id='job'):
  with patch('app.sync.datetime') as clock:
   clock.now.return_value=NOW
   return _commit_interval(job_id,'activities',DAY,'reconciliation',records,date(2026,10,28),self.path)
 def test_matches_at_commit_while_job_running_and_retry_is_idempotent(self):
  self.commit([self.activity])
  with connect(self.path) as c:c.execute("INSERT INTO jobs(id,job_type,status,checkpoint_json) VALUES('retry','garmin_sync','running','{}')")
  self.commit([self.activity],'retry')
  with connect(self.path) as c:
   self.assertEqual(c.execute("SELECT status FROM jobs WHERE id='job'").fetchone()[0],'running')
   self.assertEqual(c.execute("SELECT completion_status FROM planned_workouts WHERE id='strength'").fetchone()[0],'completed')
   self.assertEqual(c.execute("SELECT count(*) FROM training_feedback WHERE workout_id='strength' AND activity_id IS NOT NULL").fetchone()[0],1)
   self.assertEqual(c.execute("SELECT count(*) FROM training_workout_revisions WHERE workout_id='strength'").fetchone()[0],1)
 def test_ambiguous_recordings_leave_session_unmatched(self):
  self.commit([self.activity,{**self.activity,'source_record_id':'another','started_at':'2026-10-29T17:00:00Z'}])
  with connect(self.path) as c:self.assertEqual(c.execute("SELECT completion_status FROM planned_workouts WHERE id='strength'").fetchone()[0],'planned')
 def test_paused_program_is_not_changed(self):
  with connect(self.path) as c:c.execute("UPDATE active_training_program SET status='paused'")
  self.commit([self.activity])
  with connect(self.path) as c:self.assertEqual(reconcile_active(c,NOW),([],[]));self.assertEqual(c.execute("SELECT completion_status FROM planned_workouts WHERE id='strength'").fetchone()[0],'planned')
