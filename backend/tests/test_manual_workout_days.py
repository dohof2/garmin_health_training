import json
import tempfile
import unittest
from pathlib import Path
from test_training_adjustments import fixture,NOW,TZ
from app.database import connect
from app.training import list_training,encoded
from app.active_training import reschedule,swap_workouts,review


class ManualWorkoutDayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'manual.sqlite';fixture(self.path)
        self.workouts=sorted(list_training(self.path)['workouts'],key=lambda w:w['scheduled_for'])
        self.source=self.workouts[0]
    def move(self,day='2026-10-20',manual=True,revision=None):
        return reschedule(self.source['id'],None,self.source['revision'] if revision is None else revision,self.path,NOW,scheduled_date=day,manual_override=manual)
    def test_move_to_rest_day_is_explicit_exception_and_preserves_instructions(self):
        with connect(self.path) as c:preferences=c.execute('SELECT answers_json FROM training_preferences').fetchone()[0]
        with self.assertRaises(ValueError):self.move(manual=False)
        self.move()
        after=next(w for w in list_training(self.path)['workouts'] if w['id']==self.source['id'])
        self.assertEqual(after['definition']['scheduled_date'],'2026-10-20')
        self.assertEqual(after['definition']['steps'],self.source['definition']['steps'])
        self.assertTrue(after['definition']['user_adjusted'])
        with connect(self.path) as c:self.assertEqual(preferences,c.execute('SELECT answers_json FROM training_preferences').fetchone()[0])
        review(self.path,TZ,NOW)
        active=[w for w in list_training(self.path)['workouts'] if w['completion_status']=='planned']
        self.assertFalse(any(w['definition'].get('scheduled_date')=='2026-10-19' for w in active),'Review must not refill the vacated day')
        self.assertTrue(any(w['id']==self.source['id'] and w['definition']['scheduled_date']=='2026-10-20' for w in active))
    def test_manual_swap_handles_different_duration_allowances(self):
        long=next(w for w in self.workouts if w['definition']['duration_minutes']>90)
        args=(self.source['id'],long['id'],self.source['revision'],long['revision'],self.path,NOW)
        with self.assertRaises(ValueError):swap_workouts(*args)
        swap_workouts(*args,manual_override=True)
        current={w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(current[long['id']]['definition']['scheduled_date'],'2026-10-19')
        self.assertEqual(current[long['id']]['definition']['duration_minutes'],long['definition']['duration_minutes'])
    def test_failed_stale_past_or_outside_plan_moves_leave_cards_unchanged(self):
        before=list_training(self.path)
        for kwargs in ({'revision':0},{'day':'2026-10-18'},{'day':'2028-01-01'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.move(**kwargs)
        self.assertEqual(before,list_training(self.path))
    def test_completed_and_fixed_workouts_cannot_be_dragged(self):
        with connect(self.path) as c:c.execute("UPDATE planned_workouts SET completion_status='completed' WHERE id=?",(self.source['id'],))
        with self.assertRaises(ValueError):self.move()
        with connect(self.path) as c:
            d=self.source['definition'];d['fixed_commitment']=True
            c.execute("UPDATE planned_workouts SET completion_status='planned',definition_json=? WHERE id=?",(encoded(d),self.source['id']))
        with self.assertRaisesRegex(ValueError,'fixed event'):self.move()
    def test_manual_exception_does_not_bypass_recovery_after_completed_work(self):
        long=next(w for w in self.workouts if w['definition']['duration_minutes']>90)
        peer=next(w for w in self.workouts if w['definition'].get('scheduled_date')=='2026-10-21')
        with connect(self.path) as c:
            d=peer['definition'];d['duration_minutes']=120
            c.execute("UPDATE planned_workouts SET completion_status='completed',definition_json=? WHERE id=?",(encoded(d),peer['id']))
        self.source=long;before=list_training(self.path)
        with self.assertRaisesRegex(ValueError,'recovery day'):self.move(day='2026-10-22')
        self.assertEqual(before,list_training(self.path))
