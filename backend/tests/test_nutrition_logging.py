"""App chat logs understood consumption once, without a review/save round trip."""
import copy
import json
import tempfile
import unittest
from datetime import date,datetime,timezone
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.nutrition import daily_status,remove_meal
from app.nutrition_chat import chat
from app.ai_chat import chat_stream
from app.nutrition_logging import log_result,consumption_report

DAY='2026-10-25';TZ='Asia/Jerusalem';NOW=datetime(2026,10,25,10,tzinfo=timezone.utc)
FOODS={'reply':'Eggs and avocado understood.','ingredients':[
 {'name':'Eggs','grams_low':95,'grams_high':105,'grams_proposed':100,'meal_type':'breakfast','question':'Confirm?'},
 {'name':'Avocado','grams_low':60,'grams_high':90,'grams_proposed':75,'meal_type':'breakfast','question':'Confirm?'}],
 'uncertainties':['Portions estimated'],'model':'fixture','target_request':None}


class NutritionLoggingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  self.clock=patch('app.nutrition_logging.datetime',wraps=datetime).start();self.clock.now.return_value=NOW;self.addCleanup(patch.stopall)
 def run_chat(self,message='I ate eggs and avocado',operation='meal-message',response=None,**kw):
  with patch('app.nutrition_chat.analyze_food',return_value=copy.deepcopy(response or FOODS)),patch('app.nutrition_chat.search_foods',return_value={'foods':[],'status':'no_matches'}):
   return chat(message,DAY,TZ,path=self.path,auto_log=True,operation_id=operation,**kw)
 def meals(self,day=DAY):return daily_status(date.fromisoformat(day),TZ,self.path)['meals']
 def test_understood_eggs_avocado_are_saved_without_review(self):
  result=self.run_chat();self.assertTrue(result['logged']);self.assertIn('Logged breakfast',result['reply']);self.assertNotIn('Confirm?',result['reply'])
  meals=self.meals();self.assertEqual(len(meals),1);items=meals[0]['items']
  self.assertEqual([(i['name'],i['quantity']) for i in items],[('Eggs',100),('Avocado',75)])
  self.assertGreater(meals[0]['totals']['calories_kcal']['known_total'],0);self.assertEqual(meals[0]['totals']['calories_kcal']['missing_items'],0)
  self.assertTrue(all(i['detail']['portion_basis']=='estimated' for i in items));self.assertIn('Generic food reference',items[0]['detail']['uncertainty'])
 def test_same_request_retries_return_receipt_without_model_or_duplicate(self):
  first=self.run_chat()
  with patch('app.nutrition_chat.analyze_food',side_effect=AssertionError('No repeat inference')):
   second=chat('I ate eggs and avocado',DAY,TZ,path=self.path,auto_log=True,operation_id='meal-message')
  self.assertTrue(second['replayed']);self.assertEqual(first['saved_meals'],second['saved_meals']);self.assertEqual(len(self.meals()),1)
  with self.assertRaisesRegex(ValueError,'different nutrition request'):self.run_chat('I ate a banana')
 def test_identical_food_report_in_a_new_message_is_a_distinct_meal(self):
  self.run_chat(operation='first');self.run_chat(operation='second');self.assertEqual(len(self.meals()),2)
 def test_retry_after_user_removal_does_not_resurrect_meal(self):
  self.run_chat();meal=self.meals()[0];remove_meal(meal['id'],meal['revision'],True,self.path)
  result=self.run_chat();self.assertEqual(self.meals(),[]);self.assertTrue(result['deleted']);self.assertFalse(result['logged'])
 def test_questions_negation_future_and_hypotheticals_do_not_log(self):
  for message in ('What if I ate eggs and avocado?','I did not eat eggs','I will eat eggs','How many calories in the eggs I ate?','Do not log this meal','Should I eat eggs?','I am planning breakfast'):
   with self.subTest(message=message):
    result=self.run_chat(message,operation=message);self.assertFalse(result.get('logged',False))
  self.assertEqual(self.meals(),[])
 def test_multiple_meal_groups_saved_together(self):
  foods=copy.deepcopy(FOODS);foods['ingredients'][1]['meal_type']='lunch'
  result=self.run_chat('I ate eggs for breakfast and avocado at lunch',response=foods)
  self.assertEqual(len(result['saved_meals']),2);self.assertEqual({m['meal_type'] for m in self.meals()},{'breakfast','lunch'})
 def test_failure_in_second_meal_rolls_back_both_meals_and_receipt(self):
  from app import nutrition_logging
  foods=copy.deepcopy(FOODS);foods['ingredients'][1]['meal_type']='lunch';original=nutrition_logging._save_meal;count=0
  def fail(c,*args):
   nonlocal count
   count+=1
   if count==2:raise ValueError('Fictional storage failure')
   return original(c,*args)
  with patch('app.nutrition_logging._save_meal',side_effect=fail),self.assertRaises(ValueError):self.run_chat(response=foods)
  self.assertEqual(self.meals(),[])
  with connect(self.path) as c:self.assertEqual(c.execute('SELECT count(*) FROM nutrition_chat_operations').fetchone()[0],0)
 def test_unknown_nutrients_are_logged_as_missing_not_zero_or_a_random_brand(self):
  foods=copy.deepcopy(FOODS);foods['ingredients']=[{'name':'Unidentified family stew','grams_low':200,'grams_high':300,'grams_proposed':250,'question':'','meal_type':'dinner'}]
  result=self.run_chat('I ate my family stew',response=foods);self.assertTrue(result['logged']);self.assertIn('partial',result['reply'])
  meal=self.meals()[0];self.assertEqual(meal['totals']['calories_kcal']['missing_items'],1);self.assertIsNone(meal['items'][0]['calories_kcal'])
  self.assertIn('Unidentified family stew is missing calories, protein, fat, carbs',result['partial_explanation'])
  self.assertIn('no usable nutrition match or estimate was available',result['reply'])
  self.assertEqual(meal['partial_explanation'],result['partial_explanation'])
 def test_partial_source_names_only_missing_values_and_zero_is_complete(self):
  foods=copy.deepcopy(FOODS)
  foods['ingredients']=[{'name':'Family vegetable soup','grams_low':200,'grams_high':200,'grams_proposed':200,'question':'','meal_type':'dinner',
   'nutrients_per_100g':{'calories_kcal':40,'protein_grams':None,'fat_grams':0,'carbohydrate_grams':8},'estimate_assumptions':'Family recipe; protein unknown.'}]
  result=self.run_chat('I ate my vegetable soup',response=foods)
  self.assertIn('Family vegetable soup is missing protein because',result['partial_explanation'])
  self.assertIn('not supplied in the saved nutrition data',result['partial_explanation'])
  self.assertNotIn('missing fat',result['partial_explanation'])
  self.assertIn('Edit meal',result['reply'])
  meal=self.meals()[0]
  from app.nutrition import save_meal
  save_meal({'eaten_at':meal['eaten_at'],'timezone':TZ,'meal_type':'dinner','items':[
   {'name':'Family vegetable soup','quantity':200,'unit':'g','nutrients':{'calories_kcal':80,'protein_grams':3,'fat_grams':0,'carbohydrate_grams':16},'source':'Recipe calculation','portion_basis':'estimated'}]},'repair',meal['id'],meal['revision'],self.path)
  self.assertEqual(self.meals()[0]['partial_explanation'],'')
 def test_estimates_are_scaled_saved_and_added_to_daily_intake(self):
  foods=copy.deepcopy(FOODS)
  foods['ingredients']=[{'name':name,'grams_low':grams,'grams_high':grams,'grams_proposed':grams,'question':'','meal_type':'lunch',
   'nutrients_per_100g':{'calories_kcal':120,'protein_grams':4,'fat_grams':2,'carbohydrate_grams':21},'estimate_assumptions':'Cooked weight; typical recipe.'}
   for name,grams in [('Couscous',250),('Vegetable soup',300),('Malawach',130),('Cottage cheese, 3%',125)]]
  result=self.run_chat('I ate couscous, soup, malawach and cottage cheese',response=foods)
  self.assertEqual(result['logged_totals']['calories_kcal'],{'known_total':966,'missing_items':0})
  self.assertIn('Added 966 kcal to your daily intake',result['reply'])
  status=daily_status(date.fromisoformat(DAY),TZ,self.path)
  self.assertEqual(status['totals']['calories_kcal'],result['logged_totals']['calories_kcal'])
  self.assertEqual(status['totals']['protein_grams']['known_total'],32.2)
  for item in self.meals()[0]['items']:
   self.assertIn('AI nutrition estimate',item['source']);self.assertIn('Cooked weight',item['detail']['uncertainty'])
  self.run_chat('I ate couscous, soup, malawach and cottage cheese',response=foods)
  self.assertEqual(daily_status(date.fromisoformat(DAY),TZ,self.path)['totals']['calories_kcal']['known_total'],966)
 def test_sourced_nutrients_take_priority_over_model_estimates(self):
  foods=copy.deepcopy(FOODS)
  foods['ingredients'][0]['nutrients_per_100g']={'calories_kcal':1,'protein_grams':1,'fat_grams':1,'carbohydrate_grams':1}
  self.run_chat(response=foods)
  item=self.meals()[0]['items'][0]
  self.assertGreater(item['calories_kcal'],1);self.assertIn('USDA',item['source'])
 def test_invalid_estimate_does_not_save_any_part_of_meal(self):
  for value in (-1,True,float('nan'),float('inf'),901):
   foods=copy.deepcopy(FOODS);foods['ingredients'][1]['name']='Vegetable soup'
   foods['ingredients'][1]['nutrients_per_100g']={'calories_kcal':value,'protein_grams':1,'fat_grams':1,'carbohydrate_grams':1}
   with self.subTest(value=value),self.assertRaises(ValueError):self.run_chat(response=foods)
  self.assertEqual(self.meals(),[])
 def test_yesterday_and_explicit_dates_preserve_local_day(self):
  result=self.run_chat('I ate eggs yesterday');self.assertEqual(result['context_date'],'2026-10-24');self.assertEqual(len(self.meals('2026-10-24')),1)
  result=self.run_chat('Log this meal on 2026-10-23',operation='earlier');self.assertEqual(result['context_date'],'2026-10-23');self.assertEqual(len(self.meals('2026-10-23')),1)
 def test_app_shared_chat_emits_saved_confirmation_only_after_storage(self):
  with patch('app.nutrition_chat.analyze_food',return_value=copy.deepcopy(FOODS)),patch('app.nutrition_chat.search_foods',return_value={'foods':[]}):
   events=[json.loads(e) for e in chat_stream('I ate eggs and avocado',path=self.path,timezone_name=TZ,nutrition_context={'day':DAY},operation_id='shared-chat',message_time=NOW)]
  self.assertEqual(events[-1]['type'],'complete',events)
  result=next(e['evidence']['nutrition'] for e in events if e['type']=='tool')
  self.assertTrue(result['logged']);self.assertTrue(any(e['type']=='delta' and 'Logged breakfast' in e['text'] for e in events));self.assertEqual(len(self.meals()),1)
 def test_hebrew_consumption_logs_but_question_does_not(self):
  self.assertTrue(consumption_report('אכלתי ביצים ואבוקדו'))
  self.assertFalse(consumption_report('כמה קלוריות יש בביצים שאכלתי?'))
  result=self.run_chat('אכלתי ביצים ואבוקדו');self.assertIn('נשמר ביומן',result['reply']);self.assertEqual(len(self.meals()),1)
 def test_explicit_log_it_saves_previously_understood_pending_foods(self):
  pending=copy.deepcopy(FOODS['ingredients'])
  for item in pending:item.pop('portion_confirmed',None)
  result=self.run_chat('Log it',pending_foods=pending)
  self.assertTrue(result['logged']);self.assertEqual(len(self.meals()),1)
 def test_direct_app_endpoint_logs_without_confirmed_parameter(self):
  from fastapi.testclient import TestClient
  from app.main import app
  body={'message':'I ate eggs and avocado','day':DAY,'timezone':TZ,'operation_id':'endpoint-message'}
  with patch('app.database.database_path',return_value=self.path),patch('app.nutrition_chat.analyze_food',return_value=copy.deepcopy(FOODS)),patch('app.nutrition_chat.search_foods',return_value={'foods':[]}):
   with TestClient(app) as client:
    first=client.post('/api/nutrition/chat',json=body);self.assertEqual(first.status_code,200,first.text);self.assertTrue(first.json()['logged'])
    second=client.post('/api/nutrition/chat',json=body);self.assertTrue(second.json()['replayed'])
  self.assertEqual(len(self.meals()),1)
 def test_receipt_survives_backup_restore_and_respects_filtered_export(self):
  from app.exports import create_backup,restore_backup,export_json
  self.run_chat();backup=Path(self.tmp.name)/'backup.zip';restored=Path(self.tmp.name)/'restored.sqlite'
  create_backup(backup,path=self.path);restore_backup(backup,restored)
  with patch('app.nutrition_chat.analyze_food',side_effect=AssertionError('Replay must not invoke model')):
   result=chat('I ate eggs and avocado',DAY,TZ,path=restored,auto_log=True,operation_id='meal-message')
  self.assertTrue(result['replayed'])
  exported=Path(self.tmp.name)/'range.json';export_json(exported,date(2026,10,24),date(2026,10,24),self.path)
  self.assertEqual(json.loads(exported.read_text())['tables']['nutrition_chat_operations'],[])
