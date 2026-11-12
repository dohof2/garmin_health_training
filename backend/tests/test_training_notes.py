import copy
import json
import unittest
from datetime import datetime,timezone
from unittest.mock import patch

from app.database import connect,migrate
from app.training import encoded,list_training,workout_definition
from app.training_notes import save,read,apply_definition,apply_current
from app.training_prescriptions import strength
from app.active_training import review
from app.chat_access import questions_only
from app.skill_tools import available_definitions
from test_training_adjustments import NOW,TZ
import test_skill_agent as agents


class TrainingNoteTests(unittest.TestCase):
    def setUp(self):
        self.case=agents.AgentTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.path=self.case.path

    def note(self,**extra):
        return {'activity':'strength','workout_type':'all','topic':'sets','text':'Use 2 sets per exercise, including recovery weeks.',
                'settings':{'sets':2},'expected_revision':0,**extra}

    def test_notes_replace_by_topic_persist_and_reject_stale_writes(self):
        before=list_training(self.path)
        save(self.note(),self.path)
        save(self.note(text='Use 3 sets per exercise.',settings={'sets':3},expected_revision=1),self.path)
        notes=read(self.path)['notes']
        self.assertEqual(len(notes),1)
        self.assertEqual((notes[0]['revision'],notes[0]['settings']['sets']),(2,3))
        self.assertEqual(list_training(self.path)['workouts'],before['workouts'])
        with self.assertRaises(ValueError):save(self.note(),self.path)
        self.assertEqual(read(self.path)['notes'],notes)
        save(self.note(operation='delete',expected_revision=2),self.path)
        self.assertFalse(read(self.path)['notes'])
        with connect(self.path) as c:
            state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0])
            self.assertNotIn('sets',state.get('strength_set_policy',{}))

    def test_concise_limits_and_conflicting_topics_are_atomic(self):
        with self.assertRaises(ValueError):save(self.note(text='x'*161),self.path)
        save(self.note(),self.path)
        with self.assertRaises(ValueError):save(self.note(topic='another',text='Use 3 sets.',settings={'sets':3}),self.path)
        with self.assertRaises(ValueError):save(self.note(text='Use 4 sets.',expected_revision=1),self.path)
        for index in range(9):
            save({'activity':'cycling','workout_type':'all','topic':f't{index}','text':'x'*160,'expected_revision':0},self.path)
        before=read(self.path)['notes']
        with self.assertRaises(ValueError):save({'activity':'cycling','workout_type':'all','topic':'overflow','text':'x'*160,'expected_revision':0},self.path)
        self.assertEqual(read(self.path)['notes'],before)

    def test_specific_workout_overrides_activity_default_and_unrelated_sports_stay_unchanged(self):
        save(self.note(),self.path)
        save(self.note(workout_type='general_fitness',text='Use 1 set per exercise.',settings={'sets':1}),self.path)
        base={'sport':'strength','strength_purpose':'general_fitness','duration_minutes':30,'warmup_minutes':5,
              'exercises':[{'id':'squat','sets':3,'repetitions':10,'rest_seconds':90}]}
        result=apply_definition(base,read(self.path)['notes'])
        self.assertEqual(result['exercises'][0]['sets'],1)
        cycling={'sport':'cycling','workout_kind':'endurance','duration_minutes':60}
        self.assertEqual(apply_definition(cycling,read(self.path)['notes']),cycling)
        self.assertEqual(set(read(self.path)['tree']['strength']),{'all','general_fitness'})

    def test_browser_chat_can_save_edit_and_delete_notes_without_editing_workouts(self):
        before=list_training(self.path)['workouts']
        def chat(message,arguments):
            return self.case.run_chat(message,[agents.call('load_skill',skill_id='training.preferences.notes'),
                agents.call('save_training_note',**arguments),agents.answer('Recurring strength note saved.')])
        chat('Remember 2 sets for every strength workout',self.note())
        self.assertEqual(read(self.path)['notes'][0]['settings'],{'sets':2})
        chat('Keep that note shorter',self.note(text='Use 2 sets per exercise.',expected_revision=1))
        self.assertEqual(len(read(self.path)['notes']),1)
        self.assertEqual(read(self.path)['notes'][0]['text'],'Use 2 sets per exercise.')
        chat('Remove that recurring set preference',self.note(operation='delete',expected_revision=2))
        self.assertFalse(read(self.path)['notes'])
        self.assertEqual(list_training(self.path)['workouts'],before)
        with questions_only():
            self.assertIn('get_training_notes',available_definitions())
            self.assertNotIn('save_training_note',available_definitions())

    def test_upgrade_imports_approved_set_policy(self):
        with connect(self.path) as c:
            state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0]);state['strength_set_policy']={'sets':2}
            c.execute('UPDATE active_training_program SET state_json=?',(encoded(state),))
            c.execute('DROP TABLE training_notes')
            c.execute("DELETE FROM schema_migrations WHERE version='040_training_notes.sql'")
        self.assertEqual(migrate(self.path),['040_training_notes.sql'])
        self.assertEqual(read(self.path)['notes'][0]['settings'],{'sets':2})
        self.assertEqual(migrate(self.path),[])

    def test_notes_api_validates_short_text_and_supports_revisioned_edits(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.main import save_training_note,read_training_notes
        app=FastAPI();app.post('/notes')(save_training_note);app.get('/notes')(read_training_notes)
        actual_save=save;actual_read=read
        with patch('app.training_notes.save',side_effect=lambda args:actual_save(args,self.path)), \
             patch('app.training_notes.read',side_effect=lambda **kwargs:actual_read(self.path,**kwargs)):
            client=TestClient(app)
            result=client.post('/notes',json=self.note())
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(client.get('/notes').json()['notes'][0]['settings'],{'sets':2})
            self.assertEqual(client.post('/notes',json=self.note()).status_code,409)
            self.assertEqual(client.post('/notes',json=self.note(text='x'*161,expected_revision=1)).status_code,422)
            self.assertEqual(client.post('/notes',json=self.note(operation='delete',expected_revision=1)).status_code,200)
            self.assertFalse(client.get('/notes').json()['notes'])

    def test_recovery_workout_keeps_all_five_movements_two_sets_and_recalculated_time(self):
        from test_long_ride_allocation import preferences
        now=datetime(2026,11,4,9,tzinfo=timezone.utc)
        answers=preferences();answers['equipment']=['bike','bodyweight','pull_up_bar','dip_bars']
        answers['weekly_caps']={'strength':{'range_min_minutes':50,'max_minutes':50},'cycling':{'range_min_minutes':300,'max_minutes':330}}
        with connect(self.path) as c:
            state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0])
            state['brief'].update(strength_role='secondary',strength_purpose='cycling_support',strength_capacity={'pull_up_reps':3,'dip_reps':5})
            policy={'sets':2,'duration_reference_minutes':12.32,'reference_total_sets':5,'weekly_allowance_minutes':50,
                'reference_repetitions':{'air_squat':10,'hip_raise':10,'dead_bug':10,'pullup_progression':1,'dip_progression':3}}
            state['strength_set_policy']=policy
            c.execute('UPDATE active_training_program SET state_json=?',(encoded(state),))
            c.execute('UPDATE training_preferences SET answers_json=?',(encoded(answers),))
            old=strength(workout_definition('strength_foundation',20,answers),state['brief'],answers,observed_at=now)
            self.assertEqual(len(old['exercises']),4)
            old.update(scheduled_date='2026-11-10',time_unspecified=True,schedule_timezone=TZ,schedule_slot_id='1',training_block={'phase':'Recovery / review'})
            root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
            c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES('target',?,'strength',?,'2026-11-10T12:00:00+02:00',?)",(root,old['title'],encoded(old)))
        save(self.note(),self.path)
        with connect(self.path) as c:changes,warnings=apply_current(c,root,now,TZ)
        self.assertTrue(changes,warnings)
        current=next(w for w in list_training(self.path)['workouts'] if w['id']=='target')['definition']
        self.assertEqual(len(current['exercises']),5)
        self.assertEqual([e['sets'] for e in current['exercises']],[2]*5)
        self.assertEqual(current['duration_minutes'],25)
        from test_garmin_publication import FakeGarmin
        from app.garmin_training_publish import send,run,view
        client=FakeGarmin();factory=lambda path:client
        job=send({'workout_ids':['target'],'timezone':TZ},self.path,factory,now)
        run(job['id'],self.path,factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified')
        remote=next(iter(client.workouts.values()))
        work=[s for s in remote['workoutSegments'][0]['workoutSteps'] if s['endCondition']['conditionTypeKey']=='reps']
        self.assertEqual(len(work),10)
        self.assertEqual(remote['estimatedDurationInSecs'],1500)
        self.assertEqual(current['strength_timing']['rest_seconds'],900)
        self.assertEqual(current['strength_timing']['warmup_seconds'],300)
        with patch('app.readiness.readiness_history',return_value={'latest':{'date':'2026-11-04','score':70,'groups':[],'status':'complete'}}):
            review(self.path,TZ,now,trigger='daily')
        current=next(w for w in list_training(self.path)['workouts'] if w['id']=='target')['definition']
        self.assertEqual([e['sets'] for e in current['exercises']],[2]*5)
        self.assertEqual(current['duration_minutes'],25)
