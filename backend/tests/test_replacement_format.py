"""Replacement details must be applied to the new ride before Save."""
import json
import unittest

from app.database import connect
from app.session_changes import preview
from app.training import encoded, list_training
from app.training_adjustments import propose, save
from app.training_coach import read_brief
from test_training_adjustments import NOW


class ReplacementFormatTests(unittest.TestCase):
    def setUp(self):
        from test_skill_agent import AgentTests
        case = AgentTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.replacement_fixture()
        self.path = case.path
        self.identifier = case.rows[1]['id']
        with connect(self.path) as c:
            answers = json.loads(c.execute('SELECT answers_json FROM training_preferences WHERE id=1').fetchone()[0])
            answers['weekly_caps'] = {'cycling': {'range_min_minutes':300, 'max_minutes':330}}
            c.execute('UPDATE training_preferences SET answers_json=? WHERE id=1', (encoded(answers),))

    def test_structured_replacement_preserves_duration_power_and_single_block(self):
        before = list_training(self.path)
        brief = read_brief(self.path)
        result = preview({'workout_id':self.identifier, 'expected_revision':1,
            'action':'replace_with_endurance', 'minutes':60,
            'request':'Today a 1:00:00 steady ride at 125–155 W, with no separate warm-up or cool-down.'}, self.path, NOW)
        self.assertEqual(result['status'], 'proposal', result)
        self.assertEqual(list_training(self.path), before)
        definition = result['adjustments'][0]['changes']['definition']
        self.assertEqual(definition['sport'], 'cycling')
        self.assertEqual(definition['duration_minutes'], 60)
        self.assertEqual(len(definition['steps']), 1)
        step = definition['steps'][0]
        self.assertEqual(step['duration_seconds'], 3600)
        self.assertEqual((step['target']['type'], step['target']['lower'], step['target']['upper']), ('power',125,155))
        save({'message':result['request'], 'fingerprint':result['fingerprint']}, self.path, NOW)
        after = {w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(after[self.identifier]['definition'], definition)
        self.assertEqual(read_brief(self.path), brief)
        for row in before['workouts']:
            if row['id'] != self.identifier:
                self.assertEqual(after[row['id']], row)

    def test_plain_replacement_clock_duration_does_not_save_format_preferences(self):
        request = 'Replace today strength with a 1:00:00 steady ride at 125-155 W without warmup or cooldown'
        result = propose(request, self.path, NOW)
        self.assertEqual(result['status'], 'proposal', result)
        self.assertEqual(len(result['adjustments']), 1)
        self.assertEqual(result['adjustments'][0]['workout_id'], self.identifier)
        self.assertEqual(len(result['adjustments'][0]['changes']['definition']['steps']), 1)
        brief = read_brief(self.path)
        save({'message':request, 'fingerprint':result['fingerprint']}, self.path, NOW)
        self.assertEqual(read_brief(self.path), brief)

    def test_invalid_power_range_does_not_prepare_partial_replacement(self):
        before = list_training(self.path)
        result = preview({'workout_id':self.identifier, 'expected_revision':1,
            'action':'replace_with_endurance', 'minutes':60,
            'request':'steady ride at 155–125 W with no warmup or cooldown'}, self.path, NOW)
        self.assertEqual(result['status'], 'needs_input', result)
        self.assertFalse(result['adjustments'])
        self.assertEqual(list_training(self.path), before)
