"""Corrections change one recorded food, retaining the rest of the meal exactly."""
import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.nutrition import save_meal,daily_status,NUTRIENTS
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
 def test_questions_denials_and_new_food_reports_are_not_edits(self):
  for message in ('What is raw tahini?','What if I replaced the sauce?','Do not change the tahini','I ate raw tahini','How many calories are in raw tahini?'):
   self.assertFalse(correction_intent(message),message)
