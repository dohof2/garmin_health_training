"""Focused model audit using invented records only; no product repairs or real plan writes."""
import json,os,tempfile,time
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,date,timedelta,timezone
from run_chatgpt_trainer_qc import fixture
from app.config import database_path
from app.ai_providers import get_ai_settings,save_ai_settings
from app import chatgpt_auth as auth
from app.ai_chat import chat_stream
from app.training import save_preferences,training_context,accept_plan
from app.training_coach import DEFAULT,preview,create_draft
production=database_path();settings=get_ai_settings(production);original_models=auth.models;original_token=auth.access_token
cases=[
('ftp-laps','I want a varied cycling training week to improve FTP. My confirmed FTP is 220 W. Ask whether I have access to a power meter. Give actual watts or heart-rate goals and durations for every warmup, lap, recovery and cooldown.'),
('race-mixed','Plan toward a cycling race on 2026-12-06: 100 km and 1800 m ascent. Include cycling plus strength as secondary work specifically to improve cycling. Ask any missing essential information and show the progression of longer rides over eight weeks.'),
('strength-primary','I want strength as my primary training and cycling as secondary for general fitness. What changes to the plan and strength progression do you suggest?'),
('surprise-event','Tomorrow I have an unexpected hard ride, 90 km and 1500 m climbing at 08:00, probably three hours. Adapt my saved active plan around this event. What happens to the existing long rides before and after it?')]
results=[]
with tempfile.TemporaryDirectory(prefix='coach-live-acceptance-') as d:
 os.environ['HT_APP_DATA_DIR']=d;db=Path(d)/'health_training.sqlite3';fixture(db);save_ai_settings({**settings,'active_provider':'chatgpt'},db)
 a={'sports':['cycling','strength'],'priority':'endurance','availability':[{'weekday':i,'start_time':'18:00','minutes':120} for i in range(7)],'experience':{'cycling':'experienced','strength':'regular'},'equipment':['bike','bodyweight','dumbbells','pull_up_bar','dip_bars'],'weekly_minutes':{'cycling':360,'strength':120},'blocked_sports':[],'blocked_movements':[],'restrictions_notes':'','pain_or_illness':False}
 save_preferences(a,0,db)
 now=datetime.now(timezone.utc);today=now.date();week=today-timedelta(days=today.weekday());b={**DEFAULT,'goal':'endurance'}
 p=preview(b,week,'Asia/Jerusalem',db);h=create_draft(b,week,'Asia/Jerusalem',p['fingerprint'],db);accept_plan(h['plans'][0]['id'],db)
 with patch.object(auth,'models',side_effect=lambda path=None:original_models(production)),patch.object(auth,'access_token',side_effect=lambda path=None:original_token(production)):
  for identifier,message in cases:
   start=time.monotonic();events=[json.loads(e) for e in chat_stream(message,[],'Asia/Jerusalem',db)]
   answer=''.join(e.get('text','') for e in events if e['type']=='delta');evidence=[e['evidence'] for e in events if e['type']=='tool'];errors=[e['message'] for e in events if e['type']=='error']
   row={'id':identifier,'question':message,'answer':answer,'evidence':evidence,'errors':errors,'completed':any(e['type']=='complete' for e in events),'seconds':round(time.monotonic()-start,2)};results.append(row)
   Path(__file__).with_name('live-results.json').write_text(json.dumps({'data':'invented disposable training records only','results':results},indent=2))
   print(identifier,'ERROR' if errors else 'ANSWER',row['seconds'],errors,flush=True)
