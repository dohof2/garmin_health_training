"""Reviewed, durable Garmin workout publication through the pinned private client.

No retries blindly repeat a possibly successful remote create or schedule.
"""
import json
import sqlite3
import uuid
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .garmin_connection import load_client
from .garmin_workout_mapping import workout_payload, canonical, digest
from .training import encoded, _snapshot, _revision


def utcnow():return datetime.now(timezone.utc)


def account(client):
    identity=client.display_name
    if not isinstance(identity,str) or not identity.strip():raise ValueError('Garmin account identity could not be verified. Reconnect Garmin first.')
    return digest({'provider':'garminconnect','account':identity}),identity


def view(job_id,path=None):
    with connect(path) as c:
        job=c.execute('SELECT * FROM garmin_publication_jobs WHERE id=?',(job_id,)).fetchone()
        if not job:raise ValueError('Publication not found')
        items=[dict(r) for r in c.execute('SELECT * FROM garmin_publication_items WHERE job_id=? ORDER BY rowid',(job_id,))]
    output=[]
    for item in items:
        snapshot=json.loads(item.pop('snapshot_json'));payload=json.loads(item.pop('payload_json'))
        item.update(title=snapshot['definition']['title'],duration_minutes=snapshot['definition']['duration_minutes'],sport=snapshot['definition']['sport'],steps=payload.get('workoutSegments',[{}])[0].get('workoutSteps',[]) if payload else [],warnings=snapshot.get('warnings',[]))
        if item['remote_workout_id']:item['garmin_url']='https://connect.garmin.com/modern/workout/'+item['remote_workout_id']
        output.append(item)
    return {**dict(job),'items':output,'provider':'garminconnect (unofficial)','device_status':'Device delivery has not been verified. Sync a compatible device with Garmin Connect.'}


def history(path=None):
    with connect(path) as c:
        ids=[r[0] for r in c.execute("SELECT id FROM garmin_publication_jobs WHERE status!='preview' ORDER BY created_at DESC LIMIT 20")]
        pending=[dict(r) for r in c.execute("SELECT id,title,completion_status FROM planned_workouts WHERE publish_status='update_needed'")]
        local=[dict(r) for r in c.execute("""SELECT w.id,w.title,w.sport,w.scheduled_for,w.definition_json
            FROM planned_workouts w JOIN training_plans p ON p.id=w.training_plan_id
            WHERE w.publish_status='local' AND w.completion_status='planned'
              AND p.deleted_at IS NULL AND p.status IN ('active','accepted')
              AND NOT EXISTS (SELECT 1 FROM garmin_publication_items i JOIN garmin_publication_jobs j ON j.id=i.job_id WHERE i.workout_id=w.id AND j.status!='preview')
            ORDER BY w.scheduled_for,w.id LIMIT 21""")]
    for row in local:
        reasons=[]
        try:
            definition=json.loads(row.pop('definition_json'))
            if row['sport']=='strength':
                from .garmin_strength import mapping_blockers
                reasons=mapping_blockers(definition)
            if not reasons:workout_payload(definition,'local-eligibility-check')
        except (ValueError,TypeError,KeyError,AttributeError) as error:reasons=[str(error)]
        row.update(state='blocked' if reasons else 'not_queued',blocked_reasons=reasons,
                   message='No approved publication job exists for this session. A local plan is not a Garmin send.')
    return {'jobs':[view(identifier,path) for identifier in ids],'pending_updates':pending,'local_workouts':local}


