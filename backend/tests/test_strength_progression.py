import copy,unittest
from datetime import datetime,timedelta,timezone
from app.training_prescriptions import strength
NOW=datetime(2026,10,27,10,tzinfo=timezone.utc)
ANS={'priority':'strength','equipment':['dumbbells'],'blocked_movements':[],'experience':{'strength':'regular'}}
BASE={'duration_minutes':45,'rationale':[],'exercises':[{'id':'row','name':'Dumbbell row','equipment':'dumbbells','movement':'pull'},{'id':'press','name':'Dumbbell press','equipment':'dumbbells','movement':'push'}]}

def record(workout,days=1,set_index=1,rir=3,load=10):
 return {'exercise_id':'row','workout_id':workout,'set_index':set_index,'repetitions':8,'repetitions_in_reserve':rir,'load_kg':load,'recorded_at':(NOW-timedelta(days=days)).isoformat()}

def prescribed(records,tolerated=True):
 result=strength(copy.deepcopy(BASE),{'strength_role':'primary','strength_purpose':'strength_development','strength_performance':records},ANS,week_index=4,tolerated=tolerated,observed_at=NOW)
 return next(e for e in result['exercises'] if e['id']=='row')

class StrengthProgressionTests(unittest.TestCase):
 def test_two_sets_of_one_workout_do_not_authorize_progression(self):
  exercise=prescribed([record('one',set_index=1),record('one',set_index=2)])
  self.assertEqual(exercise['repetitions'],6)
  self.assertEqual(exercise['progression_evidence']['completed_sessions'],1)
  self.assertEqual(exercise['progression_evidence']['status'],'hold')
  self.assertNotIn('load_target_kg',exercise)
 def test_two_distinct_tolerated_sessions_at_same_load_progress_reps_only(self):
  exercise=prescribed([record('one',days=4),record('two')])
  self.assertEqual(exercise['repetitions'],9)
  self.assertEqual(exercise['load_target_kg'],10)
  self.assertEqual(exercise['progression_evidence']['status'],'eligible')
 def test_latest_hard_or_unknown_set_prevents_using_older_successes(self):
  for rir in (1,None):
   exercise=prescribed([record('one',days=8),record('two',days=4),record('latest',rir=rir)])
   self.assertEqual(exercise['repetitions'],6)
   self.assertEqual(exercise['progression_evidence']['status'],'hold')
 def test_a_hard_set_in_same_session_and_changed_load_hold_progression(self):
  for records in ([record('one',days=4),record('two',set_index=1),record('two',set_index=2,rir=0)],
                  [record('one',days=4,load=10),record('two',load=12)],
                  [record('one',days=4,load=None),record('two',load=None)]):
   self.assertEqual(prescribed(records)['progression_evidence']['status'],'hold')
 def test_stale_future_undated_and_no_recovery_clearance_do_not_progress(self):
  for invalid in (record('old',days=91),record('future',days=-1),{**record('undated'),'recorded_at':'invalid'}):
   self.assertEqual(prescribed([record('recent'),invalid])['progression_evidence']['status'],'hold')
  self.assertEqual(prescribed([record('one',days=4),record('two')],False)['progression_evidence']['status'],'hold')
