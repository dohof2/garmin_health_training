"""Contract tests for one reasoning agent, focused skills, and durable operations."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_training_adjustments import fixture, NOW, TZ
from app.ai_chat import chat_stream
from app.ai_providers import get_ai_settings
from app.database import connect, migrate
from app.skill_catalog import catalog, find, children, load_skill
from app.skill_tools import available_definitions, execute, lookup_workouts
from app.agent_runtime import CURRENT, Runtime, BudgetExceeded, BudgetedProvider
from app.training import list_training, encoded
from app.training_adjustments import save


def call(name, **arguments):
    return {'calls': [{'name': name, 'arguments': arguments}]}


def answer(reply='Done.', status='completed'):
    return {'reply': reply, 'status': status}


class NativeProviderFixture:
    """Script model decisions through the same native-call boundary as live providers."""
    def __init__(self, generate):
        self.generate = generate
        self.serial = 0

    def respond(self, messages, instructions, tools, **kwargs):
        payload = json.loads(messages[0]['content'])
        calls = {m['call_id']: m for m in messages if m.get('type')=='function_call'}
        payload['results'] = [{'tool':calls[m['call_id']]['name'],
            'arguments':json.loads(calls[m['call_id']]['arguments']), 'result':json.loads(m['output'])}
            for m in messages if m.get('type')=='function_call_output']
        decision = json.loads(self.generate(json.dumps(payload), instructions+'\nNative tools: '+json.dumps(tools), **kwargs))
        self.serial += 1
        native_calls = [{**c,'id':f'fixture-{self.serial}-{i}'} for i,c in enumerate(decision.get('calls',[]))]
        items = [{'type':'function_call','call_id':c['id'],'name':c['name'],'arguments':json.dumps(c.get('arguments',{}))} for c in native_calls]
        return {**decision,'calls':native_calls,'messages':items,'transport':'responses'}


class CatalogTests(unittest.TestCase):
    def test_complete_catalog_has_unique_versioned_instructions_and_working_tools(self):
        self.assertEqual(len(catalog()['skills']), 33)
        available = available_definitions()
        for skill in catalog()['skills']:
            loaded = load_skill(skill['id'])
            self.assertTrue(loaded['instructions'].strip())
            self.assertFalse(set(skill['tools']) - available.keys(), skill['id'])
            self.assertGreater(skill['version'], 0)

    def test_search_returns_cards_without_loading_instructions(self):
        result = find('replace strength endurance session')
        self.assertIn('training.sessions.edit', [s['id'] for s in result['skills']])
        self.assertTrue(all('instructions' not in s and 'tools' not in s for s in result['skills']))
        self.assertLessEqual(len(result['skills']), 3)

    def test_hierarchy_and_direct_lookup(self):
        self.assertEqual(len(children()['branches']), 8)
        self.assertEqual({b['path'] for b in children('Training')['branches']}, {'Training / Sessions','Training / Programs','Training / Preferences'})
        self.assertEqual(children('Training')['skills'], [])
        self.assertTrue(all(s['id'].startswith('training.programs.') for s in children('Training / Programs')['skills']))
        self.assertEqual(load_skill('training.programs.build')['id'], 'training.programs.build')
        with self.assertRaises(ValueError):
            load_skill('../../ai_providers')

    def test_general_conversation_does_not_need_domain_tools(self):
        from app.skill_agent import _instructions
        context = {'state': {}, 'today': '2026-10-19', 'timezone': TZ, 'runtime': Runtime()}
        instructions, tools = _instructions(context)
        self.assertNotIn('preview_session_change', tools)
        self.assertNotIn('nutrition_conversation', tools)
        self.assertNotIn('preview_training_plan', tools)
        self.assertNotIn('LONG_TERM', instructions)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        fixture(self.path)
        self.operation = 0
        self.prompts = []
        self.instructions = []
        self.rows = sorted(list_training(self.path)['workouts'], key=lambda w: w['scheduled_for'])[:2]

    def run_chat(self, message, responses, **options):
        self.operation += 1
        responses = iter(responses)
        def generate(prompt, instructions, **kwargs):
            self.assertIsNotNone(CURRENT.get())
            self.prompts.append(json.loads(prompt))
            self.instructions.append(instructions)
            return json.dumps(next(responses))
        with patch('app.ai_providers._active_provider', return_value=NativeProviderFixture(generate)):
            return [json.loads(line) for line in chat_stream(message, [], TZ, self.path,
                conversation_id=options.pop('conversation_id', 'shared'),
                operation_id=options.pop('operation_id', str(self.operation)), message_time=NOW, **options)]

    def replacement_fixture(self):
        import test_workout_swap
        test_workout_swap.SwapTests.cross_sport_fixture(self)
        with connect(self.path) as c:
            for row, day in zip(self.rows, ('2026-10-18', '2026-10-19')):
                definition = json.loads(c.execute('SELECT definition_json FROM planned_workouts WHERE id=?', (row['id'],)).fetchone()[0])
                definition['scheduled_date'] = day
                c.execute('UPDATE planned_workouts SET scheduled_for=?,definition_json=? WHERE id=?', (day+'T12:00:00+03:00', encoded(definition), row['id']))

    def test_one_model_handles_education_without_skill_search(self):
        events = self.run_chat('Explain aerobic endurance; discussion only', [answer('Aerobic endurance supports sustained exercise.')])
        self.assertEqual(events[-1]['usage']['model_calls'], 1)
        self.assertEqual(events[-1]['skills'], [])
        self.assertNotIn('chat_role', events[0])
        self.assertNotIn('nutrition_conversation', self.instructions[-1])
        self.assertNotIn('preview_training_plan', self.instructions[-1])

    def test_skill_loading_exposes_only_its_tools_and_replaces_prior_body(self):
        events = self.run_chat('Explain my session', [call('load_skill', skill_id='training.sessions.inspect'),
            call('lookup_workouts', date='2026-10-19'), answer('Your selected session is ready.')])
        self.assertNotIn('nutrition_conversation', self.instructions[-1])
        self.assertNotIn('preview_training_plan', self.instructions[-1])
        self.assertIn('lookup_workouts', self.instructions[-1])
        self.run_chat('What is my daily food balance?', [call('load_skill', skill_id='nutrition.balance'),
            call('nutrition_day', date='2026-10-19'), answer('There are no logged meals for that day.')])
        self.assertNotIn('lookup_workouts', self.instructions[-1])
        self.assertNotIn('# Training / Sessions', self.instructions[-1])
        self.assertIn('nutrition_day', self.instructions[-1])
        self.assertEqual(events[-1]['skills'], ['training.sessions.inspect'])

    def test_short_followups_keep_session_and_original_intent_without_client_history(self):
        self.replacement_fixture()
        before = list_training(self.path)
        first = self.run_chat('I did yesterdat the strength re,ove it and add an edurance ride (what was supposed to be yestrday)', [
            call('load_skill', skill_id='training.sessions.edit'),
            call('update_task', key='session_edit', value={'request': 'Replace planned strength with yesterday\'s endurance', 'source_date': '2026-10-18'}),
            answer('Should I replace today’s planned strength session?', 'awaiting_information')])
        second = self.run_chat('todays', [call('lookup_workouts', date='2026-10-19', sport='strength', details=True),
            call('lookup_workouts', date='2026-10-18', sport='cycling', details=True),
            call('update_task', key='session_edit', value={'request': 'Replace strength with past endurance',
                 'workout_id': self.rows[1]['id'], 'source_workout_id': self.rows[0]['id'], 'target_date': '2026-10-19'}),
            answer('I have today’s strength and yesterday’s ride.', 'awaiting_information')])
        third = self.run_chat('the strength', [answer('Today’s strength is selected.', 'awaiting_information')])
        final = self.run_chat('I want to remove it (i did it yestrday) and instead add a bike ride', [
            call('preview_session_change', workout_id=self.rows[1]['id'], expected_revision=1,
                action='replace_with_endurance', source_workout_id=self.rows[0]['id']),
            answer('Review replacing today’s strength with the endurance ride.', 'review')])
        self.assertEqual(final[-1]['task_status'], 'review', final)
        proposal = next(e['evidence']['training_adjustment'] for e in final if e['type']=='tool')
        self.assertEqual(proposal['status'], 'proposal', proposal)
        self.assertEqual(proposal['adjustments'][0]['workout_id'], self.rows[1]['id'])
        self.assertEqual(proposal['adjustments'][0]['changes']['definition']['sport'], 'cycling')
        self.assertEqual(before, list_training(self.path))
        self.assertEqual(final[-1]['skills'], ['training.sessions.edit'])
        self.assertTrue(self.prompts[-1]['task_memory']['selected_briefs']['session_edit']['source_workout_id'])
        self.assertNotIn('find_skills', [r.get('tool') for r in self.prompts[-1]['results']])
        self.assertNotIn('chat_role', first[0])

    def test_structured_replacement_save_preserves_history_and_rejects_repeat(self):
        self.replacement_fixture()
        events = self.run_chat('Replace today’s strength with a 30 minute bike ride', [call('load_skill', skill_id='training.sessions.edit'),
            call('preview_session_change', workout_id=self.rows[1]['id'], expected_revision=1, action='replace_with_endurance', minutes=30), answer(status='review')])
        proposal = next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
        self.assertEqual(proposal['status'], 'proposal', proposal)
        save({'message':proposal['request'], 'fingerprint':proposal['fingerprint']}, self.path, NOW)
        rows = {w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(rows[self.rows[1]['id']]['sport'], 'cycling')
        self.assertEqual(rows[self.rows[1]['id']]['definition']['duration_minutes'], 30)
        self.assertEqual(rows[self.rows[0]['id']]['scheduled_for'][:10], '2026-10-18')
        with self.assertRaises(ValueError):
            save({'message':proposal['request'], 'fingerprint':proposal['fingerprint']}, self.path, NOW)

    def test_structured_selection_chooses_exact_workout_among_same_sport(self):
        events = self.run_chat('Make the Wednesday ride 20 minutes', [call('load_skill', skill_id='training.sessions.edit'),
            call('preview_session_change', workout_id=self.rows[1]['id'], expected_revision=1, action='adjust', request='Make this ride 20 minutes'),
            answer(status='review')])
        proposal = next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
        self.assertEqual(proposal['status'], 'proposal', proposal)
        self.assertEqual([r['workout_id'] for r in proposal['adjustments']], [self.rows[1]['id']])

    def test_published_strength_replacement_updates_existing_garmin_workout(self):
        from test_garmin_publication import FakeGarmin
        from app.garmin_training_publish import preview, approve, run, view
        from app.session_changes import preview as preview_change
        self.replacement_fixture()
        identifier = self.rows[1]['id']
        client = FakeGarmin()
        factory = lambda path: client
        def send():
            proposal = preview({'workout_ids':[identifier], 'timezone':TZ}, self.path, factory, NOW)
            approve(proposal['id'], self.path, factory, NOW)
            run(proposal['id'], self.path, factory)
            result = view(proposal['id'], self.path)
            self.assertEqual(result['status'], 'verified', result)
            return result
        send()
        before = list_training(self.path)
        row = next(w for w in before['workouts'] if w['id']==identifier)
        calendar = dict(client.calendar)
        remote_id = row['garmin_workout_id']
        proposal = preview_change({'workout_id':identifier, 'expected_revision':row['revision'],
            'action':'replace_with_endurance', 'minutes':30}, self.path, NOW)
        self.assertEqual(proposal['status'], 'proposal', proposal)
        self.assertIn('Send to Garmin', proposal['message'])
        self.assertEqual(before, list_training(self.path))
        self.assertEqual(client.updates, 0)
        save({'message':proposal['request'], 'fingerprint':proposal['fingerprint']}, self.path, NOW)
        rows = {w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(rows[identifier]['sport'], 'cycling')
        self.assertEqual(rows[identifier]['publish_status'], 'update_needed')
        self.assertEqual(rows[identifier]['garmin_workout_id'], remote_id)
        self.assertEqual(client.updates, 0)
        self.assertEqual(rows[self.rows[0]['id']], next(w for w in before['workouts'] if w['id']==self.rows[0]['id']))
        result = send()
        self.assertEqual(result['items'][0]['action'], 'update')
        self.assertEqual((client.creates, client.schedules, client.updates), (1,1,1))
        self.assertEqual(client.calendar, calendar)
        self.assertEqual(client.workouts[remote_id]['sportType']['sportTypeKey'], 'cycling')
        self.assertEqual(next(w for w in list_training(self.path)['workouts'] if w['id']==identifier)['publish_status'], 'published')

    def test_unresolved_garmin_strength_replacement_requires_reconciliation(self):
        from app.session_changes import preview
        self.replacement_fixture()
        identifier = self.rows[1]['id']
        for status in ('published', 'publishing', 'update_needed'):
            with self.subTest(status=status):
                with connect(self.path) as c:
                    c.execute('UPDATE planned_workouts SET publish_status=?,garmin_workout_id=? WHERE id=?', (status,'unverified',identifier))
                before = list_training(self.path)
                result = preview({'workout_id':identifier,'expected_revision':1,
                    'action':'replace_with_endurance','minutes':30}, self.path, NOW)
                self.assertEqual(result['status'], 'not_recommended')
                self.assertIn('reconciliation', result['message'])
                self.assertEqual(before, list_training(self.path))

    def test_skill_cannot_call_an_unloaded_tool(self):
        before = list_training(self.path)
        self.run_chat('Discuss a possible workout change', [call('preview_session_change', workout_id=self.rows[0]['id'], expected_revision=1, action='skip'), answer('We can discuss that.')])
        self.assertIn('Load the appropriate skill', self.prompts[-1]['results'][0]['result']['error'])
        self.assertEqual(before, list_training(self.path))

    def test_receipt_replay_has_no_provider_or_tool_call(self):
        first = self.run_chat('Explain endurance', [answer('Sustained aerobic exercise.')], operation_id='replay')
        second = self.run_chat('Explain endurance', [], operation_id='replay')
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, 'different request'):
            self.run_chat('Different question', [], operation_id='replay')

    def test_duplicate_tool_is_executed_once(self):
        from app.skill_tools import lookup_program
        with patch('app.skill_tools.lookup_program', wraps=lookup_program) as lookup:
            self.run_chat('Explain my program', [call('load_skill', skill_id='training.sessions.inspect'), call('lookup_program'), call('lookup_program'), answer('Here is the program.')])
        self.assertEqual(lookup.call_count, 1)

    def test_longterm_brief_survives_subject_change_and_process_boundary(self):
        brief = {'title': 'Race plan', 'stage':'baseline', 'weeks':12, 'goal':'FTP', 'available_days':['Tuesday','Saturday'], 'question':'Which event date?'}
        self.run_chat('Build a new long-term plan', [call('load_skill', skill_id='training.programs.build'), call('update_task', key='plan', value=brief), answer('Which event date?', 'awaiting_information')])
        self.run_chat('How much have I eaten today?', [call('load_skill', skill_id='nutrition.balance'), answer('We can inspect today’s food log.')])
        self.assertNotIn('plan', self.prompts[-1]['task_memory']['selected_briefs'])
        self.run_chat('Back to my plan, the race is February 1', [call('load_skill', skill_id='training.programs.build'), call('read_task', key='plan'), answer('I retained your 12-week FTP plan brief.', 'awaiting_information')])
        self.assertEqual(self.prompts[-1]['task_memory']['selected_briefs']['plan'], brief)
        self.assertIn('goals', self.instructions[-1].lower())
        self.assertNotIn('nutrition_conversation', self.instructions[-1])

    def test_longterm_preview_uses_existing_program_validator_and_review_evidence(self):
        from app.training_coach import read_brief
        brief = read_brief(self.path)['brief']
        events = self.run_chat('Build a new plan with the saved brief', [call('load_skill', skill_id='training.programs.build'),
            call('preview_training_plan', message='', week_start='2026-10-19', brief=brief), answer('Review the program draft.', 'review')])
        self.assertTrue(any(e['type']=='tool' and e['evidence'].get('coaching') for e in events), events)
        self.assertIn('planning_preview', self.prompts[-1]['retained_references'])

    def test_readonly_channel_has_no_domain_write_or_preview_tools(self):
        from app.chat_access import questions_only
        before = list_training(self.path)
        with questions_only():
            events = self.run_chat('Change the workout', [call('load_skill', skill_id='training.sessions.edit'),
                call('preview_session_change', workout_id=self.rows[0]['id'], expected_revision=1, action='skip'),
                answer('Open the browser app to review that change.')])
        self.assertEqual(before, list_training(self.path))
        self.assertIn('Load the appropriate skill', self.prompts[-1]['results'][-1]['result']['error'])
        self.assertEqual(events[-1]['task_status'], 'completed')

    def test_errors_hide_provider_payload_and_keep_task_memory(self):
        self.run_chat('Build a plan', [call('load_skill', skill_id='training.programs.build'), call('update_task', key='plan', value={'weeks':12}), answer('Which goal?', 'awaiting_information')])
        with patch('app.ai_providers._active_provider', side_effect=RuntimeError('secret-provider-payload')):
            events = [json.loads(line) for line in chat_stream('FTP', [], TZ, self.path, conversation_id='shared', operation_id='failure', message_time=NOW)]
        self.assertNotIn('secret-provider-payload', str(events))
        with connect(self.path) as c:
            state = json.loads(c.execute('SELECT state_json FROM assistant_skill_sessions WHERE conversation_id=?', ('shared',)).fetchone()[0])
        self.assertEqual(state['memory']['plan']['weeks'], 12)
        self.assertEqual(events[-1]['task_status'], 'blocked')

    def test_turns_reset_usage_without_resetting_conversation(self):
        first = self.run_chat('Explain endurance', [answer('A sustained effort.')])
        second = self.run_chat('And tempo?', [answer('A stronger sustained effort.')])
        self.assertEqual(first[-1]['usage']['model_calls'], 1)
        self.assertEqual(second[-1]['usage']['model_calls'], 1)
        self.assertEqual(self.prompts[-1]['recent_exchange'][0]['content'], 'Explain endurance')

    def test_schema_migration_keeps_provider_model_and_removes_workflow_switch(self):
        settings = get_ai_settings(self.path)
        self.assertNotIn('assistant_workflow', settings)
        self.assertEqual(migrate(self.path), [])
        self.assertNotIn('chat_role', self.run_chat('Hello', [answer('Hello.')])[0])

    def test_http_stream_keeps_runtime_and_receipt_across_worker_chunks(self):
        from fastapi.testclient import TestClient
        from app.main import app
        calls = []
        def generate(prompt, instructions, **kwargs):
            self.assertIsNotNone(CURRENT.get())
            calls.append(prompt)
            return json.dumps(answer('Hello.'))
        def dispatch(message, history, tz, **kwargs):
            return chat_stream(message, history, tz, self.path, **kwargs)
        with patch.dict('os.environ', {'HT_APP_DATA_DIR': self.tmp.name}), patch('app.main.chat_stream', side_effect=dispatch), patch('app.ai_providers._active_provider', return_value=NativeProviderFixture(generate)), TestClient(app) as client:
            body = {'message':'Hello', 'timezone':TZ, 'conversation_id':'http', 'operation_id':'http-one'}
            first = client.post('/api/ai/chat', json=body)
            second = client.post('/api/ai/chat', json=body)
            index = client.get('/api/ai/skills')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.text, second.text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(index.json()['branches']), 8)

    def test_closing_stream_retains_interruption_receipt_and_releases_conversation(self):
        gen = chat_stream('Hello', [], TZ, self.path, conversation_id='closed', operation_id='closed-op', message_time=NOW)
        next(gen)
        gen.close()
        with connect(self.path) as c:
            row = c.execute('SELECT active_operation,state_json FROM assistant_skill_sessions WHERE conversation_id=?', ('closed',)).fetchone()
            receipt = c.execute('SELECT events_json FROM assistant_skill_turns WHERE operation_id=?', ('closed-op',)).fetchone()
        self.assertIsNone(row['active_operation'])
        self.assertEqual(json.loads(row['state_json'])['status'], 'interrupted')
        self.assertEqual(json.loads(receipt[0])[-1]['type'], 'complete')

    def test_operation_budget_preserves_reasoning_configuration(self):
        runtime = Runtime()
        runtime.call_limit = 0
        with self.assertRaises(BudgetExceeded):
            BudgetedProvider(SimpleNamespace(generate=lambda *a,**k:self.fail('No call')), runtime).generate('hello','rules')
        runtime = Runtime()
        runtime.observed({'input_tokens':50,'output_tokens':100,'output_tokens_details':{'reasoning_tokens':80}})
        self.assertEqual(runtime.summary()['output_tokens'], 100)
        self.assertEqual(runtime.summary()['reasoning_tokens'], 80)

    def test_food_logging_uses_one_agent_without_another_model_call(self):
        events = self.run_chat('I ate 100 grams of eggs', [call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', date='2026-10-19', ingredients=[{'name':'Eggs', 'grams':100, 'meal_type':'breakfast'}]),
            answer('Breakfast was logged.')])
        from app.nutrition import daily_status
        result = daily_status(NOW.date(), TZ, self.path)
        self.assertEqual(len(result['meals']), 1)
        self.assertEqual(result['meals'][0]['items'][0]['quantity'], 100)
        self.assertEqual(events[-1]['usage']['model_calls'], 3)
        self.assertTrue(next(e['evidence']['nutrition'] for e in events if e['type']=='tool')['logged'])
        self.assertNotIn('preview_training_plan', self.instructions[-1])

    def test_food_correction_preserves_other_items_and_locally_scales_nutrients(self):
        self.run_chat('I ate eggs and avocado', [call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', ingredients=[{'name':'Eggs','grams':100}, {'name':'Avocado','grams':80}]), answer('Logged.')])
        from app.nutrition import daily_status
        before = daily_status(NOW.date(), TZ, self.path)['meals'][0]
        egg, avocado = before['items']
        self.run_chat('The eggs were 150 grams', [call('load_skill', skill_id='nutrition.correct'),
            call('nutrition_conversation', intent='correct', meal_id=before['id'], expected_revision=before['revision'], item_id=egg['id'], quantity=150), answer('Corrected.')])
        meals = daily_status(NOW.date(), TZ, self.path)['meals']
        self.assertEqual(len(meals), 1)
        self.assertEqual(meals[0]['id'], before['id'])
        self.assertEqual(meals[0]['items'][1]['quantity'], avocado['quantity'])
        self.assertAlmostEqual(meals[0]['items'][0]['calories_kcal'], egg['calories_kcal']*1.5)

    def test_nutrition_target_is_reviewed_without_saving(self):
        before = list_training(self.path)
        events = self.run_chat('Help me set a maintenance target', [call('load_skill', skill_id='nutrition.targets'),
            call('nutrition_conversation', intent='targets', date='2026-10-19', target_request={'goal':'maintain','weight_kg':75,'height_cm':180,'age':40,'equation_sex':'male','activity_factor':1.375}),
            answer('Review this calculated target.', 'review')])
        proposal = next(e['evidence']['nutrition'] for e in events if e['type']=='tool')
        self.assertFalse(proposal['target_saved'])
        self.assertEqual(proposal['target_proposal']['status'], 'proposal')
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM nutrition_targets').fetchone()[0], 0)
        self.assertEqual(before, list_training(self.path))

    def test_food_report_supports_multiple_meals_without_duplicate_receipt(self):
        operation = 'food-two-meals'
        events = self.run_chat('Eggs at breakfast and avocado at lunch', [call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', date='2026-10-19', ingredients=[{'name':'Eggs','grams':100,'meal_type':'breakfast'},{'name':'Avocado','grams':80,'meal_type':'lunch'}]), answer('Both meals logged.')], operation_id=operation)
        replay = self.run_chat('Eggs at breakfast and avocado at lunch', [], operation_id=operation)
        from app.nutrition import daily_status
        self.assertEqual(len(daily_status(NOW.date(), TZ, self.path)['meals']), 2)
        self.assertEqual(events, replay)

    def test_telegram_food_uses_shared_agent_and_authorizer(self):
        from app.telegram_chat import conversation_reply
        messages = iter([call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', date='2026-10-19', ingredients=[{'name':'Eggs','grams':100}]), answer('Logged.')])
        def generate(*args, **kwargs):
            return json.dumps(next(messages))
        authorized = []
        with patch('app.ai_providers._active_provider', return_value=NativeProviderFixture(generate)):
            result = conversation_reply('I ate 100 grams of eggs', [], TZ, self.path, operation_id='telegram:1:1', sent_at=NOW.timestamp(), authorizer=lambda c:authorized.append(True))
        self.assertEqual(result['reply'], 'Logged.')
        self.assertTrue(authorized)
        self.assertNotIn('role', result['context'])

    def test_telegram_authorizer_can_block_food_write_at_commit(self):
        from app.telegram_chat import conversation_reply
        def denied(connection):
            raise ValueError('Channel disabled before commit')
        messages = iter([call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', ingredients=[{'name':'Eggs','grams':100}]), answer('The channel was disabled; nothing was saved.')])
        with patch('app.ai_providers._active_provider', return_value=NativeProviderFixture(lambda *a,**k:json.dumps(next(messages)))):
            conversation_reply('I ate eggs', [], TZ, self.path, operation_id='telegram:1:2', sent_at=NOW.timestamp(), authorizer=denied)
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM meals').fetchone()[0], 0)

    def test_swap_preview_and_save_use_exact_ids(self):
        before = list_training(self.path)
        first, second = self.rows
        events = self.run_chat('Swap these two sessions', [call('load_skill', skill_id='training.sessions.schedule'),
            call('preview_schedule_change', workout_id=first['id'], expected_revision=1, other_workout_id=second['id'], other_expected_revision=1), answer(status='review')])
        proposal = next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
        self.assertEqual(before, list_training(self.path))
        self.assertEqual(proposal['status'], 'proposal', proposal)
        save({'message':proposal['request'], 'fingerprint':proposal['fingerprint']}, self.path, NOW)
        rows = {w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(rows[first['id']]['scheduled_for'], second['scheduled_for'])
        self.assertEqual(rows[second['id']]['scheduled_for'], first['scheduled_for'])

    def test_move_preview_rolls_back_actual_scheduler_validation(self):
        first = self.rows[0]
        before = list_training(self.path)
        # Sunday has a cycling slot, but the requested date must be unoccupied.
        events = self.run_chat('Move this workout to next Monday', [call('load_skill', skill_id='training.sessions.schedule'),
            call('preview_schedule_change', workout_id=first['id'], expected_revision=1, date='2026-10-26'), answer(status='review')])
        self.assertEqual(before, list_training(self.path))
        self.assertTrue(any(e['type']=='tool' for e in events), self.prompts[-1]['results'])

    def test_current_pain_disclosure_cannot_disappear_from_structured_replacement(self):
        self.replacement_fixture()
        events = self.run_chat('Replace strength with a ride, but I have knee pain', [call('load_skill', skill_id='training.sessions.edit'),
            call('preview_session_change', workout_id=self.rows[1]['id'], expected_revision=1, action='replace_with_endurance', minutes=30), answer('Review the pain first.')])
        proposal = next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
        self.assertEqual(proposal['status'], 'not_recommended')

    def test_app_status_is_a_read_without_seeding_sync_checkpoints(self):
        from app.chat_access import questions_only
        with connect(self.path) as c:
            before = c.execute('SELECT COUNT(*) FROM sync_checkpoints').fetchone()[0]
        with questions_only():
            events = self.run_chat('Is sync current?', [call('load_skill', skill_id='garmin.status'), call('app_status'), answer('Here is the recorded status.')])
        self.assertTrue(any(e['type']=='tool' for e in events), self.prompts[-1]['results'])
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sync_checkpoints').fetchone()[0], before)

    def test_parallel_turn_is_not_started_while_conversation_is_active(self):
        first = chat_stream('A first question', [], TZ, self.path, conversation_id='busy', operation_id='busy-one', message_time=NOW)
        next(first)
        try:
            second = self.run_chat('A second question', [], conversation_id='busy')
            self.assertIn('still in progress', second[0]['text'])
        finally:
            first.close()

    def test_sol_provider_retains_low_reasoning_and_selected_model(self):
        from app.ai_providers import ChatGPTProvider
        stream = [SimpleNamespace(type='response.output_text.delta', delta='{"reply":"Hello"}'),
                  SimpleNamespace(type='response.completed', response=SimpleNamespace(usage=None))]
        with patch('app.chatgpt_auth.access_token', return_value='fake'), patch('app.ai_providers.OpenAI') as client:
            client.return_value.responses.create.return_value = iter(stream)
            ChatGPTProvider('gpt-6.1-sol', self.path).generate('Hello', 'Rules')
        kwargs = client.return_value.responses.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'gpt-6.1-sol')
        self.assertEqual(kwargs['reasoning'], {'effort':'low'})
        self.assertFalse(kwargs['store'])

    def test_food_identity_correction_preserves_item_and_other_food_ids(self):
        self.run_chat('I ate eggs and avocado', [call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', ingredients=[{'name':'Eggs','grams':100},{'name':'Avocado','grams':80}]), answer('Logged.')])
        from app.nutrition import daily_status
        before = daily_status(NOW.date(), TZ, self.path)['meals'][0]
        first = before['items'][0]
        self.run_chat('That first food was cooked oats', [call('load_skill', skill_id='nutrition.correct'),
            call('nutrition_conversation', intent='correct', meal_id=before['id'], expected_revision=before['revision'], item_id=first['id'],
                replacement={'name':'Cooked oats','grams':100,'nutrients_per_100g':{'calories_kcal':70,'protein_grams':2,'fat_grams':1,'carbohydrate_grams':12},'assumptions':'Generic cooked oats estimate'}), answer('Corrected.')])
        after = daily_status(NOW.date(), TZ, self.path)['meals'][0]
        self.assertEqual([i['id'] for i in before['items']], [i['id'] for i in after['items']])
        self.assertEqual(after['items'][0]['name'], 'Cooked oats')
        self.assertEqual(after['items'][0]['calories_kcal'], 70)
        self.assertEqual(after['items'][1], before['items'][1])

    def test_meal_move_preserves_items_and_updates_both_dates(self):
        self.run_chat('I ate eggs', [call('load_skill', skill_id='nutrition.log'),
            call('nutrition_conversation', intent='log', date='2026-10-19', ingredients=[{'name':'Eggs','grams':100}]), answer('Logged.')])
        from app.nutrition import daily_status
        before = daily_status(NOW.date(), TZ, self.path)['meals'][0]
        self.run_chat('Move the meal to yesterday', [call('load_skill', skill_id='nutrition.correct'),
            call('nutrition_conversation', intent='correct', meal_id=before['id'], expected_revision=before['revision'], date='2026-10-18'), answer('Moved.')])
        self.assertEqual(daily_status(NOW.date(), TZ, self.path)['meals'], [])
        from datetime import date
        after = daily_status(date(2026,10,18), TZ, self.path)['meals'][0]
        self.assertEqual(after['id'], before['id'])
        self.assertEqual(after['items'], before['items'])

    def test_profile_question_does_not_load_program_history(self):
        self.run_chat('What profile details do you have?', [call('load_skill', skill_id='profile.personal'), call('get_training_context'), answer('Here are your saved profile fields.')])
        result = self.prompts[-1]['results'][-1]['result']
        self.assertIn('profile', result)
        self.assertNotIn('training', result)
        self.assertNotIn('active_plan', result)

    def test_maintenance_logging_uses_validated_service_and_same_turn_receipt(self):
        events = self.run_chat('Log replacing the chain on my road bike yesterday', [call('load_skill', skill_id='maintenance.log'),
            call('log_maintenance', events=[{'equipment_label':'Road bike','action':'Replaced chain','event_date':'2026-10-18'}], operation_id='model-cannot-choose-receipt'), answer('Logged the chain replacement.')])
        evidence = next(e['evidence']['maintenance'] for e in events if e['type']=='tool')
        self.assertTrue(evidence['saved'])
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM maintenance_events').fetchone()[0], 1)

    def test_existing_workflow_links_are_visible_evidence_without_claiming_execution(self):
        events = self.run_chat('Help me sync', [call('load_skill', skill_id='garmin.sync'), call('open_app_workflow', workflow='sync'), answer('Open Data & sync to start synchronization.')])
        evidence = next(e['evidence'] for e in events if e['type']=='tool')
        self.assertEqual(evidence['action_link']['url'], '#data')
        self.assertEqual(self.prompts[-1]['results'][-1]['result']['status'], 'review_required')

    def test_one_session_format_change_does_not_change_other_sessions_or_preference(self):
        before = {w['id']:w for w in list_training(self.path)['workouts']}
        events = self.run_chat('Remove the warmup and cooldown from this endurance ride only', [call('load_skill', skill_id='training.sessions.edit'),
            call('preview_session_change', workout_id=self.rows[0]['id'], expected_revision=1, action='adjust', request='Remove warmup and cooldown from this steady endurance ride'), answer(status='review')])
        proposal = next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
        self.assertEqual(proposal['status'], 'proposal', proposal)
        self.assertEqual([w['workout_id'] for w in proposal['adjustments']], [self.rows[0]['id']])
        save({'message':proposal['request'],'fingerprint':proposal['fingerprint']}, self.path, NOW)
        from app.training_coach import read_brief
        self.assertFalse(read_brief(self.path)['brief']['continuous_endurance'])
        after = {w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(after[self.rows[1]['id']], before[self.rows[1]['id']])

    def test_maintenance_duplicate_with_different_argument_order_uses_one_receipt(self):
        event = {'equipment_label':'Road bike','action':'Replaced chain','event_date':'2026-10-18'}
        self.run_chat('Log the chain replacement', [call('load_skill', skill_id='maintenance.log'),
            call('log_maintenance', events=[event], operation_id='one'),
            {'calls':[{'name':'log_maintenance','arguments':{'operation_id':'two','events':[dict(reversed(list(event.items())))]}}]}, answer('Logged once.')])
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM maintenance_events').fetchone()[0], 1)

    def test_deleted_food_is_not_replayed_as_a_saved_meal(self):
        text='I ate 100 grams of eggs'
        events=self.run_chat(text,[call('load_skill',skill_id='nutrition.log'),call('nutrition_conversation',intent='log',ingredients=[{'name':'Eggs','grams':100}]),answer('Logged eggs.')],operation_id='deleted-food')
        nutrition=next(e['evidence']['nutrition'] for e in events if e['type']=='tool')
        from app.nutrition import delete_meal
        saved=nutrition['saved_meals'][0]
        delete_meal(saved['id'],saved['revision'],self.path)
        replay=self.run_chat(text,[],operation_id='deleted-food')
        self.assertNotIn('Logged eggs',str(replay))
        self.assertTrue(next(e['evidence']['nutrition'] for e in replay if e['type']=='tool')['deleted'])

    def test_upgrade_preserves_selected_sol_and_pending_task_context(self):
        import shutil
        from app.database import MIGRATIONS_DIRECTORY
        folder=Path(self.tmp.name)/'prior-migrations';folder.mkdir()
        for migration in MIGRATIONS_DIRECTORY.glob('*.sql'):
            if migration.name < '039_skill_agent.sql':shutil.copyfile(migration,folder/migration.name)
        prior=Path(self.tmp.name)/'prior.sqlite'
        with patch('app.database.MIGRATIONS_DIRECTORY',folder):migrate(prior)
        with connect(prior) as c:
            c.execute("UPDATE ai_settings SET active_provider='chatgpt',chatgpt_model='gpt-6.1-sol',assistant_workflow='efficient'")
            state={'resolved_request':'replace strength on 2026-10-19','nutrition_context':{'day':'2026-10-19','pending_foods':[{'name':'Yogurt'}]}}
            c.execute('INSERT INTO assistant_tasks(id,conversation_id,role,kind,status,request,timezone,anchor_date,state_json) VALUES(?,?,?,?,?,?,?,?,?)',('old-task','old-chat','trainer','training_edit','awaiting_information','Replace strength',TZ,'2026-10-19',json.dumps(state)))
        self.assertEqual(migrate(prior), ['039_skill_agent.sql','040_training_notes.sql'])
        self.assertEqual(get_ai_settings(prior)['chatgpt_model'], 'gpt-6.1-sol')
        self.assertNotIn('assistant_workflow',get_ai_settings(prior))
        with connect(prior) as c:
            retained=json.loads(c.execute('SELECT state_json FROM assistant_skill_sessions WHERE conversation_id=?',('old-chat',)).fetchone()[0])
        self.assertEqual(retained['memory']['previous_task']['resolved_request'],'replace strength on 2026-10-19')
        self.assertEqual(retained['nutrition']['pending_foods'],[{'name':'Yogurt'}])


if __name__ == '__main__':
    unittest.main()
