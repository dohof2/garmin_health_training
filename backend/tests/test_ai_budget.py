import json
import unittest
from unittest.mock import patch
from app.ai_budget import bounded_history


class BudgetTests(unittest.TestCase):
    def test_history_preserves_whole_recent_messages(self):
        history=[{'role':'user' if i%2==0 else 'assistant','content':str(i)*4000} for i in range(20)]
        result=bounded_history(history)
        self.assertEqual(result,history[-1:])
        self.assertEqual(history[0]['content'],'0'*4000)
