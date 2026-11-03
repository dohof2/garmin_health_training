"""New meal reports must not be intercepted by ingredient-correction routing."""
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

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


    def test_short_correction_requires_referenced_saved_meal(self):
        self.assertFalse(correction_intent('raw, 4 spoons'))
        self.assertTrue(correction_intent('raw, 4 spoons', allow_followup=True))
        self.assertTrue(correction_intent('Actually it was raw tahini, 4 spoons'))
