from __future__ import annotations
import base64
import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.database import connect,migrate
from app.main import app
from app.exports import export_csv,export_json,create_backup,restore_backup
from app.nutrition import NUTRIENTS,catalog,food_search,preview_meal,save_meal,remove_meal,daily_status,save_library,list_library,scale_library,target_preview,save_target,target_history
from app.food_vision import analyze_photo,validate_image

ITEM={'name':'Known label portion','quantity':1,'unit':'serving','nutrients':{'calories_kcal':200,'protein_grams':10,'fat_grams':4,'carbohydrate_grams':31},'source':'Synthetic label fixture','portion_basis':'label_serving','uncertainty':''}
MEAL={'eaten_at':'2026-10-10T23:30:00+03:00','timezone':'Asia/Jerusalem','meal_type':'dinner','notes':'Synthetic','items':[ITEM]}
TARGET={'method':'manual','effective_from':'2026-10-10','calories_kcal':2000,'protein_grams':100,'fat_grams':60,'carbohydrate_grams':265}
PNG='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSVEAAAAASUVORK5CYII='

class NutritionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';migrate(self.path)
 def tearDown(self):self.temp.cleanup()
 def save(self,payload=None,operation='one'):return save_meal(copy.deepcopy(payload or MEAL),operation,path=self.path)
 def day(self,day=date(2026,10,10),tz='Asia/Jerusalem'):return daily_status(day,tz,self.path)
 def test_label_totals_and_explicit_unknowns(self):
  self.save();status=self.day();self.assertEqual(status['totals']['calories_kcal']['known_total'],200);self.assertIsNone(status['remaining']['calories_kcal'])
  payload=copy.deepcopy(MEAL);payload['items'][0]['nutrients']['protein_grams']=None
  self.save(payload,'two');self.assertEqual(self.day()['totals']['protein_grams'],{'known_total':10,'missing_items':1})
 def test_usda_known_portion_uses_source_not_model_values(self):
  food=next(f for f in catalog()['foods'] if all(f[k] is not None for k in NUTRIENTS))
  item={'food_id':food['id'],'quantity':150,'unit':'g','portion_basis':'weighed','nutrients':{'calories_kcal':999}}
  preview=preview_meal({**MEAL,'items':[item]})
  self.assertAlmostEqual(preview['items'][0]['calories_kcal'],food['calories_kcal']*1.5)
  self.assertEqual(preview['items'][0]['detail']['food_id'],food['id']);self.assertTrue(preview['items'][0]['detail']['nutrition_is_estimated'])
  self.assertIn(food,food_search(food['name'])['foods'])
 def test_catalog_never_saves_negative_source_nutrients_as_zero(self):
  flagged=[f for f in catalog()['foods'] if f.get('warnings')]
  self.assertEqual(len(flagged),10)
  for food in catalog()['foods']:
   self.assertTrue(all(food[k] is None or food[k]>=0 for k in NUTRIENTS))
  preview=preview_meal({**MEAL,'items':[{'food_id':flagged[0]['id'],'quantity':100,'unit':'g','portion_basis':'weighed'}]})
  self.assertIsNone(preview['items'][0]['carbohydrate_grams']);self.assertIn('negative',preview['items'][0]['detail']['uncertainty'])
 def test_usda_unknown_nutrients_stay_unknown_and_units_validated(self):
  food=next(f for f in catalog()['foods'] if f['calories_kcal'] is None)
  item={'food_id':food['id'],'quantity':100,'unit':'g','portion_basis':'estimated'}
  self.assertEqual(preview_meal({**MEAL,'items':[item]})['totals']['calories_kcal']['missing_items'],1)
  with self.assertRaises(ValueError):preview_meal({**MEAL,'items':[{**item,'unit':'ml'}]})
 def test_per_100g_label_edit_scales_and_preserves_input_values(self):
  item={**ITEM,'quantity':150,'unit':'g','nutrient_basis':'per_100g'}
  meal=self.save({**MEAL,'items':[item]})
  self.assertEqual(meal['totals']['calories_kcal']['known_total'],300)
  self.assertEqual(meal['items'][0]['detail']['input_values']['calories_kcal'],200)
  item['quantity']=50
  edited=save_meal({**MEAL,'items':[item]},'edit',meal['id'],1,self.path)
  self.assertEqual(edited['totals']['calories_kcal']['known_total'],100)
  with self.assertRaises(ValueError):preview_meal({**MEAL,'items':[{**item,'unit':'ml'}]})
 def test_strict_validation_and_atomic_rejection(self):
  for changes in [{'quantity':True},{'quantity':float('inf')},{'unit':'cups'},{'portion_basis':'certain'},{'nutrients':{'protein_grams':-1}},{'food_id':'unknown'},{'surprise':'bad'}]:
   with self.assertRaises(ValueError):self.save({**MEAL,'items':[{**ITEM,**changes}]})
  self.assertEqual(self.day()['meals'],[])
  with self.assertRaises(ValueError):self.save({**MEAL,'eaten_at':'2026-10-10T18:00:00'})
  with self.assertRaises(ValueError):self.save({**MEAL,'timezone':'Invalid/Timezone'})
 def test_create_retry_deduplicates_and_rejects_changed_payload(self):
  first=self.save();self.assertEqual(self.save()['id'],first['id']);self.assertEqual(len(self.day()['meals']),1)
  with self.assertRaisesRegex(ValueError,'different meal'):self.save({**MEAL,'notes':'different'})
 def test_edit_revisions_and_stale_rejection(self):
  first=self.save();payload=copy.deepcopy(MEAL);payload['items'][0]['nutrients']['calories_kcal']=250
  result=save_meal(payload,'edit',first['id'],1,self.path)
  self.assertEqual(result['revision'],2);self.assertEqual(result['totals']['calories_kcal']['known_total'],250)
  with self.assertRaises(ValueError):save_meal(payload,'edit',first['id'],1,self.path)
  with connect(self.path) as c:
   snapshots=c.execute('SELECT snapshot_json FROM meal_revisions WHERE meal_id=? ORDER BY revision',(first['id'],)).fetchall()
  self.assertEqual(json.loads(snapshots[0][0])['items'][0]['calories_kcal'],200)
 def test_remove_restore_preserves_history_and_daily_totals(self):
  meal=self.save();remove_meal(meal['id'],1,True,self.path);self.assertEqual(self.day()['totals']['calories_kcal']['known_total'],0)
  self.assertTrue(self.day()['meals'][0]['deleted_at']);remove_meal(meal['id'],2,False,self.path);self.assertEqual(self.day()['totals']['calories_kcal']['known_total'],200)
 def test_local_date_and_dst_boundaries(self):
  payload={**MEAL,'eaten_at':'2026-10-10T00:30:00+03:00'};self.save(payload)
  self.assertEqual(len(self.day()['meals']),1);self.assertEqual(len(self.day(date(2026,10,9),'UTC')['meals']),1)
  self.assertEqual(len(self.day(date(2026,10,10),'UTC')['meals']),0)
  self.save({**MEAL,'eaten_at':'2026-11-01T01:30:00-04:00','timezone':'America/New_York'},'dst1')
  self.save({**MEAL,'eaten_at':'2026-11-01T01:30:00-05:00','timezone':'America/New_York'},'dst2')
  self.assertEqual(len(self.day(date(2026,11,1),'America/New_York')['meals']),2)
 def test_recipe_scaling_and_saved_snapshot(self):
  recipe=save_library({'name':'Four servings','kind':'recipe','servings':4,'items':[copy.deepcopy(ITEM),copy.deepcopy(ITEM)]},path=self.path)
  scaled=scale_library(recipe['id'],1.5,self.path)
  preview=preview_meal({**MEAL,'items':scaled['items']});self.assertEqual(preview['totals']['calories_kcal']['known_total'],150)
  self.assertEqual(len(self.day()['meals']),0)
  with self.assertRaises(ValueError):scale_library(recipe['id'],0,self.path)
  save_library({'name':'Changed','kind':'recipe','servings':2,'items':[ITEM]},recipe['id'],1,self.path)
  self.assertEqual(list_library(self.path)[0]['revision'],2)
  with self.assertRaises(ValueError):save_library({'name':'Stale','kind':'meal','servings':1,'items':[ITEM]},recipe['id'],1,self.path)
 def test_unknown_recipe_nutrients_remain_partial(self):
  item=copy.deepcopy(ITEM);item['nutrients']['fat_grams']=None
  recipe=save_library({'name':'Unknown fat','kind':'meal','servings':2,'items':[item]},path=self.path)
  scaled=scale_library(recipe['id'],1,self.path)
  self.assertIsNone(scaled['items'][0]['nutrients']['fat_grams'])
 def test_target_formula_and_optional_macros(self):
  p=target_preview({'method':'mifflin','effective_from':'2026-10-10','age':30,'weight_kg':80,'height_cm':180,'equation_sex':'male','activity_factor':1.5})
  self.assertEqual(p['assumptions']['resting_kcal'],1780);self.assertEqual(p['calories_kcal'],2670)
  self.assertIsNone(p['protein_grams']);self.assertIn('No Garmin calories',p['assumptions']['exercise_policy'])
  with self.assertRaises(ValueError):target_preview({'method':'mifflin','effective_from':'2026-10-10','age':15,'weight_kg':80,'height_cm':180,'equation_sex':'male','activity_factor':1.5})
 def test_target_preview_does_not_save_and_invalid_target_rejected(self):
  target_preview(TARGET);self.assertEqual(target_history(self.path),[])
  with self.assertRaises(ValueError):save_target({**TARGET,'calories_kcal':float('nan')},0,self.path)
  save_target(TARGET,0,self.path)
  with self.assertRaises(ValueError):save_target(TARGET,0,self.path)
 def test_target_history_preserved_for_logged_day(self):
  save_target(TARGET,0,self.path);self.save()
  save_target({**TARGET,'calories_kcal':2400},1,self.path)
  status=self.day();self.assertEqual(status['target']['calories_kcal'],2000);self.assertEqual(status['remaining']['calories_kcal'],1800)
  self.assertEqual(len(target_history(self.path)),2)
 def test_training_override_requires_accepted_plan_and_uses_local_date(self):
  save_target({**TARGET,'training_calories_kcal':2200},0,self.path)
  with connect(self.path) as c:
   c.execute("INSERT INTO training_plans(id,name,status) VALUES ('p','Test','draft')")
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES ('w','p','running','Test','2026-10-09T22:30:00+00:00','{}')")
  self.assertEqual(self.day()['target']['calories_kcal'],2000)
  with connect(self.path) as c:c.execute("UPDATE training_plans SET status='active' WHERE id='p'")
  self.assertEqual(self.day()['target']['calories_kcal'],2200)
  self.assertEqual(self.day(tz='UTC')['target']['calories_kcal'],2000)
 def test_partial_nutrients_suppress_remaining_only_where_unknown(self):
  save_target(TARGET,0,self.path);payload=copy.deepcopy(MEAL);payload['items'][0]['nutrients']['protein_grams']=None
  self.save(payload);status=self.day();self.assertIsNone(status['remaining']['protein_grams']);self.assertEqual(status['remaining']['calories_kcal'],1800)
 def test_portability_csv_filtered_children_and_backup(self):
  save_target(TARGET,0,self.path);meal=self.save();self.save({**MEAL,'eaten_at':'2026-10-11T14:00:00Z'},'outside')
  save_library({'name':'Reusable','kind':'meal','servings':1,'items':[ITEM]},path=self.path)
  output=Path(self.temp.name)/'out.json';export_json(output,date(2026,10,10),date(2026,10,10),self.path)
  tables=json.loads(output.read_text())['tables'];self.assertEqual(len(tables['meal_items']),1);self.assertEqual(len(tables['meal_revisions']),1)
  csv=Path(self.temp.name)/'out.csv';export_csv('meals',csv,path=self.path);self.assertIn('Synthetic label fixture',csv.read_text())
  backup=Path(self.temp.name)/'backup.zip';create_backup(backup,path=self.path);restored=Path(self.temp.name)/'restored.sqlite3';restore_backup(backup,restored)
  self.assertEqual(daily_status(date(2026,10,10),'Asia/Jerusalem',restored)['meals'][0]['id'],meal['id'])
  self.assertEqual(len(list_library(restored)),1)
 def test_api_isolated_confirm_and_validation(self):
  with patch('app.database.database_path',return_value=self.path):
   with TestClient(app) as client:
    response=client.post('/api/nutrition/preview',json={'payload':MEAL});self.assertEqual(response.status_code,200)
    self.assertEqual(client.post('/api/nutrition/meals',json={'payload':MEAL,'operation_id':'api','confirmed':False}).status_code,422)
    response=client.post('/api/nutrition/meals',json={'payload':MEAL,'operation_id':'api','confirmed':True});self.assertEqual(response.status_code,200)
    self.assertEqual(client.get('/api/nutrition/day',params={'day':'2026-10-10','timezone':'Asia/Jerusalem'}).json()['totals']['calories_kcal']['known_total'],200)
 def test_vision_validated_and_no_nutrients_or_writes(self):
  result={'ingredients':[{'name':'Possible rice','grams_low':100,'grams_high':200,'question':'Cooked? Any oil?'}],'uncertainties':['No scale reference']}
  stream=io.BytesIO(json.dumps({'message':{'content':json.dumps(result)}}).encode())
  with patch('app.food_vision.urlopen',return_value=stream) as request:
   out=analyze_photo(PNG,self.path)
  self.assertEqual(out['ingredients'][0]['grams_high'],200);self.assertNotIn('calories_kcal',out['ingredients'][0])
  self.assertEqual(self.day()['meals'],[]);payload=json.loads(request.call_args[0][0].data);self.assertIn('images',payload['messages'][1]);self.assertNotIn('tools',payload)
  self.assertFalse(payload['think'])
 def test_vision_response_limits_and_non_object_ingredients_rejected(self):
  for response in [{'done_reason':'length','message':{'content':'{}'}},{'message':{'content':json.dumps({'ingredients':['bad'],'uncertainties':[]})}}]:
   with patch('app.food_vision.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
    with self.assertRaises(ValueError):analyze_photo(PNG,self.path)
 def test_vision_failures_do_not_create_meals(self):
  for photo in ('bad',base64.b64encode(b'<svg/>').decode(),'a'*(8*1024*1024+1)):
   with self.assertRaises(ValueError):validate_image(photo)
  with patch('app.food_vision.urlopen',side_effect=TimeoutError):
   with self.assertRaisesRegex(ValueError,'manual logging'):analyze_photo(PNG,self.path)
  with patch('app.food_vision.urlopen',return_value=io.BytesIO(b'{"message":{"content":"not json"}}')):
   with self.assertRaises(ValueError):analyze_photo(PNG,self.path)
  self.assertEqual(self.day()['meals'],[])

if __name__=='__main__':unittest.main()
