from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import connect, migrate
from app.exports import create_backup, export_json, restore_backup
from app.readiness import DEFAULTS, calculate, get_readiness_settings, parameters, readiness_history, save_readiness_settings
from app.ai_tools import execute_tool
from app.ai_chat import _deterministic_answer, _normalize_tool_arguments
from app.main import app

DAY = date(2026,10,10)
NOW = datetime(2026,10,10,14,tzinfo=timezone.utc)
class FrozenClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


COVERAGE = {'coverage_start':'2026-01-01','coverage_end':'2026-10-10','history_backfill_next':None}


def observations():
    rows=[]
    for offset in range(100):
        day=DAY-timedelta(days=offset)
        for kind,value,unit in [('hrv_last_night_average',50,'ms'),('resting_heart_rate',50,'bpm'),('sleep_duration',28800,'s'),('sleep_score',90,'score')]:
            rows.append({'id':f'{kind}:{day}','source_name':'garmin_connect','metric_type':kind,'recorded_at':day.isoformat(),'value':value,'unit':unit,
                         'period_start':f'{day-timedelta(days=1)}T22:00:00Z' if kind.startswith('sleep') else day.isoformat(),
                         'period_end':f'{day}T06:00:00Z' if kind.startswith('sleep') else day.isoformat()})
    return rows


def activity(identifier='ride', start='2026-10-09T14:00:00Z', end='2026-10-09T15:00:00Z', load=100):
    return {'id':identifier,'started_at':start,'ended_at':end,'load':load,'load_method':'garmin_summary','source_field':'activityTrainingLoad','raw_json':'{}'}


