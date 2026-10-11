import json
import tempfile
import unittest
from pathlib import Path
from app.database import connect, migrate
from app.activity_metrics import preserve_fit_summary, backfill_fit_ascent
from app.garmin_connection import _normalise_activity
from app.sync import _upsert_activity
from app.ai_chat import _explicit_plot_arguments
from app.charts import chart_data

class AscentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';migrate(self.path)
  self.record={'source_record_id':'ride','activity_type':'cycling','started_at':'2026-10-09T10:00:00Z','duration_seconds':3600,'distance_meters':20000,'elevation_gain_meters':534}
  with connect(self.path) as c:_upsert_activity(c,self.record)
 def tearDown(self):self.tmp.cleanup()
 def row(self):
  with connect(self.path) as c:return dict(c.execute('SELECT * FROM activities').fetchone())
 def test_sync_preserves_ascent_when_later_summary_omits_it(self):
  with connect(self.path) as c:_upsert_activity(c,{**self.record,'elevation_gain_meters':None})
  self.assertEqual(self.row()['elevation_gain_meters'],534)
 def test_live_summary_records_total_climb_and_zero_is_valid(self):
  for value in (534,0):
   result=_normalise_activity({'activityId':1,'startTimeGMT':'2026-10-09T10:00:00Z','activityType':{'typeKey':'cycling'},'summaryDTO':{'elevationGain':value}})
   self.assertEqual(result['elevation_gain_meters'],value)
 def test_single_fit_session_fills_missing_ascent_only(self):
  row=self.row()
  with connect(self.path) as c:
   c.execute('UPDATE activities SET elevation_gain_meters=NULL')
   preserve_fit_summary(c,row['id'],{'session_mesgs':[{'total_ascent':87}]})
  self.assertEqual(self.row()['elevation_gain_meters'],87)
  with connect(self.path) as c:preserve_fit_summary(c,row['id'],{'session_mesgs':[{'total_ascent':99}]})
  self.assertEqual(self.row()['elevation_gain_meters'],87)
 def test_existing_fit_fallback_and_multisport_ambiguity(self):
  for sessions,expected in (([{'total_ascent':42}],1),([{'total_ascent':20},{'total_ascent':22}],0),([{'total_ascent':None}],0)):
   with connect(self.path) as c:c.execute('UPDATE activities SET elevation_gain_meters=NULL,raw_json=?',(json.dumps({'fit_sessions':sessions}),))
   self.assertEqual(backfill_fit_ascent(self.path),expected)
 def test_climb_plot_uses_ascent_meters_against_time(self):
  spec=_explicit_plot_arguments('Plot total climb against time',self.path)['plots'][0]
  self.assertEqual(spec['metric'],'activity_elevation');self.assertEqual(spec['x_metric'],'date')
  plot=chart_data(spec,self.path);self.assertEqual(plot['unit'],'m');self.assertEqual(plot['points'][0]['y'],534);self.assertEqual(plot['points'][0]['x'],'2026-10-09')
