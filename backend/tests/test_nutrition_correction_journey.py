"""Clarifications retain a correction's food/date and commit through real services."""
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.database import connect, migrate
from app.nutrition import daily_status, save_meal, delete_meal, _meal
from app.nutrition_drafts import select_context

NOW=datetime(2026,10,31,10,tzinfo=timezone.utc)
TZ='Asia/Jerusalem'
VALUES='for esterady the veggy based sausages values are: משקל יחידה 37 גרם; קלוריות 53–61; חלבונים 5.6–6.7; שומנים 2.2–3; פחמימות 1.5–2'


class CorrectionJourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        self.lunch=self.seed('lunch',[('Bread bun',60,{'calories_kcal':160,'protein_grams':5,'fat_grams':2,'carbohydrate_grams':30}),('Vegetarian sausages',100,None)])
        self.dinner=self.seed('dinner',[('Cooked couscous',75,{'calories_kcal':84,'protein_grams':3,'fat_grams':0,'carbohydrate_grams':17}),('Soup',225,None)])
        self.context={'day':'2026-10-31'};self.history=[];self.counter=0

    def seed(self,kind,items,day='2026-10-30'):
        return save_meal({'eaten_at':day+'T12:00:00+02:00','timezone':TZ,'meal_type':kind,'items':[
            {'name':name,'quantity':grams,'unit':'g','nutrients':values or {},'source':'Fixture' if values else 'nutrients unknown','portion_basis':'estimated'}
            for name,grams,values in items]},kind+day,path=self.path)


    def clarification(self,question):
        return {'food_correction':None,'ingredients':[],'reply':question,'uncertainties':[]}

    def replacement(self,meal,index,name,grams,values):
        with connect(self.path) as c:current=_meal(c,meal['id'])
        return {'food_correction':{'meal_id':meal['id'],'item_id':current['items'][index]['id'],'expected_revision':current['revision'],'keep_quantity':False},
            'ingredients':[{'name':name,'meal_type':meal['meal_type'],'grams_low':grams,'grams_high':grams,'grams_proposed':grams,
                            'nutrients_per_100g':values,'question':'','estimate_assumptions':'Approximate portion and composition.'}],
            'reply':'Ready to correct.','uncertainties':[]}


    def test_pending_context_never_crosses_the_chat_day_and_new_consumption_defaults_today(self):
        old={'day':'2026-10-29','chat_day':'2026-10-30','pending_correction':{'day':'2026-10-29','request':'old'}}
        selected,_=select_context(old,'300 ml','2026-10-31');self.assertEqual(selected,{'day':'2026-10-31'})
        selected,_=select_context({**old,'date_selected':True},'300 ml','2026-10-31');self.assertEqual(selected,{'day':'2026-10-31'})
        current={**old,'chat_day':'2026-10-31'}
        selected,_=select_context(current,'I ate an apple','2026-10-31');self.assertEqual(selected,{'day':'2026-10-31'})
