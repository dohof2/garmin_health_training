import copy
import unittest
from datetime import date
from app.training_prescriptions import RATIOS, power_range, endurance
from app.workout_edits import edit, requested, EditError

class PowerToleranceTests(unittest.TestCase):
 def test_midpoints_and_widths(self):
  for kind,bounds in RATIOS.items():
   low,high=power_range(kind,bounds)
   self.assertAlmostEqual((low+high)/2,sum(bounds)/2)
   self.assertGreaterEqual(high-low,bounds[1]-bounds[0]-1e-9)
  self.assertGreater(power_range('endurance',RATIOS['endurance'])[1]-power_range('endurance',RATIOS['endurance'])[0],power_range('threshold',RATIOS['threshold'])[1]-power_range('threshold',RATIOS['threshold'])[0])
 def test_generation_and_explicit_widening(self):
  brief={'ftp_watts':250,'calibration':{'power_access':'both','ftp_confirmed_on':'2026-11-02'}}
  original=endurance('threshold',60,brief,today=date(2026,11,2))
  before=copy.deepcopy(original)
  changed,_=edit(original,'widen the power range by 20%',{},False)
  self.assertEqual(original,before)
  for a,b in zip(original['steps'],changed['steps']):
   self.assertEqual(a['duration_seconds'],b['duration_seconds'])
   self.assertAlmostEqual(sum(a['target'][k] for k in ('lower','upper')),sum(b['target'][k] for k in ('lower','upper')))
   self.assertAlmostEqual(b['target']['upper']-b['target']['lower'],1.2*(a['target']['upper']-a['target']['lower']),places=2)
  self.assertTrue(requested('widen the power target range'))
  self.assertFalse(requested('do not widen the power target range'))
  self.assertEqual(changed['duration_minutes'],original['duration_minutes'])
 def test_no_power_does_not_invent_watts(self):
  w=endurance('endurance',60,{},today=date(2026,11,2))
  with self.assertRaises(EditError):edit(w,'widen the power range',{},False)
