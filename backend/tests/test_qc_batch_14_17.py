"""Mixed requests, reference continuity, raw-speed flags and unsent diagnostics."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.ai_chat import chat_stream,_matching_followup
from app.chat_routing import task_segments
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
 def test_task_boundaries_do_not_split_ingredients_or_fragments(self):
  self.assertEqual(task_segments('I ate bread and eggs'),[])
  self.assertEqual(task_segments('Make my ride easier and more comfortable'),[])
  self.assertEqual(task_segments('Make my ride easier and log my lunch'),['Make my ride easier','log my lunch'])
  self.assertEqual(task_segments('I ate 200 g rice; reduce my cycling this week by 20%'),['I ate 200 g rice','reduce my cycling this week by 20%'])
 def test_mixed_food_and_workout_preserve_both_cards_context_and_operation_ids(self):
  pending={'day':NOW.date().isoformat(),'pending_foods':[{'name':'rice'}]}
  proposal={'status':'proposal','message':'Review the easier ride; nothing saved.','adjustments':[]}
  with patch('app.training_adjustments.propose',return_value=proposal) as workout,patch('app.nutrition_chat.chat',return_value={'reply':'Logged rice','logged':True,'context_date':'2026-10-27'}) as food:
   events=self.events('Make my ride easier; log my lunch',operation_id='batch-1',nutrition_context=pending)
   first_id=food.call_args.kwargs['operation_id']
   self.assertEqual(food.call_args.kwargs['pending_foods'],pending['pending_foods'])
   self.assertEqual(workout.call_args.args[0],'Make my ride easier')
   self.assertEqual(food.call_args.args[0],'log my lunch')
   again=self.events('Make my ride easier; log my lunch',operation_id='batch-1',nutrition_context=pending)
   self.assertEqual(food.call_args.kwargs['operation_id'],first_id)
  self.assertEqual([e['type'] for e in events].count('complete'),1)
  evidence=[e['evidence'] for e in events if e['type']=='tool']
  self.assertTrue(any('training_adjustment' in e for e in evidence));self.assertTrue(any('nutrition' in e for e in evidence))
  self.assertTrue(any(e.get('chat_roles')==['trainer','nutrition'] for e in events));self.assertEqual(again[-1]['type'],'complete')
 def test_one_failed_task_does_not_discard_another_result(self):
  with patch('app.training_adjustments.propose',side_effect=ValueError('No saved workout')),patch('app.nutrition_chat.chat',return_value={'reply':'Logged rice','logged':True,'context_date':'2026-10-27'}) as food:
   events=self.events('Make my ride easier; log my lunch')
  food.assert_called_once();text=''.join(e.get('text','') for e in events)
  self.assertIn('could not be completed',text);self.assertIn('Logged rice',text);self.assertIn('not atomic',text)
 def test_matching_followup_preserves_user_date_not_assistant_claim(self):
  history=[{'role':'user','content':'Find matching rides for September 27th'},{'role':'assistant','content':'October 9th is the reference.'}]
  resolved=_matching_followup('Find matching rides using GPS',history,TZ)
  self.assertIn('2026-09-27',resolved)
 def test_matching_uses_selected_reference_without_provider_question(self):
  captured=[]
  def execute(name,args,path):captured.append((name,args));return {'tool':name}
  with patch('app.ai_chat.execute_tool',side_effect=execute),patch('app.ai_chat._tool_evidence',return_value={'tool':'find_same_course_rides'}),patch('app.ai_chat._deterministic_answer',return_value='Matched the selected ride'),patch('app.ai_chat._chatgpt_stream',side_effect=AssertionError('Unexpected provider call')):
   events=self.events('Find matching rides using GPS',ride_context='selected-ride')
  self.assertEqual(captured[0][1]['reference_activity_id'],'selected-ride');self.assertEqual(events[-1]['type'],'complete')
 def test_explicit_latest_overrides_selected_context_and_period_filters_remain(self):
  captured=[]
  def execute(name,args,path):captured.append(args);return {'tool':name}
  with patch('app.ai_chat.execute_tool',side_effect=execute),patch('app.ai_chat._tool_evidence',return_value={}),patch('app.ai_chat._deterministic_answer',return_value='Matched'):
   self.events('Find GPS matches for my latest ride in the past 3 months',ride_context='old-ride')
  self.assertNotIn('reference_activity_id',captured[0]);self.assertIn('candidate_start_date',captured[0])
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
