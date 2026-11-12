"""A reduced training block retains aerobic riding rather than acute recovery spins."""
import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from app.database import connect, migrate
from app.training_coach import DEFAULT, preview
from test_long_ride_allocation import START, NOW, TZ, preferences


class DeloadWeekTests(unittest.TestCase):
    def test_generated_recovery_block_preserves_base_ride_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.sqlite';migrate(path)
            with connect(path) as c:
                for index in range(8):
                    day=START-timedelta(days=1+(index//2)*7+index%2)
                    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,7920)",
                              (str(index),day.isoformat()+'T07:00:00+00:00'))
            brief={**copy.deepcopy(DEFAULT),'goal':'ftp','duration_confirmed':True,'program_start':START.isoformat(),
                   'strength_role':'secondary','strength_purpose':'cycling_support'}
            normal=preview(brief,START,TZ,path,NOW,candidate_answers=preferences())
            result=preview(brief,START+timedelta(days=21),TZ,path,NOW,candidate_answers=preferences())
            self.assertEqual(result['status'],'ready',result['questions'])
            rides=[s['definition'] for s in result['sessions'] if s['sport']=='cycling']
            self.assertTrue(rides)
            self.assertTrue(all(d['workout_kind']=='endurance' for d in rides))
            self.assertTrue(any(d['duration_minutes']>30 for d in rides))
            self.assertTrue(all(d['training_block']['phase']=='Recovery / review' for d in rides))

            self.assertEqual(sorted(d['duration_minutes'] for d in rides),sorted(s['definition']['duration_minutes'] for s in normal['sessions'] if s['sport']=='cycling'))
            self.assertGreaterEqual(max(d['duration_minutes'] for d in rides),60)
