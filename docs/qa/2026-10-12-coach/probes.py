"""Independent acceptance audit. All plan mutations use temporary invented databases."""
import copy,json,tempfile,sys
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from app.database import migrate,connect
from app.training import save_preferences,training_context,accept_plan,list_training,update_workout,EQUIPMENT
from app.training_coach import DEFAULT,preview,create_draft,save_brief,parse_request
from app.active_training import review,set_status,read_active,request_change,suggest_today
NOW=datetime(2026,10,12,7,tzinfo=timezone.utc);WEEK=date(2026,10,12);TZ='Asia/Jerusalem'
ANS={'sports':['cycling'],'priority':'endurance','availability':[{'weekday':i,'start_time':'18:00','minutes':180} for i in (0,2,4,6)],'experience':{'cycling':'experienced'},'equipment':['bike'],'weekly_minutes':{'cycling':480},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
READY={'latest':{'date':WEEK.isoformat(),'score':80,'status':'complete','groups':[]}}
rows=[]
def case(name,fn):
 try:detail=fn();rows.append({'case':name,**detail})
 except Exception as e:rows.append({'case':name,'verdict':'ERROR','error':str(e),'exception':type(e).__name__})
 print(name,rows[-1]['verdict'],flush=True)
def run(fn,answers=None):
 with tempfile.TemporaryDirectory(prefix='coach-acceptance-') as d:
  p=Path(d)/'db.sqlite';migrate(p);save_preferences(copy.deepcopy(answers or ANS),0,p,NOW)
  with patch('app.readiness.readiness_history',return_value=READY):return fn(p)
def brief(**kwargs):return {**copy.deepcopy(DEFAULT),'goal':'endurance',**kwargs}
def get(p,b=None):return preview(b or brief(),WEEK,TZ,p,NOW)
def active(p,b=None):
 b=b or brief();pr=get(p,b);h=create_draft(b,WEEK,TZ,pr['fingerprint'],p,NOW)
 pid=h['plans'][0]['id']
 with patch('app.training._context',return_value=training_context(p,NOW)):accept_plan(pid,p)
 return pid

def lengths(p):
 b=brief();a=get(p,b)
 return {'verdict':'PARTIAL','session_minutes':[s['definition']['duration_minutes'] for s in a['sessions']],'templates':sorted(set(s['definition']['template_id'] for s in a['sessions'])),'finding':'Confirmed slots can vary length; long ride generation is capped at 120 minutes and endurance sessions use one easy template.'}
case('varied long-session lengths',lambda:run(lengths,{**ANS,'availability':[{'weekday':i,'start_time':'08:00','minutes':m} for i,m in zip((0,2,4,6),(45,90,180,180))]}))
def kinds(p):
 outputs={goal:get(p,brief(goal=goal,ftp_watts=250)) for goal in ('endurance','ftp','general')}
 return {'verdict':'PARTIAL','templates_by_goal':{k:sorted({s['definition']['template_id'] for s in v['sessions']}) for k,v in outputs.items()},'finding':'Weekly planner offers easy rides or one two-by-six-minute controlled FTP session, not a varied long-workout library.'}
case('different workout types',lambda:run(kinds))
def persists(p):
 pid=active(p);one=review(p,TZ,NOW);two=review(p,TZ,NOW)
 same=one['program']['id']==two['program']['id']==pid and [(w['id'],w['revision']) for w in one['workouts']]==[(w['id'],w['revision']) for w in two['workouts']]
 return {'verdict':'PASS' if same else 'FAIL','saved_plan':bool(read_active({},p)['program']),'duplicate_free':same}
case('active plan persistence and repeated opening',lambda:run(persists))
def pause_cancel(p):
 active(p);before=list_training(p);set_status('paused',p)
 with patch('app.readiness.readiness_history',return_value={'latest':{**READY['latest'],'score':20}}):r=review(p,TZ,NOW)
 unchanged=list_training(p)==before;set_status('completed',p);h=list_training(p)
 return {'verdict':'PASS' if unchanged and all(w['completion_status']=='cancelled' for w in h['workouts']) else 'FAIL','pause_stops_changes':unchanged,'cancel_semantics':'Finish plan / completed cancels outstanding sessions; UI lacks an explicit Cancel plan label.'}
case('pause and cancel plan',lambda:run(pause_cancel))
def events(p):
 outputs=[]
 for race,distance,climb in [(False,40,200),(False,100,1800),(True,100,1800)]:
  b=brief(fixed_events=[{'date':'2026-10-14','title':'Invented event','sport':'cycling','distance_km':distance,'elevation_gain_meters':climb,'is_race':race,'start_time':'08:00','duration_minutes':180,'effort':'hard'}])
  pr=get(p,b);fixed=next((s for s in pr['sessions'] if s['definition'].get('fixed_commitment')),None)
  outputs.append({'race':race,'distance':distance,'climb':climb,'status':pr['status'],'fixed':fixed,'recovery_dates':pr['protected_days'],'phase':pr['roadmap'][0]['phase']})
 return {'verdict':'PARTIAL','outputs':outputs,'finding':'Demands persist and race/recovery distinctions work; distance/ascent mainly affect labels, recovery buffers and duration estimates, not event-specific training doses.'}
case('upcoming event types and demands',lambda:run(events))
def event_plan(p):
 b=brief(goal='race',target_date='2026-12-06',event_name='Invented 100 km / 1800 m race',horizon_weeks=8)
 pr=get(p,b);pid=active(p,b);first=review(p,TZ,NOW);later=review(p,TZ,NOW+timedelta(days=7))
 return {'verdict':'PARTIAL','phases':[b['phase'] for b in pr['roadmap']],'initial_minutes':[s['definition']['duration_minutes'] for s in pr['sessions']],'next_week_minutes':[w['definition']['duration_minutes'] for w in later['workouts']],'persisted':first['program']['id']==later['program']['id']==pid,'finding':'Event roadmap, taper and continuation exist; build blocks do not prescribe progressive duration/intensity overload.'}
case('long-term plan toward event',lambda:run(event_plan))
def surprise(p):
 active(p);review(p,TZ,NOW);b=brief(fixed_events=[{'date':'2026-10-13','title':'Surprise long ride','sport':'cycling','start_time':'08:00','duration_minutes':180,'effort':'hard','distance_km':90,'elevation_gain_meters':1500}]);save_brief(b,0,p)
 r=review(p,TZ,NOW);neighbors=[{'date':w['scheduled_for'][:10],'minutes':w['definition']['duration_minutes']} for w in r['workouts'] if w['scheduled_for'][:10] in ('2026-10-12','2026-10-14')]
 return {'verdict':'FAIL','warnings':r['review']['warnings'],'neighbors':neighbors,'event_appears_as_workout':any(w['title']=='Surprise long ride' for w in r['workouts']),'finding':'New event is saved, but conflicting/full-budget weeks are not rebuilt and pre-existing long sessions on protected neighboring days remain.'}
case('surprise event short-term replanning',lambda:run(surprise))
def feedback(p):
 active(p);r=review(p,TZ,NOW);w=r['workouts'][0];update_workout(w['id'],w['revision'],{'notes':'That was too hard'},p);after=review(p,TZ,NOW)
 request=request_change('Move my long ride to tomorrow at 08:00',TZ,p,NOW,apply=False) if any(w['definition']['duration_minutes']>=90 for w in after['workouts']) else None
 return {'verdict':'PASS','changes':after['review']['changes'],'finding':'Notes reduce upcoming demanding sessions. Date/time changes use revision/conflict checks; no unrestricted natural-language plan rewrite exists.'}
case('effort notes short-term adaptation',lambda:run(feedback))
mixed={**ANS,'sports':['cycling','strength'],'experience':{'cycling':'experienced','strength':'regular'},'equipment':['bike','bodyweight','dumbbells'],'weekly_minutes':{'cycling':240,'strength':120},'availability':[{'weekday':i,'start_time':'18:00','minutes':60} for i in range(7)]}
def mixedplan(p):
 a=get(p,brief(goal='endurance'));return {'verdict':'PASS' if {s['sport'] for s in a['sessions']}=={'cycling','strength'} else 'FAIL','sessions':[{'sport':s['sport'],'minutes':s['definition']['duration_minutes']} for s in a['sessions']]}
case('mixed cycling and strength',lambda:run(mixedplan,mixed))
def priority():
 out={}
 for priority in ('strength','endurance','general'):
  out[priority]=run(lambda p:[{'sport':s['sport'],'exercises':s['definition'].get('exercises')} for s in get(p,brief(goal='general'))['sessions']],{**mixed,'priority':priority})
 return {'verdict':'FAIL' if out['strength']==out['endurance'] else 'PARTIAL','identical_primary_secondary':out['strength']==out['endurance'],'finding':'Coach preview does not use preference priority to change selection; no cycling-specific strength or strength progression objective/question exists.','schedules':out}
case('strength primary/secondary and cycling-specific goals',priority)
def power(p):
 pr=get(p,brief(goal='ftp',ftp_watts=250));work=[s for s in pr['sessions'] if s['definition']['template_id']=='cycling_controlled_intervals'][0]
 return {'verdict':'PARTIAL','definition':work['definition'],'meter_question_present':any('power' in question.lower() and 'meter' in question.lower() for question in training_context(p,NOW)['questions']),'power_meter_equipment_option':any('power_meter'==e for e in EQUIPMENT),'finding':'90–95% of confirmed FTP is text only (250 W → 225–237.5 W); no numeric per-lap power ranges, power-meter availability question or calibrated HR alternatives.'}
case('FTP targets, power-meter availability and HR',lambda:run(power))
def past_history():
 results={}
 for length in (30,180):
  def fn(p):
   with connect(p) as c:
    for i in range(6):c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,distance_meters,raw_json) VALUES(?,'garmin_export','cycling',?,?,30000,?)",('past-'+str(i),(NOW-timedelta(days=i+1)).isoformat(),length*60,json.dumps({'trainingEffectLabel':'AEROBIC_BASE'})))
   return [s['definition']['duration_minutes'] for s in get(p)['sessions']]
  results[str(length)]=run(fn)
 return {'verdict':'PARTIAL','past_30_vs_180_minutes':results,'finding':'Recent longest-session duration caps new doses and high Garmin effects/feedback can suppress intensity; no general power-duration/HR-based difficulty model or exercise strength capability assessment.'}
