import json,tempfile,unittest
from pathlib import Path
from app.database import connect,migrate
from app.training import _revision,_snapshot
from app.workout_timing import preserve_timing,repair_saved_timing

class WorkoutTimingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  with connect(self.path) as c:c.execute("INSERT INTO training_plans(id,name,status) VALUES('plan','Plan','active')")
 def seed(self,definition,clock='12:00'):
  with connect(self.path) as c:
   c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',('ride','plan','cycling','Endurance',f'2026-11-06T{clock}:00+02:00',json.dumps({'duration_minutes':60,**definition})))
   _revision(c,_snapshot(c,'ride'))
 def current(self):
  with connect(self.path) as c:
   r=_snapshot(c,'ride');return r,json.loads(r['definition_json'])
 def test_regenerated_definition_retains_date_only_schedule_in_database_and_revision(self):
  self.seed({'scheduled_date':'2026-11-06','time_unspecified':True,'schedule_timezone':'Asia/Jerusalem'})
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET definition_json=?,revision=2 WHERE id='ride'",(json.dumps({'duration_minutes':120}),))
   _revision(c,_snapshot(c,'ride'))
   snapshot=json.loads(c.execute("SELECT snapshot_json FROM training_workout_revisions WHERE workout_id='ride' AND revision=2").fetchone()[0])
  r,d=self.current();self.assertTrue(d['time_unspecified']);self.assertEqual(d['scheduled_date'],'2026-11-06')
  self.assertEqual(json.loads(snapshot['definition_json']),d);self.assertEqual(d['duration_minutes'],120)
 def test_repairs_a_chain_of_old_dropped_flags_once_without_changing_date_or_time(self):
  self.seed({'scheduled_date':'2026-11-06','time_unspecified':True})
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET definition_json=?,revision=3 WHERE id='ride'",(json.dumps({'duration_minutes':120}),))
   # Represent an older application's broken intermediate snapshot.
   snapshot=_snapshot(c,'ride');snapshot['revision']=2
   c.execute('INSERT INTO training_workout_revisions(workout_id,revision,snapshot_json) VALUES(?,?,?)',('ride',2,json.dumps(snapshot)))
   self.assertEqual(repair_saved_timing(c),['ride']);self.assertEqual(repair_saved_timing(c),[])
  r,d=self.current();self.assertTrue(d['time_unspecified']);self.assertEqual(r['scheduled_for'],'2026-11-06T12:00:00+02:00')
 def test_real_noon_appointment_keeps_explicit_time(self):
  self.seed({'time_unspecified':False,'scheduled_date':'2026-11-06'})
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET definition_json=?,revision=2 WHERE id='ride'",(json.dumps({'duration_minutes':120}),))
   _revision(c,_snapshot(c,'ride'))
  self.assertIs(self.current()[1]['time_unspecified'],False)
 def test_explicit_change_to_timed_noon_is_not_reverted(self):
  self.seed({'time_unspecified':True,'scheduled_date':'2026-11-06'})
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET definition_json=?,revision=2 WHERE id='ride'",(json.dumps({'duration_minutes':60,'time_unspecified':False}),))
   _revision(c,_snapshot(c,'ride'));self.assertEqual(repair_saved_timing(c),[])
  self.assertIs(self.current()[1]['time_unspecified'],False)
 def test_noon_without_evidence_is_not_guessed_date_only(self):
  self.seed({})
  with connect(self.path) as c:self.assertEqual(repair_saved_timing(c),[])
  self.assertNotIn('time_unspecified',self.current()[1])
 def test_actual_schedule_move_stops_history_recovery(self):
  self.seed({'time_unspecified':True,'scheduled_date':'2026-11-06'})
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET scheduled_for='2026-11-06T14:00:00+02:00',definition_json=?,revision=2 WHERE id='ride'",(json.dumps({'duration_minutes':60}),))
   _revision(c,_snapshot(c,'ride'));self.assertEqual(repair_saved_timing(c),[])
  self.assertNotIn('time_unspecified',self.current()[1])
 def test_regeneration_helper_preserves_timing_and_uses_new_instructions(self):
  source={'duration_minutes':60,'time_unspecified':True,'scheduled_date':'2026-11-06','schedule_timezone':'Asia/Jerusalem'}
  result=preserve_timing({'duration_minutes':120},source)
  self.assertTrue(result['time_unspecified']);self.assertEqual(result['duration_minutes'],120)
  self.assertEqual(source['duration_minutes'],60)
 def test_fixed_commitment_time_is_not_repaired_from_old_date_only_history(self):
  self.seed({'time_unspecified':True,'scheduled_date':'2026-11-06'})
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET definition_json=?,revision=2 WHERE id='ride'",(json.dumps({'duration_minutes':60,'fixed_commitment':True}),))
   _revision(c,_snapshot(c,'ride'));self.assertEqual(repair_saved_timing(c),[])
  self.assertNotIn('time_unspecified',self.current()[1])
