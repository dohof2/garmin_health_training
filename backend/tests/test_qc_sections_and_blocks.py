"""One batch of explicit edit, recorded-section and conversational regressions."""
import copy,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from app.database import connect,migrate
from app.training_prescriptions import endurance
from app.training_coach import DEFAULT
from app.workout_edits import edit,EditError
from app.activity_section_analysis import analyze,conversational_selection

POLICY={'level':'normal','quality_allowed':True}
NOW=datetime(2026,10,27,10,tzinfo=timezone.utc)

class SelectedBlockTests(unittest.TestCase):
 def source(self):
  d=endurance('threshold',60,DEFAULT,today=NOW.date())
  work=[s for s in d['steps'] if s['name'].startswith('Work lap')]
  work[1]['duration_seconds']+=120
  next(s for s in d['steps'] if s['name']=='Steady endurance')['duration_seconds']-=120
  return d
 def test_one_heterogeneous_interval_changes_without_overwriting_others(self):
  original=self.source();before=copy.deepcopy(original)
  changed,summary=edit(original,'Change work interval 2 to 4 minutes',POLICY)
  self.assertEqual(original,before)
  self.assertEqual(changed['steps'][1],original['steps'][1])
  self.assertEqual(changed['steps'][3]['duration_seconds'],240)
  self.assertEqual(changed['steps'][2],original['steps'][2])
  self.assertEqual(sum(s['duration_seconds'] for s in changed['steps']),3600)
  self.assertIn('4:00',summary[0])
 def test_nested_step_path_applies_to_its_repeated_group_only(self):
  d=self.source();warm,work,rest,_,fill,cool=d['steps']
  d['steps']=[warm,{'name':'Main set','repetitions':2,'steps':[work,rest]},dict(fill,duration_seconds=1500),cool]
  changed,_=edit(d,'Change step 2.1 to 4 minutes',POLICY)
  self.assertEqual([s['duration_seconds'] for s in changed['steps'] if s['name'].startswith('Work lap')],[240,240])
  self.assertEqual([s['duration_seconds'] for s in changed['steps'] if s['name'].startswith('Recovery')],[240,240])
  self.assertEqual(sum(s['duration_seconds'] for s in changed['steps']),3600)
 def test_invalid_index_partial_request_increase_and_noop_leave_source_unchanged(self):
  d=self.source();before=copy.deepcopy(d)
  for message in ('Change interval 99 to 4 minutes','Change interval 2 to 4 minutes and power target to fast','Change interval 2 to 12 minutes','Change recovery 1 to 1 minute','Change interval 2 to 8 minutes'):
   with self.subTest(message=message),self.assertRaises(EditError):edit(d,message,POLICY)
  self.assertEqual(d,before)
 def test_targeted_recovery_and_power_method_validation(self):
  d=self.source();changed,_=edit(d,'Change recovery 1 to 5 minutes',POLICY)
  self.assertEqual(changed['steps'][2]['duration_seconds'],300)
  with self.assertRaises(EditError):edit(d,'Change interval 2 power target to 200 W',POLICY)
 def test_training_phase_changes_are_not_misread_as_timed_workout_blocks(self):
  from app.workout_edits import requested
  self.assertFalse(requested('Change my training block to 4 weeks'))
  self.assertTrue(requested('Change step 2.1 to 4 minutes'))

class RecordedSectionsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'qa.sqlite';migrate(self.path)
  with connect(self.path) as c:
   c.execute("INSERT INTO activities(id,source_name,activity_type,name,started_at,duration_seconds,raw_json) VALUES('ride','garmin_connect','cycling','Fictional section ride',?,240,?)",(NOW.isoformat(),json.dumps({'fit_laps':[{'start_time':NOW.isoformat(),'timestamp':(NOW+timedelta(seconds=60)).isoformat()}]})))
   for i in range(241):
    # Flat first minute, descent second minute, climb last half. Power has two bursts.
    height=100 if i<=60 else 100-(i-60)*.3 if i<=120 else 82+(i-120)*.3
    power=500 if 10<=i<20 or 40<=i<50 else 100 if i<120 else 200
    c.execute("INSERT INTO activity_samples(activity_id,recorded_at,power_watts,heart_rate_bpm,cadence_rpm,speed_mps,elevation_meters,raw_json) VALUES('ride',?,?,?,?,?,?,?)",((NOW+timedelta(seconds=i)).isoformat(),power,120 if i<120 else 140,80,10,height,json.dumps({'distance':i*10})))
 def run_section(self,*selections):return analyze({'activity_id':'ride','sections':list(selections)},self.path)
 def test_clipped_time_comparison_uses_all_samples_and_keeps_zeros(self):
  result=self.run_section({'kind':'time','start':60.5,'end':90.5},{'kind':'time','start':150,'end':180})
  self.assertEqual(result['sections'][0]['metrics']['power']['average'],100)
  self.assertEqual(result['comparisons']['power']['second_minus_first'],100)
  self.assertEqual(result['sections'][0]['moving_seconds'],30)
  with connect(self.path) as c:c.execute("UPDATE activity_samples SET power_watts=0 WHERE activity_id='ride' AND recorded_at<?",((NOW+timedelta(seconds=120)).isoformat(),))
  self.assertEqual(self.run_section({'kind':'time','start':60,'end':90})['sections'][0]['metrics']['power']['average'],0)
 def test_gaps_withhold_full_average_and_never_substitute_lap_average(self):
  with connect(self.path) as c:c.execute("UPDATE activity_samples SET power_watts=NULL WHERE activity_id='ride' AND recorded_at=?",((NOW+timedelta(seconds=75)).isoformat(),))
  metric=self.run_section({'kind':'time','start':60,'end':90})['sections'][0]['metrics']['power']
  self.assertIsNone(metric['average']);self.assertEqual(metric['covered_average'],100);self.assertLess(metric['coverage_fraction'],1)
 def test_recorded_distance_lap_and_ambiguous_sprint_boundaries(self):
  section=self.run_section({'kind':'distance','start':.6,'end':.9})['sections'][0]
  self.assertEqual((section['start_seconds'],section['end_seconds']),(60,90))
  self.assertEqual(self.run_section({'kind':'lap','index':1})['sections'][0]['elapsed_seconds'],60)
  candidates=self.run_section({'kind':'sprint','threshold_watts':400})
  self.assertTrue(candidates['needs_clarification']);self.assertEqual(candidates['selections'][0]['candidate_count'],2)
  selected=self.run_section({'kind':'sprint','threshold_watts':400,'index':2})['sections'][0]
  self.assertEqual((selected['start_seconds'],selected['end_seconds']),(40,50))
  self.assertEqual(selected['metrics']['power']['average'],500)
 def test_terrain_uses_recorded_elevation_and_distance(self):
  for kind in ('flat','descent','climb'):
   result=self.run_section({'kind':kind,'index':1})
   self.assertFalse(result['needs_clarification']);self.assertGreaterEqual(result['sections'][0]['elapsed_seconds'],30)
 def test_missing_distance_invalid_range_and_reversed_selection_are_explicit(self):
  for selection in ({'kind':'time','start':100,'end':90},{'kind':'time','start':0,'end':300},{'kind':'flat','start':0}):
   with self.assertRaises(ValueError):self.run_section(selection)
  with connect(self.path) as c:c.execute("UPDATE activity_samples SET raw_json='{}' WHERE activity_id='ride'")
  result=self.run_section({'kind':'distance','start':.6,'end':.9})
  self.assertTrue(result['needs_clarification']);self.assertEqual(result['selections'][0]['candidate_count'],0)
 def test_read_only_tool_is_available_without_exporting_other_records(self):
  from app.chat_access import questions_only
  from app.ai_tools import execute_tool
  with questions_only():
   result=execute_tool('analyze_activity_sections',{'activity_id':'ride','sections':[{'kind':'time','start':60,'end':90}]},self.path)
  self.assertEqual(result['activity_id'],'ride')
  self.assertNotIn('raw_json',result)
