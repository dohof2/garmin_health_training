"""Corrections change one recorded food, retaining the rest of the meal exactly."""
import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.nutrition import save_meal,daily_status,NUTRIENTS
from app.nutrition_chat import chat
from app.nutrition_correction import apply_correction,correction_intent
from app.chat_access import nutrition_writes

DAY='2026-10-29';TZ='Asia/Jerusalem'
class IngredientCorrectionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  item=lambda name,values:{'name':name,'quantity':100,'unit':'g','nutrients':values,'source':'Fixture','portion_basis':'estimated'}
  self.meal=save_meal({'eaten_at':DAY+'T13:00:00+02:00','timezone':TZ,'meal_type':'lunch','items':[
   item('Cucumber',{k:10 for k in NUTRIENTS}),item('Tomato',{k:20 for k in NUTRIENTS}),item('Tahini sauce',{k:None for k in NUTRIENTS})]},'original',path=self.path)
  self.selection={'meal_id':self.meal['id'],'item_id':self.meal['items'][2]['id'],'expected_revision':1,'keep_quantity':False}
  self.food={'name':'Raw tahini paste','grams_low':50,'grams_high':70,'grams_proposed':60,'meal_type':'lunch','question':'','estimate_assumptions':'Four tablespoons estimated at 15 g each.'}
  self.response={'ingredients':[self.food],'uncertainties':[],'reply':'Correcting the tahini.','food_correction':self.selection}
 def run_chat(self,message='Actually it was raw tahini, 4 spoons',operation='correct',response=None,**kw):
  with patch('app.nutrition_correction.analyze_food',return_value=copy.deepcopy(response or self.response)) as model:
   result=chat(message,DAY,TZ,path=self.path,auto_log=True,operation_id=operation,**kw)
  return result,model
 def status(self):return daily_status(date.fromisoformat(DAY),TZ,self.path)
 def test_identity_correction_changes_existing_item_and_recalculates(self):
  result,model=self.run_chat()
  meal=self.status()['meals'][0]
  self.assertTrue(result['logged']);self.assertTrue(result['updated']);self.assertEqual(len(self.status()['meals']),1)
  self.assertEqual(meal['id'],self.meal['id']);self.assertEqual(meal['revision'],2)
  self.assertEqual(meal['items'][:2],self.meal['items'][:2])
  corrected=meal['items'][2];self.assertEqual(corrected['id'],self.meal['items'][2]['id'])
  self.assertEqual(corrected['name'],'Raw tahini paste');self.assertEqual(corrected['quantity'],60)
  self.assertIn('Generic food reference',corrected['detail']['uncertainty']);self.assertIn('Four tablespoons',corrected['detail']['uncertainty'])
  self.assertAlmostEqual(corrected['calories_kcal'],388.8);self.assertEqual(meal['totals']['calories_kcal']['missing_items'],0)
  self.assertIn('no duplicate',result['reply']);self.assertTrue(model.call_args.kwargs['review_context']['correction_candidates'])
 def test_selected_provider_schema_and_parser_support_real_corrections(self):
  import io,json
  from app.food_vision import analyze_food
  response={**copy.deepcopy(self.response),'target_request':None}
  with patch('app.food_vision.get_ai_settings',return_value={'active_provider':'ollama','ollama_model':'fixture'}),patch('app.food_vision.urlopen',return_value=io.BytesIO(json.dumps({'message':{'content':json.dumps(response)}}).encode())) as request:
   result=analyze_food(message='Correct tahini',path=self.path,conversational=True,review_context={'correction_candidates':[self.selection]})
  self.assertEqual(result['food_correction'],self.selection)
  self.assertIn('food_correction',json.loads(request.call_args.args[0].data)['format']['properties'])
 def test_fenced_json_food_response_is_accepted(self):
  import io,json
  from app.food_vision import analyze_food
  response={**copy.deepcopy(self.response),'target_request':None}
  answer='```json\n'+json.dumps(response)+'\n```'
  with patch('app.food_vision.get_ai_settings',return_value={'active_provider':'ollama','ollama_model':'fixture'}),patch('app.food_vision.urlopen',return_value=io.BytesIO(json.dumps({'message':{'content':answer}}).encode())):
   result=analyze_food(message='Correct tahini',path=self.path,conversational=True,review_context={'correction_candidates':[self.selection]})
  self.assertEqual(result['food_correction'],self.selection)
 def test_invalid_estimate_is_not_reported_as_connection_failure(self):
  import io,json
  from app.food_vision import analyze_food
  response={**copy.deepcopy(self.response),'target_request':None};response['ingredients'][0]['grams_low']=-1
  with patch('app.food_vision.get_ai_settings',return_value={'active_provider':'ollama','ollama_model':'fixture'}),patch('app.food_vision.urlopen',return_value=io.BytesIO(json.dumps({'message':{'content':json.dumps(response)}}).encode())):
   with self.assertRaisesRegex(ValueError,'Portion lower estimate') as caught:analyze_food(message='Correct tahini',path=self.path,conversational=True,review_context={'correction_candidates':[self.selection]})
  self.assertNotIn('unavailable',str(caught.exception))
 def test_retry_never_reinfers_or_duplicates(self):
  self.run_chat()
  with patch('app.nutrition_correction.analyze_food',side_effect=AssertionError('Must replay')):
   result=chat('Actually it was raw tahini, 4 spoons',DAY,TZ,path=self.path,auto_log=True,operation_id='correct')
  self.assertTrue(result['replayed']);self.assertEqual(self.status()['meals'][0]['revision'],2)
 def test_stale_correction_rejected_without_changing_any_item(self):
  self.run_chat();before=self.status()
  with self.assertRaisesRegex(ValueError,'changed'):apply_correction('Update tahini',DAY,TZ,'meal','stale',self.selection,self.food,self.path)
  self.assertEqual(self.status(),before)
 def test_ambiguous_clarification_makes_no_write(self):
  result,_=self.run_chat(response={'food_correction':None,'ingredients':[],'reply':'Which sauce should I correct?'})
  self.assertFalse(result['logged']);self.assertEqual(self.status()['meals'][0]['revision'],1)
 def test_model_cannot_edit_a_meal_outside_candidates(self):
  response=copy.deepcopy(self.response);response['food_correction']['item_id']='not-an-item'
  with self.assertRaisesRegex(ValueError,'existing meal ingredient'):self.run_chat(response=response)
  self.assertEqual(self.status()['meals'][0]['revision'],1)
 def test_existing_portion_is_retained_when_only_preparation_changes(self):
  self.selection['keep_quantity']=True
  result,_=self.run_chat('Actually it was raw tahini')
  self.assertTrue(result['updated']);self.assertEqual(self.status()['meals'][0]['items'][2]['quantity'],100)
 def test_short_raw_spoons_answer_can_still_correct_referenced_saved_meal(self):
  result,_=self.run_chat('raw, 4 spoons',saved_meals=[{'id':self.meal['id'],'revision':1}])
  self.assertTrue(result['updated']);self.assertEqual(self.status()['meals'][0]['items'][2]['name'],'Raw tahini paste')
 def test_unknown_nutrients_remain_partial_after_identity_change(self):
  self.food['name']='Family sauce, corrected preparation'
  result,_=self.run_chat();self.assertTrue(result['updated'])
  self.assertIsNone(self.status()['meals'][0]['items'][2]['calories_kcal'])
  self.assertIn('partial',result['reply'])
 def test_explicit_grams_and_identity_do_not_only_change_old_portion(self):
  result,_=self.run_chat('Correct Tahini sauce to raw tahini paste, 60 grams')
  self.assertTrue(result['updated']);self.assertEqual(self.status()['meals'][0]['items'][2]['name'],'Raw tahini paste')
 def test_transport_write_authorizer_is_respected(self):
  def reject(c):raise ValueError('Write authorization revoked')
  with nutrition_writes(reject),self.assertRaisesRegex(ValueError,'revoked'):self.run_chat()
  self.assertEqual(self.status()['meals'][0]['revision'],1)
 def test_questions_denials_and_new_food_reports_are_not_edits(self):
  for message in ('What is raw tahini?','What if I replaced the sauce?','Do not change the tahini','I ate raw tahini','How many calories are in raw tahini?'):
   self.assertFalse(correction_intent(message),message)
 def test_old_chat_reference_uses_fresh_tools_then_revision_checks_write(self):
  with connect(self.path) as c:c.execute('UPDATE meals SET revision=2 WHERE id=?',(self.meal['id'],))
  response=copy.deepcopy(self.response);response['food_correction']['expected_revision']=2
  result,model=self.run_chat(saved_meals=[{'id':self.meal['id'],'revision':1}],response=response)
  self.assertTrue(result['updated']);self.assertEqual(self.status()['meals'][0]['revision'],3)
  self.assertEqual(model.call_args.kwargs['review_context']['correction_candidates'][0]['expected_revision'],2)
 def test_previous_day_reference_does_not_carry_into_today(self):
  refs=[{'id':self.meal['id'],'revision':1}]
  with patch('app.nutrition_correction.analyze_food',side_effect=AssertionError('No old-day inference')):
   result=chat('Actually it was raw tahini', '2026-10-30',TZ,path=self.path,auto_log=True,operation_id='next-day',saved_meals=refs)
  self.assertFalse(result['logged']);self.assertEqual(self.status()['meals'][0]['revision'],1)
