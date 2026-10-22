"""50 casual requests through chat, plus saved state and safety regressions."""
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.database import connect, migrate
from app.training_coach import DEFAULT, preview, approve
from app.training import list_training, encoded
from app.training_adjustments import propose, save
from app.ai_chat import chat_stream

NOW=datetime(2026,10,19,7,tzinfo=timezone.utc)
TZ='Asia/Jerusalem'
# Outcome checks are deliberately explicit: answering alone is not a pass.
CASES=[
 ('I am feeling good give me harder workout','proposal'),
 ('Feeling fresh, make my ride tougher today','proposal'),
 ('Can we do tempo today?','proposal'),
 ('Give me some intervals today','proposal'),
 ('I feel great, increase the intensity today','proposal'),
 ('Can you give me a harder workuot today please','proposal'),
 ('Make today easier please','proposal'),
 ('My legs are tired, cut today back','proposal'),
 ('Can we back off this week?','proposal'),
 ('Reduce my cycling this week by 20%','proposal'),
 ('Cut this week by 50%','proposal'),
 ('I need a lighter week','proposal'),
 ('Make all rides easy this week','proposal'),
 ('Halve the training this week','proposal'),
 ('I only have 30 minutes today','proposal'),
 ('Only got 20 mins for my ride today','proposal'),
 ('I can only ride for 45 minutes today','proposal'),
 ('Make the long ride easier on Friday','proposal'),
 ('Skip my ride today','proposal'),
 ('I need a rest day today','proposal'),
 ('Cancel cycling this week','proposal'),
 ('I have knee pain, make the ride easy','proposal'),
 ('I feel sick, skip today','proposal'),
 ('I have a fever, should I rest today?','proposal'),
 ('I am sore, make it easier','proposal'),
 ('My sleep was terrible, give me a harder workout','not_recommended'),
 ('I slept 3 hours but want a harder ride','not_recommended'),
 ('I have knee pain but give me harder intervals','not_recommended'),
 ('I am sick but want sprints','not_recommended'),
 ('I am exhausted but make it harder','not_recommended'),
 ('Make every workout harder this week','not_recommended'),
 ('Double my cycling this week','not_recommended'),
 ('Increase cycling time this week by 20%','not_recommended'),
 ('Make Friday a longer ride','not_recommended'),
 ('Add more time to my weekly training','not_recommended'),
 ('Give me sprint training today','not_recommended'),
 ('Can we do anaerobic intervals today?','not_recommended'),
 ('Give me spritns today','not_recommended'),
 ('Make tomorrow easier','needs_input'),
 ('Make next week lighter','needs_input'),
 ('I only have 5 minutes today','needs_input'),
 ('Make today 200 minutes','needs_input'),
 ('Reduce this week by 150%','needs_input'),
 ('Move my ride to tomorrow','needs_input'),
 ('Swap Monday and Wednesday training','needs_input'),
 ('I feel good','needs_input'),
 ('Make my strength workout harder','needs_input'),
 ('My last ride felt too hard','needs_input'),
 ("Don't make today harder",'needs_input'),
 ('Can you make today easir?','proposal'),
]


