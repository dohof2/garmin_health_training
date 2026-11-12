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

    def test_larger_conversation_budget_still_stops_before_exceeding_cap(self):
        from app.agent_runtime import Runtime, BudgetExceeded
        runtime=Runtime()
        self.assertEqual(runtime.input_limit,125000)
        self.assertEqual(runtime.call_limit,16)
        for _ in range(16):runtime.reserve({'message':'small'},'instructions')
        with self.assertRaises(BudgetExceeded):runtime.reserve({},'')
        runtime=Runtime()
        with self.assertRaises(BudgetExceeded):runtime.reserve({'message':'x'*260000},'')
        self.assertEqual(runtime.usage['model_calls'],0)

    def test_retained_proposal_summary_omits_bulk_but_preserves_review_identity(self):
        import copy
        from app.ai_budget import compact_training_proposal
        proposal={'status':'proposal','request':'@session:explicit','fingerprint':'checked',
                  'adjustments':[{'workout_id':'one','expected_revision':2,'summary':['Warning: 33% increase'],
                    'changes':{'definition':{'duration_minutes':60,'steps':[{'raw':'x'*10000}], 'exercises':[{'raw':'y'*10000}]}}}]}
        before=copy.deepcopy(proposal)
        compact=compact_training_proposal(proposal)
        self.assertEqual(compact['fingerprint'],'checked')
        self.assertEqual(compact['request'],'@session:explicit')
        self.assertEqual(compact['adjustments'][0]['expected_revision'],2)
        self.assertEqual(compact['adjustments'][0]['summary'],['Warning: 33% increase'])
        self.assertLess(len(json.dumps(compact)),len(json.dumps(proposal))/10)
        self.assertEqual(proposal,before)
