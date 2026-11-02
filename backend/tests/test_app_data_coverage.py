"""Coverage and boundary checks using a disposable database; no provider calls."""
import json
import tempfile
import unittest
from pathlib import Path
from app.database import connect, migrate
from app.app_data_queries import query
from app.app_data_catalog import catalog
from app.app_data_history import public_json
from app.ai_tools import TOOL_DEFINITIONS_BY_NAME, execute_tool
from app.chat_access import QUESTION_TOOLS, questions_only


class DataCoverageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
 def read(self,dataset,**kwargs):
  return query(dict(dataset=dataset,start_date='2026-10-25',end_date='2026-10-25',timezone='Asia/Jerusalem',**kwargs),self.path)
 def test_catalog_advertises_real_read_tools_and_no_record_claim(self):
  result=execute_tool('get_app_data_catalog',{},self.path)
  self.assertTrue(result['support_is_not_availability'])
  self.assertIn('get_app_data_catalog',QUESTION_TOOLS)
  for dataset in result['datasets']:
   for name in dataset['read_tools']:
    self.assertIn(name,TOOL_DEFINITIONS_BY_NAME,(dataset,name))
    self.assertIn(name,QUESTION_TOOLS)
  self.assertEqual(result['unavailable'][0]['dataset'],'cycling_ability')
 def test_every_generic_view_is_read_only_even_when_empty(self):
  schema=TOOL_DEFINITIONS_BY_NAME['query_app_data']['input_schema']['properties']['dataset']['enum']
  with connect(self.path) as c:before=list(c.iterdump())
  for dataset in schema:
   with self.subTest(dataset=dataset),questions_only():
    execute_tool('query_app_data',dict(dataset=dataset,start_date='2026-10-25',end_date='2026-10-25'),self.path)
  with connect(self.path) as c:self.assertEqual(before,list(c.iterdump()))
 def test_sample_pagination_dst_boundaries_and_fixture_exclusion(self):
  # Israel changes from +03 to +02 on this day: the local day lasts 25 hours.
  times=['2026-10-24T20:59:59Z','2026-10-24T21:00:00Z','2026-10-25T21:59:59Z','2026-10-25T22:00:00Z']
  with connect(self.path) as c:
   for instant in times:c.execute("INSERT INTO health_samples(source_name,recorded_at,heart_rate_bpm) VALUES('garmin_connect',?,65)",(instant,))
   c.execute("INSERT INTO health_samples(source_name,recorded_at,heart_rate_bpm) VALUES('synthetic_fixture','2026-10-25T10:00:00Z',90)")
  first=self.read('health_samples',limit=1)
  self.assertEqual(first['total_matches'],2);self.assertTrue(first['truncated']);self.assertEqual(first['next_offset'],1)
  last=self.read('health_samples',limit=1,offset=first['next_offset'])
  self.assertFalse(last['truncated']);self.assertNotEqual(first['records'],last['records'])
  self.assertEqual(first['units']['heart_rate_bpm'],'bpm')
 def test_archived_goals_and_local_day_revisions(self):
  with connect(self.path) as c:
   c.execute("INSERT INTO goals(id,goal_type,title,status) VALUES('old','fitness','Old goal','archived')")
   c.execute('DELETE FROM goal_revisions')
   c.execute("INSERT INTO goal_revisions(goal_id,snapshot_json,recorded_at) VALUES('old','{}','2026-10-24 21:30:00')")
  result=self.read('goals');self.assertEqual(result['records'][0]['status'],'archived');self.assertEqual(result['revisions']['total_matches'],1)
 def test_training_uses_definition_local_date_and_includes_feedback(self):
  with connect(self.path) as c:
   c.execute("INSERT INTO planned_workouts(id,sport,title,scheduled_for,definition_json) VALUES('w','strength','Strength','2026-10-24T21:30:00Z',?)",(json.dumps({'scheduled_date':'2026-10-25','steps':[]}),))
   c.execute("INSERT INTO training_feedback(workout_id,effort,pain_or_illness,notes) VALUES('w',5,0,'Controlled')")
   c.execute("INSERT INTO training_strength_performance(workout_id,exercise_id,set_index,load_kg,repetitions,repetitions_in_reserve,recorded_at) VALUES('w','squat',1,20,8,3,'2026-10-25T10:00:00Z')")
  result=self.read('training');self.assertEqual(result['total_matches'],1)
  self.assertEqual(result['records'][0]['feedback']['notes'],'Controlled')
  self.assertEqual(result['records'][0]['definition']['scheduled_date'],'2026-10-25')
  self.assertEqual(result['records'][0]['strength_performance'][0]['load_kg'],20)
 def test_publication_is_local_evidence_and_excludes_account_and_payload(self):
  with connect(self.path) as c:
   c.execute("INSERT INTO garmin_publication_jobs(id,account_key,account_label,timezone,created_at,expires_at,status) VALUES('job','private-key','private-label','UTC','2026-10-25T10:00:00Z','2026-10-26T10:00:00Z','failed')")
   c.execute("INSERT INTO garmin_publication_items(id,job_id,account_key,identity_key,snapshot_json,payload_json,payload_hash,scheduled_date,action,state,error) VALUES('item','job','private-key','identity','{}','{}','hash','2026-10-25','create','failed','Unsupported exercise')")
  result=self.read('publication');self.assertEqual(result['records'][0]['error'],'Unsupported exercise')
  self.assertNotIn('private-',json.dumps(result));self.assertNotIn('payload_json',result['records'][0])
 def test_current_layout_and_library_are_not_claimed_as_historical(self):
  with connect(self.path) as c:
   c.execute("INSERT INTO dashboard_cards(id,card_type,position,settings_json) VALUES('custom','line',99,?)",(json.dumps({'metric_type':'weight'}),))
  result=self.read('dashboard')
  self.assertIn('Current',result['observation_kind']);self.assertTrue(any(r['id']=='custom' and r['settings']['metric_type']=='weight' for r in result['records']))
  self.assertIn('not a historical',self.read('food_library')['observation_kind'])
 def test_payload_bounds_redaction_and_invalid_json(self):
  payload,flags=public_json(json.dumps({'email':'private','nested':{'access_token':'secret','values':list(range(110))},'long':'x'*5000}))
  self.assertNotIn('email',payload);self.assertNotIn('access_token',payload['nested'])
  self.assertEqual(len(payload['nested']['values']),100);self.assertTrue(flags)
  self.assertIn('unavailable',public_json('broken')[0])
 def test_archive_pages_and_discloses_undated_records(self):
  with connect(self.path) as c:
   for i,day in enumerate(['2026-10-25','2026-10-25',None]):
    c.execute("INSERT INTO garmin_archive_records(id,source_name,source_record_id,category,record_date,payload_json) VALUES(?,'garmin_connect',?,'test',?,?)",(str(i),str(i),day,json.dumps({'email':'private','value':i})))
  result=self.read('archive',category='test',limit=1)
  self.assertEqual(result['total_matches'],2);self.assertEqual(result['undated_record_count'],1)
  self.assertNotIn('email',result['records'][0]['data']);self.assertTrue(result['records'][0]['payload_limits'])
 def test_invalid_queries_are_rejected(self):
  for args in [dict(limit=0),dict(offset=-1),dict(limit=True),dict(dataset='accounts'),dict(dataset='health_samples',end_date='2026-11-02')]:
   request=dict(dataset='health',start_date='2026-10-25',end_date='2026-10-25');request.update(args)
   with self.subTest(args=args),self.assertRaises(ValueError):query(request,self.path)


if __name__=='__main__':unittest.main()
