import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,date
from unittest.mock import patch
from app.database import migrate,connect
from app.nutrition import save_meal,_meal,daily_status
from app.nutrition_chat import chat
from app.nutrition_drafts import cancel_pending
from app.nutrition_move import move_request

TZ='Asia/Jerusalem';NOW=datetime(2026,10,29,12,tzinfo=timezone.utc)
class MealMoveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  self.snack=self.save('snack','Chocolate',100);self.lunch=self.save('lunch','Old lunch',200)
 def save(self,kind,name,kcal):
  return save_meal({'eaten_at':'2026-10-27T12:00:00+02:00','timezone':TZ,'meal_type':kind,'notes':'Fixture', 'items':[{'name':name,'quantity':1,'unit':'serving','nutrients':{'calories_kcal':kcal,'protein_grams':5,'fat_grams':3,'carbohydrate_grams':10},'nutrient_basis':'portion','source':'fixture','portion_basis':'estimated'}]},'seed-'+kind,path=self.path)
 def refs(self):return [{'id':m['id'],'revision':m['revision'],'meal_type':m['meal_type']} for m in (self.snack,self.lunch)]
 def move(self,text='Move snacks to today',op='move',refs=None):
  with patch('app.nutrition_chat.analyze_food',side_effect=AssertionError('No model needed')):
   return chat(text,'2026-10-29',TZ,path=self.path,saved_meals=self.refs() if refs is None else refs,auto_log=True,operation_id=op,message_time=NOW)
 def test_move_updates_same_entry_preserving_item_ids_and_recalculating_both_days(self):
  before=self.snack['items'];result=self.move()
  self.assertTrue(result['moved']);self.assertEqual(result['moved_from'],'2026-10-27');self.assertEqual(result['moved_to'],'2026-10-29')
  with connect(self.path) as c:
   snack=_meal(c,self.snack['id']);lunch=_meal(c,self.lunch['id'])
   self.assertEqual(snack['items'],before);self.assertEqual(snack['revision'],2);self.assertEqual(lunch['revision'],1)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM meals').fetchone()[0],2)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM meal_revisions WHERE meal_id=?',(snack['id'],)).fetchone()[0],2)
  self.assertEqual(daily_status(date(2026,10,27),TZ,self.path)['totals']['calories_kcal']['known_total'],200)
  self.assertEqual(daily_status(date(2026,10,29),TZ,self.path)['totals']['calories_kcal']['known_total'],100)
  again=self.move();self.assertTrue(again['replayed'])
 def test_fresh_chat_can_find_snack_from_saved_data(self):
  result=self.move('Move snacks from 2026-10-27 to 2026-10-29',refs=[])
  self.assertEqual(result['saved_meals'][0]['id'],self.snack['id'])
 def test_ambiguous_generic_move_asks_without_changing_any_meal(self):
  result=self.move('Wrong date, move them to today')
  self.assertNotIn('moved',result)
  with connect(self.path) as c:self.assertTrue(all(r[0]==1 for r in c.execute('SELECT revision FROM meals')))
 def test_stale_revision_and_future_date_do_not_move_foods(self):
  self.move()
  stale=self.move(op='stale');self.assertNotIn('moved',stale)
  with self.assertRaises(ValueError):self.move('Move snacks to 2026-10-30',op='future')
 def test_hebrew_date_correction_uses_selected_snack_not_lunch(self):
  result=self.move('טעות, תעביר את הנשנושים להיום')
  self.assertEqual(result['saved_meals'][0]['id'],self.snack['id'])
 def test_other_domains_and_questions_are_not_food_date_writes(self):
  for message in ('Move my workout to today','Move my calorie target to today','Should I move snacks to today?','Do not move snacks to today'):
   self.assertFalse(move_request(message))
 def test_explicit_cancellation_does_not_resurrect_old_lunch_on_approval(self):
  foods=[{'name':'שניצל צמחי רמי לוי','meal_type':'lunch'},{'name':'מיני מקופלת','meal_type':'snack'}]
  retained,changed=cancel_pending('אין שניצלים תשכח מהם',foods)
  self.assertTrue(changed);self.assertEqual([f['meal_type'] for f in retained],['snack'])

 def test_cancel_then_approve_logs_only_remaining_food(self):
  foods=[{'name':'שניצל צמחי רמי לוי','meal_type':'lunch','grams_low':400,'grams_high':400,'grams_proposed':400,'question':''},{'name':'מיני מקופלת','meal_type':'snack','grams_low':36,'grams_high':36,'grams_proposed':36,'question':''}]
  with patch('app.nutrition_chat.analyze_food',side_effect=AssertionError('No model needed')):
   result=chat('אין שניצלים תשכח מהם','2026-10-29',TZ,path=self.path,pending_foods=foods,auto_log=True,operation_id='cancel',message_time=NOW)
  self.assertTrue(result['pending_foods_replaced']);self.assertEqual(len(result['ingredients']),1)
  approved={'reply':'','ingredients':result['ingredients'],'uncertainties':[],'target_request':None,'model':'fixture'}
  with patch('app.nutrition_chat.analyze_food',return_value=approved),patch('app.nutrition_chat.search_foods',return_value={'foods':[]}):
   saved=chat('מאשר','2026-10-29',TZ,path=self.path,pending_foods=result['ingredients'],history=[{'role':'assistant','content':'Confirm and log remaining snacks?'}],auto_log=True,operation_id='approve-after-cancel',message_time=NOW)
  self.assertEqual([m['meal_type'] for m in saved['saved_meals']],['snack'])
