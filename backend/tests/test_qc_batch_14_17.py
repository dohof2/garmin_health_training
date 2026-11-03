"""Mixed requests, reference continuity, raw-speed flags and unsent diagnostics."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.history import get_activity
from app.garmin_training_publish import history,preview,approve,run,view
from app.garmin_strength import mapping_blockers
from test_garmin_publication import FakeGarmin
from test_training_adjustments import NOW,TZ


class BatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
 def events(self,message,**kwargs):return [json.loads(line) for line in chat_stream(message,path=self.path,timezone_name=TZ,message_time=NOW,**kwargs)]
 def test_speed_is_flagged_without_rewriting_samples_or_converting_twice(self):
  with connect(self.path) as c:
   c.execute("INSERT INTO activities(id,source_name,activity_type,started_at) VALUES('ride','garmin_connect','mountain_biking','2026-10-09T02:00:00Z')")
   c.execute("INSERT INTO activity_samples(activity_id,recorded_at,speed_mps) VALUES('ride','2026-10-09T07:15:57Z',61.564)")
  result=get_activity('ride',self.path,TZ)
  self.assertEqual(result['sample_summary']['maximum_speed_mps'],61.564);self.assertIn('221.6 km/h',result['data_quality_warnings'][0])
  with connect(self.path) as c:c.execute("UPDATE activity_samples SET speed_mps=10 WHERE activity_id='ride'")
  self.assertEqual(get_activity('ride',self.path,TZ)['data_quality_warnings'],[])
 def definition(self):
  return {'sport':'strength','title':'Fictional strength','duration_minutes':30,'exercises':[{'id':'dumbbell_row','name':'Dumbbell row','sets':2,'repetitions':8,'rest_seconds':90,'load_target_kg':12.5,'load':'Leave 2 repetitions in reserve'}]}
 def test_strength_blockers_list_each_exact_unsupported_instruction(self):
  d=self.definition();d['exercises']=[{'id':'chair_squat','name':'Chair squat'},{'id':'bodyweight_hinge','name':'Hip hinge practice'}]
  reasons=mapping_blockers(d);self.assertEqual(len(reasons),2)
  with connect(self.path) as c:
   c.execute("INSERT INTO training_plans(id,name,status) VALUES('plan','Fictional plan','accepted')")
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES('workout','plan','strength','Fictional strength','2026-10-27',?)",(json.dumps(d),))
   before=list(c.iterdump())
  with patch('app.garmin_training_publish.load_client',side_effect=AssertionError('No live access')):
   result=history(self.path)
  row=result['local_workouts'][0];self.assertEqual(row['state'],'blocked');self.assertEqual(len(row['blocked_reasons']),2)
  self.assertEqual(result['jobs'],[])
  with connect(self.path) as c:self.assertEqual(list(c.iterdump()),before)
 def test_supported_strength_send_mock_readback_and_retry_are_duplicate_safe(self):
  client=FakeGarmin();factory=lambda p:client
  p=preview({'definition':self.definition(),'scheduled_date':NOW.date().isoformat(),'timezone':TZ},self.path,factory,NOW)
  approve(p['id'],self.path,factory,NOW);run(p['id'],self.path,factory)
  self.assertEqual(view(p['id'],self.path)['status'],'verified')
  self.assertEqual(client.creates,1);self.assertEqual(client.schedules,1)
  run(p['id'],self.path,factory)
  self.assertEqual(client.creates,1);self.assertEqual(client.schedules,1)


if __name__=='__main__':unittest.main()
