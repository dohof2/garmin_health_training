import unittest
from app.training_adjustments import is_adjustment

class AnalysisRoutingTests(unittest.TestCase):
    def test_analysis_is_not_edit(self):
        for text in ["look at the anerobic interval do you see the decline both within and between intervals does that make sense? what does it mean?", "it was supposed to be the max so it makes sense", "look at the intervals, do you see the fading?"]:
            with self.subTest(text=text):
                self.assertFalse(is_adjustment(text))

    def test_explicit_edit(self):
        self.assertTrue(is_adjustment("reduce tomorrow's intervals to 4 repetitions"))
