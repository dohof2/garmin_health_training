import copy
import unittest
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.readiness import DEFAULTS, _series, _sessions, calculate
from app.recovery_estimate import advance_load, estimate, session_recovery, settling_hours
from app.readiness_forecast import project
from test_readiness import DAY, NOW, COVERAGE, observations, activity


class ReadinessV5Tests(unittest.TestCase):
    def test_fit_start_timestamp_does_not_start_recovery_early(self):
        import json
        row=activity(start='2026-10-23T04:00:00Z',end=None)
        row['raw_json']=json.dumps({'fit_sessions':[{'timestamp':row['started_at'],
            'start_time':row['started_at'],'total_elapsed_time':5400,'total_timer_time':4800}]})
        session=_sessions([row])[0]
        self.assertEqual(session['end'].isoformat(),'2026-10-23T05:30:00+00:00')
        self.assertEqual(session['end_method'],'fit_session_end')

    def test_missing_context_only_rhr_does_not_block_forecast(self):
        rows=[row for row in observations() if row['metric_type']!='resting_heart_rate']
        result,inputs,missing=project(NOW,'UTC',rows,[],COVERAGE,DEFAULTS)
        self.assertIsNotNone(result)
        self.assertEqual(result['score'],100)
        self.assertIn('resting_heart_rate',missing)

    def test_recovery_elapsed_time_is_correct_through_dst(self):
        from datetime import datetime
        row=activity(start='2026-10-24T21:30:00+00:00',end='2026-10-25T01:30:00+03:00')
        row['raw_json']='{"summaryDTO":{"trainingEffect":4.5}}'
        now=datetime.fromisoformat('2026-10-25T01:30:00+02:00')
        result=session_recovery(_sessions([row])[0],now,{},DEFAULTS)
        self.assertEqual(result['remaining_hours'],47)

    def test_six_budgets_and_rhr_context_only(self):
        rows = observations()
        baseline = calculate(DAY,'UTC',rows,[],COVERAGE,DEFAULTS,now=NOW)
        changed = copy.deepcopy(rows)
        for row in changed:
            if row['metric_type']=='resting_heart_rate' and row['recorded_at']==DAY.isoformat():
                row['value']=150
        result = calculate(DAY,'UTC',changed,[],COVERAGE,DEFAULTS,now=NOW)
        self.assertEqual(result['score'],baseline['score'])
        self.assertEqual(sum(g['budget'] for g in result['groups']),100)
        self.assertEqual(len(result['groups']),6)

    def test_forecast_correction_features_cannot_reintroduce_rhr_penalty(self):
        from app.readiness_forecast import features
        rows=observations()
        result,inputs,_=project(NOW,'UTC',rows,[],COVERAGE,DEFAULTS)
        original=features(result,inputs)
        changed=copy.deepcopy(inputs)
        for row in changed:
            if row['metric']=='resting_heart_rate':row.update(predicted_value=150,recent_change=100)
        self.assertEqual(original,features(result,changed))

    def test_stress_and_sleep_history_independently_affect_score(self):
        rows=observations()
        for row in rows:
            if row['metric_type']=='average_stress' and row['recorded_at']<DAY.isoformat():row['value']=90
        result=calculate(DAY,'UTC',rows,[],COVERAGE,DEFAULTS,now=NOW)
        self.assertEqual(result['score'],85)
        self.assertEqual(next(g for g in result['groups'] if g['name']=='sleep')['penalty_min'],0)
        for row in rows:
            if row['metric_type']=='sleep_duration' and row['recorded_at']==(DAY-timedelta(days=1)).isoformat():row['value']=18000
        changed=calculate(DAY,'UTC',rows,[],COVERAGE,DEFAULTS,now=NOW)
        self.assertLess(changed['score'],result['score'])

    def test_48_hour_countdown_good_sleep_and_no_replay_compounding(self):
        end=NOW.replace(hour=6)-timedelta(days=1)
        row=activity(start=(end-timedelta(hours=1)).isoformat(),end=end.isoformat())
        row['raw_json']='{"summaryDTO":{"trainingEffect":4.5}}'
        session=_sessions([row])[0]
        rows=observations()
        for r in rows:
            if r['metric_type']=='sleep_score':r['value']=80
        series=_series(rows,ZoneInfo('UTC'))
        wake=NOW.replace(hour=6)
        self.assertEqual(session_recovery(session,wake,series,DEFAULTS)['remaining_hours'],24)
        for r in rows:
            if r['metric_type']=='sleep_score' and r['recorded_at']==DAY.isoformat():r['value']=100
        series=_series(rows,ZoneInfo('UTC'))
        first=session_recovery(session,wake,series,DEFAULTS)
        self.assertEqual(first['remaining_hours'],22)
        self.assertEqual(first,session_recovery(session,wake,series,DEFAULTS))
        self.assertEqual(session_recovery(session,wake+timedelta(hours=4),series,DEFAULTS)['remaining_hours'],18)
        self.assertEqual(session_recovery(session,wake+timedelta(hours=48),series,DEFAULTS)['remaining_hours'],0)

    def test_poor_sleep_extends_and_sleep_before_activity_does_not_apply(self):
        rows=observations()
        for r in rows:
            if r['metric_type']=='sleep_score' and r['recorded_at']==DAY.isoformat():r['value']=20
        series=_series(rows,ZoneInfo('UTC'))
        end=NOW.replace(hour=6)-timedelta(days=1)
        row=activity(end=end.isoformat(),start=(end-timedelta(hours=1)).isoformat())
        row['raw_json']='{"summaryDTO":{"trainingEffect":4.5}}'
        result=session_recovery(_sessions([row])[0],NOW.replace(hour=6),series,DEFAULTS)
        self.assertEqual(result['remaining_hours'],26)
        row.update(start=NOW.replace(hour=8).isoformat(),ended_at=NOW.replace(hour=9).isoformat())
        row['started_at']=row.pop('start')
        fresh=session_recovery(_sessions([row])[0],NOW,series,DEFAULTS)
        self.assertEqual(fresh['sleep_adjustments'],[])

    def test_ratio_evolves_both_loads_and_reaches_soft_threshold(self):
        hours=settling_hours(200,100)
        self.assertGreater(hours,0)
        acute,chronic=advance_load(200,100,hours)
        self.assertNotEqual(chronic,100)
        self.assertAlmostEqual(acute/chronic,1.3,places=7)
        self.assertEqual(settling_hours(100,100),0)
        self.assertIsNone(settling_hours(100,0))

    def test_hard_session_remains_when_recorded_ratio_is_low(self):
        end=NOW-timedelta(hours=1)
        row=activity(start=(end-timedelta(hours=1)).isoformat(),end=end.isoformat(),load=100)
        row['raw_json']='{"summaryDTO":{"trainingEffect":4.5}}'
        coverage={**COVERAGE,'load_history':[{'acute':100,'chronic':200,'observed_at':NOW.isoformat()}]}
        result=estimate(NOW,ZoneInfo('UTC'),_sessions([row]),_series(observations(),ZoneInfo('UTC')),coverage,DEFAULTS)
        self.assertLess(result['ratio'],1.3)
        self.assertEqual(result['load_settling_hours'],0)
        self.assertEqual(result['remaining_hours'],47)

    def test_measured_snapshot_is_not_sleep_adjusted_again(self):
        rows=observations()+[{'id':'recovery','source_name':'garmin_connect','metric_type':'recovery_time',
             'value':120,'unit':'min','recorded_at':(NOW-timedelta(hours=1)).isoformat()}]
        result=estimate(NOW,ZoneInfo('UTC'),[],_series(rows,ZoneInfo('UTC')),COVERAGE,DEFAULTS)
        self.assertEqual(result['session_remaining_hours'],1)
        self.assertIsNotNone(result['garmin_observation'])

    def test_forecast_bad_week_uses_longer_reference_and_latest_improvement(self):
        rows=observations()
        for row in rows:
            if (DAY-timedelta(days=6)).isoformat()<=row['recorded_at']<DAY.isoformat():
                if row['metric_type']=='sleep_duration':row['value']=18000
                if row['metric_type']=='sleep_score':row['value']=40
                if row['metric_type']=='hrv_last_night_average':row['value']=30
        result,inputs,missing=project(NOW,'UTC',rows,[],COVERAGE,DEFAULTS)
        self.assertFalse(missing)
        by_kind={r['metric']:r for r in inputs}
        self.assertGreater(by_kind['sleep_duration']['predicted_value'],18000)
        self.assertGreater(by_kind['hrv_last_night_average']['predicted_value'],30)
        self.assertEqual(by_kind['hrv_last_night_average']['observations'],28)
        self.assertEqual(result['formula_version'],'readiness-v5')

    def test_future_recovery_snapshot_cannot_leak(self):
        rows=observations()
        original=project(NOW,'UTC',rows,[],COVERAGE,DEFAULTS)
        rows.append({'id':'future_recovery','source_name':'garmin_connect','metric_type':'recovery_time',
                     'recorded_at':(NOW+timedelta(hours=1)).isoformat(),'value':9999,'unit':'min'})
        self.assertEqual(original,project(NOW,'UTC',rows,[],COVERAGE,DEFAULTS))

    def test_current_timer_uses_actual_time_even_before_morning_measurements(self):
        early=NOW.replace(hour=5)
        end=early-timedelta(hours=12)
        row=activity(start=(end-timedelta(hours=1)).isoformat(),end=end.isoformat())
        row['raw_json']='{"summaryDTO":{"trainingEffect":4.5}}'
        result=calculate(DAY,'UTC',observations(),[row],COVERAGE,DEFAULTS,now=early)
        self.assertEqual(result['status'],'awaiting_morning')
        self.assertEqual(result['inputs']['recovery']['as_of'],early.isoformat())
        self.assertEqual(result['inputs']['recovery']['session_remaining_hours'],36)

    def test_later_future_snapshot_does_not_hide_earlier_observation(self):
        rows=observations()
        for identifier,hours,minutes in [('past',-1,120),('future',1,9999)]:
            rows.append({'id':identifier,'source_name':'garmin_connect','metric_type':'recovery_time',
                         'recorded_at':(NOW+timedelta(hours=hours)).isoformat(),'value':minutes,'unit':'min'})
        result=calculate(DAY,'UTC',rows,[],COVERAGE,DEFAULTS,now=NOW)
        self.assertEqual(result['inputs']['recovery']['garmin_observation']['id'],'past')
        self.assertEqual(result['inputs']['recovery']['session_remaining_hours'],1)