def fixture(path):
    migrate(path)
    with connect(path) as c:
        for index in range(8):
            day=date(2026,10,17)-timedelta(days=index//2*7+index%2)
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,9000)",(str(index),day.isoformat()+'T07:00:00+00:00'))
    answers={'sports':['cycling'],'priority':'endurance','experience':{'cycling':'experienced'},'equipment':['bike'],'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False,
        'week_schedule':[{'weekday':d,'mode':'training' if d in (0,2,4,6) else 'rest','total_limit_minutes':None,'activities':[{'slot_id':str(d),'sport':'cycling','max_minutes':180 if d==4 else 90}] if d in (0,2,4,6) else []} for d in range(7)]}
    brief={**DEFAULT,'goal':'ftp','program_start':'2026-10-19','duration_confirmed':True,'calibration':{'power_access':'none','hr_sensor':False}}
    p=preview(brief,date(2026,10,19),TZ,path,NOW,candidate_answers=answers)
    assert p['status']=='ready',p['questions']
    approve(p['brief'],date(2026,10,19),TZ,p['fingerprint'],path,NOW,candidate_answers=p['candidate_answers'])
    # Controlled easy-only week isolates the positive intensity branch. Separate
    # tests restore a nearby quality session and verify the refusal.
    from app.training_prescriptions import endurance
    with connect(path) as c:
        for row in c.execute('SELECT * FROM planned_workouts').fetchall():
            old=json.loads(row['definition_json'])
            definition=endurance('long_endurance' if row['scheduled_for'][:10]=='2026-10-23' else 'endurance',old['duration_minutes'],brief,today=NOW.date())
            definition.update({k:v for k,v in old.items() if k.startswith('schedule_') or k in ('scheduled_date','time_unspecified')})
            c.execute('UPDATE planned_workouts SET definition_json=?,title=? WHERE id=?',(encoded(definition),definition['title'],row['id']))


