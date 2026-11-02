import unittest
from datetime import timedelta

from app.readiness import DEFAULTS, calculate
from app.readiness_forecast import project
from test_readiness import DAY, NOW, COVERAGE, observations, activity


class RecentActivityReadinessTests(unittest.TestCase):
    def ride(self, hours_ago=1, recovery_hours=34):
        end = NOW - timedelta(hours=hours_ago)
        return activity(start=(end-timedelta(hours=1)).isoformat(), end=end.isoformat(),
                        load=(recovery_hours/2)**2)

    def result(self, rides, rows=None, **kwargs):
        return calculate(DAY, 'UTC', observations() if rows is None else rows,
                         rides, COVERAGE, DEFAULTS, now=NOW, **kwargs)

    def recovery(self, result):
        return next(g for g in result['groups'] if g['name'] == 'recovery')

    def snapshot(self, hours=34, hours_ago=0):
        return {'id':'recovery', 'source_name':'garmin_connect', 'metric_type':'recovery_time',
                'recorded_at':(NOW-timedelta(hours=hours_ago)).isoformat(), 'value':hours*60, 'unit':'min'}

    def test_heavy_penalty_applies_once_and_uses_assigned_not_remaining_hours(self):
        rows=[r for r in observations() if r['metric_type']!='sleep_duration']
        result = self.result([self.ride(20), self.ride(21)],rows)
        group = self.recovery(result)
        self.assertTrue(group['recent_heavy_penalty'])
        self.assertEqual(group['activity_deduction'], 35)
        self.assertEqual(next(g for g in result['groups'] if g['name']=='post_activity')['penalty_max'],35)
        self.assertEqual(len(group['qualifying_activity_ids']), 2)
        self.assertLess(result['inputs']['recovery']['session_remaining_hours'], 24)

    def test_post_activity_deduction_is_added_to_regular_recovery(self):
        rows=[r for r in observations() if r['metric_type']!='sleep_duration']
        ride=self.ride(4,34)
        actual=self.result([ride],rows)
        ordinary=calculate(DAY,'UTC',rows,[ride],COVERAGE,DEFAULTS,now=NOW,apply_recent_activity_penalty=False)
        recovery=self.recovery(actual);base=self.recovery(ordinary)
        self.assertEqual(recovery['penalty_min'],base['penalty_min'])
        extra=next(group for group in actual['groups'] if group['name']=='post_activity')
        self.assertEqual(extra['penalty_min'],35);self.assertEqual(extra['penalty_max'],35)
        self.assertGreater(recovery['penalty_min'],0)
        self.assertAlmostEqual(sum(g['penalty_min'] for g in actual['groups'])-sum(g['penalty_min'] for g in ordinary['groups']),35)
        self.assertFalse(any(group['name']=='post_activity' for group in ordinary['groups']))

    def test_threshold_latches_without_age_expiry_until_sleep(self):
        for hours_ago, recovery_hours, expected in [(1,24,False),(1,24.1,True),(24.1,34,True),(100,34,True),(-1,34,False)]:
            with self.subTest(hours_ago=hours_ago, recovery_hours=recovery_hours):
                # Remove sleep to isolate the rolling window across midnight.
                rows=[r for r in observations() if r['metric_type']!='sleep_duration']
                result=self.result([self.ride(hours_ago,recovery_hours)],rows)
                self.assertEqual(self.recovery(result)['recent_heavy_penalty'],expected)

    def test_27_hour_assignment_stays_deducted_four_hours_later(self):
        rows=[r for r in observations() if r['metric_type']!='sleep_duration']
        group=self.recovery(self.result([self.ride(4,27)],rows))
        self.assertTrue(group['recent_heavy_penalty']);self.assertEqual(group['activity_deduction'],35)

    def test_assigned_recovery_tiers_and_boundaries(self):
        rows=[r for r in observations() if r['metric_type']!='sleep_duration']
        for hours,expected in [(24.1,35),(36,35),(36.1,45),(48,45),(48.1,60),(60,60)]:
            with self.subTest(hours=hours):
                group=self.recovery(self.result([self.ride(4,hours)],rows))
                self.assertEqual(group['activity_deduction'],expected)
                self.assertEqual(group['activity_deduction'],expected)
                self.assertEqual(group['normal_budget'],25)

    def test_highest_tier_applies_once_and_countdown_does_not_lower_it(self):
        rows=[r for r in observations() if r['metric_type']!='sleep_duration']
        group=self.recovery(self.result([self.ride(20,50),self.ride(21,34)],rows))
        self.assertEqual(group['activity_deduction'],60)
        self.assertEqual(group['assigned_recovery_hours'],50)

    def test_new_activity_recalculates_after_morning(self):
        rows=[r for r in observations() if r['metric_type']!='sleep_duration']
        morning=NOW.replace(hour=8,minute=0);end=morning+timedelta(hours=3)
        ride=activity(start=(end-timedelta(hours=1)).isoformat(),end=end.isoformat(),load=(27/2)**2)
        before=calculate(DAY,'UTC',rows,[ride],COVERAGE,DEFAULTS,now=morning)
        after=calculate(DAY,'UTC',rows,[ride],COVERAGE,DEFAULTS,now=end+timedelta(minutes=1))
        self.assertFalse(self.recovery(before)['recent_heavy_penalty']);self.assertTrue(self.recovery(after)['recent_heavy_penalty'])

    def test_replaced_garmin_snapshot_retains_qualification_but_not_live_timer(self):
        import tempfile
        from pathlib import Path
        from app.database import connect,migrate
        from app.readiness import _load
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite';migrate(path)
            with connect(path) as c:
                c.execute("INSERT INTO metric_readings(id,source_name,source_record_id,metric_type,recorded_at,value,unit) VALUES('snapshot','garmin_connect','recovery','recovery_time',?,1620,'min')",((NOW-timedelta(hours=4)).isoformat(),))
                c.execute("UPDATE metric_readings SET recorded_at=?,value=1380 WHERE id='snapshot'",(NOW.isoformat(),))
                rows,_,coverage=_load(c,DAY-timedelta(days=7),DAY)
            self.assertEqual([r['value'] for r in rows if r['metric_type']=='recovery_time'],[1380])
            self.assertEqual(coverage['high_recovery_observations'][0]['value'],1620)
            rows=[r for r in observations() if r['metric_type']!='sleep_duration']+rows
            result=calculate(DAY,'UTC',rows,[self.ride(5,20)],coverage,DEFAULTS,now=NOW)
            self.assertTrue(self.recovery(result)['recent_heavy_penalty'])
            rows.append({'id':'nap','metric_type':'sleep_duration','unit':'s','value':3600,'source_name':'garmin_connect','recorded_at':DAY.isoformat(),'period_start':(NOW-timedelta(hours=2)).isoformat(),'period_end':(NOW-timedelta(hours=1)).isoformat()})
            self.assertFalse(self.recovery(calculate(DAY,'UTC',rows,[self.ride(5,20)],coverage,DEFAULTS,now=NOW))['recent_heavy_penalty'])

    def test_completed_sleep_after_workout_removes_extra_penalty(self):
        rows=observations()+[{'id':'nap','source_name':'garmin_connect','metric_type':'sleep_duration',
                'recorded_at':DAY.isoformat(),'value':3600,'unit':'s',
                'period_start':(NOW-timedelta(hours=3)).isoformat(),
                'period_end':(NOW-timedelta(hours=2)).isoformat()}]
        result=self.result([self.ride(4)],rows)
        self.assertFalse(self.recovery(result)['recent_heavy_penalty'])
        self.assertGreater(self.recovery(result)['penalty_min'],0)

    def test_sleep_before_workout_or_unfinished_sleep_does_not_clear_penalty(self):
        self.assertTrue(self.recovery(self.result([self.ride()]))['recent_heavy_penalty'])
        rows=observations()+[{'id':'unfinished','source_name':'garmin_connect','metric_type':'sleep_duration',
                'recorded_at':DAY.isoformat(),'value':3600,'unit':'s',
                'period_start':(NOW-timedelta(minutes=30)).isoformat(),
                'period_end':(NOW+timedelta(hours=1)).isoformat()}]
        self.assertTrue(self.recovery(self.result([self.ride()],rows))['recent_heavy_penalty'])

    def test_garmin_snapshot_must_follow_workout_and_not_be_in_future(self):
        for hours_ago, expected in [(0,True),(2,False),(-1,False)]:
            with self.subTest(hours_ago=hours_ago):
                result=self.result([self.ride(recovery_hours=20)],observations()+[self.snapshot(hours_ago=hours_ago)])
                self.assertEqual(self.recovery(result)['recent_heavy_penalty'],expected)

    def test_known_penalty_applies_even_with_incomplete_history(self):
        result=calculate(DAY,'UTC',observations(),[self.ride()],{},DEFAULTS,now=NOW)
        self.assertEqual(self.recovery(result)['activity_deduction'],35)
        self.assertEqual(next(g for g in result['groups'] if g['name']=='post_activity')['penalty_min'],35)

    def test_forecast_explicitly_excludes_extra_penalty_even_without_sleep_after_ride(self):
        # Finishes after tomorrow's projected bedtime, so projected sleep cannot
        # independently clear the rule. Forecast must explicitly disable it.
        late=NOW.replace(hour=23)
        end=late-timedelta(minutes=30)
        ride=activity(start=(end-timedelta(hours=1)).isoformat(),end=end.isoformat(),load=289)
        today=calculate(DAY,'UTC',observations(),[ride],COVERAGE,DEFAULTS,now=late)
        self.assertTrue(self.recovery(today)['recent_heavy_penalty'])
        future,_,_=project(late,'UTC',observations(),[ride],COVERAGE,DEFAULTS)
        self.assertIsNotNone(future)
        self.assertFalse(self.recovery(future)['recent_heavy_penalty'])
        self.assertNotIn('recent_high_recovery_activity_without_sleep',future['warnings'])
        self.assertGreater(self.recovery(future)['penalty_min'],0)
        self.assertLess(self.recovery(future)['penalty_min'],25)
