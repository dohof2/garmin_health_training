"""Reviewed coaching: user commitments, goal-specific drafts and a bounded roadmap."""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .training import _context, _number, _revision, _snapshot, encoded, list_training, workout_definition
from .time_utils import timezone_info

GOALS = {'ftp':'Increase FTP', 'endurance':'Build endurance', 'race':'Prepare for a race', 'general':'Stay in shape'}
VERSION = 'training-coach-v1'
DEFAULT = {'goal':None,'goal_sport':'cycling','horizon_weeks':12,'target_date':None,'event_name':'','ftp_watts':None,'fixed_events':[]}


def validate_brief(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULT): raise ValueError('Unsupported coaching brief fields')
    b={**DEFAULT,**value}
    if b['goal'] is not None and (not isinstance(b['goal'],str) or b['goal'] not in GOALS): raise ValueError('Choose FTP, endurance, race or general fitness')
    if b['goal_sport'] not in ('cycling','running'): raise ValueError('Choose cycling or running for the endurance or race goal')
    _number(b['horizon_weeks'],'planning horizon',4,24,True)
    if b['target_date'] is not None and not isinstance(b['target_date'],str): raise ValueError('Race date must use YYYY-MM-DD')
    if b['target_date']: date.fromisoformat(b['target_date'])
    if not isinstance(b['event_name'],str) or len(b['event_name'])>160: raise ValueError('Event name must be text up to 160 characters')
    if b['ftp_watts'] is not None: _number(b['ftp_watts'],'confirmed FTP watts',40,700)
    if not isinstance(b['fixed_events'],list) or len(b['fixed_events'])>20: raise ValueError('Use at most twenty fixed commitments')
    events=[];seen=set()
    for event in b['fixed_events']:
        if not isinstance(event,dict) or set(event)-{'date','title','sport','start_time','duration_minutes','effort'}: raise ValueError('Unsupported fixed commitment fields')
        e={'title':'Fixed commitment','sport':'cycling','start_time':None,'duration_minutes':None,'effort':'unknown',**event}
        if not isinstance(e.get('date'),str): raise ValueError('Commitment date must use YYYY-MM-DD')
        day=date.fromisoformat(e['date']).isoformat()
        if day in seen: raise ValueError('Use one fixed commitment per date')
        seen.add(day)
        if e['sport'] not in ('cycling','running','strength'): raise ValueError('Choose a supported commitment sport')
        if not isinstance(e['title'],str) or not e['title'].strip() or len(e['title'])>160: raise ValueError('Commitment title is required (up to 160 characters)')
        if e['effort'] not in ('easy','moderate','hard','unknown'): raise ValueError('Invalid commitment effort')
        if e['duration_minutes'] is not None: _number(e['duration_minutes'],'commitment minutes',15,720,True)
        if e['start_time']:
            try:
                clock=datetime.strptime(e['start_time'],'%H:%M')
                if clock.strftime('%H:%M')!=e['start_time']: raise ValueError()
            except (ValueError,TypeError): raise ValueError('Commitment time must use HH:MM')
            if e['duration_minutes'] and clock.hour*60+clock.minute+e['duration_minutes']>1440: raise ValueError('Commitment must finish on the same day')
        events.append({**e,'date':day})
    return {**b,'fixed_events':sorted(events,key=lambda e:e['date'])}


def read_brief(path=None):
    with connect(path) as c:
        row=c.execute('SELECT * FROM training_coach_brief WHERE id=1').fetchone()
    return {'revision':row['revision'],'brief':json.loads(row['brief_json'])} if row else {'revision':0,'brief':dict(DEFAULT)}


