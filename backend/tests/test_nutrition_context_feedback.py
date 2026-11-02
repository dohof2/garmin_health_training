import copy
import json
import unittest
from datetime import date
from unittest.mock import patch

from test_nutrition_logging import NutritionLoggingTests,FOODS,DAY,TZ
from app.nutrition import daily_status,save_target
from app.nutrition_chat import chat
from app.nutrition_logging import pending_save_intent
from app.ai_chat import chat_stream


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

 def test_meal_followups_keep_nutrition_route_and_burned_calories_remain_analysis(self):
  from app.chat_routing import route
  for message in ('How was my meal?','What was that portion?','Show my food log','Analyze my breakfast'):
   self.assertEqual(route(message,previous='nutrition'),'nutrition')
  self.assertEqual(route('How many calories burned?'),'assistant')

 def test_approved_food_logs_partial_if_enrichment_is_unavailable(self):
  pending=[{'name':'Family stew','grams_low':200,'grams_high':300,'grams_proposed':250,'question':'Confirm?','meal_type':'dinner'}]
  with patch('app.nutrition_chat.analyze_food',side_effect=ValueError('Model unavailable')):
   result=chat('approved',DAY,TZ,path=self.path,pending_foods=pending,auto_log=True,operation_id='offline-approval')
  self.assertTrue(result['logged'])
  self.assertEqual(self.meals()[0]['items'][0]['quantity'],250)
  self.assertIn('partial',result['reply'])
  self.assertNotIn('0 g of recorded protein.',result['meal_assessment'])

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
  corrected=self.run_chat('Actually change Eggs to 150 g',operation='correction',saved_meals=result['saved_meals'])
  self.assertTrue(corrected['updated'])
  self.assertIn('meal_assessment',corrected)
  self.assertEqual(len(self.meals()),1)
  self.assertNotEqual(corrected['meal_assessment'],result['meal_assessment'])

 def test_role_specific_history_reaches_nutrition_model(self):
  old=[{'role':'user','content':'My yogurt was 200 g'},{'role':'assistant','content':'Retained the yogurt portion.'}]
  recent=[{'role':'user','content':'Discuss my trainer plan'}]
  response={'reply':'The portion is 200 g.','ingredients':[],'uncertainties':[],'target_request':None}
  with patch('app.nutrition_chat.analyze_food',return_value=response) as analyze:
   events=[json.loads(e) for e in chat_stream('What portion was that?',recent,TZ,self.path,chat_role='nutrition',nutrition_context={'day':DAY},role_histories={'nutrition':old})]
  self.assertEqual(events[-1]['type'],'complete',events)
  self.assertEqual(analyze.call_args.kwargs['review_context']['conversation'],old)

 def test_trainer_receives_its_retained_history_after_nutrition_turns(self):
  trainer=[{'role':'user','content':'Friday is my only available day.'},{'role':'assistant','content':'Friday is retained.'}]
  recent=[{'role':'user','content':'I ate yogurt'}]
  with patch('app.ai_chat.get_ai_settings',return_value={'active_provider':'chatgpt','chatgpt_model':'fixture'}),patch('app.ai_chat._chatgpt_stream',return_value=iter([])) as model:
   list(chat_stream('Tell me more',recent,TZ,self.path,chat_role='trainer',role_histories={'trainer':trainer}))
  self.assertEqual(model.call_args.args[2],trainer)
