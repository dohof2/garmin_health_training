"""Root-plan ownership, non-destructive removal and revision-bound lifecycle actions."""
import json
from datetime import datetime,timezone
from .database import connect

def membership(c,root):
    identifiers=[root]
    for row in c.execute('SELECT id,context_json FROM training_plans WHERE id!=?',(root,)):
        try:context=json.loads(row['context_json'])
        except (TypeError,ValueError):continue
        if isinstance(context,dict) and context.get('program_id')==root:identifiers.append(row['id'])
    return identifiers

def invalidate(c,root):
    c.execute('DELETE FROM training_review_gate WHERE plan_id=?',(root,))
    c.execute('UPDATE training_plans SET plan_revision=plan_revision+1 WHERE id=?',(root,))

def guard(c,root,expected=None):
    row=c.execute('SELECT * FROM training_plans WHERE id=?',(root,)).fetchone()
    if row is None:raise ValueError('Training plan not found')
    if row['deleted_at']:raise ValueError('This plan was removed; review a fresh proposal')
    if expected is not None and row['plan_revision']!=expected:raise ValueError('Training plan changed; refresh before continuing')
    return row

def delete_plan(root,expected,confirm,path=None):
    if confirm is not True:raise ValueError('Confirm removal of this saved plan')
    if type(expected) is not int:raise ValueError('Provide the saved plan revision')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM training_plans WHERE id=?',(root,)).fetchone()
        if row is None:raise ValueError('Training plan not found')
        if row['deleted_at']:return {'id':root,'deleted':True,'local_only':True,'message':'Plan already removed locally. Completed activities remain.'}
        guard(c,root,expected);identifiers=membership(c,root);now=datetime.now(timezone.utc).isoformat();published=0
        from .training import _snapshot,_revision
        for identifier in identifiers:
            for workout in c.execute("SELECT * FROM planned_workouts WHERE training_plan_id=? AND completion_status='planned'",(identifier,)).fetchall():
                if workout['publish_status']!='local' or workout['garmin_workout_id']:
                    published+=1;continue
                c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(workout['id'],));_revision(c,_snapshot(c,workout['id']))
            c.execute('UPDATE training_plans SET deleted_at=?,plan_revision=plan_revision+1 WHERE id=?',(now,identifier))
        c.execute('DELETE FROM active_training_program WHERE plan_id=?',(root,));c.execute('DELETE FROM training_review_gate WHERE plan_id=?',(root,))
        c.execute('UPDATE training_coach_brief SET revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=1')
        return {'id':root,'deleted':True,'local_only':True,'published_workouts_retained':published,'message':'Saved plan removed locally. Completed activities and feedback remain. Garmin/device workouts were not removed.'}

def set_program_status(root,expected_revision,status,path=None):
    if status not in ('active','paused','cancelled'):raise ValueError('Choose active, paused or cancelled')
    if type(expected_revision) is not int:raise ValueError('Provide the active program revision')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');guard(c,root)
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if program is None or program['plan_id']!=root:raise ValueError('The selected program is no longer current')
        if program['revision']!=expected_revision:raise ValueError('Active program changed; refresh before continuing')
        if program['status']=='cancelled' and status!='cancelled':raise ValueError('Cancelled plans cannot resume; review a fresh plan')
        if program['status']==status:return {'root_plan_id':root,'status':status,'revision':program['revision']}
        if status=='cancelled':
            from .training import _snapshot,_revision
            for identifier in membership(c,root):
                for row in c.execute("SELECT id FROM planned_workouts WHERE training_plan_id=? AND completion_status='planned' AND publish_status='local' AND garmin_workout_id IS NULL",(identifier,)).fetchall():
                    c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(row['id'],));_revision(c,_snapshot(c,row['id']))
                # Preserve explicit cancellation independently of completion history.
                saved=c.execute('SELECT context_json FROM training_plans WHERE id=?',(identifier,)).fetchone()
                context=json.loads(saved['context_json']);context['lifecycle_status']='cancelled'
                c.execute("UPDATE training_plans SET status='cancelled',context_json=? WHERE id=?",(json.dumps(context),identifier))
        c.execute('UPDATE active_training_program SET status=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=1',(status,));invalidate(c,root)
        return {'root_plan_id':root,'status':status,'revision':program['revision']+1}
