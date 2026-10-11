"""Live trainer QC against isolated invented records, never the user's Garmin data."""
import argparse
from datetime import date,timedelta,datetime,UTC
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from assistant_question_bank import CASES

FIT_CASES=[
    {'id':'fit-sprints-exact','category':'fit','message':'look for all the rides i ahve with short intervals (10-15 seconds multyple time) and plot the average power during the interval across time (to show the improvement of my sprints)','tool':'analyze_sprint_intervals'},
    {'id':'fit-sprints-threshold','category':'fit','message':'Find repeated 10-second efforts above 250 watts and plot their power by ride date.','tool':'analyze_sprint_intervals'},
    {'id':'fit-laps','category':'fit','message':'Show the recorded laps and continuous power from my latest ride.','tool':'get_activity_stream'},
    {'id':'fit-grit','category':'fit','message':'What grit and flow data is available in my FIT files?','tool':'find_fit_fields'},
    {'id':'fit-jumps','category':'fit','message':'How many recorded jumps were in my latest ride, and how high were they?','tool':'get_fit_activity_data'},
    {'id':'fit-grit-plot','category':'fit','message':'Plot the maximum recorded grit from each ride over time.','tool':'create_plots'},
    {'id':'fit-jump-plot','category':'fit','message':'Plot the number of recorded jumps per ride over time.','tool':'create_plots'},
    {'id':'fit-custom','category':'fit','message':'What is the average custom_sensor field in the FIT records from my latest ride?','tool':'get_fit_activity_data'},
]

TRAINER_CASES=[
    {'id':'trainer-comparison','message':'How was my last ride compared to other rides this year?','tool':'compare_latest_ride'},
    {'id':'trainer-good','seed':'How was my last ride compared to other rides this year?','message':'Was it good or not?'},
    {'id':'trainer-benefit','message':'What was the main benefit of my last ride?'},
    {'id':'trainer-personal','message':'Describe my last ride like my trainer would, briefly.'},
    {'id':'trainer-followup','seed':'Describe my last ride like my trainer would, briefly.','message':'Should I go hard tomorrow?'},
    {'id':'trainer-timing','message':'How was my last ride compared with the last year or so?','tool':'compare_latest_ride'},
    {'id':'trainer-general','message':'What is endurance training?'},
    {'id':'trainer-openai-privacy','message':'Use my ChatGPT memories to find my training goals.'},
    {'id':'trainer-goal-proposal','message':'Add a goal to improve my cycling FTP by December 2026. Do not save it without my review.','tool':'propose_settings_change'},
]


