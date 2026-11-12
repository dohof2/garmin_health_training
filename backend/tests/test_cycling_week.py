"""Weekly mix contracts: actual rides, spacing, recovery and retained remote IDs."""
import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.cycling_week import assignments,reconcile,QUALITY
from app.training import save_preferences
from app.training_coach import preview,approve
from app.training_prescriptions import endurance,advanced_cycling_eligible
from test_advanced_cycling import BRIEF,INITIAL,TZ
from test_long_ride_allocation import preferences

DAY=INITIAL.date()
NORMAL={'level':'normal','quality_allowed':True,'adverse_feedback':False}
FOCUS={'status':'unavailable','categories':{}}

class CyclingWeekTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
 def entries(self):
  return [{'id':str(day),'sport':'cycling','day':DAY+timedelta(days=day),'mutable':True,'definition':endurance('long_endurance' if day==4 else 'endurance',120 if day==4 else 60,BRIEF,today=DAY)} for day in (0,2,4,6)]
 def assign(self,c,entries=None,**kw):
  args=dict(week=DAY,today=DAY,now=INITIAL,tz=TZ,brief=BRIEF,block={'phase':'Establish consistency'},recovery=NORMAL,focus=FOCUS)
  args.update(kw);return assignments(c,entries or self.entries(),**args)
 def test_two_separated_intervals_long_and_base_without_old_gates(self):
  with connect(self.path) as c:
   targets,evidence=self.assign(c)
   self.assertEqual([key for key,kind in targets.items() if kind in QUALITY],['0','2'])
   self.assertEqual(targets['4'],'long_endurance');self.assertEqual(targets['6'],'endurance')
   self.assertEqual(evidence['selected_intervals'],2)
   self.assertTrue(advanced_cycling_eligible(c,INITIAL,'regular',0,'Establish consistency',True))
   self.assertFalse(advanced_cycling_eligible(c,INITIAL,'experienced',8,'Recovery / review',True))
   self.assertFalse(advanced_cycling_eligible(c,INITIAL,'experienced',8,'Build specificity',False))
 def test_recovery_readiness_and_limited_slots_reduce_aim(self):
  with connect(self.path) as c:
   targets,_=self.assign(c,block={'phase':'Recovery / review'})
   self.assertTrue(all(k=='endurance' for k in targets.values()))
   targets,_=self.assign(c,block={'phase':'Recovery / review'},recovery={**NORMAL,'level':'recovery','quality_allowed':False})
   self.assertEqual(targets['0'],'recovery')
   self.assertEqual(targets['2'],'endurance')
   targets,_=self.assign(c,recovery={**NORMAL,'level':'easy','quality_allowed':False})
   self.assertNotIn(targets['0'],QUALITY)
   targets,_=self.assign(c,recovery={**NORMAL,'adverse_feedback':True})
   self.assertFalse(any(k in QUALITY for k in targets.values()))
   targets,_=self.assign(c,self.entries()[1:])
   self.assertEqual(sum(k in QUALITY for k in targets.values()),2)
   self.assertNotIn('long_endurance',targets.values())
 def test_recorded_unplanned_hard_ride_reserves_slot(self):
  with connect(self.path) as c:
   c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES('actual','garmin_export','cycling','2026-10-19T02:00:00+00:00',3600)")
   with patch('app.ride_comparison.training_benefit',return_value={'source_label':'LACTATE_THRESHOLD'}):
    targets,evidence=self.assign(c,self.entries()[1:])
   self.assertEqual(evidence['recorded_hard_this_week'],1)
   self.assertEqual(sum(k in QUALITY for k in targets.values()),1)
   self.assertNotEqual(targets['2'],'threshold')
 def test_current_load_focus_influences_choice_missing_focus_has_no_fake_zero(self):
  focus={'status':'current','categories':{'high_aerobic':{'position':'above'},'anaerobic':{'position':'below'}}}
  with connect(self.path) as c:
   targets,_=self.assign(c,focus=focus)
   self.assertIn(targets['2'],('sprint','anaerobic'))
   self.assertIn(targets['0'],('threshold','tempo','vo2'))
   plain,_=self.assign(c)
   self.assertEqual(targets['4'],plain['4'])
   focused,_=self.assign(c,self.entries()[:2],focus=focus)
   plain,_=self.assign(c,self.entries()[:2])
   self.assertIn(focused['0'],('sprint','anaerobic'))
   self.assertIn(plain['0'],('threshold','tempo','vo2'))
 def test_two_actual_hard_rides_prevent_extra_intervals(self):
  with connect(self.path) as c:
   for i in range(2):
    day=DAY+timedelta(days=i)
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,3600)",(str(i),day.isoformat()+'T02:00:00+00:00'))
   now=INITIAL+timedelta(days=2)
   with patch('app.ride_comparison.training_benefit',return_value={'source_label':'LACTATE_THRESHOLD'}):
    targets,evidence=self.assign(c,self.entries()[1:],today=now.date(),now=now)
   self.assertEqual(evidence['recorded_hard_this_week'],2)
   self.assertFalse(any(kind in QUALITY for kind in targets.values()))
 def test_fixed_race_in_another_sport_protects_adjacent_days(self):
  event={'id':'event','sport':'running','day':DAY+timedelta(days=1),'mutable':False,'definition':{'fixed_commitment':True,'is_race':True,'duration_minutes':60}}
  with connect(self.path) as c:targets,_=self.assign(c,[event]+self.entries())
  self.assertNotIn(targets['0'],QUALITY);self.assertNotIn(targets['2'],QUALITY)
 def test_quality_spacing_carries_across_week_boundary(self):
  previous={'id':'sunday','sport':'cycling','day':DAY-timedelta(days=1),'mutable':False,'definition':endurance('anaerobic',60,BRIEF,today=DAY)}
  with connect(self.path) as c:
   targets,_=self.assign(c,[previous]+self.entries(),today=DAY-timedelta(days=2))
   self.assertNotIn(targets['0'],QUALITY)
   self.assertEqual(sum(k in QUALITY for k in targets.values()),2)
 def test_next_day_strength_does_not_block_real_preview(self):
  answers=preferences();answers['week_schedule'][4]['activities'][0]['min_minutes']=120
  answers['weekly_caps']={'cycling':{'range_min_minutes':300,'max_minutes':330}}
  with connect(self.path) as c:
   for i in range(12):
    day=DAY-timedelta(days=2+i*2)
    c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,7200)",(str(i),day.isoformat()+'T07:00:00+00:00'))
  save_preferences(answers,0,self.path,INITIAL)
  with patch('app.readiness.readiness_history',return_value={'latest':{'date':DAY.isoformat(),'score':80,'groups':[]}}):
   plan=preview(BRIEF,DAY,TZ,self.path,INITIAL)
  self.assertEqual(plan['status'],'ready',plan['questions'])
  rides=[s for s in plan['sessions'] if s['sport']=='cycling']
  self.assertEqual(sum(s['definition']['workout_kind'] in QUALITY for s in rides),2)
  self.assertEqual(next(s['definition']['duration_minutes'] for s in rides if s['scheduled_for'][:10]=='2026-10-23'),120)
  self.assertEqual(len(rides),4)
 def test_published_sessions_update_in_place_and_repeated_reconcile_is_stable(self):
  from test_garmin_publication import FakeGarmin
  from app.garmin_training_publish import account,preview as publication_preview,approve as publication_approve,run,view
  from app.garmin_workout_mapping import workout_payload,canonical,digest
  client=FakeGarmin();account_key=account(client)[0]
  with connect(self.path) as c:
   c.execute("INSERT INTO training_plans(id,name,status,starts_on,ends_on,context_json) VALUES('root','test','active','2026-10-19','2026-11-30','{}')")
   for e in self.entries():
    remote=str(100+int(e['id']));calendar=str(200+int(e['id']));identity='workout:'+e['id']
    payload,_=workout_payload(e['definition'],'training-app:'+digest(identity)[:24])
    client.workouts[remote]={**payload,'workoutId':int(remote)}
    client.calendar[calendar]={'workoutScheduleId':int(calendar),'workoutId':int(remote),'date':e['day'].isoformat()}
    c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,publish_status,garmin_workout_id) VALUES(?,'root','cycling','Base',?,?,'published',?)",(e['id'],e['day'].isoformat()+'T12:00:00+03:00',json.dumps(e['definition']),remote))
    c.execute("INSERT INTO garmin_publication_links(account_key,identity_key,workout_id,remote_workout_id,remote_schedule_id,verified_hash,scheduled_date,verified_payload_json) VALUES(?,?,?,?,?,?,?,?)",(account_key,identity,e['id'],remote,calendar,digest(canonical(payload)),e['day'].isoformat(),json.dumps(payload)))
   state={'brief':BRIEF,'starts_on':DAY.isoformat(),'timezone':TZ}
   def rows():return [dict(r) for r in c.execute('SELECT * FROM planned_workouts')]
   reconcile(c,rows(),state,DAY,INITIAL,NORMAL,FOCUS,preferences())
   result=rows();self.assertEqual(sum(json.loads(r['definition_json'])['workout_kind'] in QUALITY for r in result),2)
   self.assertTrue(all(r['garmin_workout_id']==str(100+int(r['id'])) for r in result))
   self.assertTrue(all(r['publish_status']=='update_needed' for r in result))
   self.assertEqual(reconcile(c,rows(),state,DAY,INITIAL,NORMAL,FOCUS,preferences()),[])
   self.assertEqual(c.execute('SELECT COUNT(*) FROM planned_workouts').fetchone()[0],4)
  proposal=publication_preview({'workout_ids':['0','2','4','6'],'timezone':TZ},self.path,lambda p:client,INITIAL)
  self.assertFalse(proposal['blocked'])
  updates=[i['action'] for i in proposal['items']].count('update')
  self.assertGreaterEqual(updates,2)
  self.assertTrue(all(i['action'] in ('update','unchanged') for i in proposal['items']))
  publication_approve(proposal['id'],self.path,lambda p:client,INITIAL)
  run(proposal['id'],self.path,lambda p:client)
  self.assertEqual(view(proposal['id'],self.path)['status'],'verified',view(proposal['id'],self.path))
  self.assertEqual(client.creates,0);self.assertEqual(client.schedules,0);self.assertEqual(client.updates,updates)
