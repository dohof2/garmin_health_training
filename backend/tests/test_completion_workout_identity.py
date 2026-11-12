"""An explicit recorded Garmin workout identity takes priority over clock heuristics."""
import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from app.database import connect,migrate
from app.training_completion import reconcile

NOW=datetime(2026,11,6,18,tzinfo=timezone.utc)
class WorkoutIdentityCompletionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  with connect(self.path) as c:
   c.execute("INSERT INTO training_plans(id,name,status) VALUES('plan','Plan','active')")
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,garmin_workout_id) VALUES('workout','plan','cycling','Long endurance','2026-11-06T12:00:00+02:00',?,'remote-ride')",(json.dumps({'duration_minutes':120}),))
 def ride(self,identifier='ride',start='2026-11-06T13:03:58Z',workout='remote-ride',duration=9333,sport='mountain_biking'):
  with connect(self.path) as c:c.execute('INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,raw_json) VALUES(?,?,?,?,?,?)',(identifier,'garmin_connect',sport,start,duration,json.dumps({'workoutId':workout})))
 def match(self):
  with connect(self.path) as c:
   rows=[dict(r) for r in c.execute('SELECT * FROM planned_workouts')]
   return reconcile(c,rows,'Asia/Jerusalem',NOW)
 def test_explicit_id_matches_later_start_and_different_duration_once(self):
  self.ride();changes,warnings=self.match();self.assertEqual(len(changes),1);self.assertFalse(warnings)
  self.assertIn('Garmin workout ID',changes[0]['reason'])
  with connect(self.path) as c:self.assertEqual(c.execute("SELECT activity_id FROM training_feedback WHERE workout_id='workout'").fetchone()[0],'ride')
  self.assertEqual(self.match(),([],[]))
 def test_no_identity_does_not_remove_existing_clock_guard(self):
  self.ride(workout=None);self.assertFalse(self.match()[0])
 def test_identity_still_requires_finished_recording_matching_day_and_sport(self):
  for values in ({'duration':999999},{'start':'2026-11-05T13:00:00Z'},{'sport':'running'}):
   with self.subTest(values=values):
    with connect(self.path) as c:c.execute('DELETE FROM activities')
    self.ride(**values);self.assertFalse(self.match()[0])
 def test_matching_id_beats_unplanned_same_day_recording(self):
  self.ride();self.ride('other',start='2026-11-06T10:15:00Z',workout=None)
  self.assertEqual(len(self.match()[0]),1)
 def test_multiple_recordings_with_same_id_are_not_guessed(self):
  self.ride();self.ride('second');changes,warnings=self.match()
  self.assertFalse(changes);self.assertTrue(warnings)
 def test_known_id_cannot_complete_a_different_same_day_slot(self):
  self.ride()
  with connect(self.path) as c:c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,garmin_workout_id) VALUES('other','plan','cycling','Other ride','2026-11-06T15:00:00+02:00',?,'other-remote')",(json.dumps({'duration_minutes':60,'time_unspecified':True}),))
  changes,_=self.match();self.assertEqual([r['workout_id'] for r in changes],['workout'])
