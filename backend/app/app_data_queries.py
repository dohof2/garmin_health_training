"""Bounded read-only views of user-facing datasets, without credential tables."""
import json
from datetime import date,timedelta
from .database import connect


def query(arguments,path=None):
    dataset=arguments.get('dataset');start=date.fromisoformat(arguments['start_date']);end=date.fromisoformat(arguments['end_date'])
    if not isinstance(dataset,str):raise ValueError('Choose a named dataset from get_app_data_catalog')
    if start>end or (end-start).days>366:raise ValueError('Choose an ordered date range of at most 367 days')
    tz=arguments.get('timezone') or 'UTC'
    from .time_utils import timezone_info
    timezone_info(tz)
    limit=arguments.get('limit',100);offset=arguments.get('offset',0)
    if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or not 0<=offset<=1000000:raise ValueError('Use a limit of 1–100 and a nonnegative offset up to 1,000,000')
    from .app_data_history import extended_query,period_filter,page,public_json
    with connect(path) as c:
        result=extended_query(dataset,c,start,end,tz,limit,offset)
    if result is not None:return {'tool':'query_app_data','dataset':dataset,'period':{'start':start.isoformat(),'end':end.isoformat()},'timezone':tz,**result}
    if dataset in ('nutrition','profile','sync') and offset:raise ValueError('This snapshot/day-summary dataset does not use record offsets')
    if dataset=='nutrition':
        if (end-start).days>30:raise ValueError('Choose up to 31 days for detailed nutrition history')
        from .nutrition import daily_status
        days=[daily_status(start+timedelta(days=i),tz,path) for i in range((end-start).days+1)]
        return {'tool':'query_app_data','dataset':dataset,'result':days[0] if start==end else {'days':days,'period':{'start':start.isoformat(),'end':end.isoformat()}}}
    if dataset=='profile':
        from .settings import _profile_row
        with connect(path) as c:
            profile=_profile_row(c)
            goals=[dict(r) for r in c.execute("SELECT id,goal_type,title,target_value,target_unit,target_date,status,notes FROM goals WHERE status!='archived'")]
        return {'tool':'query_app_data','dataset':dataset,'profile':profile,'goals':goals,'observation_kind':'Current saved profile and active goals, not a historical as-of reconstruction. Use goals for archived goals/revisions.'}
    if dataset=='sync':
        with connect(path) as c:
            checkpoints=[dict(r) for r in c.execute('SELECT data_type,coverage_start,coverage_end,status,last_success_at,error_message FROM sync_checkpoints')]
            latest=c.execute("SELECT status,started_at,finished_at,error_message FROM jobs WHERE job_type='garmin_sync' ORDER BY created_at DESC LIMIT 1").fetchone()
        return {'tool':'query_app_data','dataset':dataset,'checkpoints':checkpoints,'latest_job':dict(latest) if latest else None,'observation_kind':'Current local sync status; this query does not perform a sync.'}
    if dataset=='archive':
        category=arguments.get('category')
        with connect(path) as c:
            categories=[r[0] for r in c.execute("SELECT DISTINCT category FROM garmin_archive_records WHERE source_name!='synthetic_fixture' ORDER BY category")]
            if not category:return {'tool':'query_app_data','dataset':dataset,'available_categories':categories,'records':[]}
            result=page(c,'category,record_date,payload_json','garmin_archive_records',"category=? AND record_date>=? AND record_date<=? AND source_name!='synthetic_fixture'",[category,start.isoformat(),end.isoformat()],'record_date DESC,id',limit,offset)
            undated=c.execute("SELECT COUNT(*) FROM garmin_archive_records WHERE category=? AND (record_date IS NULL OR record_date='') AND source_name!='synthetic_fixture'",(category,)).fetchone()[0]
        for row in result['records']:
            row['date']=row.pop('record_date');row['data'],row['payload_limits']=public_json(row.pop('payload_json'))
        return {'tool':'query_app_data','dataset':dataset,**result,'available_categories':categories,'undated_record_count':undated,'note':'Undated records cannot be attributed to the requested period; trimmed/redacted payload paths are explicit.'}
    if dataset=='health':
        metric=arguments.get('metric_type')
        with connect(path) as c:
            types=[r[0] for r in c.execute("SELECT DISTINCT metric_type FROM metric_readings WHERE source_name!='synthetic_fixture' ORDER BY metric_type")]
            if not metric:return {'tool':'query_app_data','dataset':dataset,'available_metrics':types,'records':[]}
            where,params=period_filter('recorded_at',start,end,tz)
            result=page(c,'metric_type,value,unit,recorded_at,source_name,source_updated_at','metric_readings',where+" AND metric_type=? AND source_name!='synthetic_fixture'",params+[metric],'recorded_at DESC,id',limit,offset)
        return {'tool':'query_app_data','dataset':dataset,**result,'available_metrics':types,'period':{'start':start.isoformat(),'end':end.isoformat()},'timezone':tz}
    raise ValueError('Unsupported dataset. Use get_app_data_catalog to choose an explicit read path; arbitrary tables and account/credential data are not available.')
