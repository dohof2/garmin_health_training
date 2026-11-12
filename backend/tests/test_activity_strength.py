import json,tempfile,unittest
from pathlib import Path
from app.database import connect,migrate
from app.activity_strength import exercises

class RecordedStrengthTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  with connect(self.path) as c:c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,raw_json) VALUES('strength','garmin_export','strength_training','2026-11-05T08:00:00Z','{}')")
 def raw(self,data):
  with connect(self.path) as c:c.execute('UPDATE activities SET raw_json=?',(json.dumps(data),))
 def test_recorded_summary_identifies_exact_curated_exercises(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','subCategory':'AIR_SQUAT','sets':2,'reps':20},{'category':'UNKNOWN','sets':1,'reps':0}]})
  result=exercises('strength',self.path)
  self.assertEqual([{k:e[k] for k in ('id','name','sets','repetitions')} for e in result['exercises']],[{'id':'air_squat','name':'Air Squat','sets':2,'repetitions':20}])
 def test_fit_active_sets_are_grouped_without_counting_rest_or_alternatives(self):
  self.raw({'fit_messages':{'set_mesgs':[{'set_type':'active','category':['squat','squat'],'category_subtype':[100,100],'repetitions':10},{'set_type':'active','category':['squat'],'category_subtype':[100],'repetitions':12},{'set_type':'rest','category':['squat'],'category_subtype':[100],'repetitions':0}]}})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['sets'],2);self.assertEqual(result[0]['repetitions'],22)
 def test_missing_exercise_identity_is_not_inferred_from_the_plan(self):
  self.assertEqual(exercises('strength',self.path)['exercises'],[])
 def test_generic_calf_category_survives_missing_summary_subtype(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','subCategory':'AIR_SQUAT','sets':2,'reps':20},{'category':'CALF_RAISE','sets':2,'reps':20}]})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(len(result),2)
  self.assertEqual({k:result[1][k] for k in ('id','name','sets','repetitions')},{'id':'calf_raise','name':'Calf Raise','sets':2,'repetitions':20})
 def test_fit_calf_sets_without_subtypes_are_not_dropped_or_tripled(self):
  self.raw({'fit_messages':{'set_mesgs':[{'set_type':'active','category':['calf_raise']*3,'repetitions':10},{'set_type':'active','category':['calf_raise']*3,'category_subtype':None,'repetitions':10}]}})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual([{k:e[k] for k in ('id','name','sets','repetitions')} for e in result],[{'id':'calf_raise','name':'Calf Raise','sets':2,'repetitions':20}])
 def test_unspecified_squat_variant_is_not_guessed(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','sets':2,'reps':20}]})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(result[0]['identity_status'],'category_only');self.assertIsNone(result[0]['id'])
  self.assertEqual(result[0]['repetitions'],20)
 def test_partial_summary_is_supplemented_from_fit_without_double_counting(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','subCategory':'AIR_SQUAT','sets':2,'reps':20}],
            'fit_messages':{'set_mesgs':[{'set_type':'active','category':'squat','category_subtype':100,'repetitions':10},{'set_type':'active','category':'calf_raise','repetitions':10}]}})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(len(result),2);self.assertEqual(result[0]['sets'],2);self.assertEqual(result[0]['repetitions'],20)
  self.assertEqual(result[1]['id'],'calf_raise');self.assertEqual(result[1]['sets'],1)
 def test_generic_summary_uses_fit_identity_without_counting_same_sets_twice(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','sets':2,'reps':20}],
            'fit_messages':{'set_mesgs':[{'set_type':1,'category':'squat','category_subtype':100,'repetitions':10}]}})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['id'],'air_squat');self.assertEqual(result[0]['sets'],2)
 def test_unknown_protocol_codes_stay_visible_without_invented_muscle_mapping(self):
  self.raw({'summarizedExerciseSets':[{'category':64222,'subCategory':12345,'sets':3,'reps':24}]})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['repetitions'],24)
  self.assertIsNone(result[0]['id']);self.assertIn('12345',result[0]['name'])
 def test_fit_numeric_enums_and_zero_subtype_are_valid(self):
  from garmin_fit_sdk import Profile
  category=next(k for k,v in Profile['types']['exercise_category'].items() if v=='squat')
  self.raw({'fit_messages':{'set_mesgs':[{'set_type':1,'category':category,'category_subtype':0,'repetitions':10}]}})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(result[0]['id'],'machine_leg_press');self.assertEqual(result[0]['repetitions'],10)
 def test_zero_rep_unknown_placeholder_does_not_promote_an_alternative_guess(self):
  self.raw({'fit_messages':{'set_mesgs':[{'set_type':'active','category':['unknown','curl','bench_press'],'repetitions':0}]}})
  self.assertEqual(exercises('strength',self.path)['exercises'],[])
 def test_entire_installed_garmin_catalog_survives_summary_decoding(self):
  from app.garmin_strength_catalog import repertoire
  catalog=repertoire()
  self.raw({'summarizedExerciseSets':[{'category':c,'subCategory':e,'sets':1,'reps':10} for _,c,e in catalog]})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual({(e['category'],e['exercise']) for e in result},{(c,e) for _,c,e in catalog})
 def test_every_garmin_category_survives_missing_subtype(self):
  from app.garmin_strength_catalog import repertoire
  categories={c for _,c,_ in repertoire()}
  self.raw({'summarizedExerciseSets':[{'category':c,'sets':1,'reps':10} for c in categories]})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual({e['category'] for e in result},categories)
 def test_multiple_fit_variants_preserve_summary_totals_and_variant_identities(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','sets':2,'reps':20}],
            'fit_messages':{'set_mesgs':[{'set_type':1,'category':'squat','category_subtype':100,'repetitions':10},{'set_type':1,'category':'squat','category_subtype':0,'repetitions':10}]}})
  result=exercises('strength',self.path)['exercises']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['sets'],2);self.assertEqual(result[0]['repetitions'],20)
  self.assertEqual({v['id'] for v in result[0]['recorded_variants']},{'air_squat','machine_leg_press'})
 def test_garmin_corrected_names_do_not_duplicate_old_fit_sets(self):
  self.raw({'summarizedExerciseSets':[{'category':'SQUAT','subCategory':'AIR_SQUAT','sets':2,'reps':20}],
            'fit_messages':{'set_mesgs':[{'set_type':1,'category':'squat','category_subtype':0,'repetitions':10},{'set_type':1,'category':'squat','category_subtype':0,'repetitions':10}]}})
  result=exercises('strength',self.path)
  self.assertEqual(len(result['exercises']),1);self.assertEqual(result['exercises'][0]['sets'],2)
  self.assertEqual(result['exercises'][0]['id'],'air_squat');self.assertTrue(result['warnings'])
