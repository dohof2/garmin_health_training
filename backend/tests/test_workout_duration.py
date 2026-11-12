import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from app.active_training import _fill, _program_workouts
from app.database import connect
from app.training import list_training, save_preferences, training_context, encoded
from app.training_adjustments import save
from app.workout_duration import preview, apply_generated
from test_training_adjustments import fixture, NOW, TZ


class WorkoutDurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'db.sqlite'; fixture(self.path)

    def proposal(self, **kwargs):
        return preview({'scope': 'plan', 'sport': 'cycling', 'minutes': 90, **kwargs}, self.path, NOW)

    def save(self, proposal):
        return save({'message': proposal['request'], 'fingerprint': proposal['fingerprint']}, self.path, NOW)

    def state(self):
        with connect(self.path) as c:
            row = dict(c.execute('SELECT * FROM active_training_program').fetchone())
        return row, json.loads(row['state_json'])

    def test_plan_setting_updates_every_scheduled_workout_and_preferences_atomically(self):
        before = list_training(self.path)
        proposal = self.proposal()
        self.assertEqual(before, list_training(self.path))
        self.assertGreaterEqual(len(proposal['adjustments']), 4)
        result = self.save(proposal)
        self.assertEqual(result['count'], len(proposal['adjustments']))
        workouts = list_training(self.path)['workouts']
        self.assertTrue(all(w['definition']['duration_minutes'] == 90 for w in workouts if w['completion_status'] == 'planned'))
        _, state = self.state()
        self.assertEqual(state['duration_settings'][-1]['minutes'], 90)
        context = training_context(self.path, NOW)
        self.assertGreaterEqual(context['raw_answers']['weekly_caps']['cycling']['range_min_minutes'], 360)
        for workout in workouts:
            definition = workout['definition']
            self.assertEqual(sum(s['duration_seconds'] * s.get('repetitions', 1) for s in definition['steps']), 5400)

    def test_one_time_only_changes_selected_workout_and_its_dated_setting(self):
        workouts = list_training(self.path)['workouts']; selected = workouts[0]
        before = training_context(self.path, NOW)['raw_answers']
        proposal = self.proposal(scope='once', workout_id=selected['id'], minutes=100)
        self.save(proposal)
        after = list_training(self.path)['workouts']
        self.assertEqual(training_context(self.path, NOW)['raw_answers'], before)
        for old, new in zip(workouts, after):
            if old['id'] == selected['id']:
                self.assertEqual(new['definition']['duration_setting']['scope'], 'once')
                self.assertEqual(new['definition']['duration_minutes'], 100)
            else:self.assertEqual(old, new)
        self.assertNotIn('duration_settings', self.state()[1])

    def test_type_scope_preserves_other_types_and_completed_history(self):
        workouts = list_training(self.path)['workouts']; completed = workouts[0]
        with connect(self.path) as c:c.execute("UPDATE planned_workouts SET completion_status='completed' WHERE id=?", (completed['id'],))
        before = list_training(self.path)
        proposal = self.proposal(workout_type='long_endurance', minutes=150)
        self.assertTrue(proposal['adjustments'])
        self.assertTrue(all(w['changes']['definition']['workout_kind'] == 'long_endurance' for w in proposal['adjustments']))
        self.save(proposal)
        after = list_training(self.path)
        for old, new in zip(before['workouts'], after['workouts']):
            if old['completion_status'] == 'completed' or old['definition']['workout_kind'] != 'long_endurance':self.assertEqual(old, new)

    def test_future_materialization_uses_duration_setting(self):
        self.save(self.proposal(minutes=95))
        row, state = self.state()
        with connect(self.path) as c:
            warnings = _fill(c, row['plan_id'], state, NOW.date() + timedelta(days=7), NOW + timedelta(days=7))
            future = [r for r in _program_workouts(c, row['plan_id']) if r['scheduled_for'][:10] >= (NOW.date() + timedelta(days=7)).isoformat()]
        self.assertTrue(future, warnings)
        self.assertTrue(all(json.loads(r['definition_json'])['duration_minutes'] == 95 for r in future))

    def test_saving_changed_schedule_time_updates_existing_and_future_slot(self):
        before = training_context(self.path, NOW)
        schedule = copy.deepcopy(before['raw_answers']['week_schedule'])
        slot = next(s for d in schedule for s in d['activities'])
        slot['max_minutes'] = 110
        selected = [w for w in list_training(self.path)['workouts'] if w['definition'].get('schedule_slot_id') == slot['slot_id']]
        self.assertTrue(selected)
        save_preferences({'week_schedule': schedule}, before['revision'], self.path, NOW)
        after = {w['id']: w for w in list_training(self.path)['workouts']}
        self.assertTrue(all(after[w['id']]['definition']['duration_minutes'] == 110 for w in selected))
        self.assertTrue(any(r.get('slot_id') == slot['slot_id'] for r in self.state()[1]['duration_settings']))

    def test_stale_preference_revision_cannot_apply_any_workout(self):
        proposal = self.proposal()
        context = training_context(self.path, NOW)
        save_preferences({'restrictions_notes': 'Keep technique comfortable'}, context['revision'], self.path, NOW)
        before = list_training(self.path)
        with self.assertRaises(ValueError):self.save(proposal)
        self.assertEqual(before, list_training(self.path))

    def test_all_activity_rule_and_specific_override(self):
        definition = list_training(self.path)['workouts'][0]['definition']
        state = {'duration_settings': [{'sport':'all','workout_type':'all','minutes':90}, {'sport':'cycling','workout_type':'endurance','minutes':80}]}
        changed = apply_generated(definition, state, training_context(self.path, NOW)['answers'])
        self.assertEqual(changed['duration_minutes'], 80 if definition['workout_kind'] == 'endurance' else 90)

    def test_setup_save_uses_the_same_schedule_propagation(self):
        from datetime import datetime
        from unittest.mock import patch
        from app.training_coach import read_brief, save_setup
        context = training_context(self.path, NOW); brief = read_brief(self.path)
        schedule = copy.deepcopy(context['raw_answers']['week_schedule'])
        slot = next(s for d in schedule for s in d['activities']); slot['max_minutes'] = 105
        with patch('app.training_coach.datetime', wraps=datetime) as clock:
            clock.now.return_value = NOW
            result = save_setup({'week_schedule':schedule},brief['brief'],context['revision'],brief['revision'],self.path)
        self.assertGreater(result['updated_workouts'], 0)
        self.assertIn('scheduled workouts', result['message'])
        _, state = self.state()
        future = next(w for w in list_training(self.path)['workouts'] if w['definition'].get('schedule_slot_id') == slot['slot_id'])
        self.assertEqual(future['definition']['duration_minutes'], 105)
        self.assertEqual(state['duration_settings'][-1]['minutes'], 105)

    def test_published_workout_is_marked_for_update(self):
        from test_garmin_publication import GarminPublicationQC
        case = GarminPublicationQC();case.setUp();self.addCleanup(case.doCleanups)
        case.send()
        proposal = preview({'scope':'once','workout_id':case.workout['id'],'minutes':100},case.path,NOW)
        save({'message':proposal['request'],'fingerprint':proposal['fingerprint']},case.path,NOW)
        workout = next(w for w in list_training(case.path)['workouts'] if w['id']==case.workout['id'])
        self.assertEqual(workout['publish_status'], 'update_needed')
        self.assertEqual(workout['definition']['duration_minutes'], 100)

    def test_strength_budget_preserves_existing_exercises_and_set_preferences(self):
        from app.training import workout_definition
        answers = {'sports':['strength'],'equipment':['bodyweight'],'blocked_sports':[],'blocked_movements':[], 'experience':{'strength':'regular'}}
        definition = workout_definition('strength_foundation',30,answers)
        definition['strength_purpose']='general_fitness'
        from app.workout_duration import resize
        note={'activity':'strength','workout_type':'all','topic':'sets','text':'Use 2 sets per exercise.','settings':{'sets':2},'revision':1}
        result=resize(definition,60,{**answers,'_training_notes':[note]})
        self.assertEqual(result['duration_minutes'],60)
        by_id={e['id']:e for e in result['exercises']}
        for exercise in definition['exercises']:self.assertEqual(exercise,by_id[exercise['id']])
        self.assertTrue(all(e['sets']==2 for e in result['exercises']))
        self.assertGreaterEqual(len(result['exercises']),len(definition['exercises']))

    def test_type_specific_setting_does_not_change_unrelated_slot_settings(self):
        before=training_context(self.path,NOW)['raw_answers']['week_schedule']
        self.save(self.proposal(workout_type='long_endurance',minutes=200))
        after=training_context(self.path,NOW)['raw_answers']['week_schedule']
        self.assertEqual(before,after)

    def test_date_scope_only_changes_that_date(self):
        workouts=list_training(self.path)['workouts'];day=workouts[0]['scheduled_for'][:10]
        self.save(self.proposal(scope='once',sport='all',date=day,minutes=100))
        for old,new in zip(workouts,list_training(self.path)['workouts']):
            if old['scheduled_for'][:10]==day:self.assertEqual(new['definition']['duration_minutes'],100)
            else:self.assertEqual(old,new)

    def test_agent_tool_returns_a_reviewable_duration_proposal(self):
        from app.skill_tools import execute
        state={}
        result,evidence=execute('preview_workout_duration',{'scope':'plan','sport':'cycling','minutes':100},
            {'path':self.path,'state':state,'today':NOW.date().isoformat(),'timezone':TZ,'now':NOW,'message':'Give cycling 100 minutes for the rest of the plan','operation_id':'duration-test'})
        self.assertEqual(result['status'],'proposal')
        self.assertEqual(evidence['training_adjustment']['request'],result['request'])
        self.assertEqual(state['last_training_proposal']['fingerprint'],result['fingerprint'])

    def mixed_sports(self):
        from app.training import workout_definition
        with connect(self.path) as c:
            raw=json.loads(c.execute('SELECT answers_json FROM training_preferences').fetchone()[0])
            raw['sports'].append('strength');raw['equipment'].append('bodyweight');raw['experience']['strength']='regular'
            slot=raw['week_schedule'][0]['activities'][0];slot['sport']='strength'
            c.execute('UPDATE training_preferences SET answers_json=? WHERE id=1',(encoded(raw),))
            row=c.execute('SELECT * FROM planned_workouts ORDER BY scheduled_for LIMIT 1').fetchone()
            old=json.loads(row['definition_json'])
            strength=workout_definition('strength_foundation',30,raw)
            strength.update({k:v for k,v in old.items() if k.startswith('schedule_') or k in ('scheduled_date','time_unspecified')})
            c.execute('UPDATE planned_workouts SET sport=?,title=?,definition_json=? WHERE id=?',('strength',strength['title'],encoded(strength),row['id']))

    def test_all_updates_both_strength_and_cycling(self):
        self.mixed_sports()
        self.save(self.proposal(sport='all',minutes=60))
        workouts=list_training(self.path)['workouts']
        self.assertEqual({w['sport'] for w in workouts},{'strength','cycling'})
        self.assertTrue(all(w['definition']['duration_minutes']==60 for w in workouts))

    def test_strength_scope_preserves_every_cycling_workout(self):
        self.mixed_sports()
        before={w['id']:w for w in list_training(self.path)['workouts'] if w['sport']=='cycling'}
        self.save(self.proposal(sport='strength',minutes=60))
        after={w['id']:w for w in list_training(self.path)['workouts'] if w['sport']=='cycling'}
        self.assertEqual(before,after)
