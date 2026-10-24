"""Conversational changes to accepted sessions: preview first, recheck on save."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .database import connect
from .training import _context, _revision, _snapshot, encoded


def normalized(message):
    text=message.lower().replace('’', "'")
    for old,new in {'workuot':'workout','tommorow':'tomorrow','aneorbic':'anaerobic','spritns':'sprints','trianing':'training','easir':'easier'}.items():
        text=text.replace(old,new)
    return text


def is_adjustment(message):
    from .workout_format import requested
    from .workout_edits import requested as blocks_requested
    if blocks_requested(message):return True
    if requested(message):return True
    text=normalized(message)
    if re.search(r'\bdoes (it|that|this) make sense\b|\bwhat do you think\b',text) and not re.search(r'\b(change|replace|remove|save|apply)\b',text):return False
    if re.search(r'\b(how|what|show|graph|plot|compare)\b',text) and not re.search(r'\b(make|give|change|reduce|cut|can we|should i|could we|would you)\b',text):return False
    if re.search(r'\b(make|change|set)\b.{0,35}\b\d+\s*(minutes?|mins?|hours?)\b|\b(add more time|turn it up|dial it back|take it easy|less intensity|more intensity)\b',text):return True
    return bool(re.search(r'\b(harder|easier|shorter|longer|tougher|lighter|hard|easy|reduce|cut|skip|cancel|rest|sprint|sprints|anaerobic|tempo|intervals|intensity|exhausted|tired|sore|soreness|fever|sick|pain|injured|sleep|slept|feeling good|feel great|feel good|fresh|busy|only have|only got|have only|can only|back off|dial|ramp|double|halve|increase|decrease|move|reschedule|swap)\b',text)) and not bool(re.search(r'\b(new plan|build a plan|create a plan|what is|what are|explain|difference between)\b',text))


def propose(message, path=None, now=None):
    from .active_training import read_active, capability, _program_workouts
    from .training_prescriptions import endurance, recovery_policy
    from .readiness import readiness_history
    from .training_load_charts import daily_rows
    now=now or datetime.now(timezone.utc)
    if not isinstance(message,str) or not message.strip() or len(message)>1500:raise ValueError('Describe the change in up to 1,500 characters')
    from .workout_format import requested, propose as format_proposal
    if requested(message):return format_proposal(message,path,now)
    text=normalized(message);active=read_active({},path);program=active.get('program')
    base={'tool':'propose_training_adjustment','kind':'adaptation','status':'needs_input','changes':{},'adjustments':[], 'request':message}
    def answer(status,reason):return {**base,'status':status,'message':reason}
    if not program or program['status']!='active':return answer('needs_input','There is no active plan to change. Activate a plan, or ask for an independent workout today.')
    tz=program['state']['timezone'];today=now.astimezone(ZoneInfo(tz)).date()
    rows=[w for w in active['workouts'] if w['completion_status']=='planned' and w.get('scheduled_date',w['scheduled_for'][:10])>=today.isoformat()]
    weekly=bool(re.search(r'\b(week|weekly|next 7 days)\b',text))
    if 'next week' in text:return answer('needs_input','Do you mean the next seven days or the following calendar week? I can adapt the materialized sessions once those dates are clear.')
    if re.search(r'\b(last|yesterday|finished|completed|felt|feedback)\b',text) and not re.search(r'\b(today|tomorrow|next|week|make|give|reduce|cut)\b',text):return answer('needs_input','Which completed session is this feedback for? Choose Feedback / edit session so I attach it to the correct workout.')
    sport='strength' if re.search(r'\b(strength|weights|gym|dumbbell|barbell|pull.up|dips?|leg press)\b',text) else 'running' if re.search(r'\b(run|running)\b',text) else 'cycling' if re.search(r'\b(ride|bike|cycling|sprints?|anaerobic|tempo)\b',text) else None
    if sport:rows=[w for w in rows if w['sport']==sport]
    target_day=today+timedelta(days=1) if 'tomorrow' in text else today if 'today' in text else None
    explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
    if explicit:
        try:target_day=datetime.fromisoformat(explicit[0]).date()
        except ValueError:return answer('needs_input','That date is invalid. Which date should I use?')
    if target_day is None:
        for index,name in enumerate(('monday','tuesday','wednesday','thursday','friday','saturday','sunday')):
            if name in text:target_day=today+timedelta(days=(index-today.weekday())%7);break
    if weekly:rows=[w for w in rows if w.get('scheduled_date',w['scheduled_for'][:10])<(today+timedelta(days=7)).isoformat()]
    elif target_day:rows=[w for w in rows if w.get('scheduled_date',w['scheduled_for'][:10])==target_day.isoformat()]
    if 'long ride' in text:rows=[w for w in rows if w['definition'].get('workout_kind') in ('long_endurance','long_tempo') or 'long' in w['title'].lower()]
    rows=sorted(rows,key=lambda w:(w['scheduled_for'],w['id']))
    if not weekly and len(rows)>1:
        if target_day and len({w['sport'] for w in rows})>1:return answer('needs_input','Which session should I change: '+', '.join(w['title'] for w in rows)+'?')
        rows=rows[:1]
    if not rows:return answer('needs_input','There is no matching upcoming session in the active plan. Which date and activity do you want to change?')
    if re.search(r'\b(move|reschedule|swap)\b',text):
        return answer('needs_input','Which session should move, and to which date? Use the session’s Reschedule control to check availability and recovery spacing before saving.')
    with connect(path) as c:
        context=_context(c,now,timezone_name=tz)
        all_sessions=[{**w,'definition':json.loads(w['definition_json'])} for w in _program_workouts(c,program['plan_id'])]
    capacity=capability(path,today,tz)
    readiness=readiness_history(today,1,tz,path,now=now)['latest']
    loads=[r for r in daily_rows(path) if (today-timedelta(days=2)).isoformat()<=r['date']<=today.isoformat()]
    policy=recovery_policy(readiness,loads[-1] if loads else None,context['recent_feedback'],capacity,today)
    # New disclosures matter even before the user saves any feedback.
    symptoms=re.sub(r'\b(no|without) (pain|soreness|illness)\b','',text)
    illness=bool(re.search(r'\b(pain|fever|sick|illness|injured|injury|dizzy|chest)\b',symptoms))
    fatigue=bool(re.search(r'\b(tired|exhausted|sore|soreness|poor sleep|bad sleep|slept badly|slept poorly|sleep was bad|sleep was terrible|burnt out)\b|\b(slept|sleep)\s+(only\s+)?[1-4]\s*(hours?|h)\b',symptoms))
    from .workout_edits import requested as blocks_requested, edit, EditError
    if blocks_requested(text):
        if weekly or len(rows)!=1:return answer('needs_input','Choose one dated session for a block edit.')
        if illness or fatigue or context['blockers'] or policy['level']=='hold' or context['answers'].get('pain_or_illness'):
            return answer('not_recommended','Recovery or saved restrictions need review. Request an easier session or rest before editing its blocks.')
        w=rows[0];definition=w['definition']
        with connect(path) as c:
            managed=c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND verified_hash IS NOT NULL',(w['id'],)).fetchone()
            if w['publish_status'] not in ('local','published','update_needed') or w['publish_status']!='local' and not managed or definition.get('fixed_commitment') or definition.get('event_id') or definition.get('review_hold'):
                return answer('not_recommended','This session has a commitment, review hold or unfinished/unverified Garmin send. Resolve it before editing blocks.')
            from .cycling_variants import tolerated_sessions
            tolerated=tolerated_sessions(c,definition.get('workout_kind'),today,tz)
        phase=definition.get('training_block',{}).get('phase')
        day=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()
        week=max(0,(day-datetime.fromisoformat(program['state']['starts_on']).date()).days//7)
        blocks=program['state']['blocks']
        if week<len(blocks):phase=blocks[week]['phase']
        allow_increase=len(tolerated)>=2 and phase not in ('Recovery / review','Race week','Freshen up','Post-event recovery')
        try:replacement,summary=edit(definition,text,policy,allow_increase)
        except EditError as error:return answer(error.status,str(error))
        changes=[{'workout_id':w['id'],'expected_revision':w['revision'],'title':w['title'],'date':w.get('scheduled_date',w['scheduled_for'][:10]),'summary':summary,'changes':{'definition':replacement}}]
        proposal={**base,'status':'proposal','root_plan_id':program['plan_id'],'program_revision':program['revision'],'adjustments':changes,'message':'Review these block edits. Saving preserves the session date and duration. '+('Then review Send to Garmin to update its instructions.' if w['publish_status']!='local' else ''),'policy':policy}
        proposal['fingerprint']=hashlib.sha256(encoded({k:proposal[k] for k in ('root_plan_id','program_revision','adjustments')}).encode()).hexdigest()
        return proposal
    easier=bool(re.search(r'\b(easier|easy|lighter|reduce|cut|decrease|back off|dial down|dial it back|recovery|halve|less intensity|too hard)\b',text))
    harder=not easier and bool(re.search(r'\b(harder|tougher|hard|intensity|sprints?|anaerobic|tempo|intervals|ramp|push|challenge|turn it up)\b',text))
    skip=bool(re.search(r'\b(skip|cancel|rest|day off)\b',text))
    minutes_match=re.search(r'\b(\d+)\s*(?:minutes?|mins?|m)\b',text)
    minutes=int(minutes_match[1]) if minutes_match else 60 if re.search(r'\b(an? hour|one hour)\b',text) else None
    percent=re.search(r'\b(\d+)\s*%',text)
    if re.search(r"\b(don't|do not|no) (make .{0,20})?(harder|easier|change)\b",text):return answer('needs_input','I’ll leave it unchanged. What, if anything, would you like adjusted?')
    if re.search(r'\b(double|longer|more time|add time|ramp up)\b|\bincrease\b(?!\s+(the\s+)?intensity)',text) or percent and not easier:
        return answer('not_recommended','I would not add volume automatically. Your cycling allowance uses four completed weeks, with up to 20% only when tolerance and recovery support it; strength stays separate. Review a replacement week to redistribute that allowance without exceeding availability.')
    if harder and (illness or fatigue or context['blockers'] or not policy['quality_allowed']):
        reason='You reported pain or illness; rest and review that before hard training.' if illness else 'You reported poor recovery or fatigue; feeling motivated does not remove the need for recovery.' if fatigue else ' '.join(context['blockers']+policy['reasons']) or 'There is not enough current recovery and consistent training evidence to justify an intensity increase.'
        return answer('not_recommended',reason+' I recommend keeping it easy or asking to reduce this session.')
    if harder and weekly:return answer('not_recommended','I would not make every session harder. Keep most riding easy, preserve the long ride and recovery days, and choose one dated session for an intensity change.')
    if harder and re.search(r'\b(sprints?|anaerobic)\b',text):
        from .training_prescriptions import advanced_cycling_eligible
        brief=program['state']['brief'];week=max(0,(today-datetime.fromisoformat(program['state']['starts_on']).date()).days//7)
        blocks=program['state']['blocks'];phase=blocks[week]['phase'] if week<len(blocks) else ''
        with connect(path) as c:eligible=advanced_cycling_eligible(c,now,context['answers'].get('experience',{}).get('cycling'),week,phase,policy['quality_allowed'])
        if not eligible:return answer('not_recommended','Dedicated sprint or anaerobic work needs an eligible build phase, cycling experience and two tolerated completed quality sessions. Keep the current progression until that evidence is available.')
    if context['blockers'] and not (skip or illness or context['answers'].get('pain_or_illness')):
        return answer('not_recommended','The saved restrictions need review before prescribing a changed workout. '+' '.join(context['blockers'])+' You can request a rest day meanwhile.')
    if not (harder or easier or skip or minutes is not None or illness or fatigue):return answer('needs_input','Would you like a harder session, less intensity, a shorter duration, or a rest day? Tell me the session or week you mean.')
    if weekly and minutes is not None:return answer('needs_input','Is that the total time for cycling over the next seven days? Confirm the sport and weekly limit so I can redistribute it; strength time stays separate.')
    changes=[]
    for w in rows:
        definition=w['definition'];duration=definition['duration_minutes']
        managed=False
        if w['publish_status'] in ('published','update_needed'):
            with connect(path) as c:managed=bool(c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND verified_hash IS NOT NULL',(w['id'],)).fetchone())
        if (w['publish_status']!='local' and not managed) or definition.get('event_id') or definition.get('template_id')=='fixed_commitment':return answer('not_recommended','This includes a fixed event or a workout without a verified Garmin mapping. Review that commitment explicitly before changing it.')
        delta={}
        if skip or illness or policy['level']=='hold' or context['answers'].get('pain_or_illness'):delta={'completion_status':'skipped'}
        else:
            if w['sport'] not in ('cycling','running'):return answer('needs_input','For strength, choose the exercise and the change in load, sets or repetitions. I won’t infer new lifting loads from a general request.')
            if minutes is not None and not weekly:
                if not 10<=minutes<=duration:return answer('needs_input','Choose 10–'+str(duration)+' minutes for this session. A longer session needs a weekly volume and availability review.')
                duration=minutes
            elif easier or fatigue:duration=max(10,round(duration*(1-int(percent[1])/100 if percent else .75)))
            if percent and (not easier or not 1<=int(percent[1])<=90):return answer('needs_input','What reduction should I use? Choose between 1% and 90%.')
            kind=('recovery' if duration<=30 else 'endurance') if easier or fatigue else definition.get('workout_kind','endurance')
            if duration<45 and kind in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic'):kind='endurance'
            if harder:
                week=max(0,(datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()-datetime.fromisoformat(program['state']['starts_on']).date()).days//7)
                blocks=program['state']['blocks'];phase=blocks[week]['phase'] if week<len(blocks) else ''
                if phase in ('Recovery / review','Race week','Freshen up','Post-event recovery'):return answer('not_recommended','This is a recovery or event-protection week. Keep the reduced intensity and review after recovery.')
                if w['sport']!='cycling':return answer('needs_input','Which running intensity change do you want? Keep the saved session until its progression is reviewed.')
                if duration<45:return answer('not_recommended','This session is too short for an added quality workout with full warm-up and recovery. Keep it easy.')
                if definition.get('workout_kind') not in ('endurance','recovery'):return answer('not_recommended','This is already a quality or long session. Preserve its purpose rather than stacking more intensity.')
                day=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()
                quality={'tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo'}
                if any(peer['id']!=w['id'] and peer['completion_status'] in ('planned','completed') and peer['definition'].get('workout_kind') in quality and abs((datetime.fromisoformat(peer['scheduled_for']).astimezone(ZoneInfo(tz)).date()-day).days)<7 for peer in all_sessions):return answer('not_recommended','There is already a quality session nearby. Keep this ride easy to preserve recovery and the weekly training mix.')
                kind='anaerobic' if 'anaerobic' in text else 'sprint' if 'sprint' in text else 'tempo'
            replacement=endurance(kind,duration,program['state']['brief'],w['sport'],today=today)
            replacement.update({k:v for k,v in definition.items() if k.startswith('schedule_') or k in ('scheduled_date','time_unspecified')})
            replacement['user_adjusted']=True
            delta={'definition':replacement}
        changes.append({'workout_id':w['id'],'expected_revision':w['revision'],'title':w['title'],'date':w.get('scheduled_date',w['scheduled_for'][:10]),'changes':delta})
    remote_note=' Some sessions were already sent to Garmin. Saving changes this local plan; review Send to Garmin afterward to update their remote instructions or remove skipped calendar entries.' if any(w['publish_status']!='local' for w in rows) else ''
    proposal={**base,'status':'proposal','root_plan_id':program['plan_id'],'program_revision':program['revision'],'adjustments':changes,'message':('Rest is appropriate given the reported pain or illness. ' if illness else 'Sure. ')+f"Review the {len(changes)} session change(s) below. Nothing is saved yet."+remote_note,'policy':policy}
    proposal['fingerprint']=hashlib.sha256(encoded({k:proposal[k] for k in ('root_plan_id','program_revision','adjustments')}).encode()).hexdigest()
    return proposal


def save(arguments,path=None,now=None):
    """Never trust client definitions. Recompute using current recovery and compare."""
    from .workout_format import requested, save as save_format
    if requested(arguments['message']):return save_format(arguments,path,now)
    proposed=propose(arguments['message'],path,now)
    if proposed.get('status')!='proposal' or proposed.get('fingerprint')!=arguments.get('fingerprint'):raise ValueError('Training or recovery changed. Ask again and review a fresh proposal.')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not program or program['plan_id']!=proposed['root_plan_id'] or program['revision']!=proposed['program_revision'] or program['status']!='active':raise ValueError('The active plan changed. Review a fresh proposal.')
        for item in proposed['adjustments']:
            row=_snapshot(c,item['workout_id'])
            if not row or row['revision']!=item['expected_revision'] or row['completion_status']!='planned' or row['publish_status'] not in ('local','published','update_needed'):raise ValueError('A session changed. Review a fresh proposal.')
            delta=item['changes']
            if 'definition' in delta:
                c.execute('UPDATE planned_workouts SET definition_json=?,title=?,revision=revision+1 WHERE id=?',(encoded(delta['definition']),delta['definition']['title'],row['id']))
            else:c.execute("UPDATE planned_workouts SET completion_status='skipped',revision=revision+1 WHERE id=?",(row['id'],))
            if row['publish_status']!='local':c.execute("UPDATE planned_workouts SET publish_status='update_needed' WHERE id=?",(row['id'],))
            _revision(c,_snapshot(c,row['id']))
        c.execute('UPDATE active_training_program SET revision=revision+1 WHERE id=1')
        from .training_lifecycle import invalidate
        invalidate(c,program['plan_id'])
    return {'status':'saved','count':len(proposed['adjustments'])}
