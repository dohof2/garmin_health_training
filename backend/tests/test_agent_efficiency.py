import json
import unittest
import test_skill_agent as fixtures
from app.skill_agent import _memory
from app.database import connect


class AgentEfficiencyTests(unittest.TestCase):
    def test_same_skill_old_tasks_stay_indexed_without_resending_full_briefs(self):
        state={'skills':['training.sessions.edit'],'focus_task':'current','memory':{'old':{'request':'older task','evidence':'x'*9000},'current':{'request':'3 total sets, 70s rest'}},'task_skills':{'old':['training.sessions.edit'],'current':['training.sessions.edit']}}
        memory=_memory(state)
        self.assertEqual(set(memory['selected_briefs']),{'current'})
        self.assertEqual(len(memory['index']),2)
        self.assertLess(len(json.dumps(memory)),1000)

    def test_continue_receives_confirmed_results_without_repeating_tools(self):
        case=fixtures.AgentTests();case.setUp();self.addCleanup(case.doCleanups)
        case.run_chat('Remember my strength rest preference',[
            fixtures.call('load_skill',skill_id='training.sessions.edit'),
            fixtures.call('save_training_note',activity='strength',workout_type='all',topic='rest',text='Use 70 seconds rest.',settings={'rest_seconds':70},expected_revision=0),
            fixtures.answer('Saved the preference.')])
        events=case.run_chat('continue',[fixtures.answer('The 70-second preference is already saved; no workout change has been saved.')])
        self.assertEqual(events[-1]['usage']['model_calls'],1)
        results=case.prompts[-1]['previous_turn_results']
        self.assertTrue(any(r['tool']=='save_training_note' and r['result']['status']=='saved' for r in results))
        with connect(case.path) as c:
            self.assertEqual(c.execute("SELECT revision FROM training_notes WHERE topic='rest'").fetchone()[0],1)

    def test_failed_turn_preserves_exact_blocker_for_continuation(self):
        case=fixtures.AgentTests();case.setUp();self.addCleanup(case.doCleanups)
        case.run_chat('Edit strength',[
            fixtures.call('load_skill',skill_id='training.sessions.edit'),
            fixtures.call('preview_strength_prescription',workouts=[{'workout_id':'missing','expected_revision':1}],sets=3,rest_seconds=70)])
        events=case.run_chat('continue',[fixtures.answer('The selected workout could not be found; no edit was saved.')])
        self.assertEqual(events[-1]['usage']['model_calls'],1)
        result=case.prompts[-1]['previous_turn_results'][-1]
        self.assertEqual(result['tool'],'preview_strength_prescription')
        self.assertIn('changed',result['result']['error'])
