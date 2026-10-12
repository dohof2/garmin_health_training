"""Selected-night sleep evidence and recorded overnight HRV. No inferred samples."""
import json
import math
from datetime import date,datetime,timezone
from .database import connect

FIELDS={'sleep_duration':('Total sleep','s'),'deep_sleep':('Deep sleep','s'),'light_sleep':('Light sleep','s'),'rem_sleep':('REM sleep','s'),'awake_sleep':('Awake','s'),'unmeasurable_sleep':('Unmeasurable sleep','s'),'sleep_stress':('Sleep stress','score'),'sleep_respiration':('Respiration','breaths/min'),'sleep_average_heart_rate':('Sleeping heart rate','bpm'),'sleep_spo2_average':('Sleep oxygen saturation','%'),'sleep_body_battery_change':('Body Battery change','score'),'sleep_hrv_average':('Average overnight HRV','ms'),'hrv_last_night_average':('Average overnight HRV','ms')}
COMPONENTS={'totalDuration':'Duration','stress':'Stress','deepPercentage':'Deep sleep','lightPercentage':'Light sleep','remPercentage':'REM sleep','awakeCount':'Awakenings','restlessness':'Restlessness'}

def finite(value):return type(value) in (int,float) and math.isfinite(value)
def timestamp(value):
    try:
        if finite(value):return datetime.fromtimestamp(value/1000,timezone.utc)
        if isinstance(value,str):
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError,OverflowError,OSError):pass
    return None

def night(day=None,path=None):
    if day is not None:date.fromisoformat(day)
    with connect(path) as c:
        dates=[r[0] for r in c.execute("SELECT DISTINCT substr(recorded_at,1,10) AS day FROM metric_readings WHERE source_name!='synthetic_fixture' AND metric_type IN ('sleep_score','sleep_duration') ORDER BY day DESC")]
        selected=day or (dates[0] if dates else date.today().isoformat())
        readings={}
        for r in c.execute("SELECT metric_type,value,unit,source_name,period_start,period_end FROM metric_readings WHERE substr(recorded_at,1,10)=? AND source_name!='synthetic_fixture' ORDER BY CASE source_name WHEN 'garmin_connect' THEN 1 ELSE 0 END,created_at,rowid",(selected,)):
            if finite(r['value']):readings[r['metric_type']]=dict(r)
        payloads={}
        for r in c.execute("SELECT data_type,payload_json FROM garmin_sync_payloads WHERE calendar_date=? AND data_type IN ('sleep_metrics','hrv_metrics')",(selected,)):
            p=json.loads(r['payload_json'])
            if isinstance(p,dict):
                actual=p.get('dailySleepDTO',{}).get('calendarDate') if r['data_type']=='sleep_metrics' else p.get('hrvSummary',{}).get('calendarDate')
                if actual is None or actual==selected:payloads[r['data_type']]=p
    sleep=payloads.get('sleep_metrics',{});daily=sleep.get('dailySleepDTO',{});hrv=payloads.get('hrv_metrics',{})
    start=timestamp(daily.get('sleepStartTimestampGMT') or hrv.get('sleepStartTimestampGMT'))
    end=timestamp(daily.get('sleepEndTimestampGMT') or hrv.get('sleepEndTimestampGMT'))
    raw=hrv.get('hrvReadings') or sleep.get('hrvData') or []
    samples={}
    for row in raw if isinstance(raw,list) else []:
        if not isinstance(row,dict):continue
        at=timestamp(row.get('readingTimeGMT') or row.get('startGMT'));value=row.get('hrvValue',row.get('value'))
        if at and finite(value) and value>0 and (not start or at>=start) and (not end or at<=end):samples[at]=value
    points=[];previous=None;segment=0
    for at,value in sorted(samples.items()):
        if previous and (at-previous).total_seconds()>900:segment+=1
        points.append({'x':at.isoformat(),'y':value,'date':selected,'id':'night:'+selected,'source':'garmin_connect','segment':segment,'recorded_at':at.isoformat()});previous=at
    scores=daily.get('sleepScores',{})
    overall=scores.get('overall',{}) if isinstance(scores,dict) else {}
    score=readings.get('sleep_score',{}).get('value')
    if finite(overall.get('value')):score=overall['value']
    components=[]
    for key,label in COMPONENTS.items():
        value=scores.get(key,{}) if isinstance(scores,dict) else {}
        if isinstance(value,dict) and value:
            components.append({'label':label,'value':value.get('value') if finite(value.get('value')) else None,'unit':'%' if key.endswith('Percentage') else '', 'qualifier':value.get('qualifierKey')})
    metrics=[{'label':label,'value':readings[key]['value'],'unit':unit,'source':readings[key]['source_name']} for key,(label,unit) in FIELDS.items() if key in readings and not (key=='hrv_last_night_average' and 'sleep_hrv_average' in readings)]
    latest=dates[0] if dates else None
    plot={'spec':{'metric':'night_hrv','kind':'line','x_metric':'recorded_time','title':'Overnight HRV'},'points':points,'unit':'ms','x_unit':'Time','count':len(points),'excluded':0,'unpaired':0,'latest':points[-1] if points else None,'notes':['Recorded overnight HRV samples; gaps over 15 minutes remain gaps.'],'sources':['garmin_connect'] if points else []}
    return {'date':selected,'latest_date':latest,'available_dates':dates,'score':score,'qualifier':overall.get('qualifierKey'),'sleep_start':start.isoformat() if start else None,'sleep_end':end.isoformat() if end else None,'metrics':metrics,'components':components,'plot':plot}
