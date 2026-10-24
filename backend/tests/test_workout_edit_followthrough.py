"""Reviewed block edits, cross-week carry-over and Garmin propagation, isolated DBs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from test_training_adjustments import fixture,NOW,TZ
from test_garmin_publication import FakeGarmin
from app.database import connect
from app.training import list_training,encoded
from app.training_coach import DEFAULT
from app.training_prescriptions import endurance
from app.training_adjustments import propose,save
from app.training_completion import benefit_coverage,adapt_missed_stimulus
from app.active_training import _program_workouts,review
from app.garmin_training_publish import preview,approve,run,view
from app.cycling_variants import select
from app.ai_chat import chat_stream


class FollowthroughTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'fixture.sqlite';fixture(self.path)
  self.workout=next(w for w in list_training(self.path)['workouts'] if w['scheduled_for'][:10]=='2026-10-19')
  self.set_definition(endurance('threshold',60,DEFAULT,today=NOW.date()))
 def set_definition(self,d):
  d={**d,'scheduled_date':'2026-10-19','time_unspecified':True,'training_block':{'phase':'Build specificity'}}
  with connect(self.path) as c:c.execute('UPDATE planned_workouts SET sport=?,definition_json=?,title=? WHERE id=?',(d['sport'],encoded(d),d['title'],self.workout['id']))
 def current(self):return next(w for w in list_training(self.path)['workouts'] if w['id']==self.workout['id'])
 def save(self,p):return save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
 def recorded_quality(self,identifier,day,kind='threshold',benefit='LACTATE_THRESHOLD',effort=6):
  d=endurance(kind,60,DEFAULT,today=NOW.date(),variant='split_threshold' if kind=='threshold' else None)
  with connect(self.path) as c:
   root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
   c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,completion_status) VALUES(?,?,'cycling','Past quality',?,?,'completed')",(identifier,root,day+'T07:00:00+00:00',encoded(d)))
   c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,raw_json) VALUES(?,'garmin_connect','cycling',?,3600,?)",(identifier,day+'T07:00:00+00:00',encoded({'trainingEffectLabel':benefit})))
   c.execute('INSERT INTO training_feedback(workout_id,activity_id,effort,soreness,pain_or_illness,updated_at) VALUES(?,?,?,1,0,?)',(identifier,identifier,effort,day+'T10:00:00+00:00'))
 def test_chat_preview_save_and_daily_review_preserve_exact_blocks(self):
  message='Change today cycling to 2 x 4 minutes, recovery to 3 minutes'
  before=list_training(self.path)
  with patch('app.training_adjustments.datetime',wraps=type(NOW)) as clock, patch('app.ai_chat._chatgpt_stream',side_effect=AssertionError('Unexpected provider request')):
   clock.now.return_value=NOW
   events=[json.loads(e) for e in chat_stream(message,path=self.path,timezone_name=TZ)]
  p=next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
  self.assertEqual(p['status'],'proposal',p);self.assertEqual(before,list_training(self.path))
  d=p['adjustments'][0]['changes']['definition']
  self.assertEqual([s['duration_seconds'] for s in d['steps'] if s['name'].startswith('Work interval')],[240,240])
  self.assertEqual(sum(s['duration_seconds'] for s in d['steps']),3600)
  self.save(p);review(self.path,TZ,NOW)
  self.assertEqual(self.current()['definition'],d)
  with self.assertRaises(ValueError):self.save(p)
 def test_targets_recovery_and_increase_are_checked_again_on_save(self):
  p=propose('Set today cycling work target to 5-6 RPE',self.path,NOW)
  self.assertEqual(p['status'],'proposal',p)
  self.assertTrue(all(s['target']['upper']==6 for s in p['adjustments'][0]['changes']['definition']['steps'] if s['name'].startswith('Work interval')))
  self.assertEqual(propose('Change today cycling to 3 x 6 minutes',self.path,NOW)['status'],'not_recommended')
  self.recorded_quality('past1','2026-10-08');self.recorded_quality('past2','2026-10-12')
  allowed=propose('Change today cycling work intervals to 7 minutes',self.path,NOW)
  self.assertEqual(allowed['status'],'proposal',allowed)
  with connect(self.path) as c:c.execute("INSERT INTO metric_readings(source_name,metric_type,value,unit,recorded_at) VALUES('garmin_export','sleep_score',30,'score','2026-10-19T03:00:00+00:00')")
  with self.assertRaises(ValueError):self.save(allowed)
 def test_ambiguous_invalid_partial_and_negated_edits_never_write(self):
  before=list_training(self.path)
  for message in ('Change today cycling to 3 x 30 minutes','Set today cycling work target to 180-200 W','Set today cycling to 2 x 4 minutes and recovery to banana','Set today cycling to 2 x 4 minutes and load to 20','Do not change today cycling reps to 1','Change today cycling sets to 2','Change today cycling to 0 x 4 minutes'):
   with self.subTest(message=message):self.assertNotEqual(propose(message,self.path,NOW)['status'],'proposal')
  self.assertEqual(before,list_training(self.path))
 def test_strength_explicit_exercise_changes_preserve_other_exercises(self):
  d={'sport':'strength','title':'Strength','duration_minutes':30,'warmup_minutes':5,'exercises':[{'id':'dumbbell_row','name':'Dumbbell row','sets':2,'repetitions':8,'rest_seconds':90,'load_target_kg':12.5,'load':'Keep two reps in reserve'},{'id':'dead_bug','name':'Dead bug','sets':2,'repetitions':8,'rest_seconds':90}]}
  self.set_definition(d)
  p=propose('Change today strength dumbbell row reps to 6, sets to 1, load to 10 kg, rest to 120 seconds',self.path,NOW)
  self.assertEqual(p['status'],'proposal',p);self.save(p)
  after=self.current()['definition'];self.assertEqual(after['exercises'][1],d['exercises'][1]);self.assertEqual(after['exercises'][0]['load_target_kg'],10)
  self.assertEqual(propose('Change today strength reps to 6',self.path,NOW)['status'],'needs_input')
  self.assertEqual(propose('Change today strength dumbbell row load to 30 kg',self.path,NOW)['status'],'not_recommended')
 def test_saved_block_edits_update_same_garmin_workout_with_readback(self):
  client=FakeGarmin();factory=lambda p:client
  def send():
   p=preview({'workout_ids':[self.workout['id']],'timezone':TZ},self.path,factory,NOW)
   approve(p['id'],self.path,factory,NOW);run(p['id'],self.path,factory)
   result=view(p['id'],self.path);self.assertEqual(result['status'],'verified',result);return result
  send();p=propose('Change today cycling to 2 x 4 minutes, recovery to 3 minutes',self.path,NOW)
  self.assertEqual(p['status'],'proposal',p);self.save(p);self.assertEqual(self.current()['publish_status'],'update_needed')
  updated=send();self.assertEqual(updated['items'][0]['action'],'update');self.assertEqual((client.creates,client.updates,client.schedules),(1,1,1))
  steps=client.workouts['101']['workoutSegments'][0]['workoutSteps']
  self.assertEqual([s['endConditionValue'] for s in steps if 'Work interval' in s['description']],[240,240])
  self.assertEqual(sum(s['endConditionValue'] for s in steps),3600)
 def test_cross_week_pending_stimulus_moves_only_one_existing_quality_slot(self):
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET completion_status='skipped' WHERE id=?",(self.workout['id'],))
   root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
   target=c.execute("SELECT * FROM planned_workouts WHERE scheduled_for LIKE '2026-10-23%'").fetchone()
   d=endurance('tempo',60,DEFAULT,today=NOW.date());d.update(scheduled_date='2026-10-26',time_unspecified=True,training_block={'phase':'Build specificity'})
   c.execute('UPDATE planned_workouts SET definition_json=?,scheduled_for=? WHERE id=?',(encoded(d),'2026-10-26T07:00:00+00:00',target['id']))
   state=json.loads(c.execute('SELECT state_json FROM active_training_program').fetchone()[0]);rows=_program_workouts(c,root)
   later=NOW+timedelta(days=6)
   pending=benefit_coverage(c,rows,TZ,later.date(),later)['pending_stimuli'];self.assertEqual(len(pending),1)
   changes,_=adapt_missed_stimulus(c,rows,state,later.date(),later,{'quality_allowed':True,'level':'normal'},{})
   self.assertEqual(len(changes),1);self.assertEqual(changes[0]['workout_id'],target['id'])
   rows=_program_workouts(c,root)
   self.assertEqual(adapt_missed_stimulus(c,rows,state,later.date(),later,{'quality_allowed':True,'level':'normal'},{}),([],[]))
 def test_unplanned_recording_resolves_pending_but_unknown_does_not(self):
  with connect(self.path) as c:
   c.execute("UPDATE planned_workouts SET completion_status='skipped' WHERE id=?",(self.workout['id'],))
   root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
   c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,raw_json) VALUES('extra','garmin_connect','cycling','2026-10-20T07:00:00+00:00',3600,'{}')")
   rows=_program_workouts(c,root);later=NOW+timedelta(days=3)
   self.assertTrue(benefit_coverage(c,rows,TZ,later.date(),later)['pending_stimuli'])
   c.execute('UPDATE activities SET raw_json=? WHERE id=?',(encoded({'trainingEffectLabel':'LACTATE_THRESHOLD'}),'extra'))
   self.assertFalse(benefit_coverage(c,rows,TZ,later.date(),later)['pending_stimuli'])
 def test_variant_selection_uses_category_tolerance_not_elapsed_weeks(self):
  with connect(self.path) as c:self.assertEqual(select(c,'threshold',NOW.date(),TZ)[0],'split_threshold')
  self.recorded_quality('one','2026-10-08',benefit='AEROBIC_BASE');self.recorded_quality('two','2026-10-12',effort=9)
  with connect(self.path) as c:self.assertEqual(select(c,'threshold',NOW.date(),TZ)[0],'split_threshold')
  self.recorded_quality('three','2026-10-14');self.recorded_quality('four','2026-10-16')
  with connect(self.path) as c:
   choice,evidence=select(c,'threshold',NOW.date(),TZ);self.assertEqual(choice,'sustained_threshold');self.assertEqual(evidence['tolerated_recordings'],2)
   self.assertEqual(select(c,'threshold',NOW.date(),TZ,False)[0],'split_threshold')
 def test_mixed_requests_clarify_both_tasks_without_silently_editing_or_logging(self):
  for message in ('I ate eggs, change today cycling to 2 x 4 minutes','Plot my sleep and change today workout reps to 1'):
   before=list_training(self.path)
   with patch('app.nutrition_chat.chat',side_effect=AssertionError('Unexpected meal action')),patch('app.training_adjustments.propose',side_effect=AssertionError('Unexpected partial edit')):
    events=[json.loads(e) for e in chat_stream(message,path=self.path,timezone_name=TZ)]
   self.assertEqual(events[-1]['type'],'complete');self.assertIn('combined request',events[1]['text']);self.assertEqual(before,list_training(self.path))
 def test_rolling_publication_applies_edited_blocks_once(self):
  from app.rolling_publication import window,sync,status
  client=FakeGarmin();factory=lambda p:client
  with connect(self.path) as c:
   root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0];ids=window(c,root,TZ,NOW)
  p=preview({'workout_ids':ids,'timezone':TZ,'enable_rolling':True},self.path,factory,NOW)
  approve(p['id'],self.path,factory,NOW);run(p['id'],self.path,factory)
  self.assertTrue(status(self.path)['enabled'])
  p=propose('Change today cycling to 2 x 4 minutes, recovery to 3 minutes',self.path,NOW);self.save(p)
  creates=client.creates;schedules=client.schedules
  with patch('app.active_training.review'):
   sync(self.path,factory,NOW);sync(self.path,factory,NOW)
  self.assertEqual(status(self.path)['status'],'up_to_date');self.assertEqual((client.creates,client.schedules,client.updates),(creates,schedules,1))
 def test_strength_edit_reaches_garmin_rep_load_and_rest_readback(self):
  d={'sport':'strength','title':'Strength','duration_minutes':30,'warmup_minutes':5,'exercises':[{'id':'dumbbell_row','name':'Dumbbell row','sets':2,'repetitions':8,'rest_seconds':90,'load_target_kg':12.5,'load':'Keep two reps in reserve'}]}
  self.set_definition(d);client=FakeGarmin();factory=lambda p:client
  def send():
   p=preview({'workout_ids':[self.workout['id']],'timezone':TZ},self.path,factory,NOW)
   approve(p['id'],self.path,factory,NOW);run(p['id'],self.path,factory)
   self.assertEqual(view(p['id'],self.path)['status'],'verified')
  send();p=propose('Change today strength dumbbell row reps to 6, load to 10 kg, rest to 120 seconds',self.path,NOW);self.save(p);send()
  steps=client.workouts['101']['workoutSegments'][0]['workoutSteps']
  work=[s for s in steps if s['endCondition']['conditionTypeKey']=='reps']
  self.assertEqual([(s['endConditionValue'],s['weightValue']) for s in work],[(6,10000),(6,10000)])
  self.assertEqual([s['endConditionValue'] for s in steps if s['stepType']['stepTypeKey']=='rest'],[120,120])
  self.assertEqual((client.creates,client.updates),(1,1))