def save_brief(brief,expected_revision,path=None):
    b=validate_brief(brief)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT revision FROM training_coach_brief WHERE id=1').fetchone()
        if type(expected_revision) is not int or expected_revision!=(row[0] if row else 0): raise ValueError('Coaching brief changed; reload before saving')
        revision=expected_revision+1
        c.execute('INSERT INTO training_coach_brief(id,revision,brief_json) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,brief_json=excluded.brief_json,updated_at=CURRENT_TIMESTAMP',(revision,encoded(b)))
        c.execute('INSERT INTO training_coach_brief_revisions(revision,brief_json) VALUES(?,?)',(revision,encoded(b)))
    return {'revision':revision,'brief':b}


def parse_request(message,brief,week_start):
    """Extract explicit user facts only; ask for missing trip details instead of inventing them."""
    if not isinstance(message,str) or not 1<=len(message.strip())<=4000: raise ValueError('Describe your goal or commitment (up to 4,000 characters)')
    b=validate_brief(brief);text=message.lower();recognized=[]
    for typo,day in [('wedensday','wednesday'),('wensday','wednesday'),('firday','friday'),('tusday','tuesday')]:
        text=re.sub(r'\b'+typo+r'\b',day,text)
    text=re.sub(r'\b(one|two|three|four|five|six)\s+(hours?|hrs?|minutes?|mins?)\b',lambda m:str({'one':1,'two':2,'three':3,'four':4,'five':5,'six':6}[m[1]])+' '+m[2],text)
    if re.search(r'\b(running|run|marathon)\b',text): b['goal_sport']='running'
    elif re.search(r'\b(cycling|bike|ride)\b',text): b['goal_sport']='cycling'
    goals=[key for key,pattern in [('ftp',r'\bftp\b'),('race',r'\brace|marathon|competition\b'),('endurance',r'\bendurance\b'),('general',r'\b(?:keep|stay)\s+in\s+shape\b|\bfitness\b')] if re.search(pattern,text)]
    if len(goals)==1: b['goal']=goals[0];recognized.append(GOALS[goals[0]])
    elif len(goals)>1: recognized.append('Multiple goals mentioned: choose the primary goal below.')
    horizon=re.search(r'\b(\d{1,2})[ -]*weeks?\b',text)
    if horizon: b['horizon_weeks']=int(horizon[1])
    ftp=re.search(r'\bftp\s*(?:is|of|=|at)?\s*(\d{2,3})\s*(?:w|watts)\b',text)
    if ftp: b['ftp_watts']=int(ftp[1])
    days=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    clauses=re.split(r'(?<!\d)\.(?!\d)|[;\n]|\band\s+(?=(?:an?\s+)?(?:hard|easy|moderate|long)\b)|(?=\blong\s+(?:ride|trip|run)\b)',text)
    extracted=False
    for clause in clauses:
        mentioned=[i for i,name in enumerate(days) if re.search(r'\b'+name+r'\b',clause)]
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',clause)
        if not re.search(r'\b(trips?|rides?|race|runs?|workouts?|sessions?)\b',clause) or not (mentioned or dates): continue
        extracted=True
        when_list=dates or [(week_start+timedelta(days=day)).isoformat() for day in mentioned]
        duration=re.search(r'\b(\d+(?:\.\d+)?)[\s-]*(hours?|hrs?|minutes?|mins?)\b',clause)
        minutes=round(float(duration[1])*(60 if duration[2].startswith(('h','hr')) else 1)) if duration else None
        clock=re.search(r'\b(?:at|starting)\s+(\d{1,2}:\d{2})\b',clause)
        effort=next((e for e in ('hard','moderate','easy') if re.search(r'\b'+e+r'\b',clause)),'unknown')
        for when in when_list:
            event={'date':when,'title':'Race' if re.search(r'\brace\b',clause) else 'Fixed trip' if 'trip' in clause else 'Fixed session',
                   'sport':'running' if re.search(r'\brun(?:ning)?\b',clause) else 'strength' if 'strength' in clause else 'cycling',
                   'start_time':clock[1].zfill(5) if clock else None,'duration_minutes':minutes,'effort':effort}
            previous=next((e for e in b['fixed_events'] if e['date']==when),{})
            for key in ('start_time','duration_minutes'):
                if event[key] is None: event[key]=previous.get(key)
            if effort=='unknown': event['effort']=previous.get('effort','unknown')
            b['fixed_events']=[e for e in b['fixed_events'] if e['date']!=when]+[event]
            if event['title']=='Race': b['target_date']=when
            recognized.append('Fixed commitment on '+when)
    # A plain follow-up can complete the most recent incomplete commitment.
    if not extracted and b['fixed_events']:
        e=b['fixed_events'][-1]
        duration=re.search(r'\b(\d+(?:\.\d+)?)[\s-]*(hours?|hrs?|minutes?|mins?)\b',text)
        clock=re.search(r'\b(?:at|starting)\s+(\d{1,2}:\d{2})\b',text)
        if duration: e['duration_minutes']=round(float(duration[1])*(60 if duration[2].startswith('h') else 1));recognized.append('Updated commitment duration')
        if clock: e['start_time']=clock[1].zfill(5);recognized.append('Updated commitment time')
        for effort in ('hard','moderate','easy'):
            if re.search(r'\b'+effort+r'\b',text): e['effort']=effort;recognized.append('Updated commitment effort')
    if re.search(r'\b(?:train|training)\s+today\b',text): recognized.append('Training today is separate from this weekly preview; confirm its session details before scheduling it.')
    return validate_brief(b),recognized


