import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,date
from unittest.mock import patch
from app.database import migrate,connect
from app.nutrition import save_meal,_meal,daily_status
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
 def test_other_domains_and_questions_are_not_food_date_writes(self):
  for message in ('Move my workout to today','Move my calorie target to today','Should I move snacks to today?','Do not move snacks to today'):
   self.assertFalse(move_request(message))
 def test_explicit_cancellation_does_not_resurrect_old_lunch_on_approval(self):
  foods=[{'name':'שניצל צמחי רמי לוי','meal_type':'lunch'},{'name':'מיני מקופלת','meal_type':'snack'}]
  retained,changed=cancel_pending('אין שניצלים תשכח מהם',foods)
  self.assertTrue(changed);self.assertEqual([f['meal_type'] for f in retained],['snack'])
