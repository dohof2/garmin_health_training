import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from app.database import connect, migrate
from app.garmin_connection import GarminConnectProvider, _normalise_vo2
from app.sync import run_sync, SimulatedGarminProvider, sync_plan
from app.charts import chart_data, catalog

class VO2Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';migrate(self.path)
  with connect(self.path) as c:c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES('old','garmin_export','max_met_fitness','old','2026-10-06',?)",(json.dumps({'sport':'CYCLING','vo2MaxValue':44}),))
 def tearDown(self):self.tmp.cleanup()
 def payload(self):return [{'generic':{'calendarDate':'2026-10-09','sport':'CYCLING','vo2MaxPreciseValue':44.6},'cycling':{'calendarDate':'2026-10-09','vo2MaxPreciseValue':44.7,'vo2MaxValue':45}},{'generic':{'calendarDate':'2026-10-08','sport':'RUNNING','vo2MaxValue':42}}]
 def test_precise_sport_values_actual_dates_and_no_duplicate_generic(self):
  records=_normalise_vo2(self.payload());self.assertEqual(len(records),2)
  self.assertEqual(records[0]['metric_type'],'vo2_cycling');self.assertEqual(records[0]['value'],44.7);self.assertEqual(records[0]['recorded_at'],'2026-10-09');self.assertEqual(records[1]['metric_type'],'vo2_running')
 def test_missing_and_invalid_values_do_not_create_measurements(self):
  for value in (None,True,float('nan'),float('inf'),-1,0,'45'):
   self.assertEqual(_normalise_vo2([{'cycling':{'calendarDate':'2026-10-09','vo2MaxPreciseValue':value}}]),[])
  self.assertEqual(_normalise_vo2([{'generic':{'calendarDate':'2026-10-09','vo2MaxValue':45}}]),[])
  self.assertEqual(_normalise_vo2([{'cycling':{'vo2MaxValue':45}}]),[])
 def test_new_checkpoint_catches_up_from_imported_history(self):
  p=sync_plan(date(2026,10,11),self.path,overlap_days=0)
  stream=next(s for s in p['data_types'] if s['data_type']=='vo2_metrics')
  self.assertEqual(stream['coverage_end'],'2026-10-06');self.assertEqual(stream['start_date'],'2026-10-07')
 def test_live_sync_updates_dial_history_and_is_idempotent(self):
  provider=SimulatedGarminProvider({'vo2_metrics':_normalise_vo2(self.payload())})
  run_sync(provider,date(2026,10,11),self.path,data_types=('vo2_metrics',));run_sync(provider,date(2026,10,11),self.path,data_types=('vo2_metrics',))
  chart=chart_data({'metric':'vo2_cycling','kind':'dial'},self.path)
  self.assertEqual(chart['points'][-1]['y'],44.7);self.assertEqual(chart['points'][-1]['date'],'2026-10-09')
  with connect(self.path) as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM metric_readings WHERE metric_type LIKE 'vo2_%'").fetchone()[0],2)
  ids=[m['id'] for m in catalog(self.path)['metrics']];self.assertEqual(ids.count('vo2_cycling'),1)
 def test_live_value_supersedes_archive_same_day(self):
  record=_normalise_vo2([{'cycling':{'calendarDate':'2026-10-06','vo2MaxPreciseValue':44.4}}])
  run_sync(SimulatedGarminProvider({'vo2_metrics':record}),date(2026,10,6),self.path,data_types=('vo2_metrics',))
  chart=chart_data({'metric':'vo2_cycling','kind':'line'},self.path)
  self.assertEqual(len(chart['points']),1);self.assertEqual(chart['points'][0]['y'],44.4)
 def test_provider_does_not_move_old_measurement_to_requested_day(self):
  class Client:
   def get_max_metrics_range(self,start,end):return [{'cycling':{'calendarDate':'2026-10-09','vo2MaxPreciseValue':44.7}}]
  provider=GarminConnectProvider(Client());self.assertEqual(provider.fetch('vo2_metrics',date(2026,10,11),date(2026,10,11)),[])
  self.assertEqual(provider.fetch('vo2_metrics',date(2026,10,9),date(2026,10,11))[0]['recorded_at'],'2026-10-09')
