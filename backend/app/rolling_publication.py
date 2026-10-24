"""Explicitly enabled, account- and program-bound rolling seven-day publication."""
import json
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from .database import connect


def status(path=None):
    with connect(path) as c:row=c.execute('SELECT enabled,root_plan_id,timezone,last_job_id,status,detail_json FROM garmin_rolling_publication WHERE id=1').fetchone()
    return {**dict(row),'detail':json.loads(row['detail_json'])} if row else {'enabled':False,'status':'disabled'}


def disable(path=None):
    with connect(path) as c:
        c.execute("UPDATE garmin_rolling_publication SET enabled=0,status='disabled',updated_at=CURRENT_TIMESTAMP WHERE id=1")
        c.execute("UPDATE garmin_publication_jobs SET rolling_requested=0 WHERE status IN ('preview','queued','running','attention')")
    return status(path)


def window(c,root,tz,now,include_pending=True):
    from .active_training import _program_workouts
    today=now.astimezone(ZoneInfo(tz)).date();end=today+timedelta(days=6)
    result=[]
    for row in _program_workouts(c,root):
        d=json.loads(row['definition_json']);day=d.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()
        if row['completion_status']=='planned' and today.isoformat()<=day<=end.isoformat() or include_pending and row['completion_status'] in ('skipped','cancelled') and row['publish_status']=='update_needed' and row['garmin_workout_id'] and day>=today.isoformat():result.append(row['id'])
    return result


def sync(path=None,client_factory=None,now=None):
    from .garmin_training_publish import preview,approve,run,view,account
    from .garmin_connection import load_client
    from .active_training import review
    now=now or datetime.now(timezone.utc);factory=client_factory or load_client
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');policy=c.execute('SELECT * FROM garmin_rolling_publication WHERE id=1').fetchone()
        if not policy or not policy['enabled'] or policy['running']:return status(path)
        c.execute('UPDATE garmin_rolling_publication SET running=1 WHERE id=1')
    outcome='attention';detail={};job_id=None
    try:
        client=factory(path)
        if account(client)[0]!=policy['account_key']:raise ValueError('Garmin account changed. Re-enable rolling publication for the intended account.')
        with connect(path) as c:
            program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
            if not program or program['plan_id']!=policy['root_plan_id'] or program['status']!='active':raise ValueError('The approved program is no longer active. Rolling publication is paused until reviewed.')
            pending=c.execute("SELECT id FROM garmin_publication_jobs WHERE account_key=? AND status IN ('queued','running','attention','restored_review') LIMIT 1",(policy['account_key'],)).fetchone()
            if pending:raise ValueError('An unfinished Garmin publication needs review/reconciliation first.')
        review(path,policy['timezone'],now,trigger='manual')
        with connect(path) as c:identifiers=window(c,policy['root_plan_id'],policy['timezone'],now)
        if not identifiers:outcome='up_to_date';return {'enabled':True,'status':outcome}
        job=preview({'workout_ids':identifiers,'timezone':policy['timezone']},path,lambda p:client,now)
        detail={'blocked':job.get('blocked',[])};job_id=job.get('id')
        if not job_id:outcome='attention';return {'enabled':True,'status':outcome,'detail':detail}
        # One stored opt-in covers routine app-owned updates. The standard worker
        # still checks hashes, remote ownership, revisions and ambiguous outcomes.
        with connect(path) as c:
            current=c.execute('SELECT enabled,root_plan_id,account_key FROM garmin_rolling_publication WHERE id=1').fetchone()
            if not current['enabled'] or current['root_plan_id']!=policy['root_plan_id'] or current['account_key']!=policy['account_key']:raise ValueError('Automatic publication was disabled or reconfigured before this send.')
        approve(job_id,path,lambda p:client,now);run(job_id,path,lambda p:client)
        final=view(job_id,path);outcome='up_to_date' if final['status']=='verified' and not detail['blocked'] else 'attention'
    except Exception as error:
        detail={'message':str(error) if isinstance(error,ValueError) else 'Automatic Garmin update could not complete. Check the publication result and connection.'}
    finally:
        with connect(path) as c:
            c.execute("UPDATE garmin_rolling_publication SET running=0,last_job_id=COALESCE(?,last_job_id),status=CASE WHEN enabled=1 THEN ? ELSE 'disabled' END,detail_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",(job_id,outcome,json.dumps(detail)))
    return status(path)
