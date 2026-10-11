"""Independent acceptance checks. Failures are findings, not proposed fixes.
Run: PYTHONPATH=backend .venv/bin/python docs/qa/2026-10-11/acceptance_probes.py
All writes use a fresh synthetic temporary database.
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from app.ai_chat import chat_stream
from app.charts import chart_data
from app.database import migrate, connect
from app.fixtures import seed_synthetic_history
from app.garmin_connection import GarminConnectProvider
from app.sync import run_sync


class AcceptanceProbes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'health_training.sqlite3'
        migrate(self.path)
        with connect(self.path) as c:
            for i in range(1,29):
                for metric,value,unit in [('weight',70+i,'kg'),('steps',1000+i,'count'),('sleep_score',60+i,'score'),('body_battery_latest',30+i,'score'),('resting_heart_rate',50+i,'bpm')]:
                    c.execute('INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,?,?,?,?,?)',
                              (f'{metric}-{i}','manual',metric,f'2026-01-{i:02}',value,unit))

    def ask(self,text):
        with patch('app.ai_chat._today',return_value=date(2026,10,11)),patch('app.ai_chat._ollama_request',side_effect=RuntimeError('Live model intentionally disabled')):
            return [json.loads(e) for e in chat_stream(text,path=self.path,timezone_name='UTC')]

    def plots(self,events):
        return [p for e in events if e['type']=='tool' for p in e['evidence'].get('plots',[])]

    def test_fixture_observations_are_excluded_from_real_plots(self):
        seed_synthetic_history(self.path)
        d=chart_data({'metric':'activity_duration','kind':'line'},self.path)
        self.assertFalse(any(p['source']=='synthetic_fixture' for p in d['points']),
                         'Fixture activity observations must not appear in user plots')

    def test_deleted_activities_are_excluded(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,deleted_at) VALUES('removed','garmin_connect','cycling','2026-01-01T08:00:00Z',3600,'2026-01-02T00:00:00Z')")
        d=chart_data({'metric':'activity_duration','kind':'line'},self.path)
        self.assertEqual(d['count'],0,'Removed activities must not contribute to plots or statistics')

    def test_two_plot_periods_do_not_silently_become_all_history(self):
        events=self.ask('Plot weight from 2026-01-01 to 2026-01-07 and steps from 2026-01-08 to 2026-01-14')
        if any(e['type']=='error' for e in events): return  # Clear rejection is preferable to a false result.
        plots=self.plots(events)
        self.assertEqual({(p['spec'].get('start'),p['spec'].get('end')) for p in plots},
                         {('2026-01-01','2026-01-07'),('2026-01-08','2026-01-14')})

    def test_rolling_average_request_is_not_silently_raw_history(self):
        events=self.ask('Plot weekly median weight with a 7-day rolling average')
        if any(e['type']=='error' for e in events): return
        plots=self.plots(events)
        self.assertTrue(plots)
        self.assertNotEqual(plots[0]['count'],28,'A requested weekly aggregation must not silently return all raw observations')

    def test_unqualified_body_battery_comparison_is_not_dropped(self):
        events=self.ask('Plot body battery versus sleep score for the last year')
        if any(e['type']=='error' for e in events): return
        plots=self.plots(events)
        self.assertTrue(plots)
        self.assertEqual(plots[0]['spec']['kind'],'scatter','Clarify ambiguous Body Battery or return a comparison; do not silently drop it')

    def test_malformed_daily_sync_does_not_claim_success(self):
        class Client:
            def get_user_summary(self,day): return ['malformed summary']
        result=run_sync(GarminConnectProvider(Client()),date(2026,10,11),path=self.path,data_types=['daily_metrics'])
        self.assertNotEqual(result['status'],'completed','An invalid response is not a successfully fetched empty day')

    def test_control_explicit_comparison_keeps_both_metrics(self):
        plots=self.plots(self.ask('Plot resting heart rate versus cycling VO2 max with correlation'))
        # These two catalog metrics are valid even when the isolated fixture lacks observations.
        self.assertEqual(plots[0]['spec']['kind'],'scatter')
        self.assertEqual({plots[0]['spec']['metric'],plots[0]['spec']['x_metric']},{'resting_heart_rate','vo2_cycling'})

    def test_control_explicit_period_and_mean_are_preserved(self):
        plots=self.plots(self.ask('Plot weight from 2026-01-01 to 2026-01-07 with a mean line'))
        self.assertEqual(plots[0]['count'],7)
        self.assertEqual(plots[0]['analysis']['reference_lines'][0]['value'],74)


if __name__=='__main__':
    unittest.main(verbosity=2)
