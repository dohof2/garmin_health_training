"""Bounded read-only views of user-facing datasets, without credential tables."""
import json
from datetime import date,timedelta
from .database import connect


def query(arguments,path=None):
    dataset=arguments.get('dataset');start=date.fromisoformat(arguments['start_date']);end=date.fromisoformat(arguments['end_date'])
    if start>end or (end-start).days>366:raise ValueError('Choose an ordered date range of at most 367 days')
    tz=arguments.get('timezone') or 'UTC'
    from .time_utils import timezone_info
    timezone_info(tz)
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
        return {'tool':'query_app_data','dataset':dataset,'profile':profile,'goals':goals}
    if dataset=='sync':
        with connect(path) as c:
            checkpoints=[dict(r) for r in c.execute('SELECT data_type,coverage_start,coverage_end,status,last_success_at,error_message FROM sync_checkpoints')]
            latest=c.execute("SELECT status,started_at,finished_at,error_message FROM jobs WHERE job_type='garmin_sync' ORDER BY created_at DESC LIMIT 1").fetchone()
        return {'tool':'query_app_data','dataset':dataset,'checkpoints':checkpoints,'latest_job':dict(latest) if latest else None}
    if dataset=='archive':
        category=arguments.get('category')
        with connect(path) as c:
            categories=[r[0] for r in c.execute("SELECT DISTINCT category FROM garmin_archive_records WHERE source_name!='synthetic_fixture' ORDER BY category")]
            if not category:return {'tool':'query_app_data','dataset':dataset,'available_categories':categories,'records':[]}
            rows=c.execute("SELECT category,record_date,payload_json FROM garmin_archive_records WHERE category=? AND record_date>=? AND record_date<=? AND source_name!='synthetic_fixture' ORDER BY record_date DESC LIMIT 101",(category,start.isoformat(),end.isoformat())).fetchall()
        return {'tool':'query_app_data','dataset':dataset,'records':[{'date':r['record_date'],'category':r['category'],'data':json.loads(r['payload_json'])} for r in rows[:100]],'truncated':len(rows)>100,'available_categories':categories}
    if dataset=='health':
        metric=arguments.get('metric_type')
        with connect(path) as c:
            types=[r[0] for r in c.execute("SELECT DISTINCT metric_type FROM metric_readings WHERE source_name!='synthetic_fixture' ORDER BY metric_type")]
            if not metric:return {'tool':'query_app_data','dataset':dataset,'available_metrics':types,'records':[]}
            rows=c.execute("SELECT metric_type,value,unit,recorded_at,source_name FROM metric_readings WHERE metric_type=? AND source_name!='synthetic_fixture' ORDER BY recorded_at DESC",(metric,)).fetchall()
        from .time_utils import calendar_date
        records=[dict(r) for r in rows if start<=calendar_date(r['recorded_at'],tz)<=end]
        return {'tool':'query_app_data','dataset':dataset,'records':records[:100],'truncated':len(records)>100,'total_matches':len(records),'available_metrics':types}
    raise ValueError('Choose nutrition, profile, sync, archive or health; use the dedicated activity, FIT, training and maintenance tools for those datasets.')
