"""Fresh-evidence daily review and reversible automatic schedule adjustments."""
import json
from datetime import timedelta

from .training import encoded, _snapshot, _revision
from .training_accounting import session_day


def restore_budget_sessions(c, root, rows, today, tz):
    automatic=set()
    reasons={'Rest within cycling budget','Rest within recent volume budget','Rest within sport volume budget'}
    for row in c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=?',(root,)):
        for change in json.loads(row[0]).get('changes',[]):
            if change.get('action') in reasons:automatic.add(change['workout_id'])
    changes=[]
    for row in rows:
        if row['completion_status']!='cancelled' or row['publish_status']!='local' or row['garmin_workout_id']:
            continue
        definition=json.loads(row['definition_json'])
        if row['id'] not in automatic and not definition.get('automatic_budget_cancellation'):continue
        if not today<=session_day(row,tz)<today+timedelta(days=7):continue
        if definition.get('fixed_commitment') or definition.get('user_adjusted'):continue
        # Reconsider the original slot; the normal allocator must still approve
        # its volume, recovery and availability before it can remain planned.
        c.execute("UPDATE planned_workouts SET completion_status='planned',revision=revision+1 WHERE id=?",(row['id'],))
        _revision(c,_snapshot(c,row['id']))
        changes.append({'workout_id':row['id'],'title':row['title'],'action':'Reconsidered automatic rest',
                        'reason':'Recheck this system-cancelled slot against current completed work and weekly allowance.'})
    return changes


def restore_daily_baselines(c, rows, today, tz):
    for row in rows:
        if row['completion_status']!='planned' or not today<=session_day(row,tz)<today+timedelta(days=7):continue
        definition=json.loads(row['definition_json'])
        base=definition.get('daily_base_definition')
        if not base or definition.get('user_adjusted') or definition.get('fixed_commitment'):continue
        if row['publish_status'] not in ('local','published','update_needed'):continue
        from .workout_timing import preserve_timing
        base=preserve_timing(dict(base),definition)
        c.execute("UPDATE planned_workouts SET definition_json=?,title=?,revision=revision+1,publish_status=CASE WHEN publish_status='local' THEN 'local' ELSE 'update_needed' END WHERE id=?",(encoded(base),base['title'],row['id']))
        _revision(c,_snapshot(c,row['id']))


def fresh_sync(c, day):
    """Coverage alone is insufficient: wait until the sync and recovery QC finish."""
    job=c.execute("SELECT status,checkpoint_json FROM jobs WHERE job_type='garmin_sync' ORDER BY created_at DESC,rowid DESC LIMIT 1").fetchone()
    if not job or job['status']!='completed':return False
    checkpoint=json.loads(job['checkpoint_json'] or '{}')
    if checkpoint.get('failures') or day in checkpoint.get('training_load_refresh',{}).get('failed_dates',[]):return False
    qc=checkpoint.get('qc',{})
    if qc.get('through_date')!=day or qc.get('status')!='passed' or qc.get('issues'):return False
    rows={r['data_type']:r for r in c.execute("SELECT data_type,status,coverage_end FROM sync_checkpoints")}
    return all(kind in rows and rows[kind]['status']=='synced' and (rows[kind]['coverage_end'] or '')>=day
               for kind in ('sleep_metrics','daily_metrics','hrv_metrics','activities'))
