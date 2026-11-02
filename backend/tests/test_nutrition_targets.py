import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import date, timedelta

from app.database import connect, migrate
from app.nutrition import target_history
from app.nutrition_targets import recorded_context, propose, save
from app.sync import ensure_sync_checkpoints


class AdaptiveNutritionTargets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'nutrition.sqlite'
        migrate(self.path)
        ensure_sync_checkpoints(self.path)
        self.day = date(2026, 10, 21)
        with connect(self.path) as c:
            c.execute("INSERT INTO garmin_sync_payloads(data_type,calendar_date,payload_json) VALUES('supplementary_metrics',?,?)", (self.day.isoformat(), json.dumps({'endpoints': {'get_user_profile': {'userData': {'height': 175, 'weight': 80000, 'birthDate': '1986-01-01', 'gender': 'MALE'}}}})))
            c.execute("UPDATE sync_checkpoints SET coverage_start='2026-01-01',coverage_end=? WHERE data_type='activities'", (self.day.isoformat(),))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('weight','garmin_connect','weight',?,80,'kg')", (self.day.isoformat(),))
            for index in range(1, 29):
                day = (self.day-timedelta(days=index)).isoformat()
                for metric, value, unit in [('steps', 8000, 'count'), ('active_calories', 700, 'kcal'), ('resting_calories', 1700, 'kcal'), ('total_calories', 2400, 'kcal')]:
                    c.execute('INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,?,?,?,?,?)', (str(index)+metric, 'garmin_connect', metric, day, value, unit))
                c.execute("INSERT INTO garmin_sync_payloads(data_type,calendar_date,payload_json) VALUES('daily_metrics',?,?)", (day, json.dumps({'durationInMilliseconds': 86400000, 'wellnessEndTimeLocal': day+'T23:59:00'})))

    def request(self, **changes):
        return {'goal': 'lose_weight', 'target_weight_kg': 75, **changes}

    def proposal(self, **changes):
        return propose(self.request(**changes), self.day.isoformat(), self.path)

    def test_garmin_inputs_and_four_week_expenditure_without_double_counting(self):
        result = self.proposal()
        self.assertEqual(result['status'], 'proposal')
        preview = result['preview']
        self.assertEqual(preview['calories_kcal'], 2160)
        self.assertEqual(preview['assumptions']['maintenance_kcal'], 2400)
        self.assertEqual(preview['assumptions']['garmin_complete_days_used'], 28)
        self.assertEqual(preview['assumptions']['height_cm'], 175)
        self.assertEqual(preview['assumptions']['weight_kg'], 80)
        self.assertEqual(preview['assumptions']['protein_g_per_kg'], 1.6)
        macro_energy = preview['protein_grams']*4+preview['fat_grams']*9+preview['carbohydrate_grams']*4
        self.assertLessEqual(abs(macro_energy-preview['calories_kcal']), 5)
        self.assertEqual(target_history(self.path), [])

    def test_today_and_duplicate_archive_do_not_inflate_activity_or_calories(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('today','garmin_connect','total_calories',?,99999,'kcal')", (self.day.isoformat(),))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('overlap','garmin_export','total_calories',?,9000,'kcal')", ((self.day-timedelta(days=1)).isoformat(),))
        self.assertEqual(self.proposal()['preview']['assumptions']['maintenance_kcal'], 2400)

    def test_incomplete_expenditure_falls_back_to_recorded_activity_formula(self):
        with connect(self.path) as c:
            c.execute("DELETE FROM garmin_sync_payloads WHERE data_type='daily_metrics'")
        preview = self.proposal()['preview']
        self.assertIn('Mifflin', preview['assumptions']['maintenance_method'])
        self.assertEqual(preview['assumptions']['garmin_complete_days_used'], 0)
        self.assertEqual(preview['assumptions']['activity_factor'], 1.55)

    def test_gain_is_small_surplus_with_protein_and_resistance_training_note(self):
        preview = self.proposal(goal='gain_muscle', target_weight_kg=83)['preview']
        self.assertEqual(preview['calories_kcal'], 2520)
        self.assertIn('resistance training', ' '.join(preview['warnings']))

    def test_missing_goal_weight_is_one_focused_question(self):
        result = self.proposal(target_weight_kg=None)
        self.assertEqual(result['status'], 'needs_input')
        self.assertEqual(len(result['questions']), 1)
        self.assertIn('target weight', result['questions'][0])

    def test_unsafe_loss_and_excessive_pace_are_declined(self):
        self.assertEqual(self.proposal(target_weight_kg=40)['status'], 'not_recommended')
        self.assertEqual(self.proposal(rate_kg_week=3)['status'], 'not_recommended')
        self.assertEqual(self.proposal(age=16)['status'], 'needs_professional_review')
        self.assertEqual(self.proposal(special_circumstances=['pregnancy'])['status'], 'needs_professional_review')

    def test_save_rechecks_measurements_and_revision(self):
        result = self.proposal()
        with connect(self.path) as c:
            c.execute("UPDATE metric_readings SET value=81 WHERE id='weight'")
        with self.assertRaisesRegex(ValueError, 'changed'):
            save(self.request(), self.day.isoformat(), result['fingerprint'], 0, self.path)
        fresh = self.proposal()
        saved = save(self.request(), self.day.isoformat(), fresh['fingerprint'], 0, self.path)
        self.assertEqual(saved['revision'], 1)
        with self.assertRaises(ValueError):
            save(self.request(), self.day.isoformat(), fresh['fingerprint'], 0, self.path)
        self.assertEqual(len(target_history(self.path)), 1)
        self.assertEqual(target_history(self.path)[0]['assumptions']['goal'], 'lose_weight')

    def test_unknown_activity_does_not_assume_sedentary(self):
        with connect(self.path) as c:
            c.execute("DELETE FROM metric_readings WHERE metric_type!='weight'")
        self.assertIsNone(recorded_context(self.day.isoformat(), self.path)['activity']['suggested_factor'])
        self.assertEqual(self.proposal()['status'], 'needs_input')

    def test_explicit_body_corrections_keep_honest_provenance(self):
        preview = self.proposal(weight_kg=82, height_cm=176)['preview']
        sources = preview['assumptions']['input_sources']
        self.assertEqual(sources['weight']['value'], 82)
        self.assertEqual(sources['weight']['source_name'], 'User supplied correction')
        self.assertEqual(sources['height'], 'User supplied correction (cm)')

    def test_api_requires_review_and_rejects_repeated_stale_save(self):
        from fastapi.testclient import TestClient
        from app.main import app
        proposal = self.proposal()
        body = {'request':self.request(),'day':self.day.isoformat(),'fingerprint':proposal['fingerprint'],'expected_revision':0,'confirmed':False}
        with patch('app.database.database_path',return_value=self.path), TestClient(app) as client:
            self.assertEqual(client.post('/api/nutrition/targets/suggestion/save',json=body).status_code, 422)
            body['confirmed'] = True
            self.assertEqual(client.post('/api/nutrition/targets/suggestion/save',json=body).status_code, 200)
            self.assertEqual(client.post('/api/nutrition/targets/suggestion/save',json=body).status_code, 400)
        self.assertEqual(len(target_history(self.path)), 1)

    def target_chat(self, message, pending=None, history=None, operation='target-chat', model_request=None):
        from app.nutrition_chat import chat
        response={'reply':'Model answer','ingredients':[],'uncertainties':[],'target_request':model_request,'model':'fixture'}
        with patch('app.nutrition_chat.analyze_food',return_value=response):
            return chat(message,self.day.isoformat(),'UTC',history=history,path=self.path,pending_target=pending,auto_log=True,operation_id=operation)

    def test_explicit_calories_recalculate_macros_and_preserve_default_comparison(self):
        proposal=self.proposal(calories_kcal=1800)
        self.assertEqual(proposal['status'],'proposal')
        p=proposal['preview']
        self.assertEqual(p['calories_kcal'],1800)
        self.assertEqual((p['protein_grams'],p['fat_grams'],p['carbohydrate_grams']),(128,50,210))
        self.assertEqual(p['assumptions']['calculated_calories_kcal'],2160)
        self.assertIn('more aggressive',' '.join(p['warnings']))
        saved=save(self.request(calories_kcal=1800),self.day.isoformat(),proposal['fingerprint'],0,self.path)
        self.assertEqual(saved['calories_kcal'],1800)

    def test_unsupported_calorie_preference_is_explained_never_silently_replaced(self):
        proposal=self.proposal(calories_kcal=1000)
        self.assertEqual(proposal['status'],'needs_professional_review')
        self.assertIn('1000',proposal['questions'][0])
        self.assertNotIn('preview',proposal)
        for value in (0,-1,True,float('nan'),float('inf'),20001):
            with self.subTest(value=value),self.assertRaises(ValueError):self.proposal(calories_kcal=value)

    def test_user_transcript_calorie_revisions_do_not_repeat_default(self):
        pending=self.request(target_weight_kg=70)
        for message in ('I think we can go to 1800 no?','I think the goal should be 1800 calories','Could we set the target to 1,800 calories?'):
            with self.subTest(message=message):
                result=self.target_chat(message,pending,operation=message,model_request=self.request())
                self.assertEqual(result['target_proposal']['preview']['calories_kcal'],1800)
                self.assertIn('1800',result['reply'])
                self.assertFalse(result.get('target_saved',False))
        self.assertEqual(target_history(self.path),[])

    def test_chat_creates_then_changes_saved_goal_and_day_snapshot(self):
        from app.nutrition import daily_status,save_meal
        day=self.day.isoformat();yesterday=(self.day-timedelta(days=1)).isoformat()
        first=self.proposal()
        saved=save(self.request(),day,first['fingerprint'],0,self.path)
        with connect(self.path) as c:
            for d in (day,yesterday):c.execute('INSERT INTO nutrition_day_targets VALUES(?,?,?,?,CURRENT_TIMESTAMP)',(d,'UTC',saved['id'],json.dumps(saved)))
        save_meal({'eaten_at':day+'T12:00:00+00:00','timezone':'UTC','meal_type':'lunch','notes':'','items':[{'name':'Lunch','quantity':1,'unit':'serving','nutrients':{'calories_kcal':400},'source':'Fixture','portion_basis':'estimated'}]},'lunch',path=self.path)
        result=self.target_chat('Set my goal to 1800 calories',self.request(target_weight_kg=70))
        self.assertTrue(result['target_saved']);self.assertIn('Saved your daily target',result['reply'])
        current=daily_status(self.day,'UTC',self.path)
        self.assertEqual(current['target']['calories_kcal'],1800)
        self.assertEqual(current['remaining']['calories_kcal'],1400)
        self.assertEqual(len(current['meals']),1)
        self.assertEqual(daily_status(date.fromisoformat(yesterday),'UTC',self.path)['target']['calories_kcal'],2160)
        result=self.target_chat('Change my goal to 1900 calories',operation='change-goal')
        self.assertTrue(result['target_saved'])
        self.assertEqual(result['saved_target']['calories_kcal'],1900)
        self.assertNotEqual(result['saved_target']['fat_grams'],50)
        self.assertEqual(len(target_history(self.path)),3)

    def test_confirmation_saves_proposal_and_retry_does_not_save_again(self):
        from app.nutrition_chat import chat
        pending=self.request(calories_kcal=1800)
        result=self.target_chat('yes',pending,[{'role':'assistant','content':'Review the 1800 kcal target before saving. Nothing has been saved.'}])
        self.assertTrue(result['target_saved'])
        with patch('app.nutrition_chat.analyze_food',side_effect=AssertionError('Retry must not infer again')):
            replay=chat('yes',self.day.isoformat(),'UTC',path=self.path,auto_log=True,operation_id='target-chat')
        self.assertTrue(replay['replayed']);self.assertEqual(len(target_history(self.path)),1)

    def test_tentative_negative_and_unrelated_confirmations_do_not_save(self):
        for message in ('Should I set my goal to 1800 calories?',"Don't change my target to 1800 calories",'Maybe save it','yes','Explain how to change my calorie goal','What happens if I change my target to 1800 calories'):
            with self.subTest(message=message):
                result=self.target_chat(message,self.request(calories_kcal=1800),[{'role':'assistant','content':'Did you eat lunch?'}],operation=message,model_request=self.request(calories_kcal=1800))
                self.assertFalse(result.get('target_saved',False))
        self.assertEqual(target_history(self.path),[])

    def test_confirmation_saves_the_reviewed_request_even_if_model_changes_it(self):
        result=self.target_chat('yes',self.request(calories_kcal=1800),[{'role':'assistant','content':'Review before saving. Nothing has been saved.'}],model_request=self.request(calories_kcal=2000))
        self.assertEqual(result['saved_target']['calories_kcal'],1800)

    def test_food_intake_numbers_do_not_change_the_goal(self):
        from app.nutrition_chat import calorie_preference
        for message in ('I ate 1800 calories, my target is 2000','I burned 2500 calories today','How many calories remaining from my 1800 goal?'):
            self.assertIsNone(calorie_preference(message,self.request()))

    def test_shared_chat_and_api_can_save_goals_without_review_button(self):
        from app.ai_chat import chat_stream
        from fastapi.testclient import TestClient
        from app.main import app
        response={'reply':'Model answer','ingredients':[],'uncertainties':[],'target_request':self.request(calories_kcal=1800),'model':'fixture'}
        with patch('app.nutrition_chat.analyze_food',return_value=response):
            events=[json.loads(event) for event in chat_stream('Set my goal to 1800 calories',path=self.path,timezone_name='UTC',chat_role='nutrition',nutrition_context={'day':self.day.isoformat()},operation_id='stream-goal')]
        self.assertEqual(events[-1]['type'],'complete',events)
        self.assertTrue(next(e['evidence']['nutrition'] for e in events if e['type']=='tool')['target_saved'])
        response['target_request']['calories_kcal']=1900
        with patch('app.database.database_path',return_value=self.path),patch('app.nutrition_chat.analyze_food',return_value=response),TestClient(app) as client:
            body={'message':'Change my goal to 1900 calories','day':self.day.isoformat(),'timezone':'UTC','operation_id':'api-goal'}
            saved=client.post('/api/nutrition/chat',json=body)
            self.assertEqual(saved.status_code,200,saved.text)
            self.assertTrue(saved.json()['target_saved'])
            self.assertEqual(saved.json()['saved_target']['calories_kcal'],1900)
            self.assertTrue(client.post('/api/nutrition/chat',json=body).json()['replayed'])
        self.assertEqual(len(target_history(self.path)),2)

    def test_failed_receipt_rolls_back_target_and_daily_snapshot(self):
        from app.nutrition import encoded
        def fail_receipt(value):
            if isinstance(value,dict) and value.get('target_saved'):raise ValueError('Receipt failure')
            return encoded(value)
        with patch('app.nutrition.encoded',side_effect=fail_receipt),self.assertRaisesRegex(ValueError,'Receipt failure'):
            self.target_chat('Set my goal to 1800 calories',self.request())
        self.assertEqual(target_history(self.path),[])
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM nutrition_day_targets').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM nutrition_chat_operations').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
