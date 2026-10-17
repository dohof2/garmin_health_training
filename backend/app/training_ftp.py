"""Resolve only observed, sport-specific retained Garmin FTP records."""
import json
import math
from datetime import date


def resolve(c, today=None):
    today=today or date.today();candidates=[]
    for row in c.execute("SELECT payload_json,calendar_date FROM garmin_sync_payloads WHERE data_type='supplementary_metrics' ORDER BY calendar_date DESC"):
        endpoints=json.loads(row['payload_json']).get('endpoints',{})
        for endpoint in ('get_cycling_ftp','get_functional_threshold_power_range:CYCLING'):
            payload=endpoints.get(endpoint)
            records=payload if isinstance(payload,list) else [payload]
            for record in records:
                if not isinstance(record,dict) or record.get('sport')!='CYCLING':continue
                if record.get('unit','W') not in ('W','watts'):continue
                watts=record.get('functionalThresholdPower')
                if isinstance(watts,bool) or not isinstance(watts,(int,float)) or not math.isfinite(watts) or not 40<=watts<=700:continue
                raw=record.get('calendarDate');day=None
                if raw:
                    try:day=date.fromisoformat(raw[:10])
                    except (ValueError,TypeError):continue
                    if day>today:continue
                status='undated' if not day else 'stale' if (today-day).days>90 or record.get('isStale') is True else 'usable'
                candidates.append({'watts':watts,'source':'Garmin · '+endpoint,'measurement_date':day.isoformat() if day else None,'fetch_date':row['calendar_date'],'status':status,'reason':{'undated':'Measurement date unavailable','stale':'FTP needs confirmation: measurement is stale','usable':'Dated cycling FTP within 90 days'}[status]})
    if not candidates:return {'watts':None,'source':None,'measurement_date':None,'fetch_date':None,'status':'missing','reason':'No supported retained Garmin cycling FTP measurement'}
    latest=max(candidates,key=lambda v:(v['measurement_date'] or '',v['fetch_date'],v['source']))
    dated={item['measurement_date']:item for item in sorted(candidates,key=lambda item:(item['fetch_date'],item['source'])) if item['measurement_date']}
    history=[{'date':day,'watts':dated[day]['watts']} for day in sorted(dated)]
    return {**latest,'measurements':history,'measured_change_watts':history[-1]['watts']-history[-2]['watts'] if len(history)>=2 else None}