def roadmap(b,week_start,answers):
    rows=[];goal=b['goal'];n=b['horizon_weeks'];target=date.fromisoformat(b['target_date']) if b['target_date'] else None
    for i in range(n):
        start=week_start+timedelta(weeks=i)
        recovery=(i+1)%4==0
        phase='Establish consistency' if i<2 else 'Consolidate' if i>=n-2 else 'Build specificity'
        focus={'ftp':'One controlled cycling interval session when experience, workload and recovery permit; easy rides around it.',
               'endurance':f"Prioritize a longer conversational {b['goal_sport']} session within confirmed time and volume limits.",
               'race':f"Build {b['goal_sport']} endurance for {b['event_name'] or 'the event'}; review specific demands before selecting workouts.",
               'general':'Maintain manageable, consistent sessions and a mix of the selected sports.'}.get(goal,'Choose a primary goal.')
        if recovery: phase='Recovery / review';focus='Reduce generated volume and review effort, soreness and completed sessions.'
        if target and start<=target<=start+timedelta(days=6): phase='Race week';focus='Keep surrounding sessions short and easy; protect the event day.'
        elif target and 0<(target-start).days<=14: phase='Freshen up';focus='Reduce generated volume approaching the event. Fixed commitments remain visible.'
        elif target and start>target: phase='Post-event recovery';focus='Easy activity or rest; review the event before another build.'
        rows.append({'week':i+1,'starts_on':start.isoformat(),'phase':phase,'focus':focus})
    return rows


def _scheduled(day,clock,tz):
    local=datetime.fromisoformat(f'{day}T{clock}').replace(tzinfo=ZoneInfo(tz))
    if local.astimezone(timezone.utc).astimezone(ZoneInfo(tz)).replace(tzinfo=None)!=local.replace(tzinfo=None) or local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset(): raise ValueError('Choose a time outside the timezone clock change')
    return local.isoformat()