class TrainingAdjustmentQC(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'base.sqlite';fixture(self.path)

    def test_fifty_casual_requests_through_chat_and_save(self):
        self.assertEqual(len(CASES),50)
        for index,(message,expected) in enumerate(CASES):
            with self.subTest(index=index+1,message=message):
                path=Path(self.directory.name)/f'case-{index}.sqlite'
                # Cached readers may keep committed data in WAL. Copy a complete
                # SQLite snapshot rather than only the main database file.
                with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(path)) as target:
                    source.backup(target)
                before=list_training(path)
                with patch('app.training_adjustments.datetime',wraps=datetime) as clock, patch('app.ai_chat._chatgpt_stream',side_effect=AssertionError('Unexpected provider fallback')):
                    clock.now.return_value=NOW
                    events=[json.loads(line) for line in chat_stream(message,path=path,timezone_name=TZ,coaching_context={'ongoing':True})]
                self.assertFalse(any(e['type']=='error' for e in events),events)
                self.assertTrue(any(e['type']=='delta' and e.get('text') for e in events),events)
                self.assertEqual(events[-1]['type'],'complete')
                proposal=next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
                self.assertEqual(proposal['status'],expected,proposal)
                self.assertEqual(before,list_training(path),'Preview must not write')
                if expected=='proposal':
                    saved=save({'message':message,'fingerprint':proposal['fingerprint']},path,NOW)
                    self.assertEqual(saved['count'],len(proposal['adjustments']))
                    after={w['id']:w for w in list_training(path)['workouts']}
                    for item in proposal['adjustments']:
                        row=after[item['workout_id']]
                        self.assertEqual(row['revision'],item['expected_revision']+1)
                        if item['changes'].get('completion_status'):self.assertEqual(row['completion_status'],'skipped')
                        else:
                            definition=row['definition'];self.assertEqual(definition,item['changes']['definition'])
                            self.assertEqual(sum(s['duration_seconds'] for s in definition['steps']),definition['duration_minutes']*60)
                    with self.assertRaises(ValueError):save({'message':message,'fingerprint':proposal['fingerprint']},path,NOW)

    def test_stale_and_forged_proposals_do_not_write(self):
        p=propose('Make today easier',self.path,NOW);before=list_training(self.path)
        with self.assertRaises(ValueError):save({'message':p['request'],'fingerprint':'forged'},self.path,NOW)
        self.assertEqual(before,list_training(self.path))
        with connect(self.path) as c:c.execute('UPDATE planned_workouts SET revision=revision+1 WHERE id=?',(p['adjustments'][0]['workout_id'],))
        with self.assertRaises(ValueError):save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)

    def test_poor_recorded_sleep_blocks_harder_and_rechecks_on_save(self):
        p=propose('Give me a harder workout today',self.path,NOW);self.assertEqual(p['status'],'proposal')
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(source_name,metric_type,value,unit,recorded_at) VALUES('garmin_export','sleep_score',30,'score','2026-10-19T03:00:00+00:00')")
        blocked=propose(p['request'],self.path,NOW)
        self.assertEqual(blocked['status'],'not_recommended');self.assertIn('sleep',blocked['message'])
        with self.assertRaises(ValueError):save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)

    def test_existing_quality_and_recovery_week_cannot_be_overridden(self):
        from app.training_prescriptions import endurance
        with connect(self.path) as c:
            row=c.execute("SELECT * FROM planned_workouts WHERE scheduled_for LIKE '2026-10-21%'").fetchone()
            d=json.loads(row['definition_json']);d.update(endurance('tempo',60,DEFAULT,today=NOW.date()))
            c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(d),row['id']))
        p=propose('Make today harder',self.path,NOW)
        self.assertEqual(p['status'],'not_recommended');self.assertIn('quality session',p['message'])
        with connect(self.path) as c:
            c.execute("UPDATE planned_workouts SET completion_status='skipped' WHERE scheduled_for LIKE '2026-10-21%'")
            state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0]);state['blocks'][0]['phase']='Recovery / review'
            c.execute('UPDATE active_training_program SET state_json=?',(encoded(state),))
        self.assertIn('recovery',propose('Make today harder',self.path,NOW)['message'])

    def test_no_active_plan_and_ambiguous_session(self):
        with connect(self.path) as c:c.execute("UPDATE active_training_program SET status='paused'")
        self.assertEqual(propose('Make today easier',self.path,NOW)['status'],'needs_input')

    def test_recorded_load_soreness_missing_history_and_published_workouts(self):
        with patch('app.training_load_charts.daily_rows',return_value=[{'date':NOW.date().isoformat(),'acute':800,'high':400}]):
            p=propose('Make today harder',self.path,NOW)
            self.assertEqual(p['status'],'not_recommended');self.assertIn('load',p['message'])
        from app.training import update_workout
        w=list_training(self.path)['workouts'][0]
        update_workout(w['id'],w['revision'],{'soreness':7},self.path)
        p=propose('Make today harder',self.path,NOW)
        self.assertEqual(p['status'],'not_recommended');self.assertIn('soreness',p['message'])
        with connect(self.path) as c:
            c.execute('DELETE FROM training_feedback')
            c.execute('DELETE FROM activities')
        p=propose('Make today harder',self.path,NOW)
        self.assertEqual(p['status'],'not_recommended');self.assertIn('evidence',p['message'])
        with connect(self.path) as c:c.execute("UPDATE planned_workouts SET publish_status='published' WHERE id=?",(w['id'],))
        self.assertEqual(propose('Make today easier',self.path,NOW)['status'],'not_recommended')

    def test_reading_health_and_plotting_are_not_adjustments(self):
        from app.training_adjustments import is_adjustment
        for message in ('How was my sleep last night?','Plot my weekly training load','What is anaerobic training?','Compare my last hard ride','Show soreness feedback'):
            self.assertFalse(is_adjustment(message),message)

    def test_saved_changes_reach_next_seven_days_and_survive_refresh(self):
        from app.active_training import active_view, review
        p=propose('Reduce my cycling this week by 20%',self.path,NOW)
        save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        visible={w['id']:w for w in active_view(self.path,TZ,NOW)['workouts']}
        for item in p['adjustments']:
            self.assertEqual(visible[item['workout_id']]['definition'],item['changes']['definition'])
        refreshed=review(self.path,TZ,NOW)
        visible={w['id']:w for w in refreshed['workouts']}
        for item in p['adjustments']:
            self.assertIn(item['workout_id'],visible)
            self.assertLessEqual(visible[item['workout_id']]['definition']['duration_minutes'],item['changes']['definition']['duration_minutes'])
        p=propose('Skip my ride today',self.path,NOW)
        save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        refreshed=review(self.path,TZ,NOW)
        self.assertNotIn(p['adjustments'][0]['workout_id'],{w['id'] for w in refreshed['workouts']})
