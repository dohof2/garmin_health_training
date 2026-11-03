import copy
import json
import unittest
from datetime import date
from unittest.mock import patch

from test_nutrition_logging import NutritionLoggingTests,FOODS,DAY,TZ
from app.nutrition import daily_status,save_target
from app.nutrition_logging import pending_save_intent


class NutritionContextFeedbackTests(unittest.TestCase):
 setUp=NutritionLoggingTests.setUp
 run_chat=NutritionLoggingTests.run_chat
 meals=NutritionLoggingTests.meals
 def test_approval_logs_retained_foods_without_reasking_or_duplicate(self):
  pending=copy.deepcopy(FOODS['ingredients'])
  history=[{'role':'assistant','content':'Confirm these portions and log this meal?'}]
  for index,message in enumerate(('yes','approved','okay','כן','מאשר')):
   with self.subTest(message=message):
    result=self.run_chat(message,operation=f'approval-{index}',pending_foods=pending,history=history)
    self.assertTrue(result['logged'])
    self.assertIn('meal_assessment',result)
    replay=self.run_chat(message,operation=f'approval-{index}',pending_foods=pending,history=history)
    self.assertTrue(replay['replayed'])
  self.assertEqual(len(self.meals()),5)

 def test_question_and_negative_do_not_approve(self):
  for message in ('Did you log it?','not yet','do not log it','maybe','what if I approve?'):
   self.assertFalse(pending_save_intent(message,FOODS['ingredients'],[{'role':'assistant','content':'Confirm and log?'}]))
  self.assertFalse(pending_save_intent('yes',FOODS['ingredients'],[{'role':'assistant','content':'Review this calorie target before saving.'}]))


 def test_feedback_uses_saved_day_totals_and_goal_after_logging(self):
  save_target({'method':'manual','effective_from':DAY,'calories_kcal':2000,'protein_grams':100,'fat_grams':70,'carbohydrate_grams':240},0,path=self.path)
  result=self.run_chat()
  status=daily_status(date.fromisoformat(DAY),TZ,self.path)
  self.assertIn('fiber',result['meal_assessment'])
  self.assertIn('fiber grams are not tracked',result['meal_assessment'])
  self.assertIn(f"{status['totals']['protein_grams']['known_total']:g}/100 g protein",result['goal_progress'])
  self.assertIn('next meal',result['next_meal_suggestion'])
  self.assertIn('feedback',status['meals'][0])
  self.assertEqual(status['goal_progress'],result['goal_progress'])

 def test_missing_target_is_explicit_and_meal_correction_refreshes_feedback(self):
  result=self.run_chat()
  self.assertIn('No nutrition target',result['goal_progress'])
  corrected=self.run_chat('Actually change Eggs to 150 g',operation='correction',saved_meals=result['saved_meals'],quantity=150)
  self.assertTrue(corrected['updated'])
  self.assertIn('meal_assessment',corrected)
  self.assertEqual(len(self.meals()),1)
  self.assertNotEqual(corrected['meal_assessment'],result['meal_assessment'])
