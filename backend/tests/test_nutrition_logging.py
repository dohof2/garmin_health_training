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
  # Domain fixture: inputs have already been understood by the shared agent.
  from app.nutrition_operations import execute
  context={'path':self.path,'state':{},'today':DAY,'timezone':TZ,'now':NOW,'message':message}
  if kw.get('quantity') is not None:
   meal=self.meals()[0];item=next(i for i in meal['items'] if i['name']=='Eggs')
   return execute({'intent':'correct','meal_id':meal['id'],'expected_revision':meal['revision'],'item_id':item['id'],'quantity':kw['quantity']},context,operation)
  foods=kw.get('pending_foods') or (response or FOODS)['ingredients']
  return execute({'intent':'log','date':DAY,'ingredients':[{'name':f['name'],'grams':f.get('grams_proposed') or (f['grams_low']+f['grams_high'])/2,'meal_type':f.get('meal_type','meal'),'nutrients_per_100g':f.get('nutrients_per_100g')} for f in foods]},context,operation)
 def meals(self,day=DAY):return daily_status(date.fromisoformat(day),TZ,self.path)['meals']

 def test_confirmation_intent_does_not_accept_negation_or_target(self):
  from app.nutrition_logging import pending_save_intent
  for message in ['i confirm','I confirm.','I approve']:
   self.assertTrue(pending_save_intent(message,FOODS['ingredients']))
  for message in ['I do not confirm','can I confirm?','I confirm the target','בםמכןרצ']:
   self.assertFalse(pending_save_intent(message,FOODS['ingredients']))