def _preview(c,brief,week_start,tz,now,replace_plan_id):
    b=validate_brief(brief);timezone_info(tz);today=now.astimezone(ZoneInfo(tz)).date()
    if week_start.weekday()!=0 or week_start<today-timedelta(days=today.weekday()): raise ValueError('Choose a current or future Monday')
    context=_context(c,now);answers=context['answers'];questions=[];warnings=[]
    if b['goal'] is None: questions.append('What is the primary goal: FTP, endurance, race preparation or staying in shape?')
    if b['goal']=='ftp' and 'cycling' not in answers.get('sports',[]): questions.append('Select cycling in Training preferences for an FTP plan.')
    if b['goal'] in ('endurance','race') and b['goal_sport'] not in answers.get('sports',[]): questions.append('Select the goal sport in Training preferences.')
    if b['goal']=='race' and not b['event_name'].strip(): questions.append('What kind of race is it? Add its distance, terrain and demands.')
    if b['goal']=='race' and not b['target_date']: questions.append('What is the race date? Add the event name and its demands in the commitment title.')
    if b['target_date'] and date.fromisoformat(b['target_date'])<today: questions.append('The target event is in the past; choose an upcoming date.')
    questions.extend(q['question'] for q in context['questions']);questions.extend(context['blockers'])
    existing=[dict(r) for r in c.execute("SELECT * FROM planned_workouts WHERE completion_status NOT IN ('cancelled','skipped') AND scheduled_for IS NOT NULL ORDER BY id")]
    plan=c.execute('SELECT * FROM training_plans WHERE id=?',(replace_plan_id,)).fetchone() if replace_plan_id else None
    replaceable=[]
    if replace_plan_id:
        if not plan or plan['starts_on']!=week_start.isoformat() or plan['status'] not in ('draft','active'): raise ValueError('Choose a draft or active plan for this week to replace')
        replaceable=[w for w in existing if w['training_plan_id']==replace_plan_id]
        if any(w['completion_status']!='planned' or w['garmin_workout_id'] or w['publish_status']!='local' for w in replaceable): raise ValueError('Completed or published sessions cannot be replaced; choose a future week')
    active=[w for w in existing if w['training_plan_id']!=replace_plan_id]
    anchors=[e for e in b['fixed_events'] if week_start.isoformat()<=e['date']<=(week_start+timedelta(days=6)).isoformat()]
    # Adjacent commitments also protect recovery across week boundaries.
    protected={};occupied={e['date'] for e in anchors};sessions=[];allocated={s:0 for s in answers.get('sports',[])}
    hard=False
    for w in active:
        other=datetime.fromisoformat(w['scheduled_for'])
        if not other.tzinfo:
            questions.append('An existing workout has ambiguous timing; review it.');continue
        day=other.astimezone(ZoneInfo(tz)).date();definition=json.loads(w['definition_json']);minutes=definition.get('duration_minutes')
        if not isinstance(minutes,(int,float)) or isinstance(minutes,bool) or minutes<=0:
            questions.append('An existing workout has an unknown duration; review it.');continue
        if week_start<=day<=week_start+timedelta(days=6):
            if w['sport'] in allocated: allocated[w['sport']]+=minutes
            if definition.get('template_id')=='cycling_controlled_intervals' or definition.get('fixed_commitment') and 'hard' in definition.get('effort_target',{}).get('description',''): hard=True
        if minutes>=90 or definition.get('template_id')=='cycling_controlled_intervals':
            for offset in (-1,1): protected[(day+timedelta(days=offset)).isoformat()]='Recovery around an existing demanding session.'
    for e in b['fixed_events']:
        demanding=e['effort'] in ('hard','unknown') or (e['duration_minutes'] or 0)>=90
        if demanding:
            for offset in (-1,1):
                day=(date.fromisoformat(e['date'])+timedelta(days=offset)).isoformat()
                protected[day]=f"Recovery around {e['title']} on {e['date']}."
    if b['goal']=='race' and b['target_date']:
        occupied.add(b['target_date'])
        for offset in (-2,-1,1,2): protected[(date.fromisoformat(b['target_date'])+timedelta(days=offset)).isoformat()]='Protect freshness and recovery around the race.'
    for e in anchors:
        if not e['start_time'] or e['duration_minutes'] is None: questions.append(f"{e['title']} on {e['date']}: what start time and expected duration?");continue
        if datetime.fromisoformat(_scheduled(e['date'],e['start_time'],tz))<now: questions.append(f"{e['title']} is in the past; select a future commitment.")
        if e['effort']=='unknown': questions.append(f"{e['title']} on {e['date']}: is the expected effort easy, moderate or hard?")
        if e['sport'] not in allocated or e['sport'] in answers.get('blocked_sports',[]): questions.append('The fixed commitment sport must be selected and not excluded.');continue
        allocated[e['sport']]+=e['duration_minutes'];hard=hard or e['effort'] in ('hard','unknown')
        definition={'version':VERSION,'template_id':'fixed_commitment','sport':e['sport'],'title':e['title'],'duration_minutes':e['duration_minutes'],
                    'fixed_commitment':True,'effort_target':{'method':'user_reported','description':e['effort']+' effort, as specified by you.'},'rationale':['Preserved fixed commitment; time and duration come from your brief.'],'steps':[{'type':'fixed','duration_seconds':e['duration_minutes']*60,'effort':e['effort']}]}
        sessions.append({'sport':e['sport'],'title':e['title'],'scheduled_for':_scheduled(e['date'],e['start_time'],tz),'definition':definition})
    for sport,total in allocated.items():
        if total>answers.get('weekly_minutes',{}).get(sport,0): questions.append(f"Fixed and existing {sport} sessions total {total} minutes, above the confirmed weekly limit. Review the manageable volume in Training preferences; the trip is not shortened.")
    phases=roadmap(b,week_start,answers)
    # First weekly draft is a starting week; each later draft is reassessed, never automatically intensified.
    if context['ready'] and not questions:
        slots=answers['availability']
        for slot in sorted(slots,key=(lambda s:(-s['minutes'],s['weekday'])) if b['goal'] in ('endurance','race') else (lambda s:s['weekday'])):
            day=week_start+timedelta(days=slot['weekday']);key=day.isoformat()
            if day<today or key in occupied or key in protected or len(sessions)+sum(week_start<=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()<=week_start+timedelta(days=6) for w in active)>=6: continue
            if datetime.fromisoformat(_scheduled(key,slot['start_time'],tz))<now: continue
            if any(datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()==day for w in active): warnings.append(f'{key}: existing workout retained; no additional session added.');continue
            candidates=sorted(answers['sports'],key=lambda s:(allocated[s]/max(1,answers['weekly_minutes'][s]),0 if s==('cycling' if b['goal']=='ftp' else b['goal_sport']) and b['goal'] in ('ftp','endurance','race') else 1))
            for sport in candidates:
                if sport=='strength' and any(abs((datetime.fromisoformat(s['scheduled_for']).astimezone(ZoneInfo(tz)).date()-day).days)<2 for s in sessions+active if s['sport']=='strength'): continue
                minutes=min(slot['minutes'],answers['weekly_minutes'][sport]-allocated[sport],30 if answers['experience'][sport]=='new' else (120 if sport=='cycling' else 90) if sport==b['goal_sport'] and b['goal'] in ('endurance','race') else 60)
                if b['goal']=='race' and b['target_date'] and (date.fromisoformat(b['target_date'])-day).days<=14: minutes=min(minutes,30)
                template={'cycling':'cycling_easy','running':'running_easy','strength':'strength_foundation'}[sport]
                if minutes<(15 if sport=='running' else 20): continue
                definition=workout_definition(template,min(minutes,180),answers)
                if b['goal']=='ftp' and sport=='cycling' and answers['experience'][sport]!='new' and not hard and minutes>=45 and answers['weekly_minutes'][sport]>=120:
                    definition.update(template_id='cycling_controlled_intervals',title='Controlled cycling intervals',duration_minutes=minutes,
                        effort_target={'method':'confirmed_ftp' if b['ftp_watts'] else 'perceived_effort','description':f"Work intervals at 90–95% of your confirmed {b['ftp_watts']:g} W FTP; ease off if this feels harder than controlled." if b['ftp_watts'] else 'Controlled work intervals, perceived effort about 6–7/10. No FTP is inferred.'})
                    definition['steps']=[{'type':'warmup','duration_seconds':600,'effort':'easy'}, {'type':'work','duration_seconds':360,'effort':definition['effort_target']['description']}, {'type':'recovery','duration_seconds':240,'effort':'easy'}, {'type':'work','duration_seconds':360,'effort':definition['effort_target']['description']}, {'type':'easy','duration_seconds':(minutes-26)*60,'effort':'conversational'}]
                    definition['rationale'].append('One controlled interval session for the FTP goal; two 6-minute efforts are a provisional starting template.');hard=True
                    protected[(day+timedelta(days=1)).isoformat()]='Recovery after the controlled interval session.'
                definition['rationale'].append('Goal: '+GOALS[b['goal']]+'. Fixed commitments count toward the confirmed weekly budget.')
                sessions.append({'sport':sport,'title':definition['title'],'scheduled_for':_scheduled(key,slot['start_time'],tz),'definition':definition});allocated[sport]+=minutes;occupied.add(key);break
    for s in sessions:
        begin=datetime.fromisoformat(s['scheduled_for']);end=begin+timedelta(minutes=s['definition']['duration_minutes'])
        for w in active:
            other=datetime.fromisoformat(w['scheduled_for'])
            if not other.tzinfo: questions.append('An existing workout has ambiguous timing; review it.');continue
            duration=json.loads(w['definition_json']).get('duration_minutes')
            if not isinstance(duration,(int,float)) or isinstance(duration,bool) or duration<=0: questions.append('An existing workout has an unknown duration; review it.');continue
            if begin<other+timedelta(minutes=duration) and other<end: questions.append('A fixed or generated session overlaps an existing workout. Select the existing week to replace or revise the commitment.')
    recorded=[dict(r) for r in c.execute("SELECT activity_type,COUNT(*) AS activities,SUM(duration_seconds)/60 AS minutes FROM activities WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture' AND substr(started_at,1,10)>=? AND substr(started_at,1,10)<? GROUP BY activity_type",((today-timedelta(days=28)).isoformat(),today.isoformat()))]
    state={'brief':b,'today':today.isoformat(),'sessions':sessions,'preferences':context,'existing':existing,'replace_plan_id':replace_plan_id,'week_start':week_start.isoformat(),'timezone':tz}
    fingerprint=hashlib.sha256(encoded(state).encode()).hexdigest()
    questions=list(dict.fromkeys(questions))
    return {'status':'needs_input' if questions else 'ready' if sessions else 'needs_review','brief':b,'week_start':week_start.isoformat(),'timezone':tz,
            'questions':questions or ([] if sessions else ['No session fits the constraints. Review availability and fixed commitments.']),
            'warnings':warnings,'roadmap':phases,'sessions':sorted(sessions,key=lambda s:s['scheduled_for']),
            'protected_days':[{'date':day,'reason':reason} for day,reason in sorted(protected.items()) if week_start.isoformat()<=day<=(week_start+timedelta(days=6)).isoformat()],
            'weekly_minutes':allocated,'recorded_history':{'start':(today-timedelta(days=28)).isoformat(),'end':today.isoformat(),'note':'Recorded history provides context; it does not automatically increase volume.','sports':[{'activity_type':r['activity_type'],'activity_count':r['activities'],'recorded_minutes':r['minutes'] or 0} for r in recorded]},'expected_preference_revision':context['revision'],
            'fingerprint':fingerprint,'replace_plan_id':replace_plan_id,'replaces_session_count':len(replaceable),
            'rationale':['Fixed commitments retain their requested date, time and duration.','Generated volume stays within confirmed manageable weekly limits.','Demanding or long commitments protect the surrounding days.','At most one added controlled interval session; a hard fixed commitment uses that slot.','Review the multi-week direction each week using completion, effort and soreness; future readiness is not forecast.'],
            'advisory':'This is a reviewed starting plan. Phase lengths, recovery buffers and interval doses are provisional planning defaults; no FTP improvement or race result is promised.'}


