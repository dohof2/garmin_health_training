import copy
import json
import os
from fastapi.testclient import TestClient
from app.main import app
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.database import connect, migrate
from app.training import save_preferences, list_training, update_workout
from app.training_coach import DEFAULT, parse_request, preview, create_draft, read_brief, save_brief, validate_brief
from app.ai_chat import chat_stream, _forced_tool_name

NOW=datetime(2026,10,11,12,tzinfo=timezone.utc)
WEEK=date(2026,10,12)
ANSWERS={'sports':['cycling'],'priority':'endurance','availability':[{'weekday':i,'start_time':'18:00','minutes':60} for i in range(7)],'experience':{'cycling':'regular'},'equipment':['bike'],'weekly_minutes':{'cycling':300},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
class Clock(datetime):
 @classmethod
 def now(cls,tz=None): return NOW if tz else NOW.replace(tzinfo=None)

class CoachTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'health_training.sqlite3';migrate(self.path);save_preferences(copy.deepcopy(ANSWERS),0,self.path,NOW)
 def tearDown(self):self.tmp.cleanup()
 def brief(self,**patches):return {**copy.deepcopy(DEFAULT),'goal':'ftp',**patches}
 def preview(self,b=None,**kwargs):return preview(b or self.brief(),WEEK,'Asia/Jerusalem',self.path,NOW,**kwargs)
 def draft(self,b=None,**kwargs):
  b=b or self.brief();p=self.preview(b,**kwargs);return create_draft(b,WEEK,'Asia/Jerusalem',p['fingerprint'],self.path,NOW,**kwargs)
 def test_distance_ascent_race_parsing_and_roadmap(self):
  b,_=parse_request('Endurance. Wednesday race 80 km with 1500 m ascent, 3 hours at 08:00',DEFAULT,WEEK)
  event=b['fixed_events'][0];self.assertEqual(event['distance_km'],80);self.assertEqual(event['elevation_gain_meters'],1500);self.assertTrue(event['is_race'])
  b['goal']='endurance'
  p=self.preview(b);self.assertEqual(p['status'],'ready');fixed=next(s for s in p['sessions'] if s['definition'].get('fixed_commitment'))
  self.assertEqual(fixed['definition']['distance_km'],80);self.assertTrue(fixed['definition']['is_race']);self.assertEqual(p['roadmap'][0]['phase'],'Race week')
 def test_named_event_populates_upcoming_fields(self):
  b,_=parse_request('Wednesday ride named "Hill Loop" 80 km 1500 m ascent not a race',DEFAULT,WEEK)
  e=b['fixed_events'][0];self.assertEqual(e['title'],'Hill Loop');self.assertEqual(e['date'],'2026-10-14');self.assertEqual(e['distance_km'],80);self.assertEqual(e['elevation_gain_meters'],1500);self.assertFalse(e['is_race']);self.assertIsNone(b['goal'])
 def test_nonrace_distance_trip_preserves_demands(self):
  b,_=parse_request('Endurance. Wednesday ride not a race 60 km 1000 m climb hard 3 hours at 08:00',DEFAULT,WEEK)
  self.assertFalse(b['fixed_events'][0]['is_race']);self.assertEqual(b['fixed_events'][0]['elevation_gain_meters'],1000)
 def test_distance_only_duration_estimation_from_comparable_rides(self):
  with connect(self.path) as c:
   for i in range(3):c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,distance_meters,elevation_gain_meters) VALUES(?,'garmin_export','cycling',?,7200,40000,500)",('estimate-'+str(i),(NOW-timedelta(days=i+1)).isoformat()))
  b=self.brief(goal='endurance',fixed_events=[{'date':'2026-10-14','title':'Hilly trip','distance_km':40,'elevation_gain_meters':500,'effort':'hard'}])
  p=self.preview(b);event=p['brief']['fixed_events'][0];self.assertEqual(event['duration_minutes'],120);self.assertTrue(event['duration_estimated']);self.assertTrue(any('estimated' in warning for warning in p['warnings']))
 def test_api_coach_preview_draft_and_saved_brief_contract(self):
  with patch.dict(os.environ,{'HT_APP_DATA_DIR':self.tmp.name}),patch('app.training_coach.datetime',Clock),patch('app.training.datetime',Clock),TestClient(app) as client:
   self.assertEqual(client.get('/api/training/coach').json()['revision'],0)
   body={'brief':self.brief(),'week_start':WEEK.isoformat(),'timezone':'Asia/Jerusalem','message':'Wednesday hard 3-hour trip at 08:00'}
   response=client.post('/api/training/coach/preview',json=body);self.assertEqual(response.status_code,200)
   p=response.json();self.assertEqual(p['status'],'ready');self.assertEqual(client.get('/api/training').json()['plans'],[])
   response=client.post('/api/training/coach/draft',json={**body,'message':None,'brief':p['brief'],'fingerprint':p['fingerprint']})
   self.assertEqual(response.status_code,200);self.assertEqual(response.json()['plans'][0]['status'],'draft')
   saved=client.put('/api/training/coach',json={'brief':p['brief'],'expected_revision':0});self.assertEqual(saved.status_code,200)
   self.assertEqual(client.put('/api/training/coach',json={'brief':p['brief'],'expected_revision':0}).status_code,400)
 def test_clock_change_and_past_current_week_trip_require_review(self):
  b=self.brief(fixed_events=[{'date':'2026-10-25','start_time':'01:30','duration_minutes':60,'effort':'easy'}])
  with self.assertRaisesRegex(ValueError,'clock change'):preview(b,date(2026,10,19),'Asia/Jerusalem',self.path,NOW)
  b=self.brief(fixed_events=[{'date':'2026-10-11','start_time':'08:00','duration_minutes':60,'effort':'easy'}])
  p=preview(b,date(2026,10,5),'Asia/Jerusalem',self.path,NOW);self.assertEqual(p['status'],'needs_input');self.assertTrue(any('past' in q for q in p['questions']))
 def test_trip_parser_hyphenated_and_word_duration_followup(self):
  b,recognized=parse_request('Increase FTP. Wednesday a hard 3-hour trip starting at 08:00',DEFAULT,WEEK)
  self.assertEqual(b['fixed_events'][0]['duration_minutes'],180);self.assertEqual(b['fixed_events'][0]['start_time'],'08:00')
  b,_=parse_request('three hours at 09:00 moderate',b,WEEK)
  self.assertEqual(b['fixed_events'][0]['start_time'],'09:00');self.assertEqual(b['fixed_events'][0]['effort'],'moderate')
 def test_missing_details_do_not_create_calendar_or_invent_times(self):
  b,_=parse_request('I want to increase FTP. Wednesday this trip',DEFAULT,WEEK)
  p=self.preview(b);self.assertEqual(p['status'],'needs_input');self.assertTrue(p['questions']);self.assertEqual(p['sessions'],[])
  with self.assertRaises(ValueError):create_draft(b,WEEK,'Asia/Jerusalem',p['fingerprint'],self.path,NOW)
  self.assertEqual(list_training(self.path)['plans'],[])
 def test_fixed_wednesday_preserved_and_no_extra_quality(self):
  b,_=parse_request('Increase FTP. Wednesday hard 3 hours at 08:00 ride',DEFAULT,WEEK)
  p=self.preview(b);self.assertEqual(p['status'],'ready');self.assertEqual(p['weekly_minutes']['cycling'],300)
  fixed=next(s for s in p['sessions'] if s['definition']['template_id']=='fixed_commitment')
  self.assertEqual(fixed['scheduled_for'],'2026-10-14T08:00:00+03:00');self.assertEqual(fixed['definition']['duration_minutes'],180)
  self.assertEqual({d['date'] for d in p['protected_days']},{'2026-10-13','2026-10-15'})
  self.assertNotIn('cycling_controlled_intervals',[s['definition']['template_id'] for s in p['sessions']])
 def test_ftp_has_one_exact_duration_interval_without_inferred_ftp(self):
  p=self.preview();quality=[s for s in p['sessions'] if s['definition']['template_id']=='cycling_controlled_intervals']
  self.assertEqual(len(quality),1);self.assertEqual(quality[0]['definition']['effort_target']['method'],'perceived_effort')
  self.assertEqual(sum(s['duration_seconds'] for s in quality[0]['definition']['steps']),quality[0]['definition']['duration_minutes']*60)
  confirmed=self.preview(self.brief(ftp_watts=250));self.assertIn('250 W',confirmed['sessions'][0]['definition']['effort_target']['description'])
 def test_long_trip_over_budget_is_not_shortened(self):
  b,_=parse_request('Increase FTP. Wednesday hard 6 hours at 08:00 trip',DEFAULT,WEEK)
  p=self.preview(b);self.assertEqual(p['status'],'needs_input');self.assertEqual(p['sessions'][0]['definition']['duration_minutes'],360)
 def test_endurance_prioritizes_longest_slot(self):
  answers=copy.deepcopy(ANSWERS);answers['availability']=[{'weekday':0,'start_time':'18:00','minutes':30},{'weekday':5,'start_time':'08:00','minutes':120}];answers['weekly_minutes']['cycling']=120
  save_preferences(answers,1,self.path,NOW)
  p=self.preview(self.brief(goal='endurance'));self.assertEqual(p['sessions'][0]['scheduled_for'][:10],'2026-10-17');self.assertEqual(p['sessions'][0]['definition']['duration_minutes'],120)
 def test_race_requires_demands_and_running_is_not_cycling(self):
  p=self.preview(self.brief(goal='race',goal_sport='running',target_date='2026-10-25'))
  self.assertEqual(p['status'],'needs_input');self.assertTrue(any('race' in q for q in p['questions']));self.assertTrue(any('sport' in q for q in p['questions']))
 def test_nearby_race_sessions_short_and_protected(self):
  p=self.preview(self.brief(goal='race',target_date='2026-10-18',event_name='100 km cycling race'))
  self.assertEqual(p['status'],'ready');self.assertTrue(all(s['definition']['duration_minutes']<=30 for s in p['sessions']));self.assertNotIn('2026-10-18',[s['scheduled_for'][:10] for s in p['sessions']]);self.assertEqual(p['roadmap'][0]['phase'],'Race week')
 def test_draft_requires_same_context_and_replacement_keeps_history(self):
  b=self.brief();p=self.preview(b);save_preferences({'weekly_minutes':{'cycling':240}},1,self.path,NOW)
  with self.assertRaisesRegex(ValueError,'context changed'):create_draft(b,WEEK,'Asia/Jerusalem',p['fingerprint'],self.path,NOW)
  history=self.draft();old=history['plans'][0]['id'];count=len(history['workouts']);new=self.draft(self.brief(goal='general'),replace_plan_id=old)
  self.assertEqual(next(p for p in new['plans'] if p['id']==old)['status'],'superseded');self.assertEqual(sum(w['completion_status']=='cancelled' for w in new['workouts']),count)
 def test_existing_week_consumes_budget_instead_of_double_training(self):
  self.draft();p=self.preview();self.assertEqual(p['status'],'needs_review');self.assertEqual(p['weekly_minutes']['cycling'],300);self.assertEqual(p['sessions'],[])
 def test_completed_sessions_cannot_be_replaced_feedback_still_works(self):
  h=self.draft();w=h['workouts'][0]
  with patch('app.training.datetime',Clock):update_workout(w['id'],w['revision'],{'completion_status':'completed','effort':6},self.path)
  with self.assertRaisesRegex(ValueError,'Completed'):self.preview(replace_plan_id=h['plans'][0]['id'])
 def test_saved_brief_revision_and_invalid_values(self):
  self.assertEqual(read_brief(self.path)['revision'],0);save_brief(self.brief(),0,self.path)
  self.assertEqual(read_brief(self.path)['brief']['goal'],'ftp')
  with self.assertRaises(ValueError):save_brief(self.brief(goal='general'),0,self.path)
  for patchvalue in ({'horizon_weeks':True},{'ftp_watts':float('nan')},{'goal_sport':'swimming'}):
   with self.assertRaises(ValueError):validate_brief(self.brief(**patchvalue))
 def test_assistant_followup_preserves_brief_and_is_read_only(self):
  def ask(text,context=None):
   with patch('app.training_coach.datetime',Clock):return [json.loads(e) for e in chat_stream(text,coaching_context=context,timezone_name='Asia/Jerusalem',path=self.path)]
  events=ask('Increase FTP. Wednesday I have a trip');coaching=next(e['evidence']['coaching'] for e in events if e['type']=='tool')
  events=ask('3 hours at 08:00 hard',coaching);followup=next(e['evidence']['coaching'] for e in events if e['type']=='tool')
  self.assertEqual(followup['brief']['goal'],'ftp');self.assertEqual(followup['brief']['fixed_events'][0]['duration_minutes'],180);self.assertEqual(followup['status'],'ready')
  self.assertEqual(list_training(self.path)['plans'],[]);self.assertEqual(read_brief(self.path)['revision'],0)
 def test_ordinary_race_or_ftp_question_is_not_forced_to_coach(self):
  self.assertNotEqual(_forced_tool_name('What was my FTP last year?'),'preview_training_plan');self.assertNotEqual(_forced_tool_name('Compare that race to my rides'),'preview_training_plan')