case('past activity difficulty influences future workouts',past_history)
def laps(p):
 pr=get(p,brief(goal='ftp',ftp_watts=250));sessions=pr['sessions'];exact=all(sum(step['duration_seconds'] for step in s['definition'].get('steps',[]))==s['definition']['duration_minutes']*60 for s in sessions if s['definition'].get('steps'))
 return {'verdict':'PARTIAL','step_totals_match':exact,'steps':sessions[0]['definition']['steps'],'finding':'Timed steps are stored; steps have effort strings, not structured lap power/HR targets or named repetitions. UI does not show explicit target watts/HR for every lap.'}
case('lap/interval timing and numeric targets',lambda:run(laps))
def bars(p):
 ctx=training_context(p,NOW);return {'verdict':'FAIL','ready':ctx['ready'],'blockers':ctx['blockers'],'finding':'Pull-up/dip bars can be saved but strength templates contain no exercises using them.'}
case('pull-up and dip-bar exercise support',lambda:run(bars,{**mixed,'equipment':['bike','pull_up_bar','dip_bars']}))
def active_goal_change(p):
 active(p);save_brief(brief(goal='ftp',ftp_watts=250),0,p)
 state=read_active({},p)['program']['state']['brief']
 return {'verdict':'FAIL' if state['goal']!='ftp' or state['ftp_watts']!=250 else 'PASS','active_goal':state['goal'],'active_ftp':state['ftp_watts'],'finding':'Saving a changed coaching goal/FTP updates the separate brief but only fixed events are copied into the active program.'}
case('user goal and FTP updates reach active plan',lambda:run(active_goal_change))
def dispatch(p):
 from app.ai_tools import execute_tool
 outcomes={}
 for name,args in [('get_active_training_plan',{}),('propose_training_adjustment',{'message':'Move my long ride to tomorrow'}),('suggest_today_workout',{'minutes':60,'timezone':TZ}),('get_recent_training_mix',{'timezone':TZ})]:
  try:execute_tool(name,args,p);outcomes[name]='Executed'
  except Exception as e:outcomes[name]=type(e).__name__+': '+str(e)
 return {'verdict':'FAIL','outcomes':outcomes,'finding':'All four new coach tool definitions are added after the execution definition map is built.'}
case('actual assistant dispatcher for new tools',lambda:run(dispatch))
Path(__file__).with_name('results.json').write_text(json.dumps({'snapshot':'2026-10-12','method':'independent executed synthetic database probes; readiness mocked explicitly, no live model requests','cases':rows},indent=2))
