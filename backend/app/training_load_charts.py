"""Recorded daily Garmin load and personalized boundaries; never infer missing days."""
import json
import math
from datetime import datetime, timedelta
from .database import connect
from .time_utils import timezone_info


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def daily_rows(path=None):
    days = {}
    def accept(day, dto, source, identifier):
        if not isinstance(day,str) or len(day)!=10 or not finite(dto.get('dailyTrainingLoadAcute')):
            return
        try:
            datetime.strptime(day,'%Y-%m-%d')
        except ValueError:
            return
        row = {'date':day,'acute':dto['dailyTrainingLoadAcute'],'chronic':dto.get('dailyTrainingLoadChronic'),'low':dto.get('minTrainingLoadChronic'),'high':dto.get('maxTrainingLoadChronic'),'source':source,'id':identifier}
        for field in ('chronic','low','high'):
            if not finite(row[field]): row[field]=None
        if row['low'] is not None and row['high'] is not None and row['low']>row['high']: row['low']=row['high']=None
        days[day]=row
    def walk(value,identifier):
        if isinstance(value,dict):
            dto=value.get('acuteTrainingLoadDTO')
            if isinstance(dto,dict): accept(value.get('calendarDate'),dto,'garmin_connect',identifier)
            for child in value.values(): walk(child,identifier)
        elif isinstance(value,list):
            for child in value: walk(child,identifier)
    with connect(path) as c:
        for r in c.execute("SELECT id,record_date,source_name,payload_json FROM garmin_archive_records WHERE category='acute_training_load' AND source_name!='synthetic_fixture' ORDER BY record_date,id"):
            dto=json.loads(r['payload_json'])
            if isinstance(dto,dict): accept(r['record_date'],dto,r['source_name'],r['id'])
        for r in c.execute("SELECT data_type,calendar_date,payload_json FROM garmin_sync_payloads WHERE data_type IN ('supplementary_metrics','training_load_history') ORDER BY updated_at,calendar_date"):
            walk(json.loads(r['payload_json']),r['data_type']+':'+r['calendar_date'])
    return [days[day] for day in sorted(days)]


def chart(spec,path=None):
    end= datetime.now(timezone_info(spec.get('timezone','UTC'))).date()
    start=end-timedelta(days=spec.get('window_days',28)-1)
    if 'window_days' not in spec:
        start=datetime.fromisoformat(spec.get('start',start.isoformat())).date()
        end=datetime.fromisoformat(spec.get('end',end.isoformat())).date()
    spec={**spec,'start':start.isoformat(),'end':end.isoformat()}
    rows=[r for r in daily_rows(path) if start.isoformat()<=r['date']<=end.isoformat()]
    points=[];series=[]
    for field,label,color in [('acute','Acute load','#356799'),('chronic','Chronic load','#d16b22')]:
        if field=='chronic' and not spec.get('show_chronic',False):continue
        selected=[r for r in rows if r[field] is not None]
        segment=0;previous=None
        for row in selected:
            day=datetime.fromisoformat(row['date']).date()
            if previous and (day-previous).days>1:segment+=1
            points.append({'x':row['date'],'date':row['date'],'y':row[field],'source':row['source'],'id':row['id'],'series_id':field,'segment':segment});previous=day
        series.append({'id':field,'label':label,'color':color,'count':len(selected)})
    band=[{'date':r['date'],'low':r['low'],'high':r['high'],'source':r['source']} for r in rows if r['low'] is not None and r['high'] is not None] if spec.get('show_optimal_range',True) else []
    latest=next((p for p in reversed(points) if p['series_id']=='acute'),None)
    return {'spec':spec,'points':points,'series':series,'range_band':{'label':'Optimal acute load · Garmin','points':band},'x_domain':[start.isoformat(),end.isoformat()],'unit':'Garmin load','x_unit':'Date','count':len(points),'excluded':0,'unpaired':0,'latest':latest,'sources':sorted({r['source'] for r in rows}),'notes':['Recorded daily values; missing days remain gaps.','Green boundaries come from Garmin’s recorded personalized load range. Historical boundaries are not estimated.',f'{len(band)} of {len(rows)} recorded days have available range boundaries.']}


def refresh_history(path=None,days=28,timezone='UTC',client=None):
    if client is None:
        from .garmin_connection import load_client
        client=load_client(path)
    end=datetime.now(timezone_info(timezone)).date()
    fetched=0;failed=[]
    for offset in range(days-1,-1,-1):
        day=(end-timedelta(days=offset)).isoformat()
        try:
            payload=client.get_daily_training_status(day)
            with connect(path) as c:
                c.execute("INSERT INTO garmin_sync_payloads(data_type,calendar_date,payload_json) VALUES('training_load_history',?,?) ON CONFLICT(data_type,calendar_date) DO UPDATE SET payload_json=excluded.payload_json,updated_at=CURRENT_TIMESTAMP",(day,json.dumps({'endpoints':{'get_daily_training_status':payload}})))
            fetched+=1
        except Exception:
            failed.append(day)
    return {'fetched_days':fetched,'failed_dates':failed}
