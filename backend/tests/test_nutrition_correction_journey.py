"""Clarifications retain a correction's food/date and commit through real services."""
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.ai_chat import chat_stream
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

    def turn(self,message,response=None):
        self.counter+=1
        with patch('app.nutrition_correction.analyze_food',return_value=copy.deepcopy(response)) as correction, \
             patch('app.nutrition_chat.analyze_food',return_value=copy.deepcopy(response)) as normal, \
             patch('app.nutrition_chat.search_foods',return_value={'foods':[]}):
            events=[json.loads(event) for event in chat_stream(message,history=self.history[-12:],path=self.path,
                timezone_name=TZ,chat_role='nutrition',nutrition_context=self.context,message_time=NOW,
                operation_id='journey-'+str(self.counter))]
        self.assertEqual(events[-1]['type'],'complete',events)
        evidence=next(event['evidence'] for event in events if event['type']=='tool')
        result=evidence.get('nutrition',evidence.get('result'))
        self.history += [{'role':'user','content':message},{'role':'assistant','content':next(event['text'] for event in events if event['type']=='delta')}]
        if 'nutrition' in evidence:
            # Mirrors the transport fields, separately checked in chatContext tests.
            self.context['day']=result['context_date'];self.context['chat_day']=result['chat_day']
            if result.get('logged'):
                self.context['pending_foods']=[];self.context.pop('pending_correction',None)
            elif 'pending_correction' in result:self.context['pending_correction']=result['pending_correction']
            elif result.get('ingredients'):
                self.context['pending_foods']=[{key:food[key] for key in ('name','grams_low','grams_high','grams_proposed','question','meal_type','nutrients_per_100g','estimate_assumptions') if key in food} for food in result['ingredients']]
            if result.get('saved_meals'):self.context['saved_meals']=result['saved_meals']
        return result,correction,normal

    def clarification(self,question):
        return {'food_correction':None,'ingredients':[],'reply':question,'uncertainties':[]}

    def replacement(self,meal,index,name,grams,values):
        with connect(self.path) as c:current=_meal(c,meal['id'])
        return {'food_correction':{'meal_id':meal['id'],'item_id':current['items'][index]['id'],'expected_revision':current['revision'],'keep_quantity':False},
            'ingredients':[{'name':name,'meal_type':meal['meal_type'],'grams_low':grams,'grams_high':grams,'grams_proposed':grams,
                            'nutrients_per_100g':values,'question':'','estimate_assumptions':'Approximate portion and composition.'}],
            'reply':'Ready to correct.','uncertainties':[]}

    def test_user_values_then_five_sausages_update_existing_yesterday_lunch(self):
        pending,_,_=self.turn(VALUES,self.clarification('How many sausages?'))
        self.assertIn('not saved yet',pending['reply'])
        self.assertEqual(pending['pending_correction']['day'],'2026-10-30')
        per100={key:value*100/37 for key,value in {'calories_kcal':57,'protein_grams':6.15,'fat_grams':2.6,'carbohydrate_grams':1.75}.items()}
        result,model,normal=self.turn('yesterday lunch! 5',self.replacement(self.lunch,1,'Vegetarian sausages',185,per100))
        self.assertTrue(result['updated']);self.assertNotIn('pending_correction',self.context)
        self.assertEqual(model.call_args.kwargs['review_context']['correction_request'],VALUES);normal.assert_not_called()
        with connect(self.path) as c:meal=_meal(c,self.lunch['id'])
        self.assertEqual(meal['items'][0],self.lunch['items'][0])
        sausage=meal['items'][1];self.assertEqual(sausage['id'],self.lunch['items'][1]['id'])
        self.assertEqual(sausage['quantity'],185);self.assertAlmostEqual(sausage['calories_kcal'],285)
        self.assertAlmostEqual(sausage['protein_grams'],30.75);self.assertIn('User-provided',sausage['source'])
        self.assertEqual(meal['partial_explanation'],'')

    def test_soup_clarifications_commit_without_requiring_another_keyword(self):
        self.turn('for yestareday soup coreect the spoup to a vegetable and meat broth',self.clarification('How much soup?'))
        self.turn('about 300 ml',self.clarification('Did it include pieces?'))
        soup=self.replacement(self.dinner,1,'Vegetable and meat soup',300,{'calories_kcal':50,'protein_grams':4,'fat_grams':2,'carbohydrate_grams':4})
        result,model,_=self.turn('meat and vegtable',soup)
        self.assertTrue(result['updated']);self.assertEqual(result['context_date'],'2026-10-30')
        self.assertIn('300 ml',str(model.call_args.kwargs['review_context']['correction_clarifications']))
        with connect(self.path) as c:meal=_meal(c,self.dinner['id'])
        self.assertEqual(len(meal['items']),2);self.assertEqual(meal['items'][0],self.dinner['items'][0])
        self.assertEqual(meal['items'][1]['quantity'],300);self.assertEqual(meal['items'][1]['calories_kcal'],150)
        self.assertEqual(meal['partial_explanation'],'')

    def test_count_after_values_were_already_committed_still_updates_same_item(self):
        per100={key:value*100/37 for key,value in {'calories_kcal':57,'protein_grams':6.15,'fat_grams':2.6,'carbohydrate_grams':1.75}.items()}
        first=self.replacement(self.lunch,1,'Vegetarian sausages',100,per100)
        first['food_correction']['keep_quantity']=True
        result,_,_=self.turn(VALUES,first);self.assertTrue(result['updated'])
        result,model,_=self.turn('yesterday lunch! 5',self.replacement(self.lunch,1,'Vegetarian sausages',185,per100))
        self.assertTrue(result['updated']);self.assertEqual(model.call_args.kwargs['review_context']['correction_request'],VALUES)
        with connect(self.path) as c:meal=_meal(c,self.lunch['id'])
        self.assertEqual(meal['revision'],3);self.assertAlmostEqual(meal['items'][1]['calories_kcal'],285)
        self.assertIn('User-provided',meal['items'][1]['source'])

    def test_partial_question_reads_only_the_requested_meal_from_current_records(self):
        result,correction,normal=self.turn('is there still aprtial log in yesterday lunch?')
        correction.assert_not_called();normal.assert_not_called()
        self.assertEqual(result['date'],'2026-10-30')
        self.assertIn('Vegetarian sausages',self.history[-1]['content'])
        self.assertNotIn('Soup',self.history[-1]['content'])

    def test_date_correction_moves_same_entry_and_ignores_invented_assistant_dates(self):
        soup=self.seed('dinner',[('Vegetable and meat soup',300,{'calories_kcal':150,'protein_grams':12,'fat_grams':6,'carbohydrate_grams':12})],day='2026-10-31')
        self.context={'day':'2026-10-31','chat_day':'2026-10-31','saved_meals':[{'id':soup['id'],'revision':1,'meal_type':'dinner'}]}
        result,model,normal=self.turn('it was yesterday')
        self.assertTrue(result['moved']);self.assertEqual(result['moved_to'],'2026-10-30');model.assert_not_called();normal.assert_not_called()
        self.history[-1]['content']='October 29, not today' # Wrong model prose cannot choose the date.
        result,_,_=self.turn('move it');self.assertEqual(result['moved_to'],'2026-10-30')
        self.assertFalse(result['updated'])
        with connect(self.path) as c:
            current=_meal(c,soup['id']);self.assertEqual(current['items'],soup['items']);self.assertEqual(current['revision'],2)
        self.assertEqual(daily_status(date(2026,10,31),TZ,self.path)['meals'],[])

    def test_deleted_food_can_be_added_on_the_pending_date(self):
        self.turn('Correct yesterday soup to vegetable and meat soup',self.clarification('How much soup?'))
        delete_meal(self.dinner['id'],1,self.path)
        food=self.replacement(self.lunch,0,'Vegetable and meat soup',300,{'calories_kcal':50,'protein_grams':4,'fat_grams':2,'carbohydrate_grams':4})['ingredients'][0]
        food['meal_type']='dinner'
        result,_,_=self.turn('add I removed the soup',{'ingredients':[food],'reply':'','uncertainties':[]})
        self.assertTrue(result['logged']);self.assertEqual(result['context_date'],'2026-10-30')
        self.assertEqual(daily_status(date(2026,10,31),TZ,self.path)['meals'],[])
        dinners=[meal for meal in daily_status(date(2026,10,30),TZ,self.path)['meals'] if meal['meal_type']=='dinner']
        self.assertEqual(len(dinners),1);self.assertEqual(dinners[0]['items'][0]['calories_kcal'],150)

    def test_pending_context_never_crosses_the_chat_day_and_new_consumption_defaults_today(self):
        old={'day':'2026-10-29','chat_day':'2026-10-30','pending_correction':{'day':'2026-10-29','request':'old'}}
        selected,_=select_context(old,'300 ml','2026-10-31');self.assertEqual(selected,{'day':'2026-10-31'})
        selected,_=select_context({**old,'date_selected':True},'300 ml','2026-10-31');self.assertEqual(selected,{'day':'2026-10-31'})
        current={**old,'chat_day':'2026-10-31'}
        selected,_=select_context(current,'I ate an apple','2026-10-31');self.assertEqual(selected,{'day':'2026-10-31'})

    def test_bare_move_without_a_human_destination_does_not_infer_from_assistant(self):
        self.history=[{'role':'assistant','content':'Move soup to 2026-10-29'}]
        result,_,_=self.turn('move it');self.assertNotIn('moved',result)
        self.assertIn('Which date',result['reply'])
        self.history=[{'role':'user','content':'Do not move it to yesterday'}]
        result,_,_=self.turn('move it');self.assertNotIn('moved',result)

    def test_move_it_recovers_unique_human_named_food_when_old_client_lost_refs(self):
        # Remove the old soup so only the replacement exists, as in the report.
        delete_meal(self.dinner['id'],1,self.path)
        soup=self.seed('dinner',[('Vegetable and meat soup',300,{'calories_kcal':150,'protein_grams':12,'fat_grams':6,'carbohydrate_grams':12})],day='2026-10-31')
        self.context={'day':'2026-10-30','chat_day':'2026-10-31'}
        self.history=[{'role':'user','content':'add I removed the soup'},
                      {'role':'assistant','content':'Logged for today'},
                      {'role':'user','content':'it was yesterday'},
                      {'role':'assistant','content':'October 29, I cannot move entries'}]
        result,model,normal=self.turn('move it')
        self.assertEqual(result['moved_to'],'2026-10-30');self.assertEqual(result['saved_meals'][0]['id'],soup['id'])
        model.assert_not_called();normal.assert_not_called()

    def test_yestray_bread_proposal_then_log_it_saves_on_yesterday(self):
        food={'name':'Bread','meal_type':'dinner','grams_low':300,'grams_high':300,'grams_proposed':300,'question':'',
              'nutrients_per_100g':{'calories_kcal':265,'protein_grams':9,'fat_grams':3.2,'carbohydrate_grams':49}}
        result,_,_=self.turn('for yestray supper also add 300g of bread',{'ingredients':[food],'reply':'For yesterday supper','uncertainties':[]})
        self.assertFalse(result.get('logged',False));self.assertEqual(result['context_date'],'2026-10-30')
        result,correction,normal=self.turn('log it')
        self.assertTrue(result['logged']);self.assertEqual(result['context_date'],'2026-10-30')
        correction.assert_not_called();normal.assert_not_called()
        self.assertEqual(daily_status(date(2026,10,31),TZ,self.path)['meals'],[])
        with connect(self.path) as c:
            saved=_meal(c,result['saved_meals'][0]['id'])
        self.assertEqual(saved['meal_type'],'dinner');self.assertEqual(saved['items'][0]['quantity'],300)
        self.assertEqual(saved['items'][0]['calories_kcal'],795)

    def test_approval_recovers_original_date_from_human_text_for_old_pending_proposal(self):
        self.context={'day':'2026-10-31','chat_day':'2026-10-31','pending_foods':[
            {'name':'Bread','meal_type':'dinner','grams_low':300,'grams_high':300,'grams_proposed':300,'question':'',
             'nutrients_per_100g':{'calories_kcal':265,'protein_grams':9,'fat_grams':3.2,'carbohydrate_grams':49}}]}
        self.history=[{'role':'user','content':'for yestray supper also add 300g of bread'},
                      {'role':'assistant','content':'Bread for 2026-10-31'}]
        result,_,normal=self.turn('log it')
        self.assertEqual(result['context_date'],'2026-10-30');normal.assert_not_called()
