import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from app.database import connect,migrate
from app.activity_route import route


class ActivityRouteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'route.sqlite';migrate(self.path)
  with connect(self.path) as c:c.execute("INSERT INTO activities(id,source_name,activity_type,started_at) VALUES('ride','garmin_export','cycling','2026-11-05T08:00:00+00:00')")
 def point(self,second,lat=32,lon=35,power=None,speed=4):
  with connect(self.path) as c:c.execute('INSERT INTO activity_samples(activity_id,recorded_at,latitude,longitude,power_watts,speed_mps) VALUES(?,?,?,?,?,?)',('ride',(datetime(2026,11,5,8,tzinfo=timezone.utc)+timedelta(seconds=second)).isoformat(),lat,lon,power,speed))
 def test_power_default_and_speed_fallback_include_recorded_zero(self):
  self.point(0,power=0);self.point(1,power=200)
  r=route('ride',self.path);self.assertEqual(r['default_metric'],'power_watts');self.assertEqual(r['points'][0]['power_watts'],0)
  with connect(self.path) as c:c.execute('UPDATE activity_samples SET power_watts=NULL')
  self.assertEqual(route('ride',self.path)['default_metric'],'speed_mps')
 def test_gaps_invalid_coordinates_and_missing_gps(self):
  self.point(0,lat=0,lon=0);self.point(1,lat=None);self.point(2);self.point(500)
  r=route('ride',self.path);self.assertEqual(len(r['points']),3)
  self.assertNotEqual(r['points'][0]['segment'],r['points'][1]['segment'])
  self.assertNotEqual(r['points'][1]['segment'],r['points'][2]['segment'])
  with connect(self.path) as c:c.execute('UPDATE activity_samples SET latitude=NULL')
  self.assertEqual(route('ride',self.path)['points'],[])
 def test_bounded_output_preserves_endpoints(self):
  for i in range(20):self.point(i)
  result=route('ride',self.path,max_points=5)
  self.assertEqual(len(result['points']),5);self.assertTrue(result['sampled'])
  self.assertEqual(result['gps_sample_count'],20)
  self.assertEqual(result['points'][0]['recorded_at'],'2026-11-05T08:00:00+00:00')
  self.assertEqual(result['points'][-1]['recorded_at'],'2026-11-05T08:00:19+00:00')
 def test_removed_activity_is_not_exposed(self):
  with connect(self.path) as c:c.execute("UPDATE activities SET deleted_at='2026-11-05'")
  with self.assertRaises(KeyError):route('ride',self.path)
