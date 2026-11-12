import copy
import json
import unittest
from unittest.mock import patch
import test_strength_set_requests as fixtures
NOW = fixtures.NOW
from app.database import connect
from app.strength_prescription import preview
from app.training_adjustments import propose, save
from app.session_changes import preview as session_preview


class StrengthPrescriptionTests(unittest.TestCase):
    setUp = fixtures.StrengthSetRequestTests.setUp

    def args(self):
        return {'workouts':[{'workout_id':'next','expected_revision':1},{'workout_id':'later','expected_revision':1}], 'sets':3,'rest_seconds':70}

    def test_batch_total_sets_rest_and_atomic_reviewed_save(self):
        with patch('app.strength_prescription._context',return_value=self.context):
            result=preview(self.args(),self.path,NOW)
            self.assertEqual(result['status'],'proposal')
            self.assertEqual(len(result['adjustments']),2)
            for item in result['adjustments']:
                for e,old in zip(item['changes']['definition']['exercises'],self.definition['exercises']):
                    self.assertEqual((e['sets'],e['rest_seconds']),(3,70))
                    self.assertEqual((e['load'],e['repetitions']),(old['load'],old['repetitions']))
            with connect(self.path) as c:
                self.assertEqual(json.loads(c.execute("SELECT definition_json FROM planned_workouts WHERE id='next'").fetchone()[0])['exercises'][0]['sets'],1)
            save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        with connect(self.path) as c:
            for name in ('next','later'):
                self.assertEqual(json.loads(c.execute('SELECT definition_json FROM planned_workouts WHERE id=?',(name,)).fetchone()[0])['exercises'][0]['rest_seconds'],70)
            self.assertEqual(json.loads(c.execute("SELECT definition_json FROM planned_workouts WHERE id='done'").fetchone()[0])['exercises'][0]['sets'],1)

    def test_local_save_preserves_unresolved_publication(self):
        with connect(self.path) as c:
            c.execute("UPDATE planned_workouts SET publish_status='publishing' WHERE id='next'")
        with patch('app.strength_prescription._context',return_value=self.context):
            result=preview(self.args(),self.path,NOW)
            self.assertIn('local edit only',result['message'])
            save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        with connect(self.path) as c:
            self.assertEqual(c.execute("SELECT publish_status FROM planned_workouts WHERE id='next'").fetchone()[0],'publishing')
            self.assertEqual(c.execute('SELECT count(*) FROM garmin_publication_jobs').fetchone()[0],0)

    def test_stale_batch_and_fixed_commitment_cannot_be_applied(self):
        args=self.args();args['workouts'][1]['expected_revision']=99
        with patch('app.strength_prescription._context',return_value=self.context):
            with self.assertRaisesRegex(ValueError,'changed'):preview(args,self.path,NOW)
            old=copy.deepcopy(self.definition);old['fixed_commitment']=True
            with connect(self.path) as c:c.execute("UPDATE planned_workouts SET definition_json=? WHERE id='next'",(json.dumps(old),))
            with self.assertRaisesRegex(ValueError,'commitment'):preview(self.args(),self.path,NOW)

    def test_verbatim_legacy_request_uses_total_sets_and_rest(self):
        with patch('app.strength_prescription._context',return_value=self.context):
            result=session_preview({'workout_id':'next','expected_revision':1,'action':'adjust','request':'Set every existing strength exercise to 3 total sets with 70 seconds rest between sets. Preserve exercises, repetitions and loads; update estimated duration as needed. Explicit user request, including this recovery week.'},self.path,NOW)
            self.assertEqual(result['adjustments'][0]['changes']['definition']['exercises'][0]['rest_seconds'],70)
            self.assertEqual(propose(result['request'],self.path,NOW)['fingerprint'],result['fingerprint'])

    def test_rest_only_preserves_sets_and_shared_day_limit_is_enforced(self):
        args=self.args();args.pop('sets')
        with patch('app.strength_prescription._context',return_value=self.context):
            result=preview(args,self.path,NOW)
            self.assertEqual(result['adjustments'][0]['changes']['definition']['exercises'][0]['sets'],1)
            for day in self.context['answers']['week_schedule']:day['total_limit_minutes']=10
            with self.assertRaises(ValueError):preview(self.args(),self.path,NOW)
