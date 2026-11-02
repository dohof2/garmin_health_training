import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx2
from openai import APIError
from app.database import migrate
from app.ai_providers import shared_allowance_message
from app.food_vision import analyze_food
from app.ai_chat import chat_stream

class SharedAssistantLimitTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
  self.error=APIError('Limit',request=httpx2.Request('POST','https://api.openai.com/v1/responses'),body={'error':{'code':'subscription_sharing_usage_limit_exceeded','message':'private provider details'}})
  self.settings={'active_provider':'chatgpt','chatgpt_model':'fixture','openai_model':'fixture','ollama_model':'fixture'}
 def test_known_limit_message_is_actionable_without_provider_payload(self):
  message=shared_allowance_message(self.error);self.assertIn('allowance',message);self.assertIn('No paid fallback',message);self.assertNotIn('private provider details',message)
 def test_hebrew_food_analysis_reports_allowance_not_connection_failure(self):
  with patch('app.food_vision.get_ai_settings',return_value=self.settings),patch('app.food_vision.active_provider') as provider:
   provider.return_value.generate.side_effect=self.error
   with self.assertRaisesRegex(ValueError,'allowance') as caught:analyze_food(message='אכלתי שתי ביצים לארוחת בוקר',path=self.path,conversational=True)
  self.assertNotIn('unavailable',str(caught.exception))
 def test_trainer_stream_reports_the_same_shared_limit(self):
  with patch('app.ai_chat.get_ai_settings',return_value=self.settings),patch('app.ai_chat._chatgpt_stream',side_effect=self.error):
   events=[json.loads(event) for event in chat_stream('Help me understand my personal training context',path=self.path,chat_role='trainer')]
  error=next(event for event in events if event['type']=='error');self.assertIn('allowance',error['message']);self.assertNotIn('private provider details',error['message'])