def preview(arguments,path=None,client_factory=load_client,now=None,*,pending_blocks=None):
    now=now or utcnow();tz=arguments.get('timezone') or 'UTC';ZoneInfo(tz)
    if arguments.get('next_workouts') is not None:
        if type(arguments['next_workouts']) is not int or arguments['next_workouts']!=7 or arguments.get('next_days') is not None:raise ValueError('Choose the next seven calendar days')
        arguments={**arguments,'next_days':7}
        arguments.pop('next_workouts')
    identifiers=arguments.get('workout_ids') or [];definition=arguments.get('definition')
    calendar_window=arguments.get('next_days') is not None
    desired=set();generation_warnings=[]
    if calendar_window:
        if type(arguments['next_days']) is not int or arguments['next_days']!=7 or identifiers or definition or arguments.get('next_workouts') is not None or arguments.get('schedule',True) is not True:
            raise ValueError('Choose seven calendar days with scheduling enabled')
        from .rolling_publication import window
        from .active_training import _fill
        with connect(path) as c:
            c.execute('BEGIN IMMEDIATE')
            program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
            if not program:raise ValueError('Activate a program before publishing its next seven days')
            generation_warnings=_fill(c,program['plan_id'],json.loads(program['state_json']),now.astimezone(ZoneInfo(tz)).date(),now,calendar_days=7)
            identifiers=window(c,program['plan_id'],tz,now,include_pending=False,calendar_days=7)
            desired={'workout:'+identifier for identifier in identifiers}
    if not isinstance(identifiers,list) or len(identifiers)>21 or len(set(identifiers))!=len(identifiers):raise ValueError('Choose up to 21 distinct saved sessions')
    if not calendar_window and bool(identifiers)==bool(definition):raise ValueError('Choose saved sessions or one standalone workout')
    schedule=arguments.get('schedule',True)
    if type(schedule) is not bool:raise ValueError('Choose whether to schedule on the calendar')
    today=now.astimezone(ZoneInfo(tz)).date();snapshots=[];blocked=[{'title':'Upcoming schedule','reason':message} for message in generation_warnings]
    with connect(path) as c:
        for identifier in identifiers:
            row=_snapshot(c,identifier)
            if not row:raise ValueError('A selected workout no longer exists')
            parent=c.execute('SELECT deleted_at,status FROM training_plans WHERE id=?',(row['training_plan_id'],)).fetchone()
            if not parent or parent['deleted_at'] or parent['status'] not in ('active','accepted'):raise ValueError('Choose sessions from an accepted active plan')
            d=json.loads(row['definition_json']);day=d.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()
            snapshots.append({'workout_id':identifier,'revision':row['revision'],'definition':d,'date':day,'completion_status':row['completion_status'],'identity':'workout:'+identifier,'existing_remote_id':row['garmin_workout_id']})
        if definition:
            if not isinstance(definition,dict):raise ValueError('Invalid standalone workout')
            day=arguments.get('scheduled_date') or today.isoformat();date.fromisoformat(day)
            snapshots.append({'workout_id':None,'revision':None,'definition':definition,'date':day,'completion_status':'planned','identity':'standalone:'+digest({'definition':definition,'date':day})})
    rolling=arguments.get('enable_rolling',False)
    if type(rolling) is not bool:raise ValueError('Choose whether to enable rolling publication')
    rolling_root=None
    if rolling:
        if not schedule or definition:raise ValueError('Rolling publication requires saved sessions scheduled on their plan dates')
        from .rolling_publication import window
        with connect(path) as c:
            program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
            if not program:raise ValueError('Activate a program before enabling rolling publication')
            if set(identifiers)!=set(window(c,program['plan_id'],tz,now,include_pending=False)):raise ValueError('Review the next seven days before enabling daily automatic publication')
            rolling_root=program['plan_id']
    pending_blocks=pending_blocks or {}
    candidates=[]
    for snapshot in snapshots:
        if snapshot['identity'] in pending_blocks:
            blocked.append(pending_blocks[snapshot['identity']]);continue
        try:
            if snapshot['completion_status'] not in ('planned','skipped','cancelled'):raise ValueError('Completed sessions are not published')
            if snapshot['date']<today.isoformat():raise ValueError('Choose a current or future session')
            if snapshot['definition'].get('review_hold'):raise ValueError('This session is held for review; resolve it before publishing')
            payload,warnings=workout_payload(snapshot['definition'],'training-app:'+digest(snapshot['identity'])[:24])
            snapshot['warnings']=warnings;candidates.append((snapshot,payload))
        except (ValueError,TypeError,KeyError) as error:blocked.append({'title':snapshot['definition'].get('title','Workout'),'reason':str(error)})
    if not candidates and not calendar_window:return {'status':'blocked','blocked':blocked,'items':[],'message':'None of the selected sessions can be sent. No Garmin changes were made.'}
    client=client_factory(path);key,label=account(client);job_id=str(uuid.uuid4())
    if calendar_window:
        # Keep only the current saved workouts in this date window. Ownership
        # comes from this account's verified app mapping, never a title match.
        with connect(path) as c:
            links=c.execute('SELECT * FROM garmin_publication_links WHERE account_key=? AND scheduled_date>=? AND scheduled_date<? AND remote_schedule_id IS NOT NULL',
                            (key,today.isoformat(),(today+timedelta(days=7)).isoformat())).fetchall()
            for link in links:
                if link['identity_key'] in desired:continue
                if link['identity_key'] in pending_blocks:
                    blocked.append(pending_blocks[link['identity_key']]);continue
                previous=c.execute('SELECT snapshot_json FROM garmin_publication_items WHERE account_key=? AND identity_key=? ORDER BY rowid DESC LIMIT 1',(key,link['identity_key'])).fetchone()
                if not previous or not link['verified_hash'] or not link['verified_payload_json']:
                    raise ValueError('An older app calendar entry needs reconciliation before it can be removed')
                snapshot=json.loads(previous['snapshot_json'])
                snapshot.update(workout_id=None,revision=None,completion_status='cancelled',identity=link['identity_key'],date=link['scheduled_date'],cleanup=True)
                candidates.append((snapshot,json.loads(link['verified_payload_json'])))
        if not candidates:return {'status':'blocked' if blocked else 'verified','items':[],'blocked':blocked,'message':'No workouts can be sent. See the blocked sessions below.' if blocked else 'No workouts are scheduled in the next seven days and no older app entries need removing.'}
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO garmin_publication_jobs(id,account_key,account_label,timezone,created_at,expires_at) VALUES(?,?,?,?,?,?)',(job_id,key,label,tz,now.isoformat(),(now+timedelta(minutes=30)).isoformat()))
        if rolling:c.execute('UPDATE garmin_publication_jobs SET rolling_root=?,rolling_requested=1 WHERE id=?',(rolling_root,job_id))
        for snapshot,payload in candidates:
            link=c.execute('SELECT * FROM garmin_publication_links WHERE account_key=? AND identity_key=?',(key,snapshot['identity'])).fetchone()
            if snapshot.get('existing_remote_id') and not link:raise ValueError('This workout belongs to another Garmin account or has no verified app mapping. Reconnect the original account; it was not duplicated.')
            snapshot['previous_hash']=link['verified_hash'] if link else None
            payload_hash=digest(canonical(payload));target_date=snapshot['date'] if schedule else link['scheduled_date'] if link else None
            action='create'
            if snapshot['completion_status'] in ('skipped','cancelled'):
                if not link or not link['remote_schedule_id']:continue
                action='unschedule';target_date=None
            elif link:
                if not link['verified_hash']:raise ValueError('An earlier send is unresolved. Open its publication result and reconcile it first.')
                action='update' if link['verified_hash']!=payload_hash else 'reschedule' if target_date!=link['scheduled_date'] else 'unchanged'
            c.execute('INSERT INTO garmin_publication_items(id,job_id,account_key,identity_key,workout_id,workout_revision,snapshot_json,payload_json,payload_hash,scheduled_date,action,remote_workout_id,remote_schedule_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (str(uuid.uuid4()),job_id,key,snapshot['identity'],snapshot['workout_id'],snapshot['revision'],encoded(snapshot),encoded(payload),payload_hash,target_date,action,link['remote_workout_id'] if link else None,link['remote_schedule_id'] if link else None))
        if not c.execute('SELECT 1 FROM garmin_publication_items WHERE job_id=?',(job_id,)).fetchone():raise ValueError('These sessions are not scheduled in Garmin; nothing needs sending or removing.')
    return {**view(job_id,path),'blocked':blocked,'message':'Review exactly what will be sent. Garmin has not been changed.'+(' Approving also enables publication of this program’s rolling next seven days while the app is open with current sync evidence. Existing app-owned workouts are updated instead of duplicated; unrelated Garmin workouts are preserved.' if rolling else '')}


def send(arguments,path=None,client_factory=load_client,now=None):
    """A Publish click authorizes preparation and approval in one request."""
    now=now or utcnow()
    pending_blocks={}
    if arguments.get('next_workouts')==7 and arguments.get('next_days') is None:
        arguments={**arguments,'next_days':7};arguments.pop('next_workouts')
    if arguments.get('next_days')==7:
        client=client_factory(path);key,_=account(client)
        tz=arguments.get('timezone') or 'UTC';today=now.astimezone(ZoneInfo(tz)).date()
        with connect(path) as c:
            from .training_accounting import session_day
            pending=[];end=today+timedelta(days=7)
            for old_job in c.execute("SELECT id FROM garmin_publication_jobs WHERE account_key=? AND status IN ('attention','queued') ORDER BY created_at",(key,)).fetchall():
                for item in c.execute('SELECT workout_id,snapshot_json FROM garmin_publication_items WHERE job_id=?',(old_job['id'],)).fetchall():
                    old_date=date.fromisoformat(json.loads(item['snapshot_json'])['date'])
                    current=_snapshot(c,item['workout_id']) if item['workout_id'] else None
                    if today<=old_date<end or current and today<=session_day(current,tz)<end:
                        pending.append(old_job['id']);break
        for identifier in pending:
            stale_unresolved=False
            with connect(path) as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT status FROM garmin_publication_jobs WHERE id=?',(identifier,)).fetchone()[0]=='running':
                    raise ValueError('An earlier Garmin send is still running. Wait for its result before publishing the changed schedule.')
                for item in c.execute("SELECT * FROM garmin_publication_items WHERE job_id=? AND state NOT IN ('verified','superseded')",(identifier,)).fetchall():
                    current=_snapshot(c,item['workout_id']) if item['workout_id'] else None;snapshot=json.loads(item['snapshot_json'])
                    from .training_accounting import session_day
                    stale=bool(item['workout_id']) and (not current or json.loads(current['definition_json'])!=snapshot['definition'] or current['completion_status']!=snapshot['completion_status'] or session_day(current,tz).isoformat()!=snapshot['date'])
                    link=c.execute('SELECT * FROM garmin_publication_links WHERE account_key=? AND identity_key=?',(key,item['identity_key'])).fetchone()
                    safe=item['state'] in ('queued','retryable') and ((link and link['verified_hash'] and link['remote_workout_id']==item['remote_workout_id']) or (not link and not item['remote_workout_id']))
                    if not stale and not (item['state']=='retryable' and safe):continue
                    if not safe:
                        stale_unresolved=True
                        continue
                    c.execute("UPDATE garmin_publication_items SET state='superseded',error='Replaced by the current saved plan.' WHERE id=?",(item['id'],))
                    c.execute('UPDATE garmin_publication_jobs SET rolling_requested=0 WHERE id=?',(identifier,))
            if not stale_unresolved:run(identifier,path,lambda p:client)
            result=view(identifier,path)
            if result['status']!='verified':
                with connect(path) as c:
                    for item in c.execute("SELECT * FROM garmin_publication_items WHERE job_id=? AND state NOT IN ('verified','superseded')",(identifier,)).fetchall():
                        snapshot=json.loads(item['snapshot_json'])
                        pending_blocks[item['identity_key']]={'title':snapshot['definition'].get('title','Workout'),
                            'reason':item['error'] or 'An earlier upload for this workout needs reconciliation. Other workouts can still be published.'}
        with connect(path) as c:
            removed=c.execute("""SELECT w.id FROM planned_workouts w JOIN garmin_publication_links l ON l.workout_id=w.id
                WHERE l.account_key=? AND l.remote_schedule_id IS NULL AND l.scheduled_date IS NULL AND l.verified_hash IS NOT NULL
                AND w.publish_status='update_needed' AND w.completion_status IN ('skipped','cancelled')
                AND substr(w.scheduled_for,1,10)>=? AND substr(w.scheduled_for,1,10)<?""",
                (key,today.isoformat(),(today+timedelta(days=7)).isoformat())).fetchall()
            for row in removed:
                c.execute("UPDATE planned_workouts SET publish_status='published',revision=revision+1 WHERE id=?",(row['id'],))
                _revision(c,_snapshot(c,row['id']))
        client_factory=lambda p,client=client:client
    result=preview(arguments,path,client_factory,now,pending_blocks=pending_blocks)
    if not result.get('id'):return result
    approved=approve(result['id'],path,client_factory,now)
    return {**approved,'blocked':result.get('blocked',[]),'message':'Publishing to Garmin…'}


def approve(job_id,path=None,client_factory=load_client,now=None):
    now=now or utcnow();client=client_factory(path);key,_=account(client)
    try:
        with connect(path) as c:
            c.execute('BEGIN IMMEDIATE');job=c.execute('SELECT * FROM garmin_publication_jobs WHERE id=?',(job_id,)).fetchone()
            if not job or job['account_key']!=key:raise ValueError('Garmin account changed. Preview again.')
            if job['status']!='preview':return view(job_id,path)
            if datetime.fromisoformat(job['expires_at'])<now:raise ValueError('This preview expired. Preview again.')
            items=c.execute('SELECT * FROM garmin_publication_items WHERE job_id=?',(job_id,)).fetchall()
            for item in items:
                snapshot=json.loads(item['snapshot_json'])
                if item['workout_id']:
                    row=_snapshot(c,item['workout_id'])
                    from .training_accounting import session_day
                    if not row or row['revision']!=item['workout_revision'] or json.loads(row['definition_json'])!=snapshot['definition'] or session_day(row,job['timezone']).isoformat()!=snapshot['date']:raise ValueError('A workout changed. Preview again.')
                    parent=c.execute('SELECT deleted_at,status FROM training_plans WHERE id=?',(row['training_plan_id'],)).fetchone()
                    if not parent or parent['deleted_at'] or parent['status'] not in ('active','accepted'):raise ValueError('The plan is no longer active. Preview again.')
                link=c.execute('SELECT * FROM garmin_publication_links WHERE account_key=? AND identity_key=?',(key,item['identity_key'])).fetchone()
                if (link['verified_hash'] if link else None)!=snapshot.get('previous_hash'):raise ValueError('Garmin mapping changed. Preview again.')
                c.execute("UPDATE garmin_publication_items SET state='queued' WHERE id=?",(item['id'],))
                if item['workout_id'] and item['action']!='unchanged':
                    c.execute("UPDATE planned_workouts SET publish_status='publishing',revision=revision+1 WHERE id=?",(item['workout_id'],));_revision(c,_snapshot(c,item['workout_id']))
            c.execute("UPDATE garmin_publication_jobs SET status='queued',approved_at=? WHERE id=?",(now.isoformat(),job_id))
    except sqlite3.IntegrityError as error:raise ValueError('This workout already has an unfinished send. Open its result and reconcile it first.') from error
    return view(job_id,path)


def _set(item_id,path,**values):
    allowed={'state','remote_workout_id','remote_schedule_id','error'}
    if set(values)-allowed:raise ValueError('Invalid internal publication state')
    with connect(path) as c:c.execute('UPDATE garmin_publication_items SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),item_id))


def _schedule_id(response):
    if not isinstance(response,dict):return None
    value=response.get('workoutScheduleId') or response.get('scheduleId')
    if value is None and response.get('workoutId') and response.get('itemType','workout')=='workout':value=response.get('id')
    return str(value) if str(value).isdigit() and int(value)>0 else None


def _verify_schedule(client,identifier,workout_id,day):
    row=client.get_scheduled_workout_by_id(identifier)
    if not isinstance(row,dict) or str(row.get('workoutId') or (row.get('workout') or {}).get('workoutId'))!=str(workout_id) or str(row.get('date') or row.get('calendarDate'))[:10]!=day:
        raise ValueError('Garmin calendar read-back did not match the approved workout and date')


def _reconcile(item,client,path):
    """Read-only reconciliation; no match is not permission to create again."""
    if not item['remote_workout_id']:
        rows=client.get_workouts(0,100)
        if not isinstance(rows,list):raise ValueError('Unexpected Garmin workout list schema')
        expected=json.loads(item['payload_json']);matches=[]
        for row in rows:
            if row.get('description')==expected['description'] and row.get('workoutId'):
                remote=client.get_workout_by_id(row['workoutId'])
                if canonical(remote)==canonical(expected):matches.append(str(row['workoutId']))
        if len(matches)!=1:raise ValueError('Create outcome is unknown. Review Garmin Connect; no duplicate was sent.')
        item['remote_workout_id']=matches[0];_set(item['id'],path,remote_workout_id=matches[0],state='created')
    if item['remote_schedule_id']:
        with connect(path) as c:link=c.execute('SELECT * FROM garmin_publication_links WHERE account_key=? AND identity_key=?',(item['account_key'],item['identity_key'])).fetchone()
        old_day=(link['scheduled_date'] if link else None) or item['scheduled_date']
        if not old_day:raise ValueError('Unknown calendar date; review Garmin Connect')
        day=date.fromisoformat(old_day);response=client.get_scheduled_workouts(day.year,day.month)
        rows=response.get('calendarItems') if isinstance(response,dict) else None
        if not isinstance(rows,list):raise ValueError('Calendar removal could not be reconciled')
        if not any(_schedule_id(r)==item['remote_schedule_id'] for r in rows):
            item['remote_schedule_id']=None;_set(item['id'],path,remote_schedule_id=None,state='created')
    if item['scheduled_date'] and not item['remote_schedule_id']:
        day=date.fromisoformat(item['scheduled_date']);response=client.get_scheduled_workouts(day.year,day.month)
        rows=response.get('calendarItems') if isinstance(response,dict) else None
        if not isinstance(rows,list):raise ValueError('Calendar outcome is unknown. Review Garmin Connect before retrying.')
        matches=[r for r in rows if str(r.get('workoutId'))==item['remote_workout_id'] and str(r.get('date'))[:10]==day.isoformat()]
        if len(matches)!=1 or not _schedule_id(matches[0]):raise ValueError('Calendar outcome is unknown. No duplicate calendar entry was sent.')
        item['remote_schedule_id']=_schedule_id(matches[0]);_set(item['id'],path,remote_schedule_id=item['remote_schedule_id'],state='verifying')


def _process(item,client,path):
    payload=json.loads(item['payload_json']);snapshot=json.loads(item['snapshot_json']);action=item['action']
    was_unknown=item['state']=='unknown'
    if was_unknown:_reconcile(item,client,path)
    with connect(path) as c:link=c.execute('SELECT * FROM garmin_publication_links WHERE account_key=? AND identity_key=?',(item['account_key'],item['identity_key'])).fetchone()
    already_applied=False;missing_remote=False
    if item['remote_workout_id'] and action in ('update','reschedule','unschedule','unchanged') and not was_unknown:
        from garminconnect import GarminConnectNotFoundError
        try:current=client.get_workout_by_id(item['remote_workout_id'])
        except GarminConnectNotFoundError:
            if not link or not link['verified_hash']:raise ValueError('The missing Garmin workout has no verified app mapping; reconcile it before sending again.')
            missing_remote=True
            current=json.loads(link['verified_payload_json'])
            if item['remote_schedule_id']:
                day=date.fromisoformat(link['scheduled_date']);calendar=client.get_scheduled_workouts(day.year,day.month)
                entries=calendar.get('calendarItems') if isinstance(calendar,dict) else None
                if not isinstance(entries,list):raise ValueError('Could not check the old Garmin calendar entry for the missing workout.')
                found=next((r for r in entries if _schedule_id(r)==item['remote_schedule_id']),None)
                if found:
                    if str(found.get('workoutId'))!=item['remote_workout_id']:raise ValueError('The Garmin calendar entry now belongs to another workout; it was not removed.')
                    _set(item['id'],path,state='scheduling')
                    client.unschedule_workout(item['remote_schedule_id'])
                    entries=client.get_scheduled_workouts(day.year,day.month).get('calendarItems')
                    if not isinstance(entries,list) or any(_schedule_id(r)==item['remote_schedule_id'] for r in entries):raise RuntimeError('Could not verify calendar removal')
                item['remote_schedule_id']=None;_set(item['id'],path,remote_schedule_id=None,state='created')
            if action!='unschedule':
                item['remote_workout_id']=None;_set(item['id'],path,remote_workout_id=None,state='queued')
        already_applied=action=='update' and canonical(current)==canonical(payload)
        if not already_applied and (not link or digest(canonical(current))!=link['verified_hash']):raise ValueError('The Garmin workout was edited outside this app. Review the conflict; it was not overwritten.')
    if not item['remote_workout_id']:
        _set(item['id'],path,state='creating')
        response=client.upload_workout(payload);identifier=response.get('workoutId') if isinstance(response,dict) else None
        if not str(identifier).isdigit() or int(identifier)<=0:raise RuntimeError('Garmin create returned an unrecognized identifier')
        item['remote_workout_id']=str(identifier);_set(item['id'],path,remote_workout_id=str(identifier),state='created')
    elif action=='update' and not already_applied and item['state'] in ('queued','retryable'):
        _set(item['id'],path,state='updating');client.update_workout(item['remote_workout_id'],payload);_set(item['id'],path,state='created')
    remote=current if missing_remote and action=='unschedule' else client.get_workout_by_id(item['remote_workout_id'])
    if action!='unschedule' and canonical(remote)!=canonical(payload):raise ValueError('Garmin read-back differs from the approved instructions or targets. Review in Garmin before retrying.')
    if item['remote_schedule_id'] and (action=='unschedule' or link and item['remote_schedule_id']==link['remote_schedule_id'] and item['scheduled_date']!=link['scheduled_date']):
        _set(item['id'],path,state='scheduling')
        client.unschedule_workout(item['remote_schedule_id'])
        # Require an explicit list read-back proving the app-owned entry is gone.
        old=date.fromisoformat(link['scheduled_date']);calendar=client.get_scheduled_workouts(old.year,old.month)
        rows=calendar.get('calendarItems') if isinstance(calendar,dict) else None
        if not isinstance(rows,list) or any(_schedule_id(r)==item['remote_schedule_id'] for r in rows):raise RuntimeError('Could not verify calendar removal')
        item['remote_schedule_id']=None;_set(item['id'],path,remote_schedule_id=None,state='created')
    if item['scheduled_date'] and not item['remote_schedule_id']:
        _set(item['id'],path,state='scheduling')
        response=client.schedule_workout(item['remote_workout_id'],item['scheduled_date']);identifier=_schedule_id(response)
        if not identifier:raise RuntimeError('Garmin calendar response needs reconciliation')
        item['remote_schedule_id']=identifier;_set(item['id'],path,remote_schedule_id=identifier,state='verifying')
    if item['remote_schedule_id']:_verify_schedule(client,item['remote_schedule_id'],item['remote_workout_id'],item['scheduled_date'])
    verified_hash=digest(canonical(remote))
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO garmin_publication_links(account_key,identity_key,workout_id,remote_workout_id,remote_schedule_id,scheduled_date,verified_hash,verified_payload_json) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account_key,identity_key) DO UPDATE SET remote_workout_id=excluded.remote_workout_id,remote_schedule_id=excluded.remote_schedule_id,scheduled_date=excluded.scheduled_date,verified_hash=excluded.verified_hash,verified_payload_json=excluded.verified_payload_json',
            (item['account_key'],item['identity_key'],item['workout_id'],item['remote_workout_id'],item['remote_schedule_id'],item['scheduled_date'],verified_hash,encoded(remote)))
        c.execute("UPDATE garmin_publication_items SET state='verified',error=NULL WHERE id=?",(item['id'],))
        if item['workout_id']:
            current=_snapshot(c,item['workout_id'])
            from .training_accounting import session_day
            job_timezone=c.execute('SELECT timezone FROM garmin_publication_jobs WHERE id=?',(item['job_id'],)).fetchone()[0]
            changed=not current or json.loads(current['definition_json'])!=snapshot['definition'] or session_day(current,job_timezone).isoformat()!=snapshot['date'] or current['completion_status']!=snapshot['completion_status']
            if current:
                c.execute('UPDATE planned_workouts SET garmin_workout_id=?,publish_status=?,revision=revision+1 WHERE id=?',(item['remote_workout_id'],'update_needed' if changed else 'published',item['workout_id']));_revision(c,_snapshot(c,item['workout_id']))
        elif snapshot.get('cleanup') and link and link['workout_id']:
            current=_snapshot(c,link['workout_id'])
            if current and current['completion_status'] in ('skipped','cancelled'):
                c.execute("UPDATE planned_workouts SET publish_status='published',revision=revision+1 WHERE id=?",(current['id'],))
                _revision(c,_snapshot(c,current['id']))


