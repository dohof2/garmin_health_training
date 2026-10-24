"""Regression coverage for persisted short Fridays and publication-safe review."""
import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.active_training import _cycling_review_targets, _program_workouts, review
from app.database import connect, migrate
from app.training import encoded, _revision, _snapshot
from app.training_coach import DEFAULT, approve, preview

START = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 7, tzinfo=timezone.utc)
TZ = 'Asia/Jerusalem'


def preferences():
    return {'sports':['cycling','strength'],'priority':'endurance',
        'experience':{'cycling':'experienced','strength':'new'},'equipment':['bike','bodyweight'],
        'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False,
        'week_schedule':[{'weekday':day,'mode':'rest' if day==5 else 'training',
            'total_limit_minutes':None,'activities':[] if day==5 else [{
                'slot_id':str(day),'sport':'strength' if day in (1,3) else 'cycling',
                'max_minutes':30 if day in (1,3) else 300 if day==4 else 90}]} for day in range(7)]}


def rows():
    return [{'id':str(day),'scheduled_for':f'2026-10-{19+day:02d}T12:00:00+03:00',
        'completion_status':'planned','publish_status':'published' if day==2 else 'local',
        'garmin_workout_id':'remote-test' if day==2 else None,
        'definition_json':encoded({'duration_minutes':minutes,'workout_kind':'endurance',
            'planning_policy_version':'cycling-dose-v1'})}
        for day,minutes in [(0,60),(2,60),(4,54),(6,48)]]


class LongRideTargets(unittest.TestCase):
    def setUp(self):
        self.answers=preferences();self.answers['weekly_minutes']={'cycling':264,'strength':60}
        self.estimate={'effective_ceiling_minutes':264,'long_session_minutes':132}

    def targets(self,workouts=None,other_rows=()):
        return _cycling_review_targets(workouts or rows(),self.answers,self.estimate,date(2026,10,22),TZ,other_rows)

    def test_restore_friday_and_hour_weekday_reserving_past_published_ride(self):
        targets,long_id,slots=self.targets()
        self.assertEqual(targets,{'4':84,'6':60})
        self.assertEqual(long_id,'4')
        self.assertEqual(slots['4']['slot_id'],'4')
        self.assertEqual(120+sum(targets.values()),264)

    def test_future_published_ride_is_also_reserved(self):
        workouts=rows();workouts[-1]['publish_status']='published';workouts[-1]['garmin_workout_id']='remote-sunday'
        targets,_,_=self.targets(workouts)
        self.assertEqual(targets,{'4':96})  # 264 - 60 - 60 - 48

    def test_manual_duration_is_not_expanded(self):
        workouts=rows();definition=json.loads(workouts[2]['definition_json'])
        definition.update(duration_minutes=40,user_adjusted=True)
        workouts[2]['definition_json']=encoded(definition)
        targets,_,_=self.targets(workouts)
        self.assertNotIn('4',targets)
        self.assertEqual(targets['6'],60)

    def test_recovery_week_does_not_restore_long_dose(self):
        self.estimate['progression']={'recovery_week':True}
        targets,_,_=self.targets()
        self.assertTrue(all(minutes<=30 for minutes in targets.values()))

    def test_insufficient_budget_omits_filler_instead_of_shortening_long_day(self):
        self.estimate['effective_ceiling_minutes']=222
        targets,_,_=self.targets()
        self.assertEqual(targets,{'4':102,'6':0})

    def test_exact_hour_budget_does_not_turn_every_ride_into_the_same_length(self):
        self.estimate['effective_ceiling_minutes']=240
        targets,_,_=self.targets()
        self.assertGreater(targets['4'],60)
        self.assertLessEqual(120+sum(targets.values()),240)

    def test_shared_day_limit_reserves_strength_without_using_cycling_week_budget(self):
        self.answers['week_schedule'][4]['total_limit_minutes']=100
        strength={'completion_status':'planned','scheduled_for':'2026-10-23T12:00:00+03:00',
            'definition_json':encoded({'duration_minutes':30})}
        targets,_,_=self.targets(other_rows=[strength])
        self.assertEqual(targets['4'],70)
        self.assertEqual(targets['6'],60)

    def test_multiple_cycling_slots_share_one_daily_limit(self):
        self.answers['week_schedule'][4]['total_limit_minutes']=90
        self.answers['week_schedule'][4]['activities'].append({'slot_id':'extra','sport':'cycling','max_minutes':90})
        workouts=rows();definition=json.loads(workouts[2]['definition_json']);definition['schedule_slot_id']='4'
        workouts[2]['definition_json']=encoded(definition)
        extra=copy.deepcopy(workouts[2]);extra['id']='extra'
        definition['schedule_slot_id']='extra';extra['definition_json']=encoded(definition)
        workouts.append(extra)
        targets,_,_=self.targets(workouts)
        self.assertLessEqual(targets['4']+targets['extra'],90)
        self.assertGreater(targets['4'],60)


class PersistedLongRideReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        with connect(self.path) as connection:
            # Four 264-minute completed weeks; repeatable 132-minute long rides.
            for index in range(8):
                day=START-timedelta(days=1+(index//2)*7+index%2)
                connection.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,7920)",
                    (str(index),day.isoformat()+'T07:00:00+00:00'))
        brief={**copy.deepcopy(DEFAULT),'goal':'ftp','duration_confirmed':True,'program_start':START.isoformat(),
            'strength_role':'secondary','strength_purpose':'cycling_support'}
        proposal=preview(brief,START,TZ,self.path,NOW,candidate_answers=preferences())
        self.assertEqual(proposal['status'],'ready',proposal['questions'])
        approve(proposal['brief'],START,TZ,proposal['fingerprint'],self.path,NOW,candidate_answers=preferences())
        with connect(self.path) as connection:
            self.root=connection.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
            for row in _program_workouts(connection,self.root):
                day=datetime.fromisoformat(row['scheduled_for']).weekday()
                definition=json.loads(row['definition_json'])
                if row['sport']=='cycling' and day in (4,6):
                    from app.training_prescriptions import endurance
                    definition=endurance('endurance',54 if day==4 else 48,brief,today=START)
                    definition['planning_policy_version']='cycling-dose-v1'
                    connection.execute('UPDATE planned_workouts SET definition_json=?,revision=revision+1 WHERE id=?',(encoded(definition),row['id']))
                    _revision(connection,_snapshot(connection,row['id']))
                if row['sport']=='cycling' and day==2:
                    self.published_id=row['id']
                    connection.execute("UPDATE planned_workouts SET publish_status='published',garmin_workout_id='remote-test' WHERE id=?",(row['id'],))
            self.published=_snapshot(connection,self.published_id)

    def tearDown(self):
        self.tmp.cleanup()

    def run_review(self,level='normal'):
        policy={'level':level,'quality_allowed':level=='normal','reasons':[] if level=='normal' else ['Recovery concern'],
            'readiness_missing':False}
        with patch('app.readiness.readiness_history',return_value={'latest':{'date':'2026-10-22','score':80,'status':'complete','groups':[]}}), \
             patch('app.training_prescriptions.recovery_policy',return_value=policy):
            return review(self.path,TZ,NOW+timedelta(days=3))

    def test_review_repairs_saved_week_and_is_stable_on_refresh(self):
        result=self.run_review()
        friday=next(row for row in result['workouts'] if row['scheduled_for'][:10]=='2026-10-23')
        sunday=next(row for row in result['workouts'] if row['scheduled_for'][:10]=='2026-10-25')
        self.assertEqual(friday['definition']['duration_minutes'],84)
        self.assertEqual(friday['definition']['workout_kind'],'long_endurance')
        self.assertEqual(sunday['definition']['duration_minutes'],60)
        self.assertEqual(friday['definition']['duration_guidance']['weekly_reference']['as_of'],'2026-10-19')
        self.assertEqual(sum(step['duration_seconds']*step.get('repetitions',1) for step in friday['definition']['steps']),84*60)
        with connect(self.path) as connection:
            self.assertEqual(_snapshot(connection,self.published_id),self.published)
            rides=[row for row in _program_workouts(connection,self.root) if row['sport']=='cycling' and row['scheduled_for'][:10]<'2026-10-26' and row['completion_status']=='planned']
            self.assertEqual(sum(json.loads(row['definition_json'])['duration_minutes'] for row in rides),264)
        again=self.run_review()
        self.assertEqual([(row['id'],row['revision']) for row in result['workouts']],[(row['id'],row['revision']) for row in again['workouts']])

    def test_current_recovery_limit_overrides_allocation_and_explains_why(self):
        result=self.run_review('easy')
        friday=next(row for row in result['workouts'] if row['scheduled_for'][:10]=='2026-10-23')
        self.assertEqual(friday['definition']['duration_minutes'],60)
        guidance=friday['definition']['duration_guidance']
        self.assertEqual(guidance['allocated_minutes'],84)
        self.assertEqual(guidance['recovery_adjustment']['reasons'],['Recovery concern'])

    def test_weekly_reference_is_stable_within_program_week(self):
        from app.training import training_context
        first=training_context(self.path,NOW)['volume_estimates']['cycling']['weekly_reference']
        later=training_context(self.path,NOW+timedelta(days=3))['volume_estimates']['cycling']['weekly_reference']
        self.assertEqual(first,later)

    def test_reference_rolls_forward_at_next_program_week(self):
        from app.training import training_context
        first=training_context(self.path,NOW)['volume_estimates']['cycling']['weekly_reference']
        later=training_context(self.path,NOW+timedelta(days=7))['volume_estimates']['cycling']['weekly_reference']
        self.assertEqual(first['as_of'],'2026-10-19')
        self.assertEqual(later['as_of'],'2026-10-26')
        self.assertNotEqual(first['weeks'],later['weeks'])


if __name__=='__main__':unittest.main()
