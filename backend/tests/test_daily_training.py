import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from app.database import connect
from app.sync import ensure_sync_checkpoints
from app.training import encoded, list_training
from app.active_training import review
from app.rolling_publication import sync, status, DailyPublicationWorker
from app.garmin_training_publish import account, send, run
from app.training_daily import restore_budget_sessions
from app.training_volume import estimates
from test_training_adjustments import NOW, TZ
import test_garmin_publication as fixtures


def ready_sync(path, day):
    ensure_sync_checkpoints(path)
    with connect(path) as c:
        c.execute("UPDATE sync_checkpoints SET status='synced',coverage_end=?",(day.isoformat(),))
        checkpoint={'qc':{'through_date':day.isoformat(),'status':'passed','issues':[]},'training_load_refresh':{'failed_dates':[]}}
        c.execute("INSERT OR REPLACE INTO jobs(id,job_type,status,checkpoint_json) VALUES(?,'garmin_sync','completed',?)",('sync-'+day.isoformat(),encoded(checkpoint)))


def readiness(day, score=75):
    return {'latest':{'date':day.isoformat(),'score':score,'status':'complete','calculation_id':'test',
                     'inputs':{'sleep':{'wake_date':day.isoformat(),'id':'sleep'},'sleep_score':{'wake_date':day.isoformat()}},'groups':[]}}


class DailyTrainingTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.GarminPublicationQC();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.path=self.case.path;self.client=self.case.client;self.factory=self.case.factory
        with connect(self.path) as c:
            self.root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
            c.execute('INSERT INTO garmin_rolling_publication(id,enabled,account_key,root_plan_id,timezone) VALUES(1,1,?,?,?)',
                      (account(self.client)[0],self.root,TZ))

    def test_waits_for_completed_sync_and_same_day_sleep_readiness(self):
        with patch('app.active_training.review') as update, patch('app.readiness.readiness_history',return_value=readiness(NOW.date())):
            self.assertEqual(sync(self.path,self.factory,NOW)['status'],'waiting_for_sync')
            update.assert_not_called()
            ready_sync(self.path,NOW.date())
            with connect(self.path) as c:c.execute("UPDATE jobs SET status='running' WHERE job_type='garmin_sync'")
            self.assertEqual(sync(self.path,self.factory,NOW)['status'],'waiting_for_sync')
            update.assert_not_called()
            with connect(self.path) as c:c.execute("UPDATE jobs SET status='completed' WHERE job_type='garmin_sync'")
            with patch('app.readiness.readiness_history',return_value=readiness(NOW.date()-timedelta(days=1))):
                self.assertEqual(sync(self.path,self.factory,NOW)['status'],'waiting_for_readiness')
                update.assert_not_called()
            result=sync(self.path,self.factory,NOW)
            self.assertEqual(result['status'],'up_to_date',result)
            update.assert_called_once_with(self.path,TZ,NOW,trigger='daily')

    def test_once_per_local_day_and_does_not_consume_next_day_before_sync(self):
        ready_sync(self.path,NOW.date())
        with patch('app.active_training.review') as update, patch('app.readiness.readiness_history',side_effect=lambda day,*a,**k:readiness(day)):
            sync(self.path,self.factory,NOW);sync(self.path,self.factory,NOW+timedelta(hours=2))
            self.assertEqual(update.call_count,1)
            tomorrow=NOW+timedelta(days=1)
            self.assertEqual(sync(self.path,self.factory,tomorrow)['status'],'waiting_for_sync')
            ready_sync(self.path,tomorrow.date())
            self.assertEqual(sync(self.path,self.factory,tomorrow)['status'],'up_to_date')
            self.assertEqual(update.call_count,2)

    def test_publication_retry_does_not_repeat_daily_review(self):
        ready_sync(self.path,NOW.date())
        with patch('app.active_training.review') as update, patch('app.readiness.readiness_history',return_value=readiness(NOW.date())):
            with patch('app.garmin_training_publish.send',side_effect=ValueError('Temporary publication conflict')):
                self.assertEqual(sync(self.path,self.factory,NOW)['status'],'attention')
            self.assertEqual(status(self.path)['detail']['last_review_date'],NOW.date().isoformat())
            self.assertEqual(sync(self.path,self.factory,NOW)['status'],'up_to_date')
            update.assert_called_once()

    def test_local_midnight_starts_new_day_even_before_utc_midnight(self):
        from zoneinfo import ZoneInfo
        ready_sync(self.path,NOW.date())
        next_morning=NOW.replace(hour=22)
        local_day=next_morning.astimezone(ZoneInfo(TZ)).date()
        self.assertNotEqual(local_day,next_morning.date())
        with patch('app.active_training.review') as update, patch('app.readiness.readiness_history',side_effect=lambda day,*a,**k:readiness(day)):
            sync(self.path,self.factory,NOW)
            self.assertEqual(sync(self.path,self.factory,next_morning)['status'],'waiting_for_sync')
            ready_sync(self.path,local_day)
            self.assertEqual(sync(self.path,self.factory,next_morning)['status'],'up_to_date')
            self.assertEqual(update.call_count,2)

    def test_page_auto_review_waits_for_daily_worker(self):
        before=list_training(self.path)
        with patch('app.active_training._fill') as fill:
            review(self.path,TZ,NOW,trigger='auto')
            fill.assert_not_called()
        self.assertEqual(list_training(self.path),before)

    def test_automatic_budget_cancel_is_reconsidered_but_user_skip_is_preserved(self):
        rows=list_training(self.path)['workouts']
        cancelled,skipped=rows[:2]
        with connect(self.path) as c:
            c.execute("UPDATE planned_workouts SET completion_status='cancelled' WHERE id=?",(cancelled['id'],))
            c.execute("UPDATE planned_workouts SET completion_status='skipped' WHERE id=?",(skipped['id'],))
            report={'changes':[{'workout_id':r['id'],'action':'Rest within cycling budget'} for r in (cancelled,skipped)]}
            c.execute('INSERT INTO training_program_reviews(plan_id,fingerprint,review_json) VALUES(?,?,?)',(self.root,'legacy-cancel',encoded(report)))
            current=[dict(r) for r in c.execute('SELECT * FROM planned_workouts')]
            restore_budget_sessions(c,self.root,current,NOW.date(),TZ)
            self.assertEqual(c.execute('SELECT completion_status FROM planned_workouts WHERE id=?',(cancelled['id'],)).fetchone()[0],'planned')
            self.assertEqual(c.execute('SELECT completion_status FROM planned_workouts WHERE id=?',(skipped['id'],)).fetchone()[0],'skipped')

    def test_confirmed_strength_allowance_survives_sparse_history_and_recovery_week(self):
        from test_long_ride_allocation import preferences
        from app.training_coach import DEFAULT, preview
        answers=preferences();answers['weekly_caps']={'strength':{'range_min_minutes':50,'max_minutes':50}}
        brief={**DEFAULT,'goal':'general','strength_role':'secondary','strength_purpose':'cycling_support',
               'program_start':'2026-10-19','duration_confirmed':True,'calibration':{'power_access':'none','hr_sensor':False}}
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('short-strength','garmin_connect','strength_training','2026-10-18T06:00:00Z',720)")
            result=estimates(c,answers,{**brief,'_planning_day':'2026-11-09'},NOW.date(),TZ)['strength']
        self.assertEqual(result['effective_ceiling_minutes'],50)
        self.assertEqual(result['long_session_minutes'],25)
        result=preview(brief,NOW.date()+timedelta(days=21),TZ,self.path,NOW,candidate_answers=answers)
        self.assertEqual(result['status'],'ready',result.get('questions'))
        strength=[s for s in result['sessions'] if s['sport']=='strength']
        self.assertEqual(len(strength),2,result.get('warnings'))
        self.assertEqual([s['definition']['duration_minutes'] for s in strength],[20,20])

    def test_daily_review_can_reduce_app_managed_published_ride(self):
        from app.training_prescriptions import endurance
        row=self.case.workout
        definition=endurance('vo2',60,{},today=NOW.date())
        definition.update({k:v for k,v in row['definition'].items() if k.startswith('schedule_') or k in ('scheduled_date','time_unspecified')})
        with connect(self.path) as c:c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(definition),row['id']))
        job=send({'workout_ids':[row['id']],'timezone':TZ},self.path,self.factory,NOW);run(job['id'],self.path,self.factory)
        with patch('app.readiness.readiness_history',return_value=readiness(NOW.date(),40)):
            review(self.path,TZ,NOW,trigger='daily')
        after=next(r for r in list_training(self.path)['workouts'] if r['id']==row['id'])
        self.assertEqual(after['definition']['workout_kind'],'endurance')
        self.assertEqual(after['publish_status'],'update_needed')
        self.assertEqual(after['definition']['daily_base_definition']['workout_kind'],'vo2')

    def test_same_day_schedule_edit_republishes_without_repeating_daily_review(self):
        ready_sync(self.path,NOW.date())
        with patch('app.active_training.review') as update, patch('app.readiness.readiness_history',return_value=readiness(NOW.date())):
            self.assertEqual(sync(self.path,self.factory,NOW)['status'],'up_to_date')
            self.assertEqual(sync(self.path,self.factory,NOW)['status'],'up_to_date')
            self.assertEqual(update.call_count,1)
            from app.active_training import swap_workouts
            rows=sorted(list_training(self.path)['workouts'],key=lambda w:w['scheduled_for'])
            a,b=rows[:2]
            swap_workouts(a['id'],b['id'],a['revision'],b['revision'],self.path,NOW,manual_override=True)
            self.assertEqual(sync(self.path,self.factory,NOW)['status'],'up_to_date')
            self.assertEqual(update.call_count,1)
        with connect(self.path) as c:
            for identifier in (a['id'],b['id']):
                row=c.execute('SELECT definition_json FROM planned_workouts WHERE id=?',(identifier,)).fetchone()
                link=c.execute('SELECT * FROM garmin_publication_links WHERE workout_id=?',(identifier,)).fetchone()
                self.assertEqual(link['scheduled_date'],json.loads(row[0])['scheduled_date'])
                self.assertEqual(self.client.calendar[link['remote_schedule_id']]['date'],link['scheduled_date'])
