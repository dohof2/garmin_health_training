import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_training_adjustments import fixture,NOW,TZ
from app.database import connect
from app.training import list_training,encoded
from app.active_training import swap_workouts
from app.training_adjustments import propose,save


class SwapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'swap.sqlite';fixture(self.path)
        self.rows=sorted(list_training(self.path)['workouts'],key=lambda w:w['scheduled_for'])[:2]
    def swap(self,preview=False):
        a,b=self.rows
        return swap_workouts(a['id'],b['id'],a['revision'],b['revision'],self.path,NOW,preview)
    def test_preview_rollback_then_atomic_save_and_stale_rejection(self):
        before=list_training(self.path)
        self.swap(True);self.assertEqual(before,list_training(self.path))
        self.swap()
        after={w['id']:w for w in list_training(self.path)['workouts']}
        for a,b in zip(self.rows,reversed(self.rows)):
            self.assertEqual(after[a['id']]['scheduled_for'],b['scheduled_for'])
            self.assertEqual(after[a['id']]['definition']['steps'],a['definition']['steps'])
            self.assertEqual(after[a['id']]['revision'],a['revision']+1)
        with self.assertRaisesRegex(ValueError,'changed'):self.swap()
    def test_failed_second_validation_rolls_back_both(self):
        with connect(self.path) as c:
            d=self.rows[1]['definition'];d['fixed_commitment']=True
            c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(d),self.rows[1]['id']))
        before=list_training(self.path)
        with self.assertRaisesRegex(ValueError,'fixed event'):self.swap()
        self.assertEqual(before,list_training(self.path))
    def test_swap_does_not_undo_on_daily_review(self):
        from app.active_training import review
        self.swap()
        before={w['id']:w for w in list_training(self.path)['workouts']}
        review(self.path,TZ,NOW)
        after={w['id']:w for w in list_training(self.path)['workouts']}
        for row in self.rows:
            self.assertEqual(after[row['id']]['scheduled_for'],before[row['id']]['scheduled_for'])
            self.assertEqual(after[row['id']]['definition']['steps'],before[row['id']]['definition']['steps'])

    def test_unavailable_destination_rolls_back(self):
        with connect(self.path) as c:
            answers=json.loads(c.execute('SELECT answers_json FROM training_preferences WHERE id=1').fetchone()[0])
            answers['week_schedule'][2]['activities'][0]['max_minutes']=10
            c.execute('UPDATE training_preferences SET answers_json=? WHERE id=1',(encoded(answers),))
        before=list_training(self.path)
        with self.assertRaisesRegex(ValueError,'available matching sport slot'):self.swap()
        self.assertEqual(before,list_training(self.path))

    def test_negated_swap_is_not_proposed(self):
        before=list_training(self.path)
        p=propose("Don't swap Monday and Wednesday workouts",self.path,NOW)
        self.assertEqual(p['status'],'needs_input')
        self.assertEqual(before,list_training(self.path))

    def test_chat_proposal_and_save(self):
        p=propose('Switch Monday and Wednesday workouts',self.path,NOW)
        self.assertEqual(p['status'],'proposal',p)
        save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        after={w['id']:w for w in list_training(self.path)['workouts']}
        self.assertEqual(after[self.rows[0]['id']]['scheduled_for'],self.rows[1]['scheduled_for'])

    def cross_sport_fixture(self):
        """Monday cycling 60m; Tuesday strength 25m in a 30m slot."""
        with connect(self.path) as c:
            answers=json.loads(c.execute('SELECT answers_json FROM training_preferences WHERE id=1').fetchone()[0])
            answers['sports']=['cycling','strength'];answers['experience']['strength']='regular'
            answers['week_schedule'][1]={'weekday':1,'mode':'training','total_limit_minutes':30,'activities':[{'slot_id':'tue-strength','sport':'strength','max_minutes':30}]}
            c.execute('UPDATE training_preferences SET answers_json=? WHERE id=1',(encoded(answers),))
            row=self.rows[1]
            d={'title':'Cycling-support strength','sport':'strength','duration_minutes':25,'scheduled_date':'2026-10-20','time_unspecified':True,'schedule_timezone':TZ,'schedule_slot_id':'tue-strength','exercises':[{'id':'dead_bug','name':'Dead bug','sets':2,'repetitions':8,'rest_seconds':90}]}
            c.execute('UPDATE planned_workouts SET sport=?,title=?,scheduled_for=?,definition_json=? WHERE id=?',('strength',d['title'],'2026-10-20T12:00:00+03:00',encoded(d),row['id']))


    def test_cross_sport_override_keeps_recovery_guard(self):
        self.cross_sport_fixture()
        with connect(self.path) as c:
            # An adjacent demanding cycling workout still blocks moving quality work.
            a=c.execute('SELECT * FROM planned_workouts WHERE id=?',(self.rows[0]['id'],)).fetchone()
            d=json.loads(a['definition_json']);d['workout_kind']='threshold'
            c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(d),a['id']))
            peer=c.execute("SELECT * FROM planned_workouts WHERE scheduled_for LIKE '2026-10-23%' LIMIT 1").fetchone()
            d=json.loads(peer['definition_json']);d.update(scheduled_date='2026-10-21',workout_kind='threshold')
            c.execute('UPDATE planned_workouts SET scheduled_for=?,definition_json=? WHERE id=?',('2026-10-21T12:00:00+03:00',encoded(d),peer['id']))
        before=list_training(self.path)
        p=propose('swap the strenth of tomorrow with the edurance of today',self.path,NOW)
        self.assertEqual(p['status'],'not_recommended',p)
        self.assertIn('recovery day',p['message'])
        self.assertEqual(before,list_training(self.path))
