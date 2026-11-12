import copy
import json
import unittest
from unittest.mock import patch
from datetime import datetime,timezone

from app.database import connect
from app.training import encoded,list_training,workout_definition
from app.training_prescriptions import strength
from app.strength_adjustments import apply_policy
from app.strength_exercise_edits import preview
from app.session_changes import preview as session_preview
from app.training_adjustments import save
from app.training_volume import estimates
from app.training_notes import read as read_notes
from app.garmin_training_publish import send,run,view
from test_training_adjustments import TZ
from test_long_ride_allocation import preferences
import test_garmin_publication as fixtures
import test_skill_agent as agents

NOW=datetime(2026,11,4,9,tzinfo=timezone.utc)


class StrengthExerciseAdditionTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.GarminPublicationQC();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.path=self.case.path;self.client=self.case.client;self.factory=self.case.factory
        self.answers=preferences();self.answers.update(equipment=['bike','bodyweight','pull_up_bar','dip_bars'],weekly_minutes={'strength':120})
        with connect(self.path) as c:
            program=c.execute('SELECT * FROM active_training_program').fetchone();self.root=program['plan_id'];state=json.loads(program['state_json'])
            state['brief'].update(strength_role='secondary',strength_purpose='cycling_support',strength_capacity={'pull_up_reps':3,'dip_reps':5})
            policy={'sets':2,'duration_reference_minutes':12.32,'reference_total_sets':5,'weekly_allowance_minutes':50,
                    'reference_repetitions':{'air_squat':10,'hip_raise':10,'dead_bug':10,'pullup_progression':1,'dip_progression':3}}
            state['strength_set_policy']=policy
            self.brief=state['brief']
            c.execute('UPDATE active_training_program SET state_json=?',(encoded(state),))
            c.execute('UPDATE training_preferences SET answers_json=?',(encoded(self.answers),))
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('performed-strength','garmin_connect','strength_training','2026-11-02T08:00:00Z',1392)")
            self.targets=[]
            for index,day in enumerate(('2026-11-05','2026-11-10','2026-11-12')):
                definition=apply_policy(strength(workout_definition('strength_foundation',30,self.answers),state['brief'],self.answers,observed_at=NOW),policy)
                definition.update(scheduled_date=day,time_unspecified=True,schedule_timezone=TZ,schedule_slot_id=str(1 if index else 3))
                identifier='strength-'+str(index)
                c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,'strength',?,?,?)",(identifier,self.root,definition['title'],day+'T12:00:00+02:00',encoded(definition)))
                self.targets.append({'workout_id':identifier,'expected_revision':1})

    def arguments(self):return {'workouts':self.targets,'exercise':{'id':'calf_raise','sets':2}}

    def test_batch_adds_calf_raises_to_only_three_dates_and_saves_atomically(self):
        before=list_training(self.path);original={w['id']:w for w in before['workouts']};notes=read_notes(self.path)
        result=preview(self.arguments(),self.path,NOW)
        self.assertEqual(result['status'],'proposal',result)
        self.assertEqual(len(result['adjustments']),3)
        self.assertEqual(list_training(self.path),before)
        for item in result['adjustments']:
            new=item['changes']['definition'];old=original[item['workout_id']]['definition']
            self.assertEqual(new['exercises'][:-1],old['exercises'])
            calf=new['exercises'][-1]
            self.assertEqual((calf['id'],calf['sets'],calf['repetitions'],calf['rest_seconds']),('calf_raise',2,10,90))
            self.assertEqual(new['duration_minutes'],29)
        self.assertEqual([b['minutes'] for b in result['weekly_allowance_changes']],[53,58])
        saved=save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(saved['count'],3)
        after={w['id']:w for w in list_training(self.path)['workouts']}
        for row in before['workouts']:
            if row['id'] not in {t['workout_id'] for t in self.targets}:self.assertEqual(after[row['id']],row)
        self.assertEqual(read_notes(self.path),notes)
        with connect(self.path) as c:
            policy=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0])['strength_set_policy']
            self.assertEqual(policy['weekly_allowance_minutes'],50)
            current=estimates(c,self.answers,{**self.brief,'_planning_day':'2026-11-09'},NOW.date(),TZ)['strength']
            later=estimates(c,self.answers,{**self.brief,'_planning_day':'2026-11-16'},NOW.date(),TZ)['strength']
            self.assertEqual(current['effective_ceiling_minutes'],58)
            self.assertEqual(later['effective_ceiling_minutes'],50)

    def test_one_stale_workout_invalidates_the_whole_batch(self):
        result=preview(self.arguments(),self.path,NOW)
        self.assertEqual(result['status'],'proposal',result)
        with connect(self.path) as c:c.execute("UPDATE planned_workouts SET revision=revision+1 WHERE id='strength-1'")
        before=list_training(self.path)
        with self.assertRaises(ValueError):save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        self.assertEqual(list_training(self.path),before)

    def test_excluded_calf_and_explicit_weekly_cap_block_for_specific_reasons(self):
        with connect(self.path) as c:
            answers=copy.deepcopy(self.answers);answers['blocked_movements']=['calf']
            c.execute('UPDATE training_preferences SET answers_json=?',(encoded(answers),))
        result=preview(self.arguments(),self.path,NOW)
        self.assertEqual(result['status'],'not_recommended',result)
        self.assertIn('excluded movements',result['message'])
        with connect(self.path) as c:
            answers=copy.deepcopy(self.answers);answers['weekly_caps']={'strength':{'max_minutes':50,'range_min_minutes':50}}
            c.execute('UPDATE training_preferences SET answers_json=?',(encoded(answers),))
        result=preview(self.arguments(),self.path,NOW)
        self.assertEqual(result['status'],'not_recommended',result)
        self.assertIn('weekly cap',result['message'])

    def test_old_chat_request_creates_real_exercise_proposal(self):
        target=self.targets[0]
        result=session_preview({**target,'action':'adjust','request':'Add calf raises, 2 sets, respecting existing equipment and restrictions. Preserve other exercises and targets.'},self.path,NOW)
        self.assertEqual(result['status'],'proposal',result)
        self.assertEqual(result['adjustments'][0]['changes']['definition']['exercises'][-1]['id'],'calf_raise')

    def test_verified_garmin_export_contains_both_calf_sets(self):
        result=preview(self.arguments(),self.path,NOW)
        self.assertEqual(result['status'],'proposal',result)
        save({'message':result['request'],'fingerprint':result['fingerprint']},self.path,NOW)
        job=send({'workout_ids':[t['workout_id'] for t in self.targets],'timezone':TZ},self.path,self.factory,NOW)
        run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified')
        for remote in self.client.workouts.values():
            calf=[s for s in remote['workoutSegments'][0]['workoutSteps'] if s.get('category')=='CALF_RAISE']
            self.assertEqual(len(calf),2)
            self.assertTrue(all(s['exerciseName']=='CALF_RAISE' and s['endConditionValue']==10 for s in calf))
            self.assertEqual(remote['estimatedDurationInSecs'],1740)

    def test_native_chat_exposes_one_batch_review_without_saving_the_three_workouts(self):
        agent=agents.AgentTests();agent.setUp();self.addCleanup(agent.doCleanups);agent.path=self.path
        before=list_training(self.path)
        with patch('test_skill_agent.NOW',NOW):
            events=agent.run_chat('Add 2 sets of calf raises to November 5, 10 and 12; keep the other exercises unchanged',[
                agents.call('load_skill',skill_id='training.sessions.edit'),
                agents.call('preview_strength_exercise_addition',**self.arguments()),agents.answer('Review the three dated additions.',status='review')])
        result=next(e['evidence']['training_adjustment'] for e in events if isinstance(e.get('evidence'),dict) and e['evidence'].get('training_adjustment'))
        self.assertEqual(result['status'],'proposal',result)
        self.assertEqual(len(result['adjustments']),3)
        self.assertEqual(list_training(self.path),before)
