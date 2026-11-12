"""Daily strength recommendations respect time and history-derived limits."""
import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.active_training import suggest_today
from app.database import connect, migrate
from app.training import list_training, save_preferences
from app.training_volume import estimates
from test_long_ride_allocation import preferences

NOW = datetime(2026, 11, 7, 10, tzinfo=timezone.utc)
TZ = 'Asia/Jerusalem'
READY = {'latest': {'date': '2026-11-07', 'score': 50, 'status': 'complete', 'groups': []}}


class TodayStrengthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'db.sqlite'
        migrate(self.path)
        answers = copy.deepcopy(preferences())
        answers['experience']['strength'] = 'regular'
        answers['weekly_caps'] = {'strength': {'range_min_minutes': 120, 'max_minutes': 120}}
        save_preferences(answers, 0, self.path, NOW)
        with connect(self.path) as c:
            for i in range(3):
                c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_connect','strength_training',?,180)",
                          (f'short-strength-{i}', f'2026-11-0{i+1}T06:00:00Z'))

    def suggest(self, minutes=40):
        with patch('app.readiness.readiness_history', return_value=READY):
            return suggest_today({'minutes': minutes, 'sport': 'strength', 'timezone': TZ}, self.path, NOW)

    def test_sparse_short_history_does_not_reject_forty_minute_allowance(self):
        before = list_training(self.path)
        # An approved weekly override can leave a 40-minute allowance while
        # sparse history still supplies the provisional 15-minute reference.
        with self.limited_estimates(40, 15):
            result = self.suggest()
        self.assertEqual(result['status'], 'suggestion', result.get('questions'))
        self.assertEqual(result['available_minutes'], 40)
        self.assertEqual(result['volume_estimates']['strength']['long_session_minutes'], 15)
        session = result['session']
        self.assertEqual(session['sport'], 'strength')
        self.assertEqual(session['duration_minutes'], 20)
        self.assertGreaterEqual(len(session['exercises']), 2)
        self.assertTrue(all(e['sets'] == 2 for e in session['exercises']))
        self.assertFalse(result['saved'])
        self.assertEqual(list_training(self.path), before)

    def test_request_under_template_minimum_still_needs_more_time(self):
        result = self.suggest(15)
        self.assertEqual(result['status'], 'needs_input')
        self.assertIsNone(result['session'])
        self.assertIn('at least 20 minutes', result['questions'][0])

    def limited_estimates(self, ceiling, reference):
        def limited(*args, **kwargs):
            result = estimates(*args, **kwargs)
            result['strength'].update(effective_ceiling_minutes=ceiling, long_session_minutes=reference)
            return result
        return patch('app.training_volume.estimates', side_effect=limited)

    def test_lower_training_ceiling_explains_limit_without_blaming_user_time(self):
        with self.limited_estimates(15, 15):
            result = self.suggest()
        self.assertEqual(result['status'], 'needs_review')
        self.assertIsNone(result['session'])
        self.assertIn('You supplied 40 minutes', result['questions'][0])
        self.assertIn('to 15', result['questions'][0])

    def test_fractional_internal_dose_rounds_down_for_template(self):
        with self.limited_estimates(25.5, 25.5):
            result = self.suggest()
        self.assertEqual(result['status'], 'suggestion', result.get('questions'))
        self.assertEqual(result['session']['duration_minutes'], 25)

    def test_pain_still_returns_rest(self):
        save_preferences({'pain_or_illness': True}, 1, self.path, NOW)
        result = self.suggest()
        self.assertEqual(result['session']['sport'], 'rest')