def run(job_id,path=None,client_factory=load_client):
    """One claimed worker per job; network calls happen outside SQLite transactions."""
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');job=c.execute('SELECT * FROM garmin_publication_jobs WHERE id=?',(job_id,)).fetchone()
        if not job or job['status'] not in ('queued','attention'):return
        c.execute("UPDATE garmin_publication_jobs SET status='running',error=NULL WHERE id=?",(job_id,))
    try:
        client=client_factory(path);key,_=account(client)
        if key!=job['account_key']:raise ValueError('Garmin account changed. Reconnect the approved account.')
        with connect(path) as c:items=[dict(r) for r in c.execute("SELECT * FROM garmin_publication_items WHERE job_id=? AND state NOT IN ('verified','superseded') ORDER BY rowid",(job_id,))]
        for item in items:
            try:_process(item,client,path)
            except Exception as error:
                with connect(path) as c:state=c.execute('SELECT state FROM garmin_publication_items WHERE id=?',(item['id'],)).fetchone()[0]
                # A definite 4xx rejection did not accept the write. Timeouts,
                # connection loss and 5xx responses remain ambiguous.
                from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError
                status=re.search(r'(?:API Error|HTTP)\s*(400|401|403|404|409|422|429)\b',str(error))
                rejected=isinstance(error,(GarminConnectAuthenticationError,GarminConnectTooManyRequestsError)) or bool(status)
                ambiguous=state in ('creating','updating','scheduling','unknown') and not rejected
                _set(item['id'],path,state='unknown' if ambiguous else 'retryable',error='Garmin outcome needs read-back reconciliation; a possibly successful operation will not be repeated blindly.' if ambiguous else str(error) if isinstance(error,ValueError) else 'Could not verify this workout. Check Garmin/account access or a remote edit conflict, then reconcile. No verified success is claimed.')
    except Exception:
        with connect(path) as c:c.execute("UPDATE garmin_publication_jobs SET error='Garmin account is unavailable or changed. Reconnect the approved account and retry.' WHERE id=?",(job_id,))
    finally:
        with connect(path) as c:
            pending=c.execute("SELECT COUNT(*) FROM garmin_publication_items WHERE job_id=? AND state NOT IN ('verified','superseded')",(job_id,)).fetchone()[0]
            c.execute('UPDATE garmin_publication_jobs SET status=? WHERE id=?',('attention' if pending else 'verified',job_id))
            if not pending and c.execute('SELECT rolling_requested FROM garmin_publication_jobs WHERE id=?',(job_id,)).fetchone()[0]:
                program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active' AND plan_id=?",(job['rolling_root'],)).fetchone()
                if program:
                    c.execute("INSERT INTO garmin_rolling_publication(id,enabled,account_key,root_plan_id,timezone,last_job_id) VALUES(1,1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=1,account_key=excluded.account_key,root_plan_id=excluded.root_plan_id,timezone=excluded.timezone,last_job_id=excluded.last_job_id,status='enabled',updated_at=CURRENT_TIMESTAMP",(job['account_key'],job['rolling_root'],job['timezone'],job_id))



def retry(job_id,path=None,client_factory=load_client):
    job=view(job_id,path)
    if job['status']!='attention':raise ValueError('Only an unfinished publication can be reconciled')
    client=client_factory(path)
    if account(client)[0]!=job['account_key']:raise ValueError('Reconnect the Garmin account that approved this publication')
    return job


def recover(path=None):
    """Startup never resumes external writes on its own."""
    with connect(path) as c:
        c.execute('UPDATE garmin_rolling_publication SET running=0')
        c.execute("UPDATE garmin_publication_items SET state='unknown',error='App stopped during a remote operation. Reconcile before retrying.' WHERE state IN ('creating','updating','scheduling')")
        c.execute("UPDATE garmin_publication_jobs SET status='attention' WHERE status IN ('running','queued')")
