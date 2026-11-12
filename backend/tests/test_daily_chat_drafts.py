import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.nutrition_drafts import new_day,select_context
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


 def test_telegram_new_day_uses_shared_conversation_and_current_date(self):
  from app.telegram_chat import conversation_reply
  import json
  from test_skill_agent import NativeProviderFixture
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'test.sqlite';migrate(path)
   with patch('app.ai_providers._active_provider',return_value=NativeProviderFixture(lambda *a,**k:json.dumps({'reply':'Use the saved plan.'}))):
    result=conversation_reply('Show my training plan',[{'role':'user','content':'old discussion'}],TZ,path,operation_id='daily-test',context={'chat_day':'2026-10-24','role':'trainer'},sent_at=NOW.timestamp())
  self.assertNotIn('role',result['context']);self.assertEqual(result['reply'],'Use the saved plan.')

 def test_named_food_correction_uses_saved_meals_without_imported_chat_references(self):
  from test_nutrition_logging import NutritionLoggingTests
  fixture=NutritionLoggingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  fixture.run_chat()
  result=fixture.run_chat('Actually change Eggs to 150 g',operation='fresh-day-correction',quantity=150)
  self.assertTrue(result['updated']);self.assertEqual(len(fixture.meals()),1)