def preview(brief,week_start,tz,path=None,now=None,replace_plan_id=None):
    with connect(path) as c: return _preview(c,brief,week_start,tz,now or datetime.now(timezone.utc),replace_plan_id)


def create_draft(brief,week_start,tz,fingerprint,path=None,now=None,replace_plan_id=None):
    now=now or datetime.now(timezone.utc)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');p=_preview(c,brief,week_start,tz,now,replace_plan_id)
        if not isinstance(fingerprint,str) or fingerprint!=p['fingerprint']: raise ValueError('Planning context changed; preview the week again before saving')
        if p['status']!='ready': raise ValueError('Answer the coaching questions before creating a draft')
        if replace_plan_id:
            for row in c.execute("SELECT id FROM planned_workouts WHERE training_plan_id=? AND completion_status='planned'",(replace_plan_id,)).fetchall():
                c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(row['id'],));_revision(c,_snapshot(c,row['id']))
            c.execute("UPDATE training_plans SET status='superseded',updated_at=CURRENT_TIMESTAMP WHERE id=?",(replace_plan_id,))
        identifier='plan-'+str(uuid.uuid4())
        stored={**p,'preferences':_context(c,now),'rule_version':VERSION,'coaching':True}
        c.execute("INSERT INTO training_plans(id,name,status,starts_on,ends_on,context_json) VALUES(?,?,'draft',?,?,?)",(identifier,GOALS[p['brief']['goal']]+' · '+week_start.isoformat(),week_start.isoformat(),(week_start+timedelta(days=6)).isoformat(),encoded(stored)))
        for s in p['sessions']:
            wid='workout-'+str(uuid.uuid4());c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',(wid,identifier,s['sport'],s['title'],s['scheduled_for'],encoded(s['definition'])));_revision(c,_snapshot(c,wid))
    return list_training(path)


