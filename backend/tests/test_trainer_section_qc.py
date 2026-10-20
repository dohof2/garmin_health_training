"""Current trainer contracts; isolated databases, no personal plan mutations."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch
from app.database import migrate
from app.training_coach import DEFAULT, preview, approve
from app.training import list_training
from app.active_training import review, suggest_today, set_status
from app.training_questionnaire import extract_structured, turn

NOW = datetime(2026, 10, 19, 7, tzinfo=timezone.utc)
TZ = 'Asia/Jerusalem'

class TrainerSectionQC(unittest.TestCase):
    def test_three_plans_activate_roll_and_suggest(self):
        for sport,goal in [('cycling','ftp'),('running','endurance'),('strength','general')]:
            with self.subTest(sport=sport), tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'qc.sqlite';migrate(path)
                answers={'sports':[sport],'priority':'strength' if sport=='strength' else 'endurance',
                    'experience':{sport:'new'},'equipment':['bike','bodyweight'],
                    'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False,
                    'week_schedule':[{'weekday':day,'mode':'training' if day in (0,2,4) else 'rest',
                        'total_limit_minutes':None,'activities':[{'slot_id':str(day),'sport':sport,'max_minutes':45,'min_minutes':None}] if day in (0,2,4) else []} for day in range(7)]}
                brief={**DEFAULT,'goal':goal,'goal_sport':'running' if sport=='running' else 'cycling','horizon_weeks':8,'duration_confirmed':True,
                    'program_start':'2026-10-19','strength_role':'primary' if sport=='strength' else None,
                    'strength_purpose':'general_fitness','calibration':{'power_access':'none','hr_sensor':False}}
                proposal=preview(brief,date(2026,10,19),TZ,path,NOW,candidate_answers=answers)
                self.assertEqual(proposal['status'],'ready',proposal['questions'])
                self.assertTrue(proposal['sessions']);self.assertEqual(list_training(path)['plans'],[])
                saved=approve(proposal['brief'],date(2026,10,19),TZ,proposal['fingerprint'],path,NOW,candidate_answers=proposal['candidate_answers'])
                self.assertEqual(saved['plans'][0]['status'],'active')
                result=review(path,TZ,NOW+timedelta(days=8))
                self.assertEqual(result['program']['status'],'active');self.assertTrue(result['workouts'])
                self.assertTrue(all('2026-10-27'<=w['scheduled_for'][:10]<='2026-11-02' for w in result['workouts']))
                before=list_training(path)
                for mode in ('independent','plan'):
                    suggestion=suggest_today({'minutes':30,'sport':sport,'mode':mode,'timezone':TZ},path,NOW+timedelta(days=8))
                    self.assertEqual(suggestion['mode_used'],mode)
                    self.assertIsNotNone(suggestion['session'],suggestion)
                    self.assertLessEqual(suggestion['session']['duration_minutes'],30)
                self.assertEqual(before,list_training(path))
                set_status('paused',path);self.assertEqual(review(path,TZ,NOW+timedelta(days=9))['program']['status'],'paused')
                set_status('active',path);self.assertEqual(review(path,TZ,NOW+timedelta(days=9))['program']['status'],'active')
                from app.active_training import read_active
                root=read_active({},path)['program']['plan_id']
                revised=preview(brief,date(2026,10,26),TZ,path,NOW+timedelta(days=9),replace_plan_id=root)
                self.assertEqual(revised['status'],'ready',revised['questions'])
                approve(revised['brief'],date(2026,10,26),TZ,revised['fingerprint'],path,NOW+timedelta(days=9),replace_plan_id=root)
                self.assertEqual(read_active({},path)['program']['state']['starts_on'],'2026-10-19')
                from app.active_training import read_active, reschedule, save_event
                from app.training_lifecycle import set_program_status, delete_plan
                selected=next(w for w in read_active({},path)['workouts'] if w['scheduled_for'][:10]=='2026-10-28')
                reschedule(selected['id'],None,selected['revision'],path,NOW+timedelta(days=9),scheduled_date='2026-11-04')
                active=read_active({},path)['program']
                save_event({'root_plan_id':active['plan_id'],'expected_revision':active['revision'],'timezone':TZ,'operation':'upsert',
                    'event':{'id':'qc-event','title':'Easy outing','sport':sport,'date':'2026-10-30','duration_minutes':20,'effort':'easy'}},path,NOW+timedelta(days=9))
                active=read_active({},path)['program']
                self.assertTrue(any(event['id']=='qc-event' for event in active['state']['brief']['fixed_events']))
                save_event({'root_plan_id':active['plan_id'],'expected_revision':active['revision'],'timezone':TZ,'operation':'remove','event_id':'qc-event'},path,NOW+timedelta(days=9))
                active=read_active({},path)['program']
                set_program_status(active['plan_id'],active['revision'],'cancelled',path)
                active=read_active({},path)['program']
                delete_plan(active['plan_id'],active['plan_revision'],True,path)
                self.assertIsNone(read_active({},path)['program'])


    def test_friday_long_ride_gets_budget_before_shorter_weekdays(self):
        from app.database import connect
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'qc.sqlite';migrate(path)
            with connect(path) as connection:
                for index in range(8):
                    day=date(2026,10,17)-timedelta(days=(index//2)*7+index%2)
                    connection.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,9000)",(str(index),day.isoformat()+'T07:00:00+00:00'))
            answers={'sports':['cycling','strength'],'priority':'endurance','experience':{'cycling':'experienced','strength':'new'},'equipment':['bike','bodyweight'],'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False,
                'week_schedule':[{'weekday':day,'mode':'rest' if day==5 else 'training','total_limit_minutes':None,'activities':[] if day==5 else [{'slot_id':str(day),'sport':'strength' if day in (1,3) else 'cycling','max_minutes':30 if day in (1,3) else 300 if day==4 else 90}]} for day in range(7)]}
            brief={**DEFAULT,'goal':'ftp','duration_confirmed':True,'program_start':'2026-10-19','strength_role':'secondary','strength_purpose':'cycling_support'}
            proposal=preview(brief,date(2026,10,19),TZ,path,NOW,candidate_answers=answers)
            self.assertEqual(proposal['status'],'ready',proposal['questions'])
            rides=[row for row in proposal['sessions'] if row['sport']=='cycling']
            friday=next(row for row in rides if row['scheduled_for'][:10]=='2026-10-23')
            self.assertEqual(friday['definition']['duration_minutes'],120)
            self.assertEqual(friday['definition']['workout_kind'],'long_endurance')
            import copy
            cycling_only=copy.deepcopy(answers);cycling_only['sports']=['cycling']
            for day in cycling_only['week_schedule']:
                if day['weekday'] in (1,3):day.update(mode='rest',activities=[])
            solo=preview(brief,date(2026,10,19),TZ,path,NOW,candidate_answers=cycling_only)
            self.assertEqual(proposal['volume_estimates']['cycling']['effective_ceiling_minutes'],solo['volume_estimates']['cycling']['effective_ceiling_minutes'])
            self.assertEqual(proposal['weekly_minutes']['cycling'],solo['weekly_minutes']['cycling'])
            self.assertEqual(proposal['weekly_minutes']['strength'],60)
            self.assertTrue(all(row['definition']['duration_minutes']<120 for row in rides if row is not friday))
            self.assertLessEqual(sum(row['definition']['duration_minutes'] for row in rides),proposal['volume_estimates']['cycling']['effective_ceiling_minutes'])
            for offset,kind in [(0,'threshold'),(1,'tempo'),(2,'vo2'),(3,None),(4,'short_efforts')]:
                later=preview(brief,date(2026,10,19)+timedelta(weeks=offset),TZ,path,NOW,candidate_answers=answers)
                quality=[row for row in later['sessions'] if row['definition'].get('workout_kind') in ('threshold','tempo','vo2','short_efforts')]
                self.assertEqual([row['definition']['workout_kind'] for row in quality],[] if kind is None else [kind])
                if kind is None:self.assertTrue(all(row['definition']['duration_minutes']<=30 for row in later['sessions'] if row['sport']=='cycling'))
            approve(proposal['brief'],date(2026,10,19),TZ,proposal['fingerprint'],path,NOW,candidate_answers=answers)
            active=review(path,TZ,NOW)
            friday=next(row for row in active['workouts'] if row['scheduled_for'][:10]=='2026-10-23')
            self.assertEqual(friday['definition']['duration_minutes'],120)
            self.assertEqual(len([row for row in active['workouts'] if row['sport']=='strength']),2)

    def test_regular_rides_have_purposeful_hour_allocations_not_leftovers(self):
        from app.training_coach import _cycling_allocations
        result=_cycling_allocations({'mon':90,'wed':90,'fri':123,'sun':90},264,'fri')
        self.assertEqual(result,{'mon':60,'wed':60,'fri':84,'sun':60})
        low=_cycling_allocations({'mon':90,'wed':90,'fri':123,'sun':90},170,'fri')
        self.assertTrue(all(minutes>=60 for minutes in low.values()))
        self.assertLessEqual(sum(low.values()),170)

    def test_cycling_growth_is_capped_at_twenty_percent_with_recovery_hold(self):
        from app.training_volume import cycling_increment
        baseline=264
        self.assertAlmostEqual(cycling_increment(baseline,4,2,False,'normal',False),52.8)
        for overrides in ({'recovery_week':True},{'tolerated_sessions':0},{'adverse':True},{'load_status':'elevated'},{'load_status':'missing'},{'rising':True},{'observed_weeks':1}):
            arguments={'baseline':baseline,'observed_weeks':4,'tolerated_sessions':2,'adverse':False,'load_status':'normal','rising':False,**overrides}
            self.assertEqual(cycling_increment(**arguments),0)

    def test_weekly_budget_averages_all_four_completed_weeks(self):
        from app.training_volume import weekly_reference
        from app.training_prescriptions import cycling_dose
        today=date(2026,10,18)
        records=[{'date':day,'minutes':minutes} for day,minutes in [('2026-10-14',181.3),('2026-10-07',395.9),('2026-09-30',186),('2026-09-23',293.1),('2026-10-18',999)]]
        coverage={'coverage_start':'2026-09-01','coverage_end':'2026-10-18'}
        result=weekly_reference(records,today,coverage,180)
        self.assertEqual(result['weeks_used'],4)
        self.assertAlmostEqual(result['baseline_minutes'],264.075)
        dose=cycling_dose(300,{'sports':[{'sport':'cycling','recent_durations':records}],'activity_coverage':coverage},[],today)
        self.assertEqual(dose['weekly_cap_minutes'],264)
        self.assertEqual(dose['weekly_reference'],result)

    def test_unknown_weeks_are_not_zero_but_covered_rest_weeks_count(self):
        from app.training_volume import weekly_reference
        today=date(2026,10,18)
        records=[{'date':'2026-10-14','minutes':180},{'date':'2026-10-07','minutes':300}]
        partial=weekly_reference(records,today,{},180)
        self.assertEqual(partial['baseline_minutes'],240)
        self.assertEqual(partial['weeks_used'],2)
        complete=weekly_reference(records,today,{'coverage_start':'2026-09-01','coverage_end':'2026-10-18'},180)
        self.assertEqual(complete['baseline_minutes'],120)
        self.assertEqual(complete['weeks_used'],4)

    def test_mixed_plan_keeps_two_beginner_strength_days(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'qc.sqlite';migrate(path)
            answers={'sports':['cycling','strength'],'priority':'endurance','experience':{'cycling':'experienced','strength':'new'},'equipment':['bike','bodyweight'],'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False,
                'week_schedule':[{'weekday':day,'mode':'rest' if day==5 else 'training','total_limit_minutes':None,'activities':[] if day==5 else [{'slot_id':str(day),'sport':'strength' if day in (1,3) else 'cycling','max_minutes':30 if day in (1,3) else 90}]} for day in range(7)]}
            brief={**DEFAULT,'goal':'ftp','duration_confirmed':True,'program_start':'2026-10-19','strength_role':'secondary','strength_purpose':'cycling_support'}
            proposal=preview(brief,date(2026,10,19),TZ,path,NOW,candidate_answers=answers)
            self.assertEqual(proposal['status'],'ready',proposal['questions'])
            self.assertEqual([(row['scheduled_for'][:10],row['definition']['duration_minutes']) for row in proposal['sessions'] if row['sport']=='strength'],[('2026-10-20',30),('2026-10-22',30)])

    def test_selected_sport_is_never_silently_dropped(self):
        from app.training import _context
        from app.database import connect
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'qc.sqlite';migrate(path)
            answers={'sports':['cycling','strength'],'week_schedule':[{'weekday':day,'mode':'training' if day==0 else 'rest','total_limit_minutes':None,'activities':[{'slot_id':'ride','sport':'cycling','max_minutes':60}] if day==0 else []} for day in range(7)]}
            with connect(path) as connection:context=_context(connection,NOW,answers)
            self.assertIn('strength',context['answers']['sports'])
            self.assertTrue(any('strength' in message and 'no training slots' in message for message in context['blockers']))

    def test_semantic_extraction_is_bounded_and_optional(self):
        with patch('app.ai_providers.active_provider') as provider:
            provider.return_value.generate.side_effect=TimeoutError()
            self.assertEqual(extract_structured('about five'),[])
            self.assertEqual(provider.return_value.generate.call_args.kwargs['timeout_seconds'],15)

    def test_reported_strength_reply_retains_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'qc.sqlite';migrate(path)
            result=turn('For strength 30 minutes. Pull ups I do 5. Dips I do 5. I am a beginner in strength.',[],TZ,path,NOW)
            self.assertEqual(result['brief']['strength_capacity'],{'pull_up_reps':5,'dip_reps':5})
            self.assertEqual(result['candidate_answers']['experience']['strength'],'new')
