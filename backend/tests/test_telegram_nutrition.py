"""Fictional Telegram reports use the app chat and the same authoritative meal log."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, date
from pathlib import Path
from unittest.mock import patch

from app import telegram_bot as bot
from app.database import connect, migrate
from app.nutrition import daily_status, remove_meal
from app.telegram_chat import conversation_reply
from test_telegram_bot import FakeTelegram

NOW = datetime(2026,10,26,8,tzinfo=timezone.utc).timestamp()
TZ = 'Asia/Jerusalem'
FOOD = {'reply':'ביצה מובנת','ingredients':[{'name':'ביצה','grams_low':100,'grams_high':100,
        'grams_proposed':100,'question':'','meal_type':'breakfast'}],
        'uncertainties':[],'target_request':None,'model':'fictional'}


class TelegramNutritionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.sqlite3';migrate(self.path)
        self.client=FakeTelegram()
        self.analysis=patch('app.nutrition_chat.analyze_food',side_effect=lambda **kw:copy.deepcopy(FOOD)).start()
        patch('app.nutrition_chat.search_foods',return_value={'foods':[]}).start()
        self.addCleanup(patch.stopall)
        with connect(self.path) as c:
            c.execute("UPDATE telegram_settings SET enabled=1,bot_id=99,bot_username='fictional',owner_user_id=10,owner_chat_id=10,timezone=?,conversation_id='conversation'",(TZ,))

    def send(self, number, text, sent_at=NOW, user=10, **kwargs):
        bot.intake([{'update_id':number,'message':{'message_id':number,'date':sent_at,
            'from':{'id':user},'chat':{'id':user,'type':'private'},'text':text,**kwargs}}],99,self.path,now=sent_at)

    def meals(self, day='2026-10-26'):
        return daily_status(date.fromisoformat(day),TZ,self.path)['meals']

    def context(self):
        with connect(self.path) as c:
            row=c.execute('SELECT context_json FROM telegram_conversation_state ORDER BY updated_at DESC LIMIT 1').fetchone()
            return json.loads(row[0]) if row else {}

    def test_hebrew_report_saves_through_the_shared_app_chat(self):
        from app.ai_chat import chat_stream
        self.send(1,'אכלתי ביצה 100 גרם')
        with patch('app.ai_chat.chat_stream',wraps=chat_stream) as shared:
            bot.process_one(self.path,now=NOW)
        self.assertEqual(shared.call_args.kwargs['chat_role'],'nutrition')
        self.assertEqual(shared.call_args.kwargs['operation_id'],'telegram:99:1')
        self.assertFalse(shared.call_args.kwargs['nutrition_allow_target_save'])
        self.assertEqual(len(self.meals()),1)
        self.assertGreater(self.meals()[0]['totals']['calories_kcal']['known_total'],0)
        self.assertEqual(self.context()['nutrition']['saved_meals'][0]['id'],self.meals()[0]['id'])
        self.assertTrue(bot.deliver_one(self.client,self.path))
        self.assertIn('נשמר ביומן',self.client.sent[0]['text'])

    def test_correction_updates_same_meal_and_scales_calories(self):
        self.send(1,'אכלתי ביצה 100 גרם');bot.process_one(self.path,now=NOW)
        before=self.meals()[0]
        self.send(2,'תתקן ביצה ל־150 גרם',NOW+30);bot.process_one(self.path,now=NOW+30)
        after=self.meals()[0]
        self.assertEqual(len(self.meals()),1)
        self.assertEqual(after['id'],before['id']);self.assertEqual(after['revision'],before['revision']+1)
        self.assertEqual(after['items'][0]['quantity'],150)
        self.assertAlmostEqual(after['totals']['calories_kcal']['known_total'],before['totals']['calories_kcal']['known_total']*1.5)
        self.assertEqual(self.analysis.call_count,1)

    def test_restart_after_meal_commit_replays_receipt_even_after_age_limit(self):
        self.send(1,'אכלתי ביצה 100 גרם')
        def crash(*args,**kwargs):
            conversation_reply(*args,**kwargs)
            raise SystemExit('fictional crash after domain commit')
        with patch('app.telegram_chat.conversation_reply',side_effect=crash):
            with self.assertRaises(SystemExit):bot.process_one(self.path,now=NOW)
        self.assertEqual(len(self.meals()),1)
        bot.recover(self.path)
        self.analysis.side_effect=AssertionError('Saved reports must not rerun inference')
        bot.process_one(self.path,now=NOW+1200)
        self.assertEqual(len(self.meals()),1)
        self.assertEqual(self.context()['role'],'nutrition')
        bot.deliver_one(self.client,self.path)
        self.assertIn('נשמר ביומן',self.client.sent[0]['text'])

    def test_new_message_same_food_is_a_new_meal_but_redelivery_is_not(self):
        for n in (1,1,2):
            self.send(n,'אכלתי ביצה 100 גרם');bot.process_one(self.path,now=NOW)
        self.assertEqual(len(self.meals()),2)

    def test_unauthorized_sender_cannot_log(self):
        self.send(1,'אכלתי ביצה 100 גרם',user=20)
        self.assertFalse(bot.process_one(self.path,now=NOW))
        self.analysis.assert_not_called();self.assertEqual(self.meals(),[])

    def test_disable_during_inference_prevents_meal_commit(self):
        def disabled(**kwargs):
            bot.disable(self.path)
            return copy.deepcopy(FOOD)
        self.analysis.side_effect=disabled
        self.send(1,'אכלתי ביצה 100 גרם');bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals(),[])
        self.assertFalse(bot.deliver_one(self.client,self.path))

    def test_stale_meal_revision_does_not_overwrite_browser_change(self):
        self.send(1,'אכלתי ביצה 100 גרם');bot.process_one(self.path,now=NOW)
        meal=self.meals()[0]
        remove_meal(meal['id'],meal['revision'],True,self.path)
        self.send(2,'תתקן ביצה ל־150 גרם');bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals(),[])
        with connect(self.path) as c:
            self.assertTrue(c.execute('SELECT reply FROM telegram_updates WHERE update_id=2').fetchone()[0])

    def test_questions_and_negated_consumption_do_not_log(self):
        for i,text in enumerate(('כמה קלוריות יש בביצה?','לא אכלתי ביצה','What if I ate an egg?'),1):
            self.send(i,text);bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals(),[])

    def test_reference_time_across_midnight_uses_original_sent_day(self):
        sent=datetime(2026,10,25,21,58,tzinfo=timezone.utc).timestamp() # 23:58 local after DST.
        self.send(1,'אכלתי ביצה 100 גרם',sent_at=sent)
        bot.process_one(self.path,now=sent+240)
        self.assertEqual(len(self.meals('2026-10-25')),1)
        self.assertEqual(self.meals('2026-10-26'),[])

    def test_pending_foods_survive_restart_and_explicit_save_followup(self):
        self.send(1,'How many calories in an egg?');bot.process_one(self.path,now=NOW)
        self.assertTrue(self.context()['nutrition']['pending_foods'])
        self.assertEqual(self.meals(),[])
        bot.recover(self.path)
        self.send(2,'תשמור את הארוחה');bot.process_one(self.path,now=NOW)
        self.assertEqual(len(self.meals()),1)
        self.assertEqual(self.context()['nutrition']['pending_foods'],[])

    def test_training_writes_still_use_read_only_adapter(self):
        self.send(1,'Change my workout tomorrow')
        with patch('app.telegram_chat.answer',return_value='Use the browser to review this change') as read, patch('app.ai_chat.chat_stream') as write:
            bot.process_one(self.path,now=NOW)
        read.assert_called_once();write.assert_not_called()

    def test_nutrition_target_write_is_not_enabled_with_meal_access(self):
        target=copy.deepcopy(FOOD);target.update(ingredients=[],target_request={'goal':'maintain','calories_kcal':2000})
        self.analysis.side_effect=lambda **kw:copy.deepcopy(target)
        proposal={'status':'proposal','request':target['target_request'],'questions':[],
            'preview':{'calories_kcal':2000,'protein_grams':100,'fat_grams':60,'carbohydrate_grams':265,
                'warnings':[],'assumptions':{'maintenance_kcal':2200,'calculated_calories_kcal':2000}}}
        self.send(1,'Set my goal to 2000 calories')
        with patch('app.nutrition_targets.propose',return_value=proposal),patch('app.nutrition_chat.save_chat_target') as save:
            bot.process_one(self.path,now=NOW)
        save.assert_not_called()
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM nutrition_targets').fetchone()[0],0)

    def test_ambiguous_correction_does_not_change_either_food(self):
        foods=copy.deepcopy(FOOD)
        foods['ingredients'].append({**copy.deepcopy(FOOD['ingredients'][0]),'name':'אבוקדו','grams_low':50,'grams_high':50,'grams_proposed':50})
        self.analysis.side_effect=lambda **kw:copy.deepcopy(foods)
        self.send(1,'אכלתי ביצה ואבוקדו');bot.process_one(self.path,now=NOW)
        before=self.meals()[0]
        self.send(2,'תתקן ל־150 גרם');bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals()[0]['revision'],before['revision'])
        self.assertEqual([i['quantity'] for i in self.meals()[0]['items']],[100,50])

    def test_named_correction_preserves_other_food_and_retries_once(self):
        foods=copy.deepcopy(FOOD)
        foods['ingredients'].append({**copy.deepcopy(FOOD['ingredients'][0]),'name':'אבוקדו','grams_low':50,'grams_high':50,'grams_proposed':50})
        self.analysis.side_effect=lambda **kw:copy.deepcopy(foods)
        self.send(1,'אכלתי ביצה ואבוקדו');bot.process_one(self.path,now=NOW)
        self.send(2,'תתקן ביצה ל־150 גרם');bot.process_one(self.path,now=NOW)
        meal=self.meals()[0]
        self.assertEqual([i['quantity'] for i in meal['items']],[150,50])
        with connect(self.path) as c:c.execute("UPDATE telegram_updates SET state='processing' WHERE update_id=2")
        bot.recover(self.path);bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals()[0]['revision'],meal['revision'])

    def test_negated_correction_and_hypothetical_do_not_write(self):
        self.send(1,'אכלתי ביצה 100 גרם');bot.process_one(self.path,now=NOW)
        before=self.meals()[0]
        for n,message in enumerate(('אל תתקן ביצה ל־150 גרם','לא תעדכן ביצה ל־150 גרם','What if I change egg to 150 g?'),2):
            self.send(n,message);bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals()[0]['revision'],before['revision'])
        self.assertEqual(len(self.meals()),1)

    def test_hebrew_pending_save_commands_and_dictation_typo_persist(self):
        commands=('שמור את זה בנשנושים','יש אישור תתעד את זה בנשנושים','מאה אחוז תוסף לסנאקס','תנסה שוב לשמור','תמס הם שוב לשמור')
        for n,command in enumerate(commands):
            with self.subTest(command=command):
                with connect(self.path) as c:
                    c.execute('UPDATE telegram_settings SET conversation_id=?',(f'confirm-{n}',))
                estimate=copy.deepcopy(FOOD)
                estimate['ingredients']=[{'name':'עוגיות בדיקה','grams_low':20,'grams_high':30,'grams_proposed':24,'question':'','meal_type':'snack',
                    'nutrients_per_100g':{'calories_kcal':450,'protein_grams':8,'fat_grams':16,'carbohydrate_grams':65},'estimate_assumptions':'Fictional test reference.'}]
                self.analysis.side_effect=lambda **kw:copy.deepcopy(estimate)
                self.send(100+n*2,'כמה קלוריות בעוגיות בדיקה?');bot.process_one(self.path,now=NOW)
                self.analysis.side_effect=AssertionError('Retained estimate must save without another model call')
                self.send(101+n*2,command);bot.process_one(self.path,now=NOW)
                self.assertEqual(len(self.meals()),n+1)
                self.assertEqual(self.meals()[-1]['meal_type'],'snack')
                self.assertAlmostEqual(self.meals()[-1]['totals']['calories_kcal']['known_total'],108)

    def test_pending_status_questions_and_negative_commands_do_not_save(self):
        self.send(1,'כמה קלוריות יש בביצה?');bot.process_one(self.path,now=NOW)
        for n,message in enumerate(('שמרת את זה?','למה? תאשר ששמרת ביומן','האם זה נשמר?','אל תתעד את זה','אל תוסיף לנשנושים','אם תשמור את זה'),2):
            self.send(n,message);bot.process_one(self.path,now=NOW)
        self.assertEqual(self.meals(),[])

    def test_legacy_pending_proposal_can_save_without_retained_estimates(self):
        pending={'role':'nutrition','nutrition':{'day':'2026-10-26','pending_foods':[{'name':'עוגיות בדיקה','grams_low':20,'grams_high':30,'grams_proposed':24,'question':'','meal_type':'snack'}]}}
        with connect(self.path) as c:c.execute('INSERT INTO telegram_conversation_state(bot_id,conversation_id,context_json) VALUES(99,?,?)',('conversation',json.dumps(pending)))
        enriched=copy.deepcopy(FOOD);enriched['ingredients']=[{**pending['nutrition']['pending_foods'][0],
            'nutrients_per_100g':{'calories_kcal':450,'protein_grams':8,'fat_grams':16,'carbohydrate_grams':65}}]
        self.analysis.side_effect=lambda **kw:copy.deepcopy(enriched)
        self.send(1,'יש אישור תתעד את זה בנשנושים');bot.process_one(self.path,now=NOW)
        self.assertEqual(len(self.meals()),1)
        self.assertAlmostEqual(self.meals()[0]['totals']['calories_kcal']['known_total'],108)

    def test_new_save_again_message_confirms_existing_meal_without_duplicate(self):
        self.send(1,'אכלתי ביצה 100 גרם');bot.process_one(self.path,now=NOW)
        self.analysis.side_effect=AssertionError('A saved confirmation needs no new food inference')
        for n,message in enumerate(('תנסה שוב לשמור','יש אישור תתעד את זה בנשנושים'),2):
            self.send(n,message);bot.process_one(self.path,now=NOW)
        self.assertEqual(len(self.meals()),1)
        with connect(self.path) as c:
            self.assertIn('כבר שמורה',c.execute('SELECT reply FROM telegram_updates WHERE update_id=3').fetchone()[0])


if __name__=='__main__':unittest.main()
