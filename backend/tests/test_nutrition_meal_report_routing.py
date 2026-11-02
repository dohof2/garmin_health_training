"""New meal reports must not be intercepted by ingredient-correction routing."""
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.ai_chat import chat_stream
from app.database import migrate
from app.nutrition import daily_status
from app.nutrition_correction import correction_intent
from app.nutrition_drafts import requested_day, select_context
from app.nutrition_logging import consumption_report

REPORT = ('yetarday for breakfast aet 2 fried eggs as normal at lunch a but with '
          '2 vegis saugesages ) with another 4 sauseges for supper cuscus (5 spoons) '
          'with soup and 2 buullets (tunisiam meat wrapped in potatoes piling)')
NOW = datetime(2026, 10, 31, 10, tzinfo=timezone.utc)
TZ = 'Asia/Jerusalem'


class MealReportRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        migrate(self.path)

    def test_meal_descriptions_and_spoons_are_not_correction_instructions(self):
        for message in (REPORT, 'Breakfast: 2 fried eggs', 'For lunch 5 spoons of couscous',
                        'I aet raw tahini with lunch', 'For supper had soup with raw vegetables'):
            with self.subTest(message=message):
                self.assertTrue(consumption_report(message))
                self.assertFalse(correction_intent(message, allow_followup=True))
        self.assertFalse(correction_intent('5 spoons of couscous'))

    def test_questions_future_meals_and_denials_do_not_authorize_logging(self):
        for message in ('What should I eat for lunch?', 'For lunch tomorrow I will have 2 eggs',
                        'Breakfast: 2 eggs would be a good idea', 'I did not eat lunch',
                        'Do not log breakfast: 2 eggs', 'For lunch suggest 2 sausages'):
            with self.subTest(message=message):
                self.assertFalse(consumption_report(message))

    def test_yesterday_spelling_is_shared_by_context_and_storage(self):
        for spelling in ('yesterday', 'yestarday', 'yetarday', 'yesyerday', 'yesterdya', 'אתמול'):
            with self.subTest(spelling=spelling):
                self.assertEqual(requested_day(spelling, '2026-10-31'), '2026-10-30')
                context, _ = select_context({'day': '2026-10-31', 'pending_foods': ['old']}, spelling, '2026-10-31')
                self.assertEqual(context, {'day': '2026-10-30'})
        self.assertEqual(requested_day('yesterday on 2026-10-28', '2026-10-31'), '2026-10-28')

    def test_exact_report_reaches_food_analysis_and_logs_three_meals_once(self):
        # The provider still interprets food identities/portions. This regression
        # checks actual routing, date selection, atomic grouping and retry storage.
        foods = [('Fried eggs', 'breakfast', 100), ('Bun', 'lunch', 60),
                 ('Vegetarian sausages', 'lunch', 100), ('Vegetarian sausages', 'dinner', 200),
                 ('Cooked couscous', 'dinner', 75),
                 ('Soup', 'dinner', 250), ('Tunisian meat and potato boulettes', 'dinner', 200)]
        response = {'ingredients': [dict(name=name, meal_type=meal, grams_low=grams,
                    grams_high=grams, grams_proposed=grams, question='') for name, meal, grams in foods],
                    'uncertainties': ['Household portions estimated'], 'reply': '', 'target_request': None}
        kwargs = dict(path=self.path, timezone_name=TZ, message_time=NOW,
                      nutrition_context={'day': '2026-10-31'}, operation_id='exact-report')
        with patch('app.nutrition_chat.analyze_food', return_value=copy.deepcopy(response)) as analyze, \
             patch('app.nutrition_chat.search_foods', return_value={'foods': []}), \
             patch('app.nutrition_correction.analyze_food', side_effect=AssertionError('Not a correction')):
            events = [json.loads(event) for event in chat_stream(REPORT, **kwargs)]
            self.assertEqual(events[-1]['type'], 'complete', events)
            result = next(event['evidence']['nutrition'] for event in events if event['type'] == 'tool')
            self.assertTrue(result['logged'])
            self.assertEqual(result['context_date'], '2026-10-30')
            self.assertEqual(analyze.call_args.kwargs['review_context']['date'], '2026-10-30')
            self.assertNotIn('correction_candidates', analyze.call_args.kwargs['review_context'])
            analyze.reset_mock()
            replay = [json.loads(event) for event in chat_stream(REPORT, **kwargs)]
            self.assertTrue(next(event['evidence']['nutrition']['replayed'] for event in replay if event['type'] == 'tool'))
            analyze.assert_not_called()
        meals = daily_status(date(2026, 10, 30), TZ, self.path)['meals']
        self.assertEqual(len(meals), 3)
        self.assertEqual({meal['meal_type']: [item['name'] for item in meal['items']] for meal in meals},
                         {kind: [name for name, meal, _ in foods if meal == kind] for kind in ('breakfast', 'lunch', 'dinner')})
        self.assertEqual(daily_status(date(2026, 10, 31), TZ, self.path)['meals'], [])

    def test_short_correction_requires_referenced_saved_meal(self):
        self.assertFalse(correction_intent('raw, 4 spoons'))
        self.assertTrue(correction_intent('raw, 4 spoons', allow_followup=True))
        self.assertTrue(correction_intent('Actually it was raw tahini, 4 spoons'))

    def test_pending_portion_answer_keeps_other_meals_instead_of_editing_saved_food(self):
        from app.nutrition_chat import chat
        pending = [dict(name=name, meal_type=kind, grams_low=grams, grams_high=grams,
                        grams_proposed=grams, question='') for name, kind, grams in
                   [('Eggs', 'breakfast', 100), ('Vegetarian sausages', 'lunch', 240),
                    ('Tahini paste', 'dinner', 30)]]
        clarified = {**pending[-1], 'grams_low': 60, 'grams_high': 60, 'grams_proposed': 60}
        with patch('app.nutrition_chat.analyze_food', return_value={
                'ingredients': [clarified], 'uncertainties': [], 'reply': 'Portion clarified.'}), \
             patch('app.nutrition_chat.search_foods', return_value={'foods': []}), \
             patch('app.nutrition_correction.analyze_food', side_effect=AssertionError('Not a saved correction')):
            result = chat('raw, 4 spoons', '2026-10-31', TZ, path=self.path, auto_log=True,
                          pending_foods=pending, saved_meals=[{'id': 'older-saved-meal', 'revision': 1}],
                          message_time=NOW)
        self.assertEqual([(food['name'], food['grams_proposed']) for food in result['ingredients']],
                         [('Eggs', 100), ('Vegetarian sausages', 240), ('Tahini paste', 60)])
        self.assertFalse(result.get('logged', False))
