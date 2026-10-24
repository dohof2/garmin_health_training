"""Cross-service regressions for the first four roadmap workstreams; no live writes."""
import copy
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from test_training_adjustments import fixture,NOW,TZ
from test_garmin_publication import FakeGarmin
from app.database import connect,migrate
from app.training import list_training,encoded
from app.training_prescriptions import endurance
from app.training_coach import DEFAULT,read_brief
from app.training_adjustments import propose,save
from app.training_completion import reconcile,benefit_coverage,adapt_missed_stimulus
from app.active_training import _program_workouts,active_view
from app.activity_sections import plots,climbs
from app.garmin_workout_mapping import workout_payload,canonical,digest
from app.garmin_training_publish import preview,approve,run,view
from app.rolling_publication import window,sync,status,disable
from app.chat_routing import route
from app.ai_chat import chat_stream
from app.ai_tools import execute_tool


class RoadmapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite';fixture(self.path)
 def rows(self):
  with connect(self.path) as c:
   p=c.execute('SELECT * FROM active_training_program').fetchone()
   return p['plan_id'],_program_workouts(c,p['plan_id'])
 def add_activity(self,identifier='recorded',day='2026-10-19',benefit='AEROBIC_BASE',kind='indoor_cycling',seconds=1800):
  with connect(self.path) as c:c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,raw_json) VALUES(?,'garmin_connect',?,?,?,?)",(identifier,kind,day+'T08:00:00+00:00',seconds,json.dumps({'trainingEffectLabel':benefit})))
 def test_format_is_previewed_saved_and_reused(self):
  before=list_training(self.path);p=propose('For cycling steady endurance remove warm up and cool down for all future rides',self.path,NOW)
  self.assertEqual(p['status'],'proposal');self.assertEqual(list_training(self.path),before)
  old={w['id']:w for w in before['workouts']}
  for row in p['adjustments']:
   d=row['changes']['definition'];self.assertEqual(len(d['steps']),1);self.assertEqual(d['duration_minutes'],old[row['workout_id']]['definition']['duration_minutes'])
  save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
  b=read_brief(self.path)['brief'];self.assertTrue(b['continuous_endurance'])
  self.assertEqual(len(endurance('endurance',80,b)['steps']),1)
  self.assertGreater(len(endurance('threshold',60,b)['steps']),1)
  with self.assertRaises(ValueError):save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
 def test_format_change_is_atomic_on_stale_session(self):
  p=propose('Steady cycling endurance without warmup or cooldown',self.path,NOW)
  with connect(self.path) as c:c.execute('UPDATE planned_workouts SET revision=revision+1 WHERE id=?',(p['adjustments'][0]['workout_id'],))
  with self.assertRaises(ValueError):save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
  self.assertFalse(read_brief(self.path)['brief']['continuous_endurance'])
 def test_date_only_completion_uses_local_day_and_virtual_rides(self):
  self.add_activity(kind='virtual_ride',seconds=900);root,rows=self.rows()
  with connect(self.path) as c:changes,warnings=reconcile(c,rows,TZ,NOW+timedelta(hours=5))
  self.assertEqual(len(changes),1);self.assertFalse(warnings)
  result=active_view(self.path,TZ,NOW+timedelta(hours=5));self.assertEqual(len(result['completed_workouts']),1)
  self.assertEqual(result['completed_workouts'][0]['feedback']['activity_id'],'recorded')
  root,rows=self.rows()
  with connect(self.path) as c:self.assertEqual(reconcile(c,rows,TZ,NOW+timedelta(hours=5)),([],[]))
 def test_multiple_recordings_are_not_guessed(self):
  self.add_activity();self.add_activity('second');root,rows=self.rows()
  with connect(self.path) as c:changes,warnings=reconcile(c,rows,TZ,NOW+timedelta(hours=5))
  self.assertFalse(changes);self.assertTrue(warnings)
 def test_one_recording_cannot_complete_multiple_same_day_slots(self):
  self.add_activity();root,rows=self.rows();row=next(r for r in rows if r['scheduled_for'][:10]=='2026-10-19')
  with connect(self.path) as c:
   c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',('duplicate-slot',root,'cycling','Second ride',row['scheduled_for'],row['definition_json']))
  root,rows=self.rows()
  with connect(self.path) as c:changes,warnings=reconcile(c,rows,TZ,NOW+timedelta(hours=5))
  self.assertFalse(changes);self.assertTrue(warnings)
 def test_stimulus_is_separate_from_completion_and_unknown_stays_unknown(self):
  self.add_activity(benefit='TEMPO');root,rows=self.rows()
  with connect(self.path) as c:reconcile(c,rows,TZ,NOW+timedelta(hours=5))
  root,rows=self.rows()
  with connect(self.path) as c:coverage=benefit_coverage(c,rows,TZ,NOW.date())
  self.assertEqual(coverage['completed'][0]['intended'],'base');self.assertEqual(coverage['completed'][0]['achieved'],'tempo');self.assertFalse(coverage['completed'][0]['matches_intent'])
  with connect(self.path) as c:c.execute("UPDATE activities SET raw_json='{}' WHERE id='recorded'")
  with connect(self.path) as c:self.assertIsNone(benefit_coverage(c,rows,TZ,NOW.date())['completed'][0]['matches_intent'])
 def test_variant_structures_targets_sources_and_exact_durations(self):
  from app.cycling_variants import options
  b={**DEFAULT,'continuous_endurance':True,'ftp_watts':200,'calibration':{'power_access':'both','ftp_confirmed_on':'2026-10-01'}}
  for kind in ('endurance','threshold','sprint','anaerobic'):
   definitions=[endurance(kind,60,b,today=NOW.date(),variant=v['id']) for v in options(kind)]
   self.assertEqual(len(definitions),2);self.assertNotEqual(definitions[0]['steps'],definitions[1]['steps'])
   for d in definitions:self.assertEqual(sum(s['duration_seconds'] for s in d['steps']),3600);self.assertTrue(d['sources'])
  with self.assertRaises(ValueError):endurance('sprint',60,b,variant='made-up')
 def test_strength_sets_reps_load_rest_and_readback_comparison(self):
  d={'sport':'strength','title':'Invented strength','duration_minutes':30,'warmup_minutes':5,'exercises':[{'id':'dumbbell_row','name':'Dumbbell row','sets':2,'repetitions':8,'rest_seconds':90,'load_target_kg':12.5,'load':'Leave 2 repetitions in reserve'}]}
  payload,warnings=workout_payload(d,'test');steps=payload['workoutSegments'][0]['workoutSteps']
  work=[s for s in steps if s['endCondition']['conditionTypeKey']=='reps'];self.assertEqual(len(work),2);self.assertEqual(work[0]['endConditionValue'],8);self.assertEqual(work[0]['weightValue'],12500)
  changed=copy.deepcopy(payload);changed['workoutSegments'][0]['workoutSteps'][1]['weightValue']=20000
  self.assertNotEqual(digest(canonical(payload)),digest(canonical(changed)))
  d['exercises'][0]['id']='chair_squat'
  with self.assertRaisesRegex(ValueError,'Unsupported exact'):workout_payload(d,'test')
 def test_rolling_requires_initial_approved_window_and_repeated_sync_is_idempotent(self):
  client=FakeGarmin();factory=lambda p:client;root,_=self.rows()
  with connect(self.path) as c:ids=window(c,root,TZ,NOW)
  p=preview({'workout_ids':ids,'timezone':TZ,'enable_rolling':True},self.path,factory,NOW)
  self.assertFalse(status(self.path)['enabled']);approve(p['id'],self.path,factory,NOW);self.assertFalse(status(self.path)['enabled'])
  run(p['id'],self.path,factory);self.assertEqual(view(p['id'],self.path)['status'],'verified');self.assertTrue(status(self.path)['enabled'])
  creates=client.creates;schedules=client.schedules
  with patch('app.active_training.review'):
   sync(self.path,factory,NOW);sync(self.path,factory,NOW)
  self.assertEqual(client.creates,creates);self.assertEqual(client.schedules,schedules)
  self.assertEqual(status(self.path)['status'],'up_to_date')
  disable(self.path);self.assertFalse(status(self.path)['enabled'])
 def test_rolling_refuses_partial_window_and_account_switch(self):
  client=FakeGarmin();factory=lambda p:client;root,rows=self.rows()
  with self.assertRaises(ValueError):preview({'workout_ids':[rows[0]['id']],'timezone':TZ,'enable_rolling':True},self.path,factory,NOW)
  with connect(self.path) as c:ids=window(c,root,TZ,NOW)
  p=preview({'workout_ids':ids,'timezone':TZ,'enable_rolling':True},self.path,factory,NOW);approve(p['id'],self.path,factory,NOW);run(p['id'],self.path,factory)
  client.display_name='another-account';creates=client.creates;sync(self.path,factory,NOW)
  self.assertEqual(status(self.path)['status'],'attention');self.assertEqual(creates,client.creates)
 def test_shared_chat_roles_and_nutrition_do_not_call_training_adjustments(self):
  for text,role in [('Plot weight and sleep','assistant'),('How many calories burned?','assistant'),('I ate eggs','nutrition'),('Make my endurance ride easier','trainer'),('My sleep was terrible, make my workout easier','trainer'),('How was my sleep?','assistant')]:self.assertEqual(route(text),role)
  self.assertEqual(route('yes','auto','nutrition'),'nutrition');self.assertEqual(route('I ate eggs','trainer'),'trainer')
  with patch('app.nutrition_chat.chat',return_value={'reply':'Review invented eggs','ingredients':[],'context_date':'2026-10-19'}),patch('app.training_adjustments.propose',side_effect=AssertionError('Wrong route')):
   events=[json.loads(line) for line in chat_stream('I ate eggs',path=self.path,timezone_name=TZ)]
  self.assertEqual(events[0]['chat_role'],'nutrition');self.assertEqual(events[-1]['type'],'complete')
 def add_stream(self,missing=False):
  self.add_activity('stream',seconds=300)
  origin=datetime(2026,10,19,8,tzinfo=timezone.utc)
  with connect(self.path) as c:
   for t in range(301):
    elevation=-20+t*.5 if t<=200 else 80-(t-200)
    c.execute('INSERT INTO activity_samples(activity_id,recorded_at,elevation_meters,power_watts,speed_mps,cadence_rpm,raw_json) VALUES(?,?,?,?,?,?,?)',('stream',(origin+timedelta(seconds=t)).isoformat(),elevation,None if missing and t==100 else 0 if t==10 else 200,4,80,json.dumps({'distance':t*4})))
 def test_climb_uses_timestamp_weighted_power_and_preserves_zero(self):
  self.add_stream();result=climbs({'activity_id':'stream'},self.path);self.assertEqual(result['candidate_count'],1)
  climb=result['candidates'][0];self.assertGreater(climb['elapsed_seconds'],190);self.assertLess(climb['average_power_watts'],200);self.assertGreater(climb['average_power_watts'],198)
  self.assertIsNotNone(climb['start_distance_km']);self.assertEqual(climb['power_coverage_fraction'],1)
 def test_missing_power_does_not_become_full_climb_average(self):
  self.add_stream(missing=True);result=climbs({'activity_id':'stream'},self.path)['candidates'][0]
  self.assertIsNone(result['average_power_watts']);self.assertLess(result['power_coverage_fraction'],1);self.assertIsNotNone(result['covered_average_power_watts'])
 def test_plot_axes_keep_recorded_distances_negative_altitude_and_gaps(self):
  self.add_stream();result=plots('stream',self.path);self.assertTrue(result['distance_available']);self.assertLess(result['traces']['elevation']['points'][0]['y'],0)
  self.assertEqual(result['traces']['speed']['points'][20]['distance'],.08)
  with connect(self.path) as c:c.execute("UPDATE activity_samples SET power_watts=NULL WHERE activity_id='stream' AND id=(SELECT min(id)+10 FROM activity_samples WHERE activity_id='stream')")
  self.assertGreater(len({p['segment'] for p in plots('stream',self.path)['traces']['power']['points']}),1)
 def test_climb_followup_retains_activity_without_provider_or_lap_substitution(self):
  self.add_stream()
  with patch('app.ai_chat._chatgpt_stream',side_effect=AssertionError('Unexpected external inference')):
   events=[json.loads(line) for line in chat_stream('there is a chunk of up hill what was the avg power there and how long was it?',path=self.path,timezone_name=TZ,ride_context='stream')]
  self.assertEqual(events[-1]['type'],'complete');self.assertTrue(any(e.get('evidence',{}).get('activity_id')=='stream' for e in events));self.assertIn('Time-weighted average power',next(e['text'] for e in events if e['type']=='delta'))
 def test_app_data_discovers_metrics_without_account_tables(self):
  result=execute_tool('query_app_data',{'dataset':'health','start_date':'2026-10-01','end_date':'2026-10-24'},self.path)
  self.assertIn('available_metrics',result)
  with self.assertRaises(ValueError):execute_tool('query_app_data',{'dataset':'chatgpt_auth','start_date':'2026-10-01','end_date':'2026-10-24'},self.path)

 def test_missed_stimulus_reassigns_one_existing_slot_and_recovery_defers(self):
  self.add_activity(benefit='AEROBIC_BASE');root,rows=self.rows()
  with connect(self.path) as c:
   monday=next(w for w in rows if w['scheduled_for'][:10]=='2026-10-19')
   friday=next(w for w in rows if w['scheduled_for'][:10]=='2026-10-23')
   for row,kind in ((monday,'threshold'),(friday,'tempo')):
    d=endurance(kind,60,DEFAULT,today=NOW.date());d.update({'time_unspecified':True,'scheduled_date':row['scheduled_for'][:10],'training_block':{'phase':'Build specificity','week':5}})
    c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(d),row['id']))
  root,rows=self.rows();later=NOW+timedelta(days=1,hours=5)
  with connect(self.path) as c:
   reconcile(c,rows,TZ,later)
   state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0])
  root,rows=self.rows()
  with connect(self.path) as c:
   changes,warnings=adapt_missed_stimulus(c,rows,state,later.date(),later,{'quality_allowed':False,'level':'recovery'},{})
   self.assertFalse(changes);self.assertTrue(warnings)
   changes,warnings=adapt_missed_stimulus(c,rows,state,later.date(),later,{'quality_allowed':True,'level':'normal'},{})
   self.assertEqual(len(changes),1)
   changed=c.execute('SELECT definition_json FROM planned_workouts WHERE id=?',(changes[0]['workout_id'],)).fetchone()[0]
   self.assertEqual(json.loads(changed)['workout_kind'],'threshold')
   self.assertEqual(json.loads(changed)['duration_minutes'],60)
 def test_turning_off_rolling_before_initial_worker_prevents_enable(self):
  client=FakeGarmin();factory=lambda p:client;root,_=self.rows()
  with connect(self.path) as c:ids=window(c,root,TZ,NOW)
  p=preview({'workout_ids':ids,'timezone':TZ,'enable_rolling':True},self.path,factory,NOW);approve(p['id'],self.path,factory,NOW)
  disable(self.path);run(p['id'],self.path,factory)
  self.assertFalse(status(self.path)['enabled'])
 def test_all_query_views_are_read_only(self):
  with connect(self.path) as c:before=list(c.iterdump())
  for dataset in ('profile','sync','nutrition','health','archive'):
   execute_tool('query_app_data',{'dataset':dataset,'start_date':'2026-10-19','end_date':'2026-10-19'},self.path)
  with connect(self.path) as c:self.assertEqual(before,list(c.iterdump()))
 def test_yesterday_food_query_reads_log_without_estimating_a_new_meal(self):
  with patch('app.nutrition_chat.chat',side_effect=AssertionError('Read question must not estimate food')):
   events=[json.loads(line) for line in chat_stream('What did I eat yesterday?',path=self.path,timezone_name=TZ)]
  self.assertEqual(events[-1]['type'],'complete');self.assertTrue(any(e.get('evidence',{}).get('dataset')=='nutrition' for e in events))

 def test_format_scope_and_yes_followups_retain_the_original_request(self):
  from app.workout_format import resolve_followup,requested
  history=[{'role':'user','content':"In my steady edurance I don't need warm up and cool down it is very easy as is"}]
  for followup in ('in general for cycling edurance steady','also for the pkanning ahead','yes apply it'):
   resolved=resolve_followup(followup,history)
   self.assertTrue(requested(resolved));self.assertEqual(propose(resolved,self.path,NOW)['status'],'proposal')
   history.append({'role':'user','content':followup})
  self.assertEqual(resolve_followup('no do not apply it',history),'no do not apply it')