def fixture(path):
    from app.database import migrate,connect
    migrate(path)
    today=date(2026,10,11)
    with connect(path) as c:
        for index in range(53):
            day=today-timedelta(days=2+7*index)
            identifier=f'qc-ride-{index}'
            c.execute('INSERT INTO activities(id,source_name,name,activity_type,started_at,distance_meters,duration_seconds,raw_json) VALUES(?,?,?,?,?,?,?,?)',
                (identifier,'garmin_connect','QC invented ride','cycling',day.isoformat()+'T08:00:00Z',70000 if index==0 else 30000,18000 if index==0 else 5400,json.dumps({'trainingEffectLabel':'AEROBIC_BASE','fit_sessions':[{'total_training_effect':3.3,'total_anaerobic_training_effect':1.1}]})))
            c.execute("INSERT INTO activity_metrics(activity_id,metric_type,value,unit,source_method,source_field) VALUES(?,'average_power',?,'W','qc_fixture','average_power')",(identifier,90 if index==0 else 140))

            records=[]
            for second in range(201):
                power=(500-index*3) if 20<=second<30 or 60<=second<70 or 100<=second<115 or 150<=second<165 else 100
                timestamp=day.isoformat()+f'T08:{second//60:02d}:{second%60:02d}Z'
                records.append({'timestamp':timestamp,'power':power,'grit':2+index/10,'flow':1.5,'custom_sensor':4})
                c.execute('INSERT INTO activity_samples(activity_id,recorded_at,power_watts) VALUES(?,?,?)',(identifier,timestamp,power))
            lap={'start_time':day.isoformat()+'T08:00:20Z','timestamp':day.isoformat()+'T08:00:30Z','total_timer_time':10,'avg_power':500-index*3}
            messages={'record_mesgs':records,'lap_mesgs':[lap],'jump_mesgs':[{'height':1.2,'hang_time':0.4},{'height':1.6,'hang_time':0.6}]}
            payload={'trainingEffectLabel':'AEROBIC_BASE','fit_sessions':[{'total_training_effect':3.3,'total_anaerobic_training_effect':1.1}],'fit_laps':[lap],'fit_messages':messages,'fit_field_inventory':{name:sorted({key for row in rows for key in row}) for name,rows in messages.items()}}
            c.execute('UPDATE activities SET raw_json=? WHERE id=?',(json.dumps(payload),identifier))

        for index in range(365):
            day=(today-timedelta(days=index)).isoformat()
            for metric,value,unit in [('steps',7000+index%100,'steps'),('sleep_duration',27000,'s'),('sleep_score',80,'score'),('weight',75+index/1000,'kg'),('hrv_last_night_average',55,'ms'),('resting_heart_rate',55,'bpm'),('body_battery_latest',60,'score'),('hydration',2000,'ml'),('acute_training_load',300,'score')]:
                c.execute('INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,?,?,?,?,?)',(f'qc-{metric}-{index}','garmin_connect',metric,day+'T06:00:00Z',value,unit))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--offset',type=int,default=0)
    parser.add_argument('--limit',type=int,default=8)
    parser.add_argument('--output',default='docs/qa/2026-10-11/chatgpt-trainer-live.json')
    parser.add_argument('--category',action='append')
    parser.add_argument('--case',action='append')
    args=parser.parse_args()
    from app.config import database_path
    from app.ai_providers import get_ai_settings,save_ai_settings
    from app import chatgpt_auth as auth
    production_path=database_path();settings=get_ai_settings(production_path)
    original_models=auth.models;original_token=auth.access_token
    results=[]
    with tempfile.TemporaryDirectory(prefix='garmin-trainer-qc-') as directory:
        os.environ['HT_APP_DATA_DIR']=directory
        db=Path(directory)/'health_training.sqlite3';fixture(db)
        save_ai_settings({**settings,'active_provider':'chatgpt'},db)
        from app.ai_chat import chat_stream
        def ask(message,history=None,context=None):
            events=[json.loads(event) for event in chat_stream(message,history or [],'Asia/Jerusalem',db,plot_context=context)]
            return events,''.join(e.get('text','') for e in events if e['type']=='delta'),[e['evidence'] for e in events if e['type']=='tool']
        with patch.object(auth,'models',side_effect=lambda path=None:original_models(production_path)),patch.object(auth,'access_token',side_effect=lambda path=None:original_token(production_path)):
            cases=TRAINER_CASES+CASES+FIT_CASES
            if args.category:
                cases=[case for case in cases if case.get('category','trainer') in args.category]
            if args.case:
                cases=[case for case in cases if case['id'] in args.case]
            for case in cases[args.offset:args.offset+args.limit]:
                started=time.monotonic();history=[];context=None;errors=[]
                if case.get('seed'):
                    seed_events,seed_answer,seed_evidence=ask(case['seed'])
                    errors.extend(e['message'] for e in seed_events if e['type']=='error')
                    history=[{'role':'user','content':case['seed']},{'role':'assistant','content':seed_answer or 'No answer available.'}]
                    context=[p['spec'] for e in seed_evidence for p in e.get('plots',[])] or None
                events,answer,evidence=ask(case['message'],history,context)
                errors.extend(e['message'] for e in events if e['type']=='error')
                checks=[]
                if not any(e['type']=='complete' for e in events):checks.append('No completion')
                if not answer:checks.append('No answer')
                if 'could not retrieve grounded evidence' in answer.lower():checks.append('Legacy generic failure')
                if len(answer.split())>220:checks.append('Long answer')
                if case.get('tool') and case['tool'] not in {e['tool'] for e in evidence}:checks.append('Expected tool absent (review semantic alternatives)')
                if case.get('clarify') and case['clarify'].lower() not in answer.lower():checks.append('Review clarification wording/behavior')
                if case.get('period'):
                    periods=[list((p['spec'].get('start'),p['spec'].get('end'))) for e in evidence for p in e.get('plots',[])] or [[e.get('period',{}).get('start'),e.get('period',{}).get('end')] for e in evidence if e['tool']==case.get('tool')]
                    if periods and any(p!=case['period'] for p in periods):checks.append('Period differs from bank expectation')
                plots=[plot for item in evidence for plot in item.get('plots',[])]
                if case.get('metrics') and plots:
                    metrics={value for plot in plots for value in [plot['spec']['metric'],plot['spec'].get('x_metric')] if value and value!='date'}
                    if metrics!=set(case['metrics']):checks.append('Plot metrics differ from request')
                if case.get('spec') and plots:
                    if any(plot['spec'].get(key)!=value for plot in plots for key,value in case['spec'].items()):checks.append('Plot transformation differs from request')
                row={'id':case['id'],'question':case['message'],'answer':answer,'evidence':evidence,'errors':errors,'review_flags':checks,'seconds':round(time.monotonic()-started,2)}
                results.append(row)
                Path(args.output).write_text(json.dumps({'fixture':'invented isolated records; no user health data','results':results},indent=2))
                print(case['id'],'ERROR' if errors else 'REVIEW' if checks else 'OK',row['seconds'],errors,checks,flush=True)
    print('TOTAL',len(results),'ERRORS',sum(bool(r['errors']) for r in results),'REVIEW',sum(bool(r['review_flags']) for r in results),flush=True)


if __name__=='__main__':main()
