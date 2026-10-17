import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.database import migrate
from app.ai_chat import chat_stream,_educational_answer,_instructions,_trainer_instructions


class EducationTests(unittest.TestCase):
 def test_general_metric_questions_do_not_check_personal_records(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'education.sqlite';migrate(path)
   for question,word in [('What is power?','watts'),('What is TSS?','100 TSS'),('Explain FTP','threshold'),('What is VO2 max?','oxygen')]:
    with self.subTest(question=question),patch('app.ai_chat._execute_calls',side_effect=AssertionError('No record tools needed')):
     events=[json.loads(event) for event in chat_stream(question,path=path)]
     self.assertFalse(any(event['type']=='tool' for event in events))
     answer=' '.join(event.get('text','') for event in events)
     self.assertIn(word,answer);self.assertNotIn('Garmin',answer)
 def test_personal_questions_still_require_evidence(self):
  for question in ('What is my TSS today?','Explain power in my last ride','What was my FTP last year?'):
   self.assertIsNone(_educational_answer(question))
 def test_natural_tone_instruction_is_present_for_both_providers(self):
  self.assertIn('natural, direct',_instructions('UTC'))
  self.assertIn('conversational wording',_trainer_instructions('UTC'))
