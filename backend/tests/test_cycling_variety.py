"""Variant contracts and real planner previews; fictional data, no external writes."""
import copy
import json
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from app.database import connect,migrate
from app.cycling_variants import VARIANTS,options,select
from app.training_prescriptions import endurance
from app.training import save_preferences
from app.training_coach import preview,approve
from test_advanced_cycling import BRIEF,ANS,INITIAL,NOW,TZ


class CyclingVarietyTests(unittest.TestCase):
 def test_all_categories_have_distinct_prescriptions_with_exact_duration(self):
  self.assertEqual(len(VARIANTS),9)
  for kind,variants in VARIANTS.items():
   signatures=[]
   for variant in variants:
    with self.subTest(kind=kind,variant=variant['id']):
     workout=endurance(kind,60,BRIEF,today=NOW.date(),variant=variant['id'])
     self.assertEqual(workout['workout_kind'],kind)
     self.assertEqual(workout['variant_id'],variant['id'])
     self.assertEqual(sum(s['duration_seconds']*s['repetitions'] for s in workout['steps']),3600)
     self.assertEqual(workout['sources'],[variant['source']])
     signatures.append([(s['duration_seconds'],s['target']['lower'],s['target']['upper']) for s in workout['steps']])
   self.assertNotEqual(signatures[0],signatures[1],kind)

 def test_easy_variants_keep_continuous_preference_and_hard_variants_keep_recovery(self):
  for kind in ('recovery','endurance','long_endurance'):
   for variant in options(kind):
    workout=endurance(kind,60,{**BRIEF,'continuous_endurance':True},today=NOW.date(),variant=variant['id'])
    self.assertEqual(len(workout['steps']),1)
    self.assertEqual(workout['steps'][0]['duration_seconds'],3600)
  for kind in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic'):
   for variant in options(kind):
    workout=endurance(kind,60,{**BRIEF,'continuous_endurance':True},today=NOW.date(),variant=variant['id'])
    self.assertEqual(workout['steps'][0]['name'],'Warm-up')
    self.assertEqual(workout['steps'][-1]['name'],'Cool-down')
    repetitions,work,recovery=variant['intervals']
    work_steps=[s for s in workout['steps'] if s['name'].startswith(('Work lap','Sprint','Anaerobic effort'))]
    self.assertEqual(len(work_steps),repetitions)
    self.assertTrue(all(s['duration_seconds']==work for s in work_steps))
    self.assertTrue(all(s['duration_seconds']==recovery for s in workout['steps'] if s['name'].startswith('Recovery')))

 def test_new_categories_keep_recorded_tolerance_gate(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'test.sqlite';migrate(path)
   with connect(path) as c:
    for kind in VARIANTS:
     chosen,evidence=select(c,kind,NOW.date(),TZ)
     self.assertEqual(chosen,options(kind)[0]['id'])
     self.assertEqual(evidence['tolerated_recordings'],0)

 def test_generated_build_weeks_include_distinct_stimuli_and_keep_recovery_weeks_easy(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'test.sqlite';migrate(path)
   with connect(path) as c:
    for window,end in enumerate((date(2026,10,17),date(2026,11,14))):
     for index in range(8):
      day=end-timedelta(days=index//2*7+index%2)
      c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,9000)",(f'{window}-{index}',day.isoformat()+'T07:00:00+00:00'))
   save_preferences(copy.deepcopy(ANS),0,path,INITIAL)
   initial=preview(BRIEF,INITIAL.date(),TZ,path,INITIAL)
   root=approve(initial['brief'],INITIAL.date(),TZ,initial['fingerprint'],path,INITIAL)['plans'][0]['id']
   with connect(path) as c:
    for index in range(2):
     day=NOW-timedelta(days=4+index*3);wid=f'completed-quality-{index}'
     c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,completion_status) VALUES(?,?,'cycling','Fictional tolerated intervals',?,?,'completed')",(wid,root,day.isoformat(),json.dumps(endurance('threshold',60,BRIEF,today=day.date()))))
     c.execute('INSERT INTO training_feedback(workout_id,effort,soreness,pain_or_illness,updated_at) VALUES(?,5,1,0,?)',(wid,day.isoformat()))
   seen=set()
   quality={'tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo','climbing_endurance'}
   for index in range(4,12):
    week=INITIAL.date()+timedelta(weeks=index)
    plan=preview(BRIEF,week,TZ,path,NOW,replace_plan_id=root)
    self.assertEqual(plan['status'],'ready',plan['questions'])
    definitions=[s['definition'] for s in plan['sessions'] if s['sport']=='cycling']
    seen.update('tempo' if d['workout_kind']=='long_tempo' else d['workout_kind'] for d in definitions)
    self.assertLessEqual(sum(d['workout_kind'] in quality for d in definitions),2)
    if (index+1)%4==0:
     self.assertFalse(any(d['workout_kind'] in quality for d in definitions))
    self.assertTrue(all(d.get('variant_id') or d['workout_kind'] in ('long_tempo','climbing_endurance') for d in definitions))
   self.assertTrue({'long_endurance','endurance','threshold','tempo','vo2','sprint','anaerobic'}<=seen,seen)