def assistant_preview(arguments,path=None):
    now=datetime.now(timezone.utc);tz=arguments.get('timezone') or 'UTC';today=now.astimezone(timezone_info(tz)).date()
    week=date.fromisoformat(arguments['week_start']) if arguments.get('week_start') else today+timedelta(days=(7-today.weekday())%7)
    message=arguments.get('message') or ''
    if not arguments.get('week_start'):
        weekday=next((i for i,name in enumerate(('monday','tuesday','wednesday','thursday','friday','saturday','sunday')) if re.search(r'\b'+name+r'\b',message,re.I)),None)
        if weekday is not None and weekday>=today.weekday(): week=today-timedelta(days=today.weekday())
    brief=arguments.get('brief') or read_brief(path)['brief']
    brief,recognized=parse_request(message,brief,week)
    return {'tool':'preview_training_plan',**preview(brief,week,tz,path,now,arguments.get('replace_plan_id')),'recognized':recognized}


def assistant_answer(result):
    b=result['brief'];lines=[f"Coaching preview: {GOALS.get(b['goal'],'choose your primary goal')} · {b['horizon_weeks']} weeks. Nothing has been saved."]
    lines.extend(result['recognized'])
    if result['questions']:
        lines.append(result['questions'][0])
        if len(result['questions'])>1: lines.append('The remaining details are listed in the review panel.')
    else:
        lines.append('Weekly volume: '+', '.join(f'{sport}: {minutes} min' for sport,minutes in result['weekly_minutes'].items())+'.')
        if result['protected_days']: lines.append('Recovery is protected around your fixed commitments.')
    lines.extend(result['warnings'])
    lines.append('Open the proposal in Training to review the full week and longer-term direction before saving.')
    return '\n\n'.join(lines)
