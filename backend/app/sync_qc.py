"""Small, local post-sync audit. No model calls and no invented measurements."""
import json
from datetime import timedelta
from .database import connect

EXPECTED={
    'sleep_metrics':('sleep','sleep_duration','sleep_score'),
    'daily_metrics':('daily','steps','resting_heart_rate','total_calories'),
    'hrv_metrics':('hrv','hrv_last_night_average'),
}


def audit(job_id,through_date,requested,path,load_refresh=None):
    day=through_date.isoformat();checks=[]
    with connect(path) as c:
        for family in requested:
            intervals=c.execute('SELECT interval_start,status,empty_result FROM sync_intervals WHERE job_id=? AND data_type=? ORDER BY id',(job_id,family)).fetchall()
            latest=next((r for r in reversed(intervals) if r['interval_start']==day),None)
            failed=any(r['status']=='failed' for r in intervals)
            status='failed' if failed else 'missing_interval' if not latest else 'ok'
            detail='An interval failed; retry sync.' if failed else 'The requested end date was not fetched.' if not latest else 'Requested intervals committed.'
            missing=[];expected=[]
            if status=='ok' and family in EXPECTED:
                prefix,*candidates=EXPECTED[family]
                # Only require device-supported measures that have previously
                # arrived. Weight/VO2 and optional endpoints are not daily quotas.
                historical={r['metric_type'] for r in c.execute("SELECT DISTINCT metric_type FROM metric_readings WHERE source_name!='synthetic_fixture' AND source_record_id LIKE ? AND substr(recorded_at,1,10)>=? AND substr(recorded_at,1,10)<?",(prefix+':%',(through_date-timedelta(days=28)).isoformat(),day))}
                expected=[metric for metric in candidates if metric in historical]
                current={r['metric_type']:dict(r) for r in c.execute("SELECT metric_type,value,period_start,period_end FROM metric_readings WHERE source_name!='synthetic_fixture' AND source_record_id=? AND substr(recorded_at,1,10)=?",(prefix+':'+day,day))}
                missing=[metric for metric in expected if metric not in current or current[metric]['value'] is None or metric in ('sleep_duration','hrv_last_night_average','resting_heart_rate') and current[metric]['value']<=0]
                if 'sleep_duration' in expected and 'sleep_duration' not in missing:
                    row=current['sleep_duration']
                    if not row['period_start'] or not row['period_end'] or row['period_start']>=row['period_end'] or row['period_start']==row['period_end']==day:missing.append('sleep_duration')
                if missing:
                    status='missing_measures';detail='Expected measurements are missing or incomplete; the source may not have posted them yet.'
                elif not expected and latest['empty_result']:
                    status='source_empty';detail='Source returned no records; no established daily measurement is assumed.'
            elif status=='ok' and latest['empty_result']:
                status='source_empty';detail='Source returned no records; this is not assumed to mean a missing activity, weigh-in or VO₂ test.'
            if family=='supplementary_metrics' and status in ('ok','source_empty'):
                row=c.execute("SELECT payload_json FROM garmin_sync_payloads WHERE data_type=? AND calendar_date=?",(family,day)).fetchone()
                try:payload=json.loads(row[0]) if row else {}
                except (TypeError,ValueError):payload={}
                if isinstance(payload,dict) and payload.get('failures'):
                    status='partial_source';detail='Some additional Garmin endpoints failed; retained data is partial.'
            checks.append({'data_type':family,'date':day,'status':status,'expected':expected,'missing':missing,'detail':detail,
                           'retryable':status=='missing_measures'})
    if load_refresh and load_refresh.get('failed_dates'):
        checks.append({'data_type':'training_load_history','date':day,'status':'failed','expected':[],'missing':[],
                       'detail':'Daily training load refresh failed; the activity may already be saved.','retryable':False})
    issues=[check for check in checks if check['status'] not in ('ok','source_empty')]
    return {'version':'sync-qc-v1','through_date':day,'status':'attention' if issues else 'passed','checks':checks,
            'issues':issues,'retry_attempted':[], 'note':'Checks requested families and previously supported daily recovery measures; empty optional feeds are explicit, not fabricated as zeros.'}


def check_and_retry(provider,job_id,through_date,requested,path,load_refresh,totals):
    result=audit(job_id,through_date,requested,path,load_refresh)
    attempted=[];retry_failed=[]
    from .sync import _commit_interval
    for check in result['issues']:
        if not check['retryable'] or check['data_type'] not in EXPECTED:continue
        family=check['data_type'];attempted.append(family)
        # Exactly one retry per requested recovery family. No history scan or
        # recursive sync, and no advancing coverage over a failed interval.
        try:
            records=provider.fetch(family,through_date,through_date)
            with connect(path) as c:
                c.execute('UPDATE jobs SET progress_total=progress_total+1 WHERE id=?',(job_id,))
                old=c.execute('SELECT coverage_end FROM sync_checkpoints WHERE data_type=?',(family,)).fetchone()[0]
                used={r[0] for r in c.execute('SELECT interval_kind FROM sync_intervals WHERE job_id=? AND data_type=? AND interval_start=?',(job_id,family,through_date.isoformat()))}
                retry_kind=next(kind for kind in ('reconciliation','overlap','gap') if kind not in used)
            from datetime import date
            counts=_commit_interval(job_id,family,through_date,retry_kind,records,date.fromisoformat(old) if old else None,path,getattr(provider,'interval_payload',None))
            totals['received']+=len(records)
            for key in ('created','updated','unchanged','detail_samples'):totals[key]+=counts[key]
        except Exception:
            # Never store source exception text/URLs from an audit retry.
            retry_failed.append(family)
    if attempted:result=audit(job_id,through_date,requested,path,load_refresh)
    result['retry_attempted']=attempted;result['retry_failed']=retry_failed
    return result
