import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.nutrition_drafts import new_day,select_context
from app.nutrition_chat import chat
from app.database import migrate
from test_nutrition_logging import FOODS,DAY,TZ,NOW

class DailyDraftTests(unittest.TestCase):
 def test_daily_reset_discards_every_unfinished_request(self):
  old={'day':'2026-10-27','pending_foods':FOODS['ingredients'],'pending_target':{'goal':'maintain'},'saved_meals':[{'id':'old'}],'pending_drafts':[{'day':'2026-10-26'}]}
  self.assertEqual(new_day(old,'2026-10-29'),{'day':'2026-10-29'})
  selected,others=select_context(old,'Snacks for today','2026-10-29')
  self.assertEqual(selected,{'day':'2026-10-29'});self.assertEqual(others,[])
 def test_approval_cannot_revive_an_old_lunch(self):
  selected,others=select_context({'day':'2026-10-27','pending_foods':FOODS['ingredients']},'yes','2026-10-29')
  self.assertEqual(selected,{'day':'2026-10-29'});self.assertEqual(others,[])
 def test_explicit_date_can_select_historical_records_but_not_revive_drafts(self):
  selected,others=select_context({'day':'2026-10-29','pending_foods':[{'name':'Today apple'}],'pending_drafts':[{'day':'2026-10-28','pending_foods':FOODS['ingredients']}]},'Log yesterday breakfast','2026-10-29')
  self.assertEqual(selected,{'day':'2026-10-28'});self.assertEqual(others,[])
 def test_clarifying_supper_preserves_other_meals_and_all_foods_on_approval(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'test.sqlite';migrate(path)
   pending=copy.deepcopy(FOODS['ingredients']);pending[1]['meal_type']='lunch'
   supper={**pending[0],'name':'Rice','meal_type':'dinner','grams_low':150,'grams_high':250,'grams_proposed':200}
   pending.append(supper)
   response={**copy.deepcopy(FOODS),'ingredients':[{**supper,'grams_low':220,'grams_high':220,'grams_proposed':220}],'reply':'Supper portion clarified.'}
   with patch('app.nutrition_chat.analyze_food',return_value=response),patch('app.nutrition_chat.search_foods',return_value={'foods':[],'status':'no_matches','source':'fixture'}):
    result=chat('The supper rice was 220 g',DAY,TZ,path=path,pending_foods=pending,message_time=NOW)
   self.assertEqual([(f['name'],f['meal_type']) for f in result['ingredients']],[('Eggs','breakfast'),('Avocado','lunch'),('Rice','dinner')])
   self.assertEqual(result['ingredients'][2]['grams_proposed'],220)
   with patch('app.nutrition_chat.analyze_food',return_value=response),patch('app.nutrition_chat.search_foods',return_value={'foods':[],'status':'no_matches','source':'fixture'}):
    saved=chat('Yes, log all three meals',DAY,TZ,path=path,pending_foods=[{key:food[key] for key in ('name','meal_type','grams_low','grams_high','grams_proposed','question','nutrients_per_100g','estimate_assumptions') if key in food} for food in result['ingredients']],history=[{'role':'assistant','content':'Confirm all three meals and log them?'}],auto_log=True,operation_id='all-meals-approved',message_time=NOW)
   self.assertTrue(saved['logged']);self.assertEqual({m['meal_type'] for m in saved['saved_meals']},{'breakfast','lunch','dinner'})


 def test_telegram_new_day_drops_old_text_and_reads_state_through_tools(self):
  from app.telegram_chat import conversation_reply
  with patch('app.telegram_chat.answer',return_value='Read from saved plan') as answer:
   result=conversation_reply('Show my training plan',[{'role':'user','content':'old discussion'}],TZ,operation_id='daily-test',context={'chat_day':'2026-10-24','summary':'Do not import','role':'trainer'},sent_at=NOW.timestamp())
  self.assertEqual(answer.call_args.args[1],[])
  self.assertNotIn('summary',result['context']);self.assertEqual(result['context']['chat_day'],DAY)

 def test_named_food_correction_uses_saved_meals_without_imported_chat_references(self):
  from test_nutrition_logging import NutritionLoggingTests
  fixture=NutritionLoggingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  fixture.run_chat()
  result=fixture.run_chat('Actually change Eggs to 150 g',operation='fresh-day-correction')
  self.assertTrue(result['updated']);self.assertEqual(len(fixture.meals()),1)
