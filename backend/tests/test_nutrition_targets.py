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


if __name__ == '__main__':
    unittest.main()
