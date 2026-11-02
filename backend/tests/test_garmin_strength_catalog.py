"""Catalog-backed planning and payload compatibility without live Garmin calls."""
import unittest
from app.garmin_strength_catalog import catalog,repertoire,planner_exercises,SPECS
from app.garmin_strength import mapping_blockers
from app.garmin_workout_mapping import workout_payload
from app.training import workout_definition
from app.training_prescriptions import strength
from app.chat_access import questions_only
from app.ai_tools import execute_tool


class StrengthCatalogTests(unittest.TestCase):
 def answers(self,equipment,blocked=()):
  return dict(sports=['strength'],blocked_sports=[],equipment=equipment,blocked_movements=list(blocked),experience={'strength':'regular'},priority='strength')
 def test_entire_repertoire_is_paginated_without_losing_entries(self):
  rows=[];offset=0
  while True:
   page=catalog({'limit':100,'offset':offset});rows.extend(page['records'])
   if page['next_offset'] is None:break
   offset=page['next_offset']
  self.assertEqual(len(rows),len(repertoire()));self.assertEqual(page['catalog_count'],1527)
  self.assertEqual(len(page['categories']),47)
  self.assertEqual({(r['category'],r['exercise']) for r in rows},{(c,e) for _,c,e in repertoire()})
 def test_reviewed_subset_is_exact_and_every_exercise_exports(self):
  self.assertEqual(len(planner_exercises()),len(SPECS))
  for exercise in planner_exercises():
   d=dict(sport='strength',title='Fictional strength',duration_minutes=30,exercises=[dict(exercise,sets=2,repetitions=8,rest_seconds=60)])
   with self.subTest(exercise=exercise['id']):
    self.assertEqual(mapping_blockers(d),[])
    payload,_=workout_payload(d,'test-only');work=payload['workoutSegments'][0]['workoutSteps'][0]
    self.assertEqual(work['category'],exercise['garmin_category']);self.assertEqual(work['exerciseName'],exercise['garmin_exercise'])
 def test_generated_plans_obey_equipment_restrictions_and_export(self):
  for equipment in (['bodyweight'],['dumbbells'],['bands'],['gym'],['barbell'],['bodyweight','pull_up_bar','dip_bars']):
   for blocked in ([],['push']):
    with self.subTest(equipment=equipment,blocked=blocked):
     answers=self.answers(equipment,blocked)
     base=workout_definition('strength_foundation',45,answers)
     d=strength(base,{'strength_capacity':{'pull_up_reps':5,'dip_reps':5}},answers)
     self.assertTrue(all(e['equipment'] in equipment and e['movement'] not in blocked for e in d['exercises']))
     self.assertEqual(mapping_blockers(d),[]);workout_payload(d,'test-only')
     self.assertNotIn('chair_squat',{e['id'] for e in d['exercises']})
     self.assertNotIn('bodyweight_hinge',{e['id'] for e in d['exercises']})
 def test_unknown_or_zero_bar_capacity_does_not_create_invented_assistance(self):
  answers=self.answers(['bodyweight','pull_up_bar','dip_bars']);base=workout_definition('strength_foundation',60,answers)
  with self.assertRaisesRegex(ValueError,'Confirm comfortable'):strength(base,{},answers)
  d=strength(base,{'strength_capacity':{'pull_up_reps':0,'dip_reps':0}},answers)
  self.assertFalse(any(e['equipment'] in ('pull_up_bar','dip_bars') for e in d['exercises']))
  workout_payload(d,'test-only')
 def test_insufficient_allowed_movements_still_block(self):
  with self.assertRaises(ValueError):workout_definition('strength_foundation',45,self.answers(['bodyweight'],['squat','hinge','push']))
 def test_full_catalog_search_and_reviewed_filter_are_available_to_questions(self):
  with questions_only():
   result=execute_tool('get_garmin_strength_catalog',{'query':'Chair'},None)
   self.assertTrue(result['records']);self.assertTrue(all(r['planning_metadata'] is None for r in result['records']))
   planned=execute_tool('get_garmin_strength_catalog',{'planner_only':True},None)
  self.assertEqual(planned['total_matches'],len(SPECS));self.assertTrue(all(r['planning_metadata'] for r in planned['records']))
  for args in ({'limit':True},{'offset':-1},{'planner_only':'yes'}):
   with self.assertRaises(ValueError):catalog(args)


if __name__=='__main__':unittest.main()
