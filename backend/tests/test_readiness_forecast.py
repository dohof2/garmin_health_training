import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.database import connect,migrate
from app.readiness import DEFAULTS,calculate
from app.readiness_forecast import forecast,project,fit_predict
from test_readiness import observations, DAY, NOW, COVERAGE, activity

class ForecastTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'db';migrate(self.path)
  self.rows=observations()
  with connect(self.path) as c:
   for row in self.rows:c.execute('INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit,period_start,period_end) VALUES (:id,:source_name,:metric_type,:recorded_at,:value,:unit,:period_start,:period_end)',row)
   c.execute("INSERT INTO sync_checkpoints(data_type,provider_name,coverage_start,coverage_end,status) VALUES ('activities','garmin_connect','2026-01-01','2026-10-10','synced')")
 def tearDown(self):self.temp.cleanup()
 def test_regularized_fit_learns_residuals_and_stays_bounded(self):
  examples=[{'features':[i/100],'baseline':40,'actual':40+20*i/100} for i in range(80)]
  predicted=fit_predict(examples,[.8],40)
  self.assertLess(abs(predicted-56),abs(40-56))
  self.assertTrue(0<=fit_predict(examples,[100],40)<=100)
 def test_assistant_tomorrow_request_routes_read_only_forecast(self):
  from app.ai_chat import chat_stream
  class Clock(datetime):
   @classmethod
   def now(cls,tz=None):return NOW
  with patch('app.readiness_forecast.datetime',Clock):events=[json.loads(line) for line in chat_stream('What is my projected training readiness tomorrow?',timezone_name='UTC',path=self.path)]
  self.assertTrue(any(e['type']=='delta' and "Tomorrow's projected" in e['text'] for e in events))
  self.assertTrue(any(e['type']=='tool' and e['evidence']['tool']=='get_projected_training_readiness' for e in events))
 def test_early_completed_wake_unlocks_before_fallback_hour(self):
  now=datetime(2026,10,10,6,10,tzinfo=timezone.utc)
  result=calculate(DAY,'UTC',self.rows,[],COVERAGE,DEFAULTS,now=now)
  self.assertEqual(result['status'],'complete');self.assertEqual(result['cutoff'],'2026-10-10T06:00:00+00:00');self.assertEqual(result['score'],100)
 def test_sleep_not_finished_does_not_unlock(self):
  result=calculate(DAY,'UTC',self.rows,[],COVERAGE,DEFAULTS,now=datetime(2026,10,10,5,59,tzinfo=timezone.utc))
  self.assertEqual(result['status'],'awaiting_morning');self.assertIsNone(result['score'])
 def test_forecast_uses_recent_trends_and_backtest_without_writes(self):
  before=[]
  with connect(self.path) as c:before=[tuple(r) for r in c.execute('SELECT * FROM metric_readings ORDER BY id')]
  r=forecast('UTC',self.path,NOW)
  self.assertEqual(r['date'],'2026-10-11');self.assertEqual(r['status'],'projected');self.assertEqual(r['score'],100);self.assertEqual(r['range'],{'low':95,'high':100});self.assertEqual(r['model']['lookback_days'],100);self.assertGreaterEqual(r['validation']['mornings'],14);self.assertEqual(r['model']['selected'],'recent_median')
  with connect(self.path) as c:self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM metric_readings ORDER BY id')]);self.assertEqual(c.execute('SELECT COUNT(*) FROM readiness_calculations').fetchone()[0],0)
 def test_improving_hrv_does_not_create_forecast_cliff_without_workouts(self):
  with connect(self.path) as c:
   c.execute("UPDATE metric_readings SET value=30 WHERE metric_type='hrv_last_night_average'")
   c.execute("UPDATE metric_readings SET value=35 WHERE metric_type='hrv_last_night_average' AND recorded_at=?",(DAY.isoformat(),))
   c.execute("UPDATE metric_readings SET value=24 WHERE metric_type='hrv_last_night_average' AND recorded_at>=? AND recorded_at<?",((DAY-timedelta(days=6)).isoformat(),DAY.isoformat()))
  r=forecast('UTC',self.path,NOW)
  comparison=r['comparison'];parts={p['name']:p for p in comparison['contributors']}
  self.assertEqual(parts['Workout load']['score_change'],0)
  self.assertGreaterEqual(parts['HRV and resting heart rate']['score_change'],0)
  self.assertGreaterEqual(comparison['baseline_score'],comparison['today_score'])
  self.assertIn('seven-day average',comparison['explanation'])
  self.assertAlmostEqual(r['hrv_7day']['average'],(5*24+35+(24+24+35)/3)/7)
 def test_future_observations_and_today_whole_day_rhr_do_not_leak(self):
  original=project(NOW,'UTC',self.rows,[],COVERAGE,DEFAULTS)
  changed=copy.deepcopy(self.rows)
  for row in changed:
   if row['metric_type']=='resting_heart_rate' and row['recorded_at']==DAY.isoformat():row['value']=200
  for row in self.rows[:4]:
   future={**row,'id':'future:'+row['id'],'recorded_at':(DAY+timedelta(days=1)).isoformat(),'period_end':'2026-10-11T06:00:00Z','value':1};changed.append(future)
  self.assertEqual(original,project(NOW,'UTC',changed,[],COVERAGE,DEFAULTS))
 def test_forecast_rhr_is_labeled_projection_for_target_not_future_measurement(self):
  result,inputs,missing=project(NOW,'UTC',self.rows,[],COVERAGE,DEFAULTS)
  self.assertFalse(missing)
  self.assertEqual(result['inputs']['rhr']['source_name'],'projection')
  self.assertEqual(result['inputs']['rhr']['wake_date'],'2026-10-11')
  self.assertEqual(result['inputs']['rhr_selection']['kind'],'projected')
  self.assertFalse(result['inputs']['rhr_selection']['provisional'])
  self.assertTrue(all(row['latest_date']<='2026-10-10' for row in inputs))
 def test_future_fit_activity_end_does_not_enter_projection(self):
  baseline=project(NOW,'UTC',self.rows,[],COVERAGE,DEFAULTS)
  row=activity(start='2026-10-10T13:00:00Z',end=None,load=10000);row['raw_json']=json.dumps({'fit_sessions':[{'timestamp':'2026-10-10T15:00:00Z'}]})
  self.assertEqual(baseline,project(NOW,'UTC',self.rows,[row],COVERAGE,DEFAULTS))
 def test_insufficient_recent_history_and_stale_sync_do_not_invent_score(self):
  with connect(self.path) as c:c.execute("DELETE FROM metric_readings WHERE metric_type='hrv_last_night_average'")
  r=forecast('UTC',self.path,NOW);self.assertIsNone(r['score']);self.assertIn('hrv_last_night_average',r['missing_metrics'])
 def test_incomplete_workload_keeps_forecast_unavailable(self):
  with connect(self.path) as c:c.execute("UPDATE sync_checkpoints SET coverage_end='2026-10-08'")
  self.assertIsNone(forecast('UTC',self.path,NOW)['score'])
 def test_api_forecast_contract_and_timezone_validation(self):
  class Clock(datetime):
   @classmethod
   def now(cls,tz=None):return NOW
  with patch('app.database.database_path',return_value=self.path),patch('app.readiness_forecast.datetime',Clock),TestClient(app) as client:
   r=client.get('/api/readiness/forecast?timezone=UTC');self.assertEqual(r.status_code,200);self.assertEqual(r.json()['date'],'2026-10-11')
   self.assertEqual(client.get('/api/readiness/forecast?timezone=Invalid/Zone').status_code,400)
