import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from app.database import connect
from app.training import encoded, list_training, _context
from app.training_accounting import counts_toward_plan, completed_minutes
from app.training_completion import reconcile
from app.session_changes import preview
from test_training_adjustments import NOW, TZ


class WeeklyAccountingTests(unittest.TestCase):
    def setUp(self):
        from test_skill_agent import AgentTests
        self.case=AgentTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.case.replacement_fixture();self.path=self.case.path

    def test_missed_plan_does_not_reserve_load_even_if_published(self):
        row=dict(self.case.rows[0]);row['scheduled_for']='2026-10-18T12:00:00+03:00'
        row['definition']={**row['definition'],'scheduled_date':'2026-10-18'}
        row['publish_status']='published'
        self.assertFalse(counts_toward_plan(row,NOW.date(),TZ))
        row['completion_status']='completed'
        self.assertTrue(counts_toward_plan(row,NOW.date(),TZ))
        row['completion_status']='planned';row['definition']['scheduled_date']='2026-10-19'
        self.assertTrue(counts_toward_plan(row,NOW.date(),TZ))

    def test_confirmed_range_is_shared_with_replacement_not_old_five_percent_cap(self):
        with connect(self.path) as c:
            answers=json.loads(c.execute('SELECT answers_json FROM training_preferences WHERE id=1').fetchone()[0])
            answers['weekly_caps']={'cycling':{'range_min_minutes':300,'max_minutes':330}}
            c.execute('UPDATE training_preferences SET answers_json=? WHERE id=1',(encoded(answers),))
            context=_context(c,NOW,timezone_name=TZ)
        self.assertEqual(context['volume_estimates']['cycling']['effective_ceiling_minutes'],330)
        # Old weekly-dose limit is deliberately incompatible. The real shared
        # estimate must permit the replacement; individual-dose checks remain.
        with patch('app.training_prescriptions.cycling_dose',return_value={'weekly_cap_minutes':20,'minutes':90}):
            result=preview({'workout_id':self.case.rows[1]['id'],'expected_revision':1,
                'action':'replace_with_endurance','minutes':60},self.path,NOW)
        self.assertEqual(result['status'],'proposal',result)

    def test_past_missed_is_hidden_and_late_recording_restores_completion(self):
        identifier=self.case.rows[0]['id']
        with connect(self.path) as c:
            row=dict(c.execute('SELECT * FROM planned_workouts WHERE id=?',(identifier,)).fetchone())
            reconcile(c,[row],TZ,NOW)
        self.assertNotIn(identifier,[w['id'] for w in list_training(self.path)['workouts']])
        with connect(self.path) as c:
            self.assertEqual(c.execute('SELECT completion_status FROM planned_workouts WHERE id=?',(identifier,)).fetchone()[0],'missed')
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('late','garmin_export','cycling','2026-10-18T09:00:00+00:00',3600)")
            row=dict(c.execute('SELECT * FROM planned_workouts WHERE id=?',(identifier,)).fetchone())
            reconcile(c,[row],TZ,NOW)
        self.assertEqual(next(w for w in list_training(self.path)['workouts'] if w['id']==identifier)['completion_status'],'completed')

    def test_partial_sync_counts_actual_rides_once_and_never_counts_missed_plans(self):
        identifier=self.case.rows[0]['id'];week=NOW.date()
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('actual','garmin_export','cycling','2026-10-19T04:00:00+00:00',2700)")
            row=dict(c.execute('SELECT * FROM planned_workouts WHERE id=?',(identifier,)).fetchone())
            self.assertEqual(completed_minutes(c,[row],week,NOW.date(),TZ),45)
            row['completion_status']='completed';row['scheduled_for']='2026-10-19T12:00:00+03:00'
            definition=json.loads(row['definition_json']);definition['scheduled_date']='2026-10-19';row['definition_json']=encoded(definition)
            c.execute("INSERT INTO training_feedback(workout_id,pain_or_illness,activity_id) VALUES(?,0,'actual')",(identifier,))
            self.assertEqual(completed_minutes(c,[row],week,NOW.date(),TZ),45)

    def test_weekly_review_frees_missed_minutes_without_requiring_sync_coverage(self):
        from app.active_training import _cycling_review_targets
        with connect(self.path) as c:
            rows=[dict(r) for r in c.execute("SELECT * FROM planned_workouts WHERE sport='cycling'")]
            past=rows[0];definition=json.loads(past['definition_json']);definition['scheduled_date']='2026-10-18'
            past.update(scheduled_for='2026-10-18T12:00:00+03:00',definition_json=encoded(definition),publish_status='published')
            context=_context(c,NOW,timezone_name=TZ)
        future=[r for r in rows if r['scheduled_for'][:10]>='2026-10-19']
        estimate={'effective_ceiling_minutes':300,'long_session_minutes':90}
        a=_cycling_review_targets(future,context['answers'],estimate,NOW.date(),TZ)[0]
        b=_cycling_review_targets([past,*future],context['answers'],estimate,NOW.date(),TZ)[0]
        self.assertEqual(a,b)

    def test_replacement_uses_program_week_when_it_is_not_monday_to_sunday(self):
        with connect(self.path) as c:
            answers=json.loads(c.execute('SELECT answers_json FROM training_preferences WHERE id=1').fetchone()[0])
            answers['weekly_caps']={'cycling':{'range_min_minutes':300,'max_minutes':330}}
            c.execute('UPDATE training_preferences SET answers_json=? WHERE id=1',(encoded(answers),))
            state=json.loads(c.execute('SELECT state_json FROM active_training_program WHERE id=1').fetchone()[0])
            state['starts_on']='2026-10-13';state['brief']['program_start']='2026-10-13'
            c.execute('UPDATE active_training_program SET state_json=? WHERE id=1',(encoded(state),))
            peer=c.execute("SELECT * FROM planned_workouts WHERE sport='cycling' AND scheduled_for>='2026-10-20' LIMIT 1").fetchone()
            definition=json.loads(peer['definition_json']);definition.update(duration_minutes=300,scheduled_date='2026-10-20')
            c.execute('UPDATE planned_workouts SET scheduled_for=?,definition_json=? WHERE id=?',('2026-10-20T12:00:00+03:00',encoded(definition),peer['id']))
        result=preview({'workout_id':self.case.rows[1]['id'],'expected_revision':1,
            'action':'replace_with_endurance','minutes':30},self.path,NOW)
        self.assertEqual(result['status'],'proposal',result)