class ReadinessCalculationTests(unittest.TestCase):
    def setUp(self):
        self.rows=observations()

    def run_model(self, rows=None, activities=None, config=None, coverage=None, zone='UTC', now=NOW):
        return calculate(DAY,zone,rows if rows is not None else self.rows,activities or [],coverage if coverage is not None else COVERAGE,config or DEFAULTS,now=now)

    def change(self,kind,value,offset=0):
        next(row for row in self.rows if row['metric_type']==kind and row['recorded_at']==(DAY-timedelta(days=offset)).isoformat())['value']=value

    def test_normal_full_evidence_scores_100_and_zero_load_ties_have_midrank(self):
        result=self.run_model()
        self.assertEqual(result['score'],100)
        self.assertEqual(result['groups'][2]['percentile'],.5)
        self.assertEqual(result['groups'][0]['hrv_baseline']['count'],28)
        self.assertEqual(result['inputs']['rhr_previous_day']['wake_date'],'2026-10-09')

    def test_severe_hrv_and_rhr_share_one_bounded_penalty(self):
        self.change('hrv_last_night_average',35)
        self.change('resting_heart_rate',60,1)
        result=self.run_model()
        self.assertEqual(result['groups'][0]['penalty_min'],40)
        self.assertEqual(result['score'],60)

    def test_high_hrv_no_bonus_and_context_flag(self):
        self.change('hrv_last_night_average',80)
        result=self.run_model()
        self.assertEqual(result['score'],100)
        self.assertIn('unusually_high_hrv_no_bonus',result['warnings'])

    def test_sleep_duration_and_score_do_not_double_count(self):
        self.change('sleep_duration',18000)
        self.change('sleep_score',20)
        result=self.run_model()
        self.assertEqual(result['groups'][1]['penalty_min'],35)
        self.assertEqual(result['score'],65)

    def test_all_three_groups_can_reach_low_band(self):
        self.change('sleep_duration',18000)
        self.change('hrv_last_night_average',30)
        result=self.run_model(activities=[activity(load=1000)])
        self.assertEqual(result['score'],0)
        self.assertEqual(result['band'],'lower')

    def test_load_decays_and_in_progress_or_future_sessions_are_excluded(self):
        recent=self.run_model(activities=[activity()])
        older=self.run_model(activities=[activity(start='2026-10-08T14:00:00Z',end='2026-10-08T15:00:00Z')])
        self.assertAlmostEqual(older['groups'][2]['exposure']/recent['groups'][2]['exposure'],2**(-24/36),places=4)
        excluded=self.run_model(activities=[activity(start='2026-10-10T07:00:00Z',end='2026-10-10T09:00:00Z'),activity('future',start='2026-10-11T07:00:00Z',end='2026-10-11T09:00:00Z')])
        self.assertEqual(excluded['groups'][2]['exposure'],0)

    def test_missing_load_keeps_fixed_unknown_budget(self):
        result=self.run_model(activities=[activity(load=None)])
        self.assertIsNone(result['score'])
        self.assertEqual(result['score_range'],{'low':75,'high':100})
        self.assertEqual(result['groups'][2]['missing_activity_ids'],['ride'])

    def test_workload_requires_verification_of_the_morning_date(self):
        coverage={**COVERAGE,'coverage_end':'2026-10-09'}
        result=self.run_model(coverage=coverage)
        self.assertIsNone(result['score'])
        self.assertEqual(result['score_range'],{'low':75,'high':100})

    def test_missing_hrv_or_unverified_coverage_never_fabricates_score(self):
        rows=[r for r in self.rows if r['metric_type']!='hrv_last_night_average' or r['recorded_at']!=DAY.isoformat()]
        self.assertEqual(self.run_model(rows=rows)['score_range'],{'low':60,'high':100})
        self.assertEqual(self.run_model(coverage={})['score_range'],{'low':75,'high':100})
        rows=[r for r in rows if r['metric_type']!='hrv_last_night_average']
        self.assertEqual(self.run_model(rows=rows)['status'],'insufficient_data')

    def test_missing_or_unfinished_sleep_not_substituted_with_latest_history(self):
        rows=[r for r in self.rows if not (r['metric_type']=='sleep_duration' and r['recorded_at']==DAY.isoformat())]
        self.assertEqual(self.run_model(rows=rows)['status'],'insufficient_data')
        self.assertEqual(self.run_model(now=datetime(2026,10,10,5,tzinfo=timezone.utc))['status'],'awaiting_morning')

    def test_future_metrics_and_current_day_rhr_cannot_change_morning(self):
        expected=self.run_model()
        self.change('resting_heart_rate',150)
        future=copy.deepcopy(self.rows[0]);future.update(id='future',recorded_at='2026-10-11',value=500)
        actual=self.run_model(rows=self.rows+[future])
        self.assertEqual(actual['score'],expected['score'])
        self.assertEqual(actual['groups'],expected['groups'])

    def test_reference_has_no_recent_window_leak_and_duplicates_prefer_live(self):
        row=copy.deepcopy(self.rows[0]);row.update(id='archive-duplicate',source_name='garmin_export',value=5)
        result=self.run_model(rows=self.rows+[row])
        self.assertEqual(result['inputs']['hrv']['value'],50)
        self.assertEqual(result['groups'][0]['baseline_end'],'2026-10-07')
        self.assertNotIn(self.rows[0]['id'],result['groups'][0]['baseline_input_ids'])

    def test_unit_mismatch_and_invalid_values_are_missing(self):
        self.change('hrv_last_night_average',float('nan'))
        result=self.run_model()
        self.assertIsNone(result['inputs']['hrv'])
        self.rows=observations()
        self.rows[0]['unit']='seconds'
        self.assertIsNone(self.run_model()['inputs']['hrv'])

    def test_wake_date_timezone_and_dst_cutoffs(self):
        rows=[r for r in observations() if not (r['metric_type'].startswith('sleep') and r['recorded_at']=='2026-10-10')]
        for row in rows:
            if row['metric_type'].startswith('sleep') and row['recorded_at']=='2026-10-09':
                row['period_end']='2026-10-09T23:30:00Z'
        result=self.run_model(rows=rows,zone='Asia/Jerusalem')
        self.assertEqual(result['cutoff'],'2026-10-10T05:00:00+00:00')
        for day,expected in [(date(2026,3,29),'06:00'),(date(2026,10,25),'07:00')]:
            result=calculate(day,'Europe/Berlin',[],[],COVERAGE,DEFAULTS,now=NOW)
            self.assertIn(expected,result['cutoff'])

    def test_fit_end_is_used_but_active_duration_is_not_guessed_as_elapsed(self):
        fit=activity(end=None);fit['raw_json']=json.dumps({'fit_sessions':[{'timestamp':'2026-10-09T15:00:00Z'}]})
        self.assertEqual(self.run_model(activities=[fit])['groups'][2]['sessions'][0]['end_method'],'fit_session_end')
        unknown=activity(end=None);unknown['duration_seconds']=3600
        self.assertEqual(self.run_model(activities=[unknown])['status'],'partial')

    def test_severity_monotonicity_for_hrv_sleep_and_rhr(self):
        for kind,values,offset in [('hrv_last_night_average',[50,48,45,40,35],0),('sleep_duration',[28800,27000,25200,21600,18000],0),('resting_heart_rate',[50,51,52,54,56],1)]:
            self.rows=observations()
            scores=[]
            for value in values:
                self.change(kind,value,offset)
                scores.append(self.run_model()['score'])
            self.assertEqual(scores,sorted(scores,reverse=True))


class ReadinessPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';migrate(self.path)
        with connect(self.path) as c:
            for row in observations():
                c.execute('INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit,period_start,period_end) VALUES (:id,:source_name,:metric_type,:recorded_at,:value,:unit,:period_start,:period_end)',row)
            c.execute("INSERT INTO sync_checkpoints(data_type,provider_name,coverage_start,coverage_end,status) VALUES ('activities','garmin_connect','2026-01-01','2026-10-10','synced')")

    def tearDown(self):self.temp.cleanup()

    def history(self,**kwargs):return readiness_history(DAY,14,'UTC',self.path,now=NOW,**kwargs)

    def test_repeat_queries_reuse_calculations_and_late_correction_creates_revision(self):
        first=self.history();second=self.history()
        self.assertEqual(first['latest']['calculation_id'],second['latest']['calculation_id'])
        with connect(self.path) as c:c.execute("UPDATE metric_readings SET value=18000 WHERE id='sleep_duration:2026-10-10'")
        corrected=self.history()
        self.assertEqual(corrected['latest']['score'],65)
        self.assertNotEqual(first['latest']['calculation_id'],corrected['latest']['calculation_id'])
        with connect(self.path) as c:
            old=json.loads(c.execute('SELECT result_json FROM readiness_calculations WHERE id=?',(first['latest']['calculation_id'],)).fetchone()[0])
        self.assertEqual(old['score'],100)

    def test_parameter_versions_preserve_old_formula_and_portability(self):
        first=self.history();version=first['latest']['config_version']
        updated=save_readiness_settings({'sleep_target_hours':9},self.path)
        self.assertNotEqual(version,updated['config_version'])
        self.assertEqual(self.history(config_version=version)['latest']['score'],100)
        self.assertLess(self.history()['latest']['score'],100)
        out=Path(self.temp.name)/'export.json';export_json(out,path=self.path)
        self.assertEqual(len(json.loads(out.read_text())['tables']['readiness_configs']),2)
        backup=Path(self.temp.name)/'backup.zip';restored=Path(self.temp.name)/'restore.sqlite3'
        create_backup(backup,self.path);restore_backup(backup,restored)
        self.assertEqual(get_readiness_settings(restored)['config_version'],updated['config_version'])

    def test_configuration_and_date_validation(self):
        for params in [{'sleep_target_hours':float('nan')},{'sleep_weight':99},{'baseline_days':True},{'unknown':1},{'baseline_min_nights':35}]:
            with self.assertRaises(ValueError):parameters(params)
        with self.assertRaises(ValueError):readiness_history(DAY,1,'Invalid/Zone',self.path,now=NOW)
        with self.assertRaises(ValueError):readiness_history(DAY+timedelta(days=1),1,'UTC',self.path,now=NOW)
        with self.assertRaises(ValueError):self.history(config_version='unknown')

    def test_band_sensitivity_is_separate_from_complete_data(self):
        with connect(self.path) as c:
            c.execute("UPDATE metric_readings SET value=23400 WHERE id='sleep_duration:2026-10-10'")
        result=self.history()['latest']
        self.assertEqual(result['data_quality'],'complete')
        self.assertTrue(result['sensitivity']['band_changes'])
        self.assertIn('band_sensitive_to_provisional_parameters',result['warnings'])

    def test_tool_is_advisory_and_deterministic_answer_preserves_partial_status(self):
        with patch('app.readiness.datetime', FrozenClock):
            result=execute_tool('get_training_readiness',{'date':'2026-10-10','timezone':'UTC'},self.path)
        self.assertTrue(result['advisory_only'])
        answer=_deterministic_answer([{'name':'get_training_readiness','result':result}])
        self.assertIn('100/100',answer);self.assertIn('does not prove recovery',answer)
        self.assertEqual(_normalize_tool_arguments('get_training_readiness',{'date':'2020-01-01'},'Readiness on 2026-10-09','UTC')['date'],'2026-10-09')

    def test_api_read_config_write_and_errors(self):
        with patch('app.database.database_path',return_value=self.path),patch('app.readiness.datetime', FrozenClock):
            with TestClient(app) as client:
                response=client.get('/api/readiness?end_date=2026-10-10&days=2&timezone=UTC')
                self.assertEqual(response.status_code,200)
                self.assertEqual(len(response.json()['trend']),2)
                self.assertEqual(client.put('/api/readiness/settings',json={'parameters':{'sleep_target_hours':9}}).status_code,200)
                self.assertEqual(client.put('/api/readiness/settings',json={'parameters':{'sleep_weight':100}}).status_code,400)
                self.assertEqual(client.get('/api/readiness?timezone=Invalid/Zone').status_code,400)
                self.assertEqual(client.get('/api/readiness?days=100').status_code,422)
