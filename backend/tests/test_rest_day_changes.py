import unittest

from app.session_changes import preview
from app.training import list_training
from app.training_adjustments import propose, save
from test_training_adjustments import NOW, TZ
import test_skill_agent as agent_fixture
from test_skill_agent import call, answer


class RestDayChangeTests(unittest.TestCase):
    def setUp(self):
        self.case=agent_fixture.AgentTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.path=self.case.path
        self.row=self.case.rows[0]

    def assert_only_skips_selected(self, result):
        self.assertEqual(result['status'],'proposal',result)
        self.assertEqual(len(result['adjustments']),1)
        self.assertEqual(result['adjustments'][0]['workout_id'],self.row['id'])
        self.assertEqual(result['adjustments'][0]['changes'],{'completion_status':'skipped'})

    def test_explicit_skip_ignores_accompanying_edit_text_and_replays_on_save(self):
        before=list_training(self.path)
        result=preview({'workout_id':self.row['id'],'expected_revision':self.row['revision'],'action':'skip',
            'request':'Make October 19 a rest day by skipping this planned ride only.\ncontinue'},self.path,NOW)
        self.assert_only_skips_selected(result)
        self.assertEqual(list_training(self.path),before)
        save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        after={w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(after[self.row['id']]['completion_status'],'skipped')
        self.assertEqual(after[self.row['id']]['definition'],self.row['definition'])
        for row in before['workouts']:
            if row['id']!=self.row['id']:self.assertEqual(after[row['id']],row)
        with self.assertRaises(ValueError):save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)

    def test_rest_day_phrases_do_not_enter_interval_rest_editor(self):
        for request in ('Make today a rest day','Change today to rest','Make today rest','Set this workout as rest'):
            with self.subTest(request=request):
                self.assert_only_skips_selected(propose(request,self.path,NOW,selected_id=self.row['id']))

    def test_chat_skip_is_isolated_from_another_days_edit(self):
        before=list_training(self.path)
        events=self.case.run_chat('Make today rest; tomorrow add another 15 minutes to endurance without warmup or cooldown',[
            call('load_skill',skill_id='training.sessions.edit'),
            call('preview_session_change',workout_id=self.row['id'],expected_revision=self.row['revision'],action='skip',
                 request='Make today a rest day by skipping this planned ride only.'),
            answer('Review skipping today’s session.',status='review')])
        result=next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool' and 'training_adjustment' in e.get('evidence',{}))
        self.assert_only_skips_selected(result)
        self.assertEqual(list_training(self.path),before)

    def test_published_skip_is_saved_then_removed_from_garmin_calendar(self):
        from test_garmin_publication import FakeGarmin
        from app.garmin_training_publish import preview as publication, approve, run, view
        client=FakeGarmin()
        factory=lambda path:client
        def send():
            proposal=publication({'workout_ids':[self.row['id']],'timezone':TZ},self.path,factory,NOW)
            approve(proposal['id'],self.path,factory,NOW)
            run(proposal['id'],self.path,factory)
            result=view(proposal['id'],self.path)
            self.assertEqual(result['status'],'verified',result)
        send()
        row=next(w for w in list_training(self.path)['workouts'] if w['id']==self.row['id'])
        calendar=dict(client.calendar)
        result=preview({'workout_id':row['id'],'expected_revision':row['revision'],'action':'skip',
                        'request':'Make today a rest day.'},self.path,NOW)
        self.assert_only_skips_selected(result)
        self.assertEqual(client.calendar,calendar)
        save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(client.calendar,calendar)
        send()
        self.assertFalse(client.calendar)
