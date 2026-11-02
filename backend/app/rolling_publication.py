"""Explicitly enabled, account/program-bound daily next-seven-workout publication."""
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
    today=now.astimezone(ZoneInfo(tz)).date()
    planned=[];pending=[]
    for row in sorted(_program_workouts(c,root),key=lambda r:(r['scheduled_for'],r['id'])):
        d=json.loads(row['definition_json']);day=d.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()
        if row['completion_status']=='planned' and day>=today.isoformat():planned.append(row['id'])
        elif include_pending and row['completion_status'] in ('skipped','cancelled') and row['publish_status']=='update_needed' and row['garmin_workout_id'] and day>=today.isoformat():pending.append(row['id'])
    return planned[:7]+pending[:14]


def sync(path=None,client_factory=None,now=None):
    from .garmin_training_publish import preview,approve,run,view,account
    from .garmin_connection import load_client
    from .active_training import review
    now=now or datetime.now(timezone.utc);factory=client_factory or load_client
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');policy=c.execute('SELECT * FROM garmin_rolling_publication WHERE id=1').fetchone()
        if not policy or not policy['enabled'] or policy['running']:return status(path)
        prior=json.loads(policy['detail_json'])
        if prior.get('last_success_date')==now.astimezone(ZoneInfo(policy['timezone'])).date().isoformat():return status(path)
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
        if not identifiers:
            outcome='up_to_date';detail['last_success_date']=now.astimezone(ZoneInfo(policy['timezone'])).date().isoformat()
            return {'enabled':True,'status':outcome}
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
        if outcome=='up_to_date':detail['last_success_date']=now.astimezone(ZoneInfo(policy['timezone'])).date().isoformat()
    except Exception as error:
        detail={'message':str(error) if isinstance(error,ValueError) else 'Automatic Garmin update could not complete. Check the publication result and connection.'}
    finally:
        with connect(path) as c:
            c.execute("UPDATE garmin_rolling_publication SET running=0,last_job_id=COALESCE(?,last_job_id),status=CASE WHEN enabled=1 THEN ? ELSE 'disabled' END,detail_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",(job_id,outcome,json.dumps(detail)))
    return status(path)


class DailyPublicationWorker:
    """Foreground app worker; never installs a login item/background service."""
    def __init__(self,path=None):
        import threading
        self.path=path;self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self.run,name='daily-workout-publication',daemon=True)

    def start(self):self.thread.start()

    def stop(self):
        self.stop_event.set();self.thread.join(timeout=1)

    def run(self):
        while not self.stop_event.is_set():
            try:self.tick()
            except Exception:pass  # The normal sync/publication screens retain errors.
            self.stop_event.wait(60)

    def tick(self,now=None,client_factory=None):
        now=now or datetime.now(timezone.utc)
        with connect(self.path) as c:
            policy=c.execute('SELECT * FROM garmin_rolling_publication WHERE id=1').fetchone()
            if not policy or not policy['enabled'] or policy['running']:return
            today=now.astimezone(ZoneInfo(policy['timezone'])).date().isoformat()
            if json.loads(policy['detail_json']).get('last_success_date')==today:return
            # Do not publish from stale or partially collected core evidence.
            ready={r['data_type']:r for r in c.execute("SELECT data_type,status,coverage_end FROM sync_checkpoints WHERE data_type IN ('activities','daily_metrics','sleep_metrics','hrv_metrics')")}
            if any(kind not in ready or ready[kind]['status']!='synced' or (ready[kind]['coverage_end'] or '')<today for kind in ('activities','daily_metrics','sleep_metrics','hrv_metrics')):return
            job=c.execute("SELECT checkpoint_json FROM jobs WHERE job_type='garmin_sync' ORDER BY created_at DESC LIMIT 1").fetchone()
            load=json.loads(job['checkpoint_json'] or '{}').get('training_load_refresh',{}) if job else {}
            if today in load.get('failed_dates',[]):return
            qc=json.loads(job['checkpoint_json'] or '{}').get('qc',{}) if job else {}
            if any(issue['data_type'] in ('sleep_metrics','daily_metrics','hrv_metrics') for issue in qc.get('issues',[])):return
        return sync(self.path,client_factory,now)
