"""Shared sprint/anaerobic planner acceptance; isolated synthetic records only."""
import json,tempfile,unittest
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from app.database import connect,migrate
from app.training_coach import DEFAULT,preview,approve
from app.training_prescriptions import endurance,cycling_mix,advanced_cycling_eligible
from app.training import save_preferences,training_context
from app.active_training import review,read_active,suggest_today
TZ='Asia/Jerusalem';INITIAL=datetime(2026,10,19,7,tzinfo=timezone.utc);NOW=INITIAL+timedelta(weeks=4)
BRIEF={**DEFAULT,'goal':'ftp','duration_confirmed':True,'horizon_weeks':12,'program_start':'2026-10-19','ftp_watts':250,'calibration':{'power_access':'both','ftp_confirmed_on':'2026-10-16','hr_sensor':False}}
ANS={'sports':['cycling'],'priority':'endurance','experience':{'cycling':'experienced'},'equipment':['bike'],'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False,'week_schedule':[{'weekday':day,'mode':'training' if day in (0,2,4,6) else 'rest','total_limit_minutes':None,'activities':[{'slot_id':str(day),'sport':'cycling','max_minutes':300 if day==4 else 90}] if day in (0,2,4,6) else []} for day in range(7)]}
class AdvancedCyclingTests(unittest.TestCase):
 def test_prescriptions_have_distinct_efforts_recovery_and_exact_time(self):
  for kind,seconds in [('sprint',8),('anaerobic',30)]:
   workout=endurance(kind,60,BRIEF,today=NOW.date())
   work=[step for step in workout['steps'] if step['name'].startswith(('Sprint','Anaerobic effort'))]
   self.assertEqual(len(work),4);self.assertTrue(all(step['duration_seconds']==seconds for step in work))
   self.assertTrue(all(step['target']['type']=='perceived_effort' and step['power_reference_fractions'] is None for step in work))
   self.assertTrue(all(step['duration_seconds']==240 for step in workout['steps'] if step['name'].startswith('Recovery')))
   self.assertEqual(sum(step['duration_seconds'] for step in workout['steps']),3600)
   self.assertEqual(endurance(kind,30,BRIEF,today=NOW.date())['workout_kind'],'endurance')
   with self.assertRaises(ValueError):endurance(kind,60,BRIEF,'running',today=NOW.date())
 def test_loading_training_readiness_does_not_write_under_plan_review_lock(self):
  from app.readiness import get_readiness_settings
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'qc.sqlite';migrate(path);expected=get_readiness_settings(path)
   with connect(path) as writer:
    writer.execute('BEGIN IMMEDIATE')
    self.assertEqual(get_readiness_settings(path),expected)
 def test_focus_weights_cover_all_supported_stimuli_without_claiming_time_percentages(self):
  ftp=cycling_mix(BRIEF);distance=cycling_mix({**BRIEF,'goal':'endurance'});race=cycling_mix({**BRIEF,'goal':'race','event_name':'Criterium'})
  self.assertNotEqual(ftp['quality_session_weights'],distance['quality_session_weights'])
  self.assertNotEqual(ftp['quality_session_weights'],race['quality_session_weights'])
  for mix in (ftp,distance,race):
   self.assertTrue({'threshold','tempo','vo2','sprint','anaerobic'}<=set(mix['quality_session_weights']))
   self.assertEqual(sum(mix['quality_session_weights'].values()),mix['rotation_length'])
   self.assertEqual(mix['quality_session_limit'],1)
 def test_global_preview_activation_review_and_plan_today_use_the_same_eligibility(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'qc.sqlite';migrate(path)
   with connect(path) as c:
    for window,end in enumerate((date(2026,10,17),date(2026,11,14))):
     for index in range(8):
      day=end-timedelta(days=index//2*7+index%2)
      c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds) VALUES(?,'garmin_export','cycling',?,9000)",(f'{window}-{index}',day.isoformat()+'T07:00:00+00:00'))
   save_preferences(ANS,0,path,INITIAL)
   p=preview(BRIEF,INITIAL.date(),TZ,path,INITIAL)
   self.assertEqual(p['status'],'ready',p['questions']);self.assertFalse(any(s['definition'].get('workout_kind') in ('sprint','anaerobic') for s in p['sessions']))
   approved=approve(p['brief'],INITIAL.date(),TZ,p['fingerprint'],path,INITIAL)
   root=approved['plans'][0]['id']
   with connect(path) as c:
    for index in range(2):
     day=NOW-timedelta(days=4+index*3);wid=f'completed-quality-{index}'
     c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json,completion_status) VALUES(?,?,'cycling','Completed intervals',?,?,'completed')",(wid,root,day.isoformat(),json.dumps(endurance('threshold',60,BRIEF,today=day.date()))))
     c.execute('INSERT INTO training_feedback(workout_id,effort,soreness,pain_or_illness,updated_at) VALUES(?,5,1,0,?)',(wid,day.isoformat()))
    self.assertTrue(advanced_cycling_eligible(c,NOW,'experienced',4,'Build specificity',True))
    for experience,stage,phase,allowed in [('new',4,'Build specificity',True),('experienced',0,'Establish consistency',True),('experienced',7,'Recovery / review',True),('experienced',4,'Build specificity',False)]:self.assertFalse(advanced_cycling_eligible(c,NOW,experience,stage,phase,allowed))
   for goal in ('ftp','endurance','general','race'):
    goal_brief={**BRIEF,'goal':goal,**({'event_name':'Criterium','target_date':'2027-01-01'} if goal=='race' else {})}
    p=preview(goal_brief,NOW.date(),TZ,path,NOW,replace_plan_id=root)
    self.assertEqual(p['status'],'ready',p['questions']);self.assertEqual(p['volume_estimates']['cycling']['increment_minutes'],0);self.assertLessEqual(p['weekly_minutes']['cycling'],p['volume_estimates']['cycling']['baseline_minutes']);self.assertTrue(any(s['definition'].get('workout_kind')=='sprint' for s in p['sessions']),(goal,[(s['title'],s['definition']['duration_minutes']) for s in p['sessions']],p['warnings']))
   anaerobic=preview(BRIEF,NOW.date()+timedelta(weeks=2),TZ,path,NOW,replace_plan_id=root)
   self.assertTrue(any(s['definition'].get('workout_kind')=='anaerobic' for s in anaerobic['sessions']))
   recovery=preview(BRIEF,NOW.date()+timedelta(weeks=3),TZ,path,NOW,replace_plan_id=root)
   self.assertFalse(any(s['definition'].get('workout_kind') in ('sprint','anaerobic') for s in recovery['sessions']))
   p=preview(BRIEF,NOW.date(),TZ,path,NOW,replace_plan_id=root)
   approve(p['brief'],NOW.date(),TZ,p['fingerprint'],path,NOW,replace_plan_id=root)
   readiness={'latest':{'date':NOW.date().isoformat(),'score':80,'status':'complete','groups':[]}}
   with patch('app.readiness.readiness_history',return_value=readiness):
    active=review(path,TZ,NOW,trigger='manual')
    sprint=next(s for s in active['workouts'] if s['definition'].get('workout_kind')=='sprint')
    self.assertEqual(sprint['scheduled_for'][:10],NOW.date().isoformat())
    suggestion=suggest_today({'mode':'plan','minutes':60,'sport':'cycling','workout_id':sprint['id'],'timezone':TZ},path,NOW)
    self.assertEqual(suggestion['session']['workout_kind'],'sprint')
    short=suggest_today({'mode':'plan','minutes':30,'sport':'cycling','workout_id':sprint['id'],'timezone':TZ},path,NOW)
    self.assertEqual(short['session']['workout_kind'],'endurance')
    with connect(path) as c:c.execute("UPDATE training_feedback SET effort=9,notes='too hard',updated_at=? WHERE workout_id='completed-quality-0'",(NOW.isoformat(),))
    changed=review(path,TZ,NOW,trigger='manual')
    self.assertFalse(any(s['definition'].get('workout_kind') in ('sprint','anaerobic') for s in changed['workouts']))
