"""Exercise real provider event parsing, not a simulated JSON reply envelope."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from app.ai_chat import chat_stream
from app.ai_providers import ChatGPTProvider, OpenAIProvider, OllamaProvider, response_result, tool_result_message
from app.database import migrate
from app.skill_tools import definition


class NativeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'test.sqlite'
        migrate(self.path)

    def test_metadata_only_terminal_preserves_streamed_calls_and_opaque_reasoning(self):
        reasoning = {'id':'rs-one','type':'reasoning','summary':[],'encrypted_content':'opaque-provider-state'}
        function = {'type':'function_call','id':'fc-one','call_id':'call-one','name':'lookup_workouts','arguments':'{"date":"2026-11-03"}'}
        stream = [NS(type='response.output_item.done',item=reasoning),
                  NS(type='response.output_item.done',item=function),
                  NS(type='response.completed',response=NS(output=None,usage=None))]
        with patch('app.chatgpt_auth.access_token',return_value='fake'),patch('app.ai_providers.OpenAI') as client:
            client.return_value.responses.create.return_value=iter(stream)
            result=ChatGPTProvider('gpt-6.1-sol',self.path).respond([{'role':'user','content':'Change today’s workout'}],'Instructions',
                [definition('lookup_workouts','Read sessions',{'date':{'type':'string'}})])
        self.assertEqual(result['calls'],[{'id':'call-one','name':'lookup_workouts','arguments':{'date':'2026-11-03'}}])
        self.assertEqual(result['messages'],[reasoning,function])
        sent=client.return_value.responses.create.call_args.kwargs
        self.assertEqual(sent['reasoning'],{'effort':'low'})
        self.assertEqual(sent['tools'][0]['type'],'function')
        self.assertFalse(sent['store'])

    def test_natural_language_final_answer_is_not_parsed_as_json(self):
        raw='מצאתי את אימון הכוח של היום. כמה זמן תרצה לרכוב?'
        stream=[NS(type='response.output_text.delta',delta=raw),NS(type='response.completed',response=NS(output=None,usage=None))]
        with patch('app.chatgpt_auth.access_token',return_value='fake'),patch('app.ai_providers.OpenAI') as client:
            client.return_value.responses.create.return_value=iter(stream)
            result=ChatGPTProvider('gpt-6.1-sol',self.path).respond([], 'Instructions', [])
        self.assertEqual(result['reply'],raw)
        self.assertEqual(result['calls'],[])

    def test_native_call_and_output_retain_the_same_call_id(self):
        result=response_result([{'type':'function_call','call_id':'chosen-by-provider','name':'find_skills','arguments':'{"query":"edit workout"}'}])
        message=tool_result_message(result['calls'][0],{'skills':[]})
        self.assertEqual(message,{'type':'function_call_output','call_id':'chosen-by-provider','output':'{"skills":[]}'})

    def test_malformed_function_arguments_become_tool_validation_feedback(self):
        replies=iter([
            response_result([{'type':'function_call','call_id':'load','name':'load_skill','arguments':'{"skill_id":"training.sessions.edit"}'}]),
            response_result([{'type':'function_call','call_id':'one','name':'lookup_workouts','arguments':'not valid JSON'}]),
            {'reply':'Let me correct that lookup.','calls':[],'messages':[]},
        ])
        seen=[]
        def respond(messages,*a,**k):
            seen.append(messages.copy())
            return next(replies)
        with patch('app.ai_providers._active_provider',return_value=NS(respond=respond)):
            events=[json.loads(line) for line in chat_stream('Change today’s strength',[], 'Asia/Jerusalem',self.path,conversation_id='validation',operation_id='validation')]
        self.assertFalse(any(e['type']=='error' for e in events),events)
        feedback=next(m for m in seen[-1] if m.get('call_id')=='one' and m.get('type')=='function_call_output')
        self.assertEqual(json.loads(feedback['output'])['status'],'not_applied')

    def test_openai_native_response_retains_plain_reply_and_tool_schemas(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake'}),patch('app.ai_providers.OpenAI') as client:
            client.return_value.responses.create.return_value=NS(status='completed',output=[],output_text='A natural reply.',usage=None)
            result=OpenAIProvider('selected-model').respond([{'role':'user','content':'Hello'}],'Rules',[definition('lookup','Read',{})])
        self.assertEqual(result['reply'],'A natural reply.')
        self.assertEqual(client.return_value.responses.create.call_args.kwargs['tools'][0]['name'],'lookup')

    def test_ollama_native_tools_keep_function_messages_and_thinking_state(self):
        message={'role':'assistant','content':'','thinking':'model-native state','tool_calls':[{'function':{'name':'find_skills','arguments':{'query':'meal logging'}}}]}
        with patch('app.ai_providers.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value=json.dumps({'message':message}).encode()
            result=OllamaProvider('local-model').respond([{'role':'user','content':'Log food'}],'Rules',[definition('find_skills','Search',{'query':{'type':'string'}})])
        self.assertEqual(result['calls'][0]['arguments'],{'query':'meal logging'})
        self.assertEqual(result['messages'],[message])
        self.assertEqual(tool_result_message(result['calls'][0],{'skills':[]},result['transport'])['role'],'tool')

    def test_three_native_responses_can_finish_with_plain_clarification(self):
        replies=iter([
            response_result([{'type':'function_call','call_id':'search','name':'find_skills','arguments':'{"query":"change workout"}'}]),
            response_result([{'type':'function_call','call_id':'load','name':'load_skill','arguments':'{"skill_id":"training.sessions.edit"}'}]),
            {'reply':'How many minutes would you like for the bike ride?','calls':[],'messages':[],'transport':'responses'},
        ])
        sent=[]
        def respond(messages,instructions,tools,**kwargs):
            sent.append(json.loads(json.dumps(messages)))
            return next(replies)
        with patch('app.ai_providers._active_provider',return_value=NS(respond=respond)):
            events=[json.loads(line) for line in chat_stream('can you change the workout for today? I did strength yestreday and i want to do a bike ride instead',[], 'Asia/Jerusalem', self.path,conversation_id='workout',operation_id='workout')]
        self.assertFalse(any(e['type']=='error' for e in events),events)
        self.assertEqual(events[-1]['usage']['model_calls'],3)
        self.assertIn('How many minutes',next(e['text'] for e in events if e['type']=='delta'))
        self.assertTrue(any(m.get('type')=='function_call_output' and m['call_id']=='search' for m in sent[1]))

    def test_hebrew_food_report_accepts_plain_native_answer_without_loading_unrelated_skills(self):
        raw='האם הגביע היה של 150 גרם?'
        with patch('app.ai_providers._active_provider',return_value=NS(respond=lambda *a,**k:{'reply':raw,'calls':[],'messages':[],'transport':'responses'})):
            events=[json.loads(line) for line in chat_stream('אכלתי לארוחת צהריים גביע יוגורט אחד',[], 'Asia/Jerusalem', self.path,conversation_id='food',operation_id='food')]
        self.assertFalse(any(e['type']=='error' for e in events),events)
        self.assertEqual(next(e['text'] for e in events if e['type']=='delta'),raw)

    def test_failed_turn_keeps_original_request_for_a_retry(self):
        original='אכלתי לארוחת צהריים גביע יוגורט אחד'
        with patch('app.ai_providers._active_provider',side_effect=RuntimeError('private provider details')):
            list(chat_stream(original,[], 'Asia/Jerusalem', self.path,conversation_id='retry',operation_id='failed'))
        seen=[]
        def respond(messages,*args,**kwargs):
            seen.append(json.loads(messages[0]['content']))
            return {'reply':'האם זה גביע של 150 גרם?','calls':[],'messages':[]}
        with patch('app.ai_providers._active_provider',return_value=NS(respond=respond)):
            list(chat_stream('נסה שוב',[], 'Asia/Jerusalem',self.path,conversation_id='retry',operation_id='next'))
        self.assertTrue(any(m['content']==original for m in seen[0]['recent_exchange']))
        self.assertNotIn('private provider details',str(seen))
