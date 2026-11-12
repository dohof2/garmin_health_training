import copy
import json
import unittest

from app.database import connect
from app.session_changes import preview
from app.training import encoded, list_training
from app.training_adjustments import save
from app.training_prescriptions import endurance
from app.training_coach import DEFAULT
from test_training_adjustments import NOW, TZ


class EnduranceExtensionTests(unittest.TestCase):
    def setUp(self):
        from test_workout_edit_followthrough import FollowthroughTests
        self.case = FollowthroughTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.path = self.case.path
        self.identifier = self.case.workout['id']
        self.case.set_definition(endurance('vo2',60,DEFAULT,today=NOW.date()))
        # Leave room in the accepted week for a deliberate extension.
        with connect(self.path) as c:
            peer=c.execute("SELECT id FROM planned_workouts WHERE id!=? AND completion_status='planned' ORDER BY scheduled_for LIMIT 1",(self.identifier,)).fetchone()
            c.execute("UPDATE planned_workouts SET completion_status='skipped' WHERE id=?",(peer['id'],))

    def proposal(self, request='Keep the VO2 max and add another 15 minutes of edurance'):
        row = self.case.current()
        return preview({'workout_id':self.identifier,'expected_revision':row['revision'],
                        'action':'adjust','request':request},self.path,NOW)

    def test_extension_preserves_vo2_blocks_and_targets_through_save(self):
        before = list_training(self.path)
        original = self.case.current()['definition']
        result = self.proposal()
        self.assertEqual(result['status'],'proposal',result)
        self.assertEqual(list_training(self.path),before)
        updated = result['adjustments'][0]['changes']['definition']
        self.assertEqual(updated['duration_minutes'],75)
        for old,new in zip(original['steps'],updated['steps']):
            expected = copy.deepcopy(old)
            if old['name']=='Steady endurance':
                self.assertEqual(old['duration_seconds'],1800)
                expected['duration_seconds']=2700
            self.assertEqual(new,expected)
        save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(self.case.current()['definition'],updated)
        rows={w['id']:w for w in list_training(self.path)['workouts']}
        for row in before['workouts']:
            if row['id']!=self.identifier:self.assertEqual(rows[row['id']],row)
        with self.assertRaises(ValueError):
            save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)

    def test_explicit_from_to_duration(self):
        result=self.proposal('Extend only the steady endurance section from 30:00 to 45:00; keep VO2 intervals unchanged')
        self.assertEqual(result['status'],'proposal',result)
        self.assertEqual(result['adjustments'][0]['changes']['definition']['duration_minutes'],75)

    def test_availability_and_recovery_rechecked_before_save(self):
        result=self.proposal()
        self.assertEqual(result['status'],'proposal',result)
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(source_name,metric_type,value,unit,recorded_at) VALUES('garmin_export','sleep_score',30,'score','2026-10-19T03:00:00+00:00')")
        before=list_training(self.path)
        self.assertEqual(self.proposal()['status'],'not_recommended')
        with self.assertRaises(ValueError):save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(list_training(self.path),before)

    def test_excess_volume_and_negation_do_not_write(self):
        before=list_training(self.path)
        for request in ('Add 60 minutes to steady endurance','Do not add 15 minutes to endurance',
                        'Extend endurance from 20:00 to 45:00',
                        'Add 15 minutes to endurance and change power target to 180-200 W'):
            with self.subTest(request=request):
                self.assertNotEqual(self.proposal(request)['status'],'proposal')
                self.assertEqual(list_training(self.path),before)

    def test_weekly_allowance_is_rechecked_on_save(self):
        result=self.proposal()
        self.assertEqual(result['status'],'proposal',result)
        with connect(self.path) as c:
            row=c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status='planned' LIMIT 1",(self.identifier,)).fetchone()
            definition=json.loads(row['definition_json'])
            definition['duration_minutes']=720
            c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(definition),row['id']))
        before=list_training(self.path)
        rejected=self.proposal()
        self.assertEqual(rejected['status'],'not_recommended',rejected)
        self.assertIn('week',rejected['message'])
        with self.assertRaises(ValueError):save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(list_training(self.path),before)

    def test_published_extension_updates_existing_garmin_workout(self):
        from test_garmin_publication import FakeGarmin
        from app.garmin_training_publish import preview as publication, approve, run, view
        client=FakeGarmin()
        factory=lambda path:client
        def send():
            proposal=publication({'workout_ids':[self.identifier],'timezone':TZ},self.path,factory,NOW)
            approve(proposal['id'],self.path,factory,NOW)
            run(proposal['id'],self.path,factory)
            self.assertEqual(view(proposal['id'],self.path)['status'],'verified')
        send()
        remote=self.case.current()['garmin_workout_id']
        result=self.proposal()
        self.assertEqual(result['status'],'proposal',result)
        save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(self.case.current()['publish_status'],'update_needed')
        self.assertEqual(self.case.current()['garmin_workout_id'],remote)
        send()
        self.assertEqual((client.creates,client.updates,client.schedules),(1,1,1))
