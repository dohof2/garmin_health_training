"""Reviewed coaching: user commitments, goal-specific drafts and a bounded roadmap."""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .training import _context, _number, _revision, _snapshot, encoded, list_training, workout_definition, validate_answers
from .time_utils import timezone_info

GOALS = {'ftp':'Increase FTP', 'endurance':'Build endurance', 'race':'Prepare for a race', 'general':'Stay in shape'}
VERSION = 'training-coach-v1'
DEFAULT = {'goal':None,'goal_sport':'cycling','horizon_weeks':12,'target_date':None,'event_name':'','ftp_watts':None,'fixed_events':[],'calibration':{},'strength_role':None,'strength_purpose':None,'strength_capacity':{},'program_start':None,'workout_location':'outdoor','duration_confirmed':False,'ftp_selection':'manual','ftp_authorization':None,'sport_days':{},'weekly_time_ranges':{}}


def validate_brief(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULT): raise ValueError('Unsupported coaching brief fields')
    b={**DEFAULT,**value}
    if b['goal'] is not None and (not isinstance(b['goal'],str) or b['goal'] not in GOALS): raise ValueError('Choose FTP, endurance, race or general fitness')
    if b['goal_sport'] not in ('cycling','running'): raise ValueError('Choose cycling or running for the endurance or race goal')
    if not isinstance(b['weekly_time_ranges'],dict) or set(b['weekly_time_ranges'])-{'cycling','running','strength'}:raise ValueError('Invalid weekly time ranges')
    for bounds in b['weekly_time_ranges'].values():
        if not isinstance(bounds,list) or len(bounds)!=2:raise ValueError('Weekly ranges require lower and upper minutes')
        for minutes in bounds:_number(minutes,'weekly range minutes',0,1260,True)
        if bounds[0]>bounds[1]:raise ValueError('Weekly range minimum exceeds maximum')
    if type(b['duration_confirmed']) is not bool:raise ValueError('Duration confirmation must be yes or no')
    _number(b['horizon_weeks'],'planning horizon',4,24,True)
    if b['target_date'] is not None and not isinstance(b['target_date'],str): raise ValueError('Race date must use YYYY-MM-DD')
    if b['target_date']: date.fromisoformat(b['target_date'])
    if not isinstance(b['event_name'],str) or len(b['event_name'])>160: raise ValueError('Event name must be text up to 160 characters')
    if not isinstance(b['sport_days'],dict) or set(b['sport_days'])-{'cycling','running','strength','hiking','other'}:raise ValueError('Invalid sport days')
    for days in b['sport_days'].values():
        if not isinstance(days,list) or any(type(day) is not int or not 0<=day<=6 for day in days) or len(set(days))!=len(days):raise ValueError('Use unique weekdays 0–6')
    authorization=b['ftp_authorization']
    if authorization is not None:
        if not isinstance(authorization,dict) or set(authorization)!={'authorized_on','watts','measurement_date','source'}:raise ValueError('Invalid FTP authorization metadata')
        date.fromisoformat(authorization['authorized_on']);_number(authorization['watts'],'authorized FTP',40,700)
        if authorization['measurement_date']:date.fromisoformat(authorization['measurement_date'])
        if not isinstance(authorization['source'],str):raise ValueError('FTP authorization source is required')
    if b['ftp_selection'] not in ('manual','garmin'):raise ValueError('Choose manual or Garmin FTP')
    if b['ftp_watts'] is not None: _number(b['ftp_watts'],'confirmed FTP watts',40,700)
    if not isinstance(b['fixed_events'],list) or len(b['fixed_events'])>20: raise ValueError('Use at most twenty fixed commitments')
    from .training_prescriptions import validate_calibration
    b['calibration']=validate_calibration(b['calibration'])
    if b['workout_location'] not in ('indoor','outdoor'):raise ValueError('Choose indoor or outdoor cycling')
    if b['strength_role'] not in (None,'primary','secondary'):raise ValueError('Strength role must be primary or secondary')
    if b['strength_purpose'] not in (None,'general_fitness','cycling_support','strength_development'):raise ValueError('Choose a strength purpose')
    if not isinstance(b['strength_capacity'],dict) or set(b['strength_capacity'])-{'pull_up_reps','dip_reps'}:raise ValueError('Invalid strength capability fields')
    for count in b['strength_capacity'].values():_number(count,'confirmed comfortable repetitions',0,50,True)
    if b['program_start']:date.fromisoformat(b['program_start'])
    events=[];seen=set()
    for event in b['fixed_events']:
        if not isinstance(event,dict) or set(event)-{'date','title','sport','start_time','duration_minutes','effort','distance_km','elevation_gain_meters','is_race','duration_estimated','id'}: raise ValueError('Unsupported fixed commitment fields')
        e={'duration_estimated':False,'distance_km':None,'elevation_gain_meters':None,'is_race':False,'title':'Fixed commitment','sport':'cycling','start_time':None,'duration_minutes':None,'effort':'unknown',**event}
        if not isinstance(e.get('date'),str): raise ValueError('Commitment date must use YYYY-MM-DD')
        day=date.fromisoformat(e['date']).isoformat()
        if 'id' not in e:e['id']='event-'+str(uuid.uuid5(uuid.NAMESPACE_URL,e['title']+'|'+day+'|'+str(e['start_time'])))
        if not isinstance(e['id'],str) or len(e['id'])>160 or e['id'] in seen:raise ValueError('Each event needs a unique stable ID')
        seen.add(e['id'])
        if e['sport'] not in ('cycling','running','strength','hiking','other'): raise ValueError('Choose a supported commitment sport')
        if not isinstance(e['title'],str) or not e['title'].strip() or len(e['title'])>160: raise ValueError('Commitment title is required (up to 160 characters)')
        if type(e['duration_estimated']) is not bool:raise ValueError('Duration estimate flag must be yes or no')
        if type(e['is_race']) is not bool:raise ValueError('Race flag must be yes or no')
        if e['distance_km'] is not None:_number(e['distance_km'],'commitment distance km',.1,1500)
        if e['elevation_gain_meters'] is not None:_number(e['elevation_gain_meters'],'commitment elevation gain',0,30000)
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
        active=c.execute("SELECT state_json FROM active_training_program WHERE id=1 AND status IN ('active','paused')").fetchone()
    from .training_ftp import resolve
    with connect(path) as c:ftp=resolve(c)
    return {'garmin_ftp':ftp,'revision':row['revision'] if row else 0,'brief':validate_brief(json.loads(row['brief_json'])) if row else validate_brief(json.loads(active['state_json'])['brief']) if active else dict(DEFAULT),'active_brief':validate_brief(json.loads(active['state_json'])['brief']) if active else None}


def save_brief(brief,expected_revision,path=None):
    b=validate_brief(brief)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT revision FROM training_coach_brief WHERE id=1').fetchone()
        if type(expected_revision) is not int or expected_revision!=(row[0] if row else 0): raise ValueError('Coaching brief changed; reload before saving')
        revision=expected_revision+1
        _store_brief(c,b,revision)
    return {'revision':revision,'brief':b}


def _store_brief(c,b,revision):
    c.execute('INSERT INTO training_coach_brief(id,revision,brief_json) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,brief_json=excluded.brief_json,updated_at=CURRENT_TIMESTAMP',(revision,encoded(b)))
    c.execute('INSERT INTO training_coach_brief_revisions(revision,brief_json) VALUES(?,?)',(revision,encoded(b)))


def parse_request(message,brief,week_start,today=None):
    """Extract explicit user facts only; ask for missing trip details instead of inventing them."""
    if not isinstance(message,str) or not 1<=len(message.strip())<=4000: raise ValueError('Describe your goal or commitment (up to 4,000 characters)')
    today=today or date.today()
    b=validate_brief(brief);text=message.lower();recognized=[]
    for typo,day in [('wedensday','wednesday'),('wensday','wednesday'),('firday','friday'),('tusday','tuesday')]:
        text=re.sub(r'\b'+typo+r'\b',day,text)
    text=re.sub(r'\b(one|two|three|four|five|six)\s+(hours?|hrs?|minutes?|mins?)\b',lambda m:str({'one':1,'two':2,'three':3,'four':4,'five':5,'six':6}[m[1]])+' '+m[2],text)
    if re.search(r'\bstrength\b.*\bprimary\b|\bprimary\b.*\bstrength\b',text):b['strength_role']='primary';b['strength_purpose']='strength_development'
    if re.search(r'\bstrength\b.*\bsecondary\b|\bsecondary\b.*\bstrength\b',text):b['strength_role']='secondary'
    if re.search(r'\b(cycling.support|strength.*(?:improve|support).*cycling)\b',text):b['strength_purpose']='cycling_support'
    if 'strength' in text and 'general fitness' in text:b['strength_purpose']='general_fitness'
    if re.search(r'\b(?:indoor|trainer) (?:workout|ride|session)s?\b',text):b['workout_location']='indoor'
    if re.search(r'\boutdoor (?:workout|ride|session)s?\b',text):b['workout_location']='outdoor'
    power=re.search(r'\bpower meter\b.*\b(indoors?|outdoors?|both|neither|none)\b',text)
    if power:b['calibration']['power_access']={'indoors':'indoor','outdoors':'outdoor','neither':'none'}.get(power[1],power[1])
    if re.search(r'\b(?:no|without|don.t have a) power meter\b',text):b['calibration']['power_access']='none'
    if re.search(r'\b(running|run|marathon)\b',text): b['goal_sport']='running'
    elif re.search(r'\b(cycling|bike|ride)\b',text): b['goal_sport']='cycling'
    goal_text=re.sub(r'\b(?:not (?:a )?|non[- ])race\b','',text)
    goals=[key for key,pattern in [('ftp',r'\bftp\b'),('race',r'\brace|marathon|competition\b'),('endurance',r'\bendurance\b'),('general',r'\b(?:keep|stay)\s+in\s+shape\b|\bfitness\b')] if re.search(pattern,goal_text)]
    if len(goals)==1: b['goal']=goals[0];recognized.append(GOALS[goals[0]])
    elif len(goals)>1: recognized.append('Multiple goals mentioned: choose the primary goal below.')
    horizon=re.search(r'\b(\d{1,2})[ -]*weeks?\b',text)
    if horizon: b['horizon_weeks']=int(horizon[1]);b['duration_confirmed']=True
    ftp=re.search(r'\bftp\s*(?:is|of|=|at)?\s*(\d{2,3})\s*(?:w|watts)\b',text)
    if ftp:
        previous_ftp=b['ftp_watts'];b['ftp_watts']=int(ftp[1])
        measured=re.search(r'\b(?:measured|tested|confirmed)(?:\s+on)?\s+(\d{4}-\d{2}-\d{2})\b',text)
        if measured:b['calibration']['ftp_confirmed_on']=date.fromisoformat(measured[1]).isoformat()
        elif re.search(r'\b(?:measured|tested|confirmed)(?:\s+it)?\s+today\b',text):b['calibration']['ftp_confirmed_on']=today.isoformat()
        elif previous_ftp!=b['ftp_watts']:b['calibration']['ftp_confirmed_on']=None
    days=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    clauses=re.split(r'(?<!\d)\.(?!\d)|[;\n]|\band\s+(?=(?:an?\s+)?(?:hard|easy|moderate|long)\b)|(?=\blong\s+(?:ride|trip|run)\b)',text)
    extracted=False
    for clause in clauses:
        mentioned=[i for i,name in enumerate(days) if re.search(r'\b'+name+r'\b',clause)]
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',clause)
        if not dates and not mentioned and re.search(r'\btomorrow\b',clause):dates=[(today+timedelta(days=1)).isoformat()]
        elif not dates and not mentioned and re.search(r'\btoday\b',clause):dates=[today.isoformat()]
        if not re.search(r'\b(trips?|rides?|race|runs?|workouts?|sessions?)\b',clause) or not (mentioned or dates): continue
        extracted=True
        when_list=dates or [(week_start+timedelta(days=(day-week_start.weekday())%7)).isoformat() for day in mentioned]
        duration=re.search(r'\b(\d+(?:\.\d+)?)[\s-]*(hours?|hrs?|minutes?|mins?)\b',clause)
        minutes=round(float(duration[1])*(60 if duration[2].startswith(('h','hr')) else 1)) if duration else None
        clock=re.search(r'\b(?:at|starting)\s+(\d{1,2}:\d{2})\b',clause)
        distance=re.search(r'\b(\d+(?:\.\d+)?)\s*(?:km|kilomet(?:er|re)s?)\b',clause)
        climb=re.search(r'\b(\d+(?:\.\d+)?)\s*m(?:eters?|etres?)?\s*(?:of\s+)?(?:climb|ascent|elevation|elevation gain)',clause) or re.search(r'(?:climb|ascent|elevation(?: gain)?)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*m\b',clause)
        race=bool(re.search(r'\brace\b',clause)) and not bool(re.search(r'\b(?:not a|non[- ]|not)\s*race\b',clause))
        effort=next((e for e in ('hard','moderate','easy') if re.search(r'\b'+e+r'\b',clause)),'unknown')
        event_name=re.search(r'\b(?:called|named)\s+[\"“]([^\"”]+)[\"”]',clause) or re.search(r'\b(?:called|named)\s+(.+?)(?=\s+on\b|[,;]|$)',clause)
        for when in when_list:
            event={'date':when,'title':'Race' if race else 'Fixed trip' if 'trip' in clause else 'Fixed session',
                   'sport':'running' if re.search(r'\brun(?:ning)?\b',clause) else 'strength' if 'strength' in clause else 'cycling',
                   'start_time':clock[1].zfill(5) if clock else None,'duration_minutes':minutes,'effort':effort,'distance_km':float(distance[1]) if distance else None,'elevation_gain_meters':float(climb[1]) if climb else None,'is_race':race}
            matches=[e for e in b['fixed_events'] if e['date']==when and (not event_name or e['title'].lower()==event_name[1].strip().lower())]
            if len(matches)>1:raise ValueError('More than one event is on that date; identify it by name or ID.')
            previous=matches[0] if matches else {}
            if previous.get('id'):event['id']=previous['id']

            if event_name:event['title']=event_name[1].strip().title()
            elif previous.get('title'):event['title']=previous['title']
            for key in ('start_time','duration_minutes','distance_km','elevation_gain_meters'):
                if event[key] is None: event[key]=previous.get(key)
            if effort=='unknown': event['effort']=previous.get('effort','unknown')
            b['fixed_events']=[e for e in b['fixed_events'] if not previous or e.get('id')!=previous.get('id')]+[event]
            if race: b['target_date']=when
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
        if goal in ('ftp','endurance','race') and phase=='Build specificity':focus+=' Dedicated sprint/anaerobic sessions may replace the weekly quality session after recorded tolerance and recovery checks.'
        if b.get('strength_role')=='primary':focus='Prioritize strength development: record actual load, clean repetitions and repetitions in reserve; progress only after tolerated completion. Cycling supports recovery and general aerobic fitness.'
        elif b.get('strength_purpose')=='cycling_support':focus+=' Secondary strength supports squat/hinge/core capacity around key rides.'
        if recovery: phase='Recovery / review';focus='Reduce generated volume and review effort, soreness and completed sessions.'
        if target and start<=target<=start+timedelta(days=6): phase='Race week';focus='Keep surrounding sessions short and easy; protect the event day.'
        elif target and 0<(target-start).days<=14: phase='Freshen up';focus='Reduce generated volume approaching the event. Fixed commitments remain visible.'
        elif target and start>target: phase='Post-event recovery';focus='Easy activity or rest; review the event before another build.'
        upcoming=[e for e in b['fixed_events'] if start<=date.fromisoformat(e['date'])<=start+timedelta(days=42)]
        if upcoming:
            event=min(upcoming,key=lambda e:e['date'])
            demands=f"{event['distance_km']:g} km" if event.get('distance_km') is not None else 'distance not yet specified'
            if event.get('elevation_gain_meters') is not None:demands+=f", {event['elevation_gain_meters']:g} m ascent"
            focus+=f" Prepare for {'race' if event.get('is_race') else 'fixed trip'} on {event['date']}: {demands}; emphasize sustained endurance and climbing as relevant."
        races=[e for e in b['fixed_events'] if e.get('is_race')]
        if any(start<=date.fromisoformat(e['date'])<=start+timedelta(days=6) for e in races):phase='Race week';focus+=' Prioritize freshness around the fixed race.'
        from .training_prescriptions import cycling_mix
        objectives={'cycling_mix':cycling_mix(b),'volume_ceiling_minutes':sum(answers.get('weekly_minutes',{}).values()),'long_session_available_minutes':max((a['minutes'] for a in answers.get('availability',[])),default=0),'quality_session_limit':0 if recovery or phase in ('Race week','Freshen up','Post-event recovery') else 1,'progression':'Reassess completed sport-specific work and tolerated feedback; build only within confirmed limits.'}
        rows.append({'week':i+1,'starts_on':start.isoformat(),'phase':phase,'focus':focus,'objectives':objectives})
    return rows


def summarize_blocks(phases):
    blocks=[]
    for phase in phases:
        if blocks and blocks[-1]['phase']==phase['phase']:
            blocks[-1]['end_week']=phase['week'];blocks[-1]['weeks']+=1
        else:blocks.append({'phase':phase['phase'],'start_week':phase['week'],'end_week':phase['week'],'weeks':1,'focus':phase['focus']})
    return blocks


def _scheduled(day,clock,tz):
    local=datetime.fromisoformat(f"{day}T{clock or '12:00'}").replace(tzinfo=ZoneInfo(tz))
    if local.astimezone(timezone.utc).astimezone(ZoneInfo(tz)).replace(tzinfo=None)!=local.replace(tzinfo=None) or local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset(): raise ValueError('Choose a time outside the timezone clock change')
    return local.isoformat()


def _cycling_allocations(caps,budget,long_slot_id=None):
    """Aim for hour-long regular rides; omit unsupported slots instead of adding leftover fillers."""
    caps={key:int(value) for key,value in caps.items() if value>=20}
    selected=list(caps);budget=max(0,int(budget))
    minimum={key:min(60,value) for key,value in caps.items()}
    while selected and sum(minimum[key] for key in selected)>budget:
        removable=[key for key in selected if key!=long_slot_id]
        selected.remove(removable[-1] if removable else selected[-1])
    result={key:minimum[key] for key in selected}
    remaining=budget-sum(result.values())
    if long_slot_id in result:
        extra=min(remaining,caps[long_slot_id]-result[long_slot_id]);result[long_slot_id]+=extra;remaining-=extra
    for key in selected:
        if key==long_slot_id:continue
        extra=min(remaining,caps[key]-result[key]);result[key]+=extra;remaining-=extra
    return result

def _preview(c,brief,week_start,tz,now,replace_plan_id,candidate_answers=None,session_changes=None,resolve_ftp=True):
    b=validate_brief(brief);timezone_info(tz);today=now.astimezone(ZoneInfo(tz)).date()
    anchor=date.fromisoformat(b['program_start']) if b['program_start'] else None
    if anchor:
        if week_start<anchor or week_start+timedelta(days=6)<today:raise ValueError('Choose a current or future seven-day window within the agreed program dates')
    elif week_start.weekday()!=0 or week_start<today-timedelta(days=today.weekday()):raise ValueError('Choose a current or future Monday, or agree an explicit program start date')
    from .training_ftp import resolve
    garmin_ftp=resolve(c,today)
    if b['ftp_selection']=='garmin' and resolve_ftp:
        b['ftp_watts']=garmin_ftp['watts']
        b['calibration']['ftp_confirmed_on']=garmin_ftp['measurement_date']
    from .training import validate_answers
    patch=validate_answers(candidate_answers or {})
    context=_context(c,now,patch,{**b,'_planning_day':week_start.isoformat()},tz)
    answers=context['answers'];questions=[];warnings=[]
    if answers.get('pain_or_illness'):questions.append('Resolve current pain or illness before approving training')
    if answers.get('restrictions_notes'):questions.append('Review training restrictions before approval')
    if b['goal'] is None: questions.append('What is the primary goal: FTP, endurance, race preparation or staying in shape?')
    if b['goal']=='ftp' and 'cycling' not in answers.get('sports',[]): questions.append('Select cycling in Training preferences for an FTP plan.')
    if b['goal'] in ('endurance','race') and b['goal_sport'] not in answers.get('sports',[]): questions.append('Select the goal sport in Training preferences.')
    if b['goal']=='race' and not b['event_name'].strip(): questions.append('What kind of race is it? Add its distance, terrain and demands.')
    if b['goal']=='race' and not b['target_date']: questions.append('What is the race date? Add the event name and its demands in the commitment title.')
    if b['target_date'] and date.fromisoformat(b['target_date'])<today and not b['program_start']: questions.append('The target event is in the past; choose an upcoming date.')
    from .training_prescriptions import questions as calibration_questions
    sensor_questions=calibration_questions(b,answers.get('sports',[]))
    if b['goal']=='ftp' and b['ftp_watts'] and b['calibration']['power_access']=='unknown':questions.append(sensor_questions[0])
    strength_questions=[]
    if 'strength' in answers.get('sports',[]):
        if b['strength_role'] is None:strength_questions.append('Is strength primary or secondary, and should it support cycling, general fitness, or strength development?')
        for equipment,key in [('pull_up_bar','pull_up_reps'),('dip_bars','dip_reps')]:
            if equipment in answers.get('equipment',[]) and key not in b['strength_capacity']:questions.append('How many comfortable '+('pull-ups' if key=='pull_up_reps' else 'dips')+' can you perform? Equipment alone does not establish capability.')
    questions.extend(q['question'] for q in context['questions']);questions.extend(context['blockers'])
    active_legacy=c.execute("SELECT state_json FROM active_training_program WHERE id=1 AND status IN ('active','paused')").fetchone()
    legacy_duration=bool(active_legacy and b.get('program_start') and json.loads(active_legacy['state_json']).get('starts_on')==b['program_start'])
    if not b['duration_confirmed'] and not legacy_duration:
        duration_question='How many weeks would you like to train for? Choose 4, 8, 12, 16, or a custom duration from 4–24 weeks.'
        return {'status':'needs_input','brief':b,'duration_confirmed':False,'questions':[duration_question]+questions,'calibration_questions':sensor_questions,'strength_questions':strength_questions,'warnings':warnings,'roadmap':[],'block_summary':[],'sessions':[],'protected_days':[],'weekly_minutes':{},'week_start':week_start.isoformat(),'timezone':tz,'garmin_ftp':garmin_ftp,'candidate_answers':patch,'session_changes':session_changes or [],'expected_preference_revision':context['revision'],'fingerprint':None,'replace_plan_id':replace_plan_id,'replaces_session_count':0,'rationale':[],'advisory':'Choose the duration in the trainer conversation before reviewing a long-term plan.'}
    existing=[dict(r) for r in c.execute("SELECT w.* FROM planned_workouts w JOIN training_plans p ON p.id=w.training_plan_id WHERE p.deleted_at IS NULL AND w.completion_status NOT IN ('cancelled','skipped') AND w.scheduled_for IS NOT NULL ORDER BY w.id")]
    plan=c.execute('SELECT * FROM training_plans WHERE id=? AND deleted_at IS NULL',(replace_plan_id,)).fetchone() if replace_plan_id else None
    replaceable=[];replace_ids=set()
    if replace_plan_id:
        if not plan or plan['status'] not in ('draft','active'):raise ValueError('Choose a draft or active plan to replace')
        replace_ids.add(replace_plan_id)
        for child in c.execute("SELECT id,context_json FROM training_plans WHERE status='active' AND deleted_at IS NULL"):
            if json.loads(child['context_json']).get('program_id')==replace_plan_id:replace_ids.add(child['id'])
        replaceable=[w for w in existing if w['training_plan_id'] in replace_ids and w['completion_status']=='planned' and (datetime.fromisoformat(w['scheduled_for'])>=now or json.loads(w['definition_json']).get('time_unspecified') and datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()>=today)]
        if any(w['garmin_workout_id'] or w['publish_status']!='local' for w in replaceable):raise ValueError('Published sessions cannot be replaced locally')
    excluded={w['id'] for w in replaceable}
    active=[w for w in existing if w['id'] not in excluded]
    import statistics
    for event in b['fixed_events']:
        if event['duration_minutes'] is None and event.get('distance_km') and event['sport'] in ('cycling','running'):
            estimates=[]
            for ride in c.execute("SELECT id,activity_type,duration_seconds,distance_meters,elevation_gain_meters FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND started_at>=? AND substr(started_at,1,10)<? AND duration_seconds>0 AND distance_meters>0",((today-timedelta(days=365)).isoformat(),today.isoformat())):
                if event['sport']=='cycling' and not any(t in ride['activity_type'].lower() for t in ('cycl','bik')):continue
                if event['sport']=='running' and 'run' not in ride['activity_type'].lower():continue
                km=ride['distance_meters']/1000
                if not .6*event['distance_km']<=km<=1.6*event['distance_km']:continue
                if event.get('elevation_gain_meters') is not None:
                    if ride['elevation_gain_meters'] is None:continue
                    desired=event['elevation_gain_meters']/event['distance_km'];observed=ride['elevation_gain_meters']/km
                    if abs(desired-observed)>max(5,desired*.5):continue
                estimates.append((ride['duration_seconds']/60)*event['distance_km']/km)
            if len(estimates)>=3:
                estimated=round(statistics.median(estimates)/5)*5
                if 15<=estimated<=720:event['duration_minutes']=estimated;event['duration_estimated']=True
        if not event.get('start_time'):
            slots=[slot for slot in answers.get('availability',[]) if slot['weekday']==date.fromisoformat(event['date']).weekday()]
            if slots:event['start_time']=slots[0]['start_time']
        if event.get('duration_estimated'):warnings.append(f"{event['title']}: approximately {event['duration_minutes']} minutes estimated from comparable recorded activities. Distance/elevation remain the planned demands; review this estimate.")
    anchors=[e for e in b['fixed_events'] if week_start.isoformat()<=e['date']<=(week_start+timedelta(days=6)).isoformat() and not (e['date']<today.isoformat() and any(json.loads(w['definition_json']).get('event_id')==e['id'] for w in existing))]
    # Adjacent commitments also protect recovery across week boundaries.
    protected={};occupied=set();sessions=[];allocated={s:0 for s in answers.get('sports',[])}
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
            if definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo') or definition.get('template_id')=='cycling_controlled_intervals' or definition.get('fixed_commitment') and 'hard' in definition.get('effort_target',{}).get('description',''): hard=True
        if minutes>=90 or definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo') or definition.get('template_id')=='cycling_controlled_intervals':
            for offset in (-1,1): protected[(day+timedelta(days=offset)).isoformat()]='Recovery around an existing demanding session.'
    for e in b['fixed_events']:
        demanding=e.get('is_race') or e['effort'] in ('hard','unknown') or (e['duration_minutes'] or 0)>=90 or (e.get('distance_km') or 0)>=60 or (e.get('elevation_gain_meters') or 0)>=1000
        if demanding:
            for offset in (-1,1):
                day=(date.fromisoformat(e['date'])+timedelta(days=offset)).isoformat()
                protected[day]=f"Recovery around {e['title']} on {e['date']}."
    if b['goal']=='race' and b['target_date']:
        occupied.add(b['target_date'])
        for offset in (-2,-1,1,2): protected[(date.fromisoformat(b['target_date'])+timedelta(days=offset)).isoformat()]='Protect freshness and recovery around the race.'
    for e in anchors:
        if e['duration_minutes'] is None: questions.append(f"{e['title']} on {e['date']}: what expected duration?");continue
        if (e['start_time'] and datetime.fromisoformat(_scheduled(e['date'],e['start_time'],tz))<now) or e['date']<today.isoformat(): questions.append(f"{e['title']} is in the past; select a future commitment.")
        if e.get('is_race') and e['effort']=='unknown':e['effort']='hard'
        if e['effort']=='unknown': questions.append(f"{e['title']} on {e['date']}: is the expected effort easy, moderate or hard?")
        if e['sport'] not in allocated or e['sport'] in answers.get('blocked_sports',[]): questions.append('The fixed commitment sport must be selected and not excluded.');continue
        allocated[e['sport']]+=e['duration_minutes'];hard=hard or e['effort'] in ('hard','unknown')
        definition={'version':VERSION,'template_id':'fixed_commitment','sport':e['sport'],'title':e['title'],'duration_minutes':e['duration_minutes'],
                    'fixed_commitment':True,'event_id':e['id'],'distance_km':e.get('distance_km'),'elevation_gain_meters':e.get('elevation_gain_meters'),'is_race':e.get('is_race',False),'duration_estimated':e.get('duration_estimated',False),'effort_target':{'method':'user_reported','description':e['effort']+' effort, as specified by you.'},'rationale':['Preserved fixed commitment; time and duration come from your brief.'],'steps':[{'type':'fixed','duration_seconds':e['duration_minutes']*60,'effort':e['effort']}]}
        if e['start_time'] is None:definition.update(scheduled_date=e['date'],time_unspecified=True,schedule_timezone=tz)
        sessions.append({'sport':e['sport'],'title':e['title'],'scheduled_for':_scheduled(e['date'],e['start_time'],tz),'definition':definition})
    for sport,total in allocated.items():
        if total>answers.get('weekly_minutes',{}).get(sport,0): questions.append(f"Fixed and existing {sport} sessions total {total} minutes, above the confirmed weekly limit. Review the manageable volume in Training preferences; the trip is not shortened.")
    program_start=date.fromisoformat(b['program_start']) if b['program_start'] else week_start
    phases=roadmap(b,program_start,answers)
    block=next((phase for phase in phases if date.fromisoformat(phase['starts_on'])<=week_start<date.fromisoformat(phase['starts_on'])+timedelta(days=7)),None)
    if block is None:questions.append('The reviewed week is outside the chosen training duration')
    block=block or {'phase':'Outside plan','objectives':{'quality_session_limit':0}}
    reduced=block['phase'] in ('Recovery / review','Freshen up','Post-event recovery','Race week')
    if block['objectives']['quality_session_limit']==0:hard=True
    from .active_training import capability
    from pathlib import Path
    db_path=Path(c.execute('PRAGMA database_list').fetchone()['file'])
    capacity=capability(db_path,today,tz)
    adverse_feedback=any((f['effort'] or 0)>=8 or (f['soreness'] or 0)>=5 or re.search(r'\b(too hard|exhausted|too tired)\b',f['notes'] or '',re.I) for f in context['recent_feedback'])
    if adverse_feedback: hard=True;warnings.append('Recent feedback limits added intensity; the coming week stays easy.')
    if capacity['activity_count']>=6 and capacity['aerobic_effect'] is not None and capacity['aerobic_effect']>=4:
        hard=True;warnings.append('Recent Garmin aerobic training effects are high; preserve endurance work without adding intensity.')
    if capacity['activity_count']>=6 and capacity['anaerobic_effect'] is not None and capacity['anaerobic_effect']>=3:
        hard=True;warnings.append('Recent Garmin anaerobic stimulus is substantial; no additional interval session is added.')

    for sport_context in capacity.get('sports',[]):
        for observed in sport_context.get('difficulty',{}).get('demanding_sessions',[]):
            day=date.fromisoformat(observed['date'])
            if day>=today-timedelta(days=1):protected[(day+timedelta(days=1)).isoformat()]='Recovery after demanding recorded '+sport_context['sport']+' activity.'
    program_start=date.fromisoformat(b['program_start']) if b['program_start'] else week_start
    week_index=max(0,(week_start-program_start).days//7)
    strength_performance=[dict(r) for r in c.execute("SELECT s.* FROM training_strength_performance s JOIN planned_workouts w ON w.id=s.workout_id WHERE w.completion_status='completed' ORDER BY recorded_at")]
    history_feedback=context['recent_feedback']
    tolerated=sum(f.get('completion_status')=='completed' and f.get('effort') is not None and f['effort']<=7 and (f.get('soreness') or 0)<=3 and not f['pain_or_illness'] for f in history_feedback)>=2 and not adverse_feedback
    priority_strength=b['strength_role']=='primary' or answers.get('priority')=='strength'
    from .training_prescriptions import cycling_dose,recovery_policy
    dose_context=cycling_dose(max((slot['minutes'] for slot in answers.get('availability',[])),default=60),capacity,history_feedback,today)
    cycling_weekly_cap=context.get('planning_limits',{}).get('cycling',0)
    if allocated.get('cycling',0)>cycling_weekly_cap:warnings.append('Fixed/existing cycling already exceeds the recent-volume planning reference; no generated cycling volume is added. Fixed commitments are not shortened.')
    recovery_context=recovery_policy({'score':None,'groups':[]},None,history_feedback,capacity,today)
    from .training_constraints import slots_for,day_limit
    schedule_days=answers['week_schedule']
    def used_on(day):
        return sum(item['definition']['duration_minutes'] for item in sessions if item['scheduled_for'][:10]==day)+sum(json.loads(item['definition_json'])['duration_minutes'] for item in active if datetime.fromisoformat(item['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()==day)
    def slot_taken(slot,day):
        entries=[(item['sport'],item['definition']) for item in sessions if item['scheduled_for'][:10]==day]+[(item['sport'],json.loads(item['definition_json'])) for item in active if datetime.fromisoformat(item['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()==day]
        if any(definition.get('schedule_slot_id')==slot['slot_id'] for sport,definition in entries):return True
        legacy=sum(sport==slot['sport'] and not definition.get('schedule_slot_id') for sport,definition in entries)
        peers=slots_for(schedule_days,slot['weekday'],slot['sport']);rank=next((index for index,peer in enumerate(peers) if peer['slot_id']==slot['slot_id']),0)
        return legacy>rank
    from .training_prescriptions import advanced_cycling_eligible,cycling_quality_kind
    advanced_ready=advanced_cycling_eligible(c,now,answers.get('experience',{}).get('cycling'),week_index,block['phase'],recovery_context['quality_allowed'] and not hard and not priority_strength)
    if advanced_ready and cycling_quality_kind(week_index,True,b) in ('sprint','anaerobic'):
        volume=context['volume_estimates'].get('cycling',{})
        baseline=int(volume.get('baseline_minutes',cycling_weekly_cap))
        cycling_weekly_cap=min(cycling_weekly_cap,baseline)
        answers['weekly_minutes']['cycling']=cycling_weekly_cap
        context['planning_limits']['cycling']=cycling_weekly_cap
        context['volume_estimates']['cycling']={**volume,'increment_minutes':0,'estimate_minutes':baseline,'effective_ceiling_minutes':cycling_weekly_cap,'intensity_progression_volume_hold':True}
        warnings.append('Dedicated sprint/anaerobic work replaces the quality session; cycling volume is held at the recent baseline rather than increased at the same time.')
    # First weekly draft is a starting week; each later draft is reassessed, never automatically intensified.
    if context['ready'] and not questions:
        slots=[{'weekday':row['weekday'],'start_time':None,'minutes':slot['max_minutes'],'priority':index,**slot} for row in schedule_days if row['mode']=='training' for index,slot in enumerate(row['activities'])]
        # Reserve the uniquely longest primary cycling slot before spending its weekly budget.
        # Equal availability retains chronological allocation; secondary slots keep daily priority.
        cycling_slots=[slot for slot in slots if slot['sport']=='cycling' and slot['priority']==0 and slot['minutes']>=90]
        longest=max((slot['minutes'] for slot in cycling_slots),default=0)
        preferred=[slot for slot in cycling_slots if slot['minutes']==longest]
        long_slot_id=preferred[0]['slot_id'] if len(preferred)==1 else None
        cycling_caps={}
        for candidate in sorted(slots,key=lambda slot:(slot['weekday'],slot['priority'])):
            if candidate['sport']!='cycling':continue
            candidate_day=week_start+timedelta(days=(candidate['weekday']-week_start.weekday())%7)
            if candidate_day<today or candidate_day.isoformat() in occupied or slot_taken(candidate,candidate_day.isoformat()):continue
            ceiling=min(candidate['minutes'],context.get('volume_estimates',{}).get('cycling',{}).get('long_session_minutes',60),max(0,day_limit(schedule_days,candidate['weekday'])-used_on(candidate_day.isoformat())))
            if answers.get('experience',{}).get('cycling')=='new' or candidate_day.isoformat() in protected:ceiling=min(ceiling,30)
            cycling_caps[candidate['slot_id']]=ceiling
        cycling_targets=_cycling_allocations(cycling_caps,max(0,cycling_weekly_cap-allocated.get('cycling',0)),long_slot_id)
        if len(cycling_targets)<len(cycling_caps):warnings.append('The cycling budget cannot support every available day as a purposeful session; omitted days remain rest rather than receiving leftover minutes.')
        for slot in sorted(slots,key=lambda slot:(slot['slot_id']!=long_slot_id,slot['weekday'],slot['priority'])):
            day=week_start+timedelta(days=(slot['weekday']-week_start.weekday())%7);key=day.isoformat()
            if day<today or key in occupied or slot_taken(slot,key):continue
            if slot['start_time'] is not None and datetime.fromisoformat(_scheduled(key,slot['start_time'],tz))<now: continue
            protected_day=key in protected
            candidates=[slot['sport']]
            for sport in candidates:
                if protected_day and (sport!='cycling' or answers.get('pain_or_illness') or recovery_context['level']=='hold'):continue

                if sport=='strength' and any(abs((datetime.fromisoformat(s['scheduled_for']).astimezone(ZoneInfo(tz)).date()-day).days)<2 for s in sessions+active if s['sport']=='strength'): continue
                minutes=min(slot['minutes'],max(0,day_limit(schedule_days,day.weekday())-used_on(key)),(min(answers['weekly_minutes'][sport],cycling_weekly_cap) if sport=='cycling' else answers['weekly_minutes'][sport])-allocated[sport],30 if answers.get('experience',{}).get(sport,'regular')=='new' else slot['minutes'] if sport=='cycling' else 90 if sport==b['goal_sport'] and b['goal'] in ('endurance','race') else 60)
                if b['goal']=='race' and b['target_date'] and (date.fromisoformat(b['target_date'])-day).days<=14: minutes=min(minutes,30)
                template={'cycling':'cycling_easy','running':'running_easy','strength':'strength_foundation','hiking':'hiking_easy','other':'other_easy'}[sport]
                estimate=context.get('volume_estimates',{}).get(sport,{})
                minutes=min(minutes,estimate.get('long_session_minutes',slot['minutes']))
                if sport=='cycling':minutes=min(minutes,cycling_targets.get(slot['slot_id'],0))
                if protected_day:minutes=min(minutes,30)
                if reduced:minutes=min(minutes,30) if sport=='cycling' else round(minutes*.7)
                if adverse_feedback: minutes=min(minutes,45)
                if minutes<(15 if sport=='running' else 10 if sport in ('hiking','other') else 20): continue
                definition=workout_definition(template,minutes,answers)
                from .training_prescriptions import endurance, strength
                if sport=='strength':
                    try:definition=strength(definition,{**b,'strength_performance':strength_performance},answers,week_index,tolerated)
                    except ValueError as error:questions.append(str(error));continue
                elif sport=='cycling':
                    kind='endurance'
                    long_already=any(s['sport']=='cycling' and s['definition']['duration_minutes']>=90 for s in sessions)
                    if slot['slot_id']==long_slot_id and minutes>=60 or minutes>=90 and not long_already:
                        kind='climbing_endurance' if any((e.get('elevation_gain_meters') or 0)>=1000 for e in b['fixed_events']) else 'long_tempo' if tolerated and week_index%3==2 and not hard else 'long_endurance'
                        if kind=='long_tempo':hard=True
                    elif long_already:minutes=min(minutes,60)
                    if slot['slot_id']!=long_slot_id and (b['goal'] in ('ftp','general') or b['goal'] in ('endurance','race') and b['goal_sport']=='cycling') and not priority_strength and answers.get('experience',{}).get(sport,'regular')!='new' and not hard and recovery_context['quality_allowed'] and not slots_for(schedule_days,(day.weekday()+1)%7,'strength') and minutes>=45 and answers['weekly_minutes'][sport]>=120:
                        kind=cycling_quality_kind(week_index,advanced_ready,b);minutes=min(minutes,60);hard=True
                        requested_quality=cycling_quality_kind(week_index,True,b)
                        if requested_quality!=kind:warnings.append(f'{requested_quality.title()} deferred: dedicated advanced work needs the build phase, experienced cycling, two tolerated completed quality sessions and recovery clearance. Controlled short efforts are used instead.')
                        protected[(day+timedelta(days=1)).isoformat()]='Recovery after a quality cycling session.'
                    if reduced or protected_day:kind='recovery'
                    definition=endurance(kind,minutes,b,sport,today=today)
                    if slot['slot_id']==long_slot_id:definition['rationale'].append('Your longest available cycling day is prioritized for the long ride before allocating shorter rides; history and recovery still cap its duration.')
                    definition['rationale'].append(f'Building-block week {week_index+1}; sustained endurance for the selected event/direction.')
                    if any((e.get('elevation_gain_meters') or 0)>=1000 for e in b['fixed_events']):definition['rationale'].append('For the hilly event, use a sustained climbing route while keeping the prescribed intensity.')
                definition['schedule_slot_id']=slot['slot_id'];definition['schedule_slot_label']=slot.get('label')
                if sport=='other':definition['title']=slot.get('label') or 'Easy activity'
                if sport in ('hiking','other'):definition['rationale'].append('Simple explicitly selected duration-based activity; no sport-specific capacity or calibration is inferred.')
                if sport=='cycling':
                    definition['duration_guidance']={**cycling_dose(slot['minutes'],capacity,history_feedback,today),'weekly_cap_minutes':cycling_weekly_cap,'weekly_reference_minutes':context.get('volume_estimates',{}).get('cycling',{}).get('baseline_minutes'),'weekly_budget_policy':context.get('volume_estimates',{}).get('cycling',{}).get('policy_version')}
                    definition['rationale'].append(definition['duration_guidance']['reason'])
                    if protected_day:definition['rationale'].append('Optional short recovery on an available cycling day: '+protected[key])
                definition['training_block']={'phase':block['phase'],'week':week_index+1,'program_start':program_start.isoformat()}
                definition['rationale'].append('Current block: '+block['phase']+'. '+block.get('focus',''))
                definition['rationale'].append('Goal: '+GOALS[b['goal']]+'. Fixed commitments count toward the confirmed weekly budget.')
                if slot['start_time'] is None:definition.update(scheduled_date=key,time_unspecified=True,schedule_timezone=tz)
                sessions.append({'sport':sport,'title':definition['title'],'scheduled_for':_scheduled(key,slot['start_time'],tz),'definition':definition});allocated[sport]+=minutes;break
    sessions.sort(key=lambda session:session['scheduled_for'])
    for index,session in enumerate(sessions):session['candidate_index']=index
    changes=session_changes or []
    if not isinstance(changes,list) or len(changes)>20:raise ValueError('Use at most twenty session changes')
    for change in changes:
        if not isinstance(change,dict) or set(change)-{'index','scheduled_for','scheduled_date','start_time','duration_minutes','title','exercises','schedule_slot_id'}:raise ValueError('Unsupported session change')
        index=change.get('index')
        if type(index) is not int or not 0<=index<len(sessions):raise ValueError('Session changed; preview again')
        session=sessions[index]
        original_schedule={key:session['definition'][key] for key in ('scheduled_date','time_unspecified','schedule_timezone','schedule_slot_id','schedule_slot_label') if key in session['definition']}
        if session['definition'].get('fixed_commitment'):raise ValueError('Edit fixed commitments in the event fields')
        if 'title' in change:
            if not isinstance(change['title'],str) or not 1<=len(change['title'].strip())<=160:raise ValueError('Session title required up to 160 characters')
            session['title']=change['title'].strip()
        if 'scheduled_for' in change:
            when=datetime.fromisoformat(change['scheduled_for'])
            if not when.tzinfo or when<now or not week_start<=when.astimezone(ZoneInfo(tz)).date()<=week_start+timedelta(days=6):raise ValueError('Choose a future session time in the reviewed week')
            session['scheduled_for']=when.isoformat();original_schedule={}
        if 'scheduled_date' in change:
            date_only=date.fromisoformat(change['scheduled_date']);clock=change.get('start_time')
            if date_only<today or not week_start<=date_only<=week_start+timedelta(days=6):raise ValueError('Choose a current or future day in the reviewed window')
            session['scheduled_for']=_scheduled(date_only.isoformat(),clock,tz)
            original_schedule={'scheduled_date':date_only.isoformat(),'time_unspecified':clock is None,'schedule_timezone':tz}
        if 'duration_minutes' in change:
            minutes=_number(change['duration_minutes'],'session minutes',20,360,True)
            from .training_prescriptions import endurance,strength
            if session['sport']=='strength':
                base=workout_definition('strength_foundation',minutes,answers)
                session['definition']=strength(base,b,answers,week_index,tolerated)
            else:session['definition']=endurance(session['definition'].get('workout_kind','endurance'),minutes,b,session['sport'],today=today)
            if 'title' not in change:session['title']=session['definition']['title']
        if 'exercises' in change:
            if session['sport']!='strength' or not isinstance(change['exercises'],list) or not 1<=len(change['exercises'])<=20:raise ValueError('Exercise edits require a strength session')
            existing_exercises={exercise['id']:exercise for exercise in session['definition'].get('exercises',[])}
            seen=set()
            for edit in change['exercises']:
                if not isinstance(edit,dict) or set(edit)-{'id','sets','repetitions','rest_seconds','load_target_kg'} or edit.get('id') not in existing_exercises or edit['id'] in seen:raise ValueError('Edit each existing exercise at most once')
                seen.add(edit['id']);exercise=existing_exercises[edit['id']]
                for field,bounds in [('sets',(1,10)),('repetitions',(1,50)),('rest_seconds',(15,600))]:
                    if field in edit:_number(edit[field],field,*bounds,True);exercise[field]=edit[field]
                if 'load_target_kg' in edit:
                    _number(edit['load_target_kg'],'exercise load kg',0,500);exercise['load_target_kg']=edit['load_target_kg']
            cost=sum(exercise['sets']*(60+exercise['rest_seconds']) for exercise in existing_exercises.values())
            if cost>session['definition']['duration_minutes']*60-300:raise ValueError('Exercise sets and rest exceed session time; increase duration or reduce sets')
        for key in ('scheduled_date','time_unspecified','schedule_timezone','schedule_slot_id','schedule_slot_label'):session['definition'].pop(key,None)
        session['definition'].update(original_schedule)
        day=datetime.fromisoformat(session['scheduled_for']).astimezone(ZoneInfo(tz))
        from .training_constraints import assign_slot
        used_ids=[other['definition'].get('schedule_slot_id') for other in sessions if other is not session and other['scheduled_for'][:10]==session['scheduled_for'][:10]]
        assigned=assign_slot(schedule_days,day.weekday(),session['sport'],session['definition']['duration_minutes'],change.get('schedule_slot_id') or session['definition'].get('schedule_slot_id'),used_ids)
        session['definition']['schedule_slot_id']=assigned['slot_id']
    for sport in answers.get('sports',[]):
        if changes and sum(x['definition']['duration_minutes'] for x in sessions if x['sport']==sport)>answers['weekly_minutes'][sport]:raise ValueError('Edited sessions exceed weekly volume')
    for i,s in enumerate(sessions):
        start=datetime.fromisoformat(s['scheduled_for']);finish=start+timedelta(minutes=s['definition']['duration_minutes'])
        for other in sessions[i+1:]:
            if s['definition'].get('time_unspecified') or other['definition'].get('time_unspecified'):continue
            other_start=datetime.fromisoformat(other['scheduled_for'])
            if start<other_start+timedelta(minutes=other['definition']['duration_minutes']) and other_start<finish:questions.append('Upcoming events overlap; choose distinct times or an event priority.')
    for s in sessions:
        begin=datetime.fromisoformat(s['scheduled_for']);end=begin+timedelta(minutes=s['definition']['duration_minutes'])
        for w in active:
            if s['definition'].get('time_unspecified') or json.loads(w['definition_json']).get('time_unspecified'):continue
            other=datetime.fromisoformat(w['scheduled_for'])
            if not other.tzinfo: questions.append('An existing workout has ambiguous timing; review it.');continue
            duration=json.loads(w['definition_json']).get('duration_minutes')
            if not isinstance(duration,(int,float)) or isinstance(duration,bool) or duration<=0: questions.append('An existing workout has an unknown duration; review it.');continue
            if begin<other+timedelta(minutes=duration) and other<end: questions.append('A fixed or generated session overlaps an existing workout. Select the existing week to replace or revise the commitment.')
    for session in sessions:
        session['scheduled_date']=session['definition'].get('scheduled_date') or session['scheduled_for'][:10]
        session['time_unspecified']=session['definition'].get('time_unspecified',False)
    for day in {session['scheduled_date'] for session in sessions if session['time_unspecified'] or any(json.loads(w['definition_json']).get('time_unspecified') and datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()==session['scheduled_date'] for w in active)}:
        day_sessions=[session for session in sessions if session['scheduled_date']==day]
        day_total=sum(session['definition']['duration_minutes'] for session in day_sessions)+sum(json.loads(w['definition_json'])['duration_minutes'] for w in active if datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()==day)
        slot=next((slot for slot in answers.get('availability',[]) if slot['weekday']==date.fromisoformat(day).weekday()),None)
        if day_total>(slot['minutes'] if slot else 1440):questions.append('Sessions on '+day+' exceed the confirmed day budget; adjust duration or assign explicit non-overlapping times.')
    recorded=[dict(r) for r in c.execute("SELECT activity_type,COUNT(*) AS activities,SUM(duration_seconds)/60 AS minutes FROM activities WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture' AND substr(started_at,1,10)>=? AND substr(started_at,1,10)<? GROUP BY activity_type",((today-timedelta(days=28)).isoformat(),today.isoformat()))]
    state={'brief':b,'today':today.isoformat(),'sessions':sessions,'candidate_answers':patch,'session_changes':changes,'preferences':context,'source_brief_revision':(c.execute('SELECT revision FROM training_coach_brief WHERE id=1').fetchone() or [0])[0],'source_program':dict(c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone() or {}),'existing':existing,'replace_plan_id':replace_plan_id,'week_start':week_start.isoformat(),'timezone':tz}
    fingerprint=hashlib.sha256(encoded(state).encode()).hexdigest()
    from .training_prescriptions import cycling_mix
    questions=list(dict.fromkeys(questions))
    return {'cycling_mix':cycling_mix(b),'volume_estimates':context.get('volume_estimates',{}),'candidate_answers':patch,'session_changes':changes,'garmin_ftp':garmin_ftp,'duration_confirmed':b['duration_confirmed'],'status':'needs_input' if questions else 'ready' if sessions else 'needs_review','brief':b,'week_start':week_start.isoformat(),'timezone':tz,
            'calibration_questions':sensor_questions,'strength_questions':strength_questions,'questions':questions or ([] if sessions else ['No session fits the constraints. Review availability and fixed commitments.']),
            'week_schedule':schedule_days,'warnings':warnings,'roadmap':phases,'block_summary':summarize_blocks(phases),'sessions':sorted(sessions,key=lambda s:s['scheduled_for']),
            'protected_days':[{'date':day,'reason':reason} for day,reason in sorted(protected.items()) if week_start.isoformat()<=day<=(week_start+timedelta(days=6)).isoformat()],
            'weekly_minutes':allocated,'capability_context':capacity,'recorded_history':{'start':(today-timedelta(days=28)).isoformat(),'end':today.isoformat(),'note':'Recorded history provides context; it does not automatically increase volume.','sports':[{'activity_type':r['activity_type'],'activity_count':r['activities'],'recorded_minutes':r['minutes'] or 0} for r in recorded]},'expected_preference_revision':context['revision'],
            'fingerprint':fingerprint,'replace_plan_id':replace_plan_id,'replaces_session_count':len(replaceable),
            'rationale':['Fixed commitments retain their requested date, time and duration.','Generated volume stays within confirmed manageable weekly limits.','Demanding or long commitments protect the surrounding days.','At most one added controlled interval session; a hard fixed commitment uses that slot.','Review the multi-week direction each week using completion, effort and soreness; future readiness is not forecast.'],
            'advisory':'This is a reviewed starting plan. Phase lengths, recovery buffers and interval doses are provisional planning defaults; no FTP improvement or race result is promised.'}


def preview(brief,week_start,tz,path=None,now=None,replace_plan_id=None,candidate_answers=None,session_changes=None):
    if brief.get('program_start') and week_start<date.fromisoformat(brief['program_start']):week_start=date.fromisoformat(brief['program_start'])
    with connect(path) as c: return _preview(c,brief,week_start,tz,now or datetime.now(timezone.utc),replace_plan_id,candidate_answers,session_changes)


def create_draft(brief,week_start,tz,fingerprint,path=None,now=None,replace_plan_id=None):
    now=now or datetime.now(timezone.utc)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');p=_preview(c,brief,week_start,tz,now,replace_plan_id)
        if not isinstance(fingerprint,str) or fingerprint!=p['fingerprint']: raise ValueError('Planning context changed; preview the week again before saving')
        if p['status']!='ready': raise ValueError('Answer the coaching questions before creating a draft')
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
    from .training_questionnaire import candidate_snapshot
    candidate=candidate_snapshot(path,tz,now)
    brief=arguments.get('brief') or candidate['brief']
    brief,recognized=parse_request(message,brief,week,today)
    answers=arguments.get('candidate_answers',candidate['candidate_answers'])
    return {'tool':'preview_training_plan',**preview(brief,week,tz,path,now,arguments.get('replace_plan_id'),candidate_answers=answers,session_changes=arguments.get('session_changes')),'recognized':recognized}


def assistant_answer(result):
    b=result['brief']
    if result.get('questionnaire') and result.get('questions'):
        return ' '.join([*result.get('recognized',[]),result['questions'][0]])
    if not b.get('duration_confirmed') and not b.get('program_start'):
        return 'Before I build your long-term plan: '+result['questions'][0]
    lines=[f"Here is the proposed {b['horizon_weeks']}-week plan to {GOALS.get(b['goal'],'work toward your goal').lower()}. Nothing has been saved."]
    lines.extend(result.get('recognized',[]))
    for block in result.get('block_summary',[]):
        span=str(block['start_week']) if block['start_week']==block['end_week'] else str(block['start_week'])+'–'+str(block['end_week'])
        lines.append(f"Weeks {span}: {block['phase']} ({block['weeks']} {'week' if block['weeks']==1 else 'weeks'}). {block['focus']}")
    if result['questions']:lines.append(result['questions'][0])
    else:
        lines.append('Your next seven days follow the current block, confirmed availability and upcoming events: '+', '.join(f"{sport}: {minutes} min" for sport,minutes in result['weekly_minutes'].items())+'.')
    lines.extend(result['warnings'])
    lines.append('Review the proposal and choose Approve and activate plan when you are happy with it.')
    return '\n\n'.join(lines)


def propose_setup(arguments,path=None):
    from .training import validate_answers
    current=training_context_for_setup(path);saved=read_brief(path)
    changes=arguments.get('answers') or {};patch=arguments.get('brief_changes') or {}
    answers=validate_answers(changes)
    b=validate_brief({**saved['brief'],**patch})
    if not answers and not patch:raise ValueError('Provide explicit preference or direction changes')
    return {'tool':'propose_training_setup','answers':answers,'brief':b,'expected_preference_revision':current['revision'],'expected_brief_revision':saved['revision'],'status':'proposal','message':'Review the preferences and direction extracted from your conversation; nothing is saved yet.'}


def training_context_for_setup(path=None):
    from .training import training_context
    return training_context(path)


def save_setup(answers,brief,expected_preference_revision,expected_brief_revision,path=None):
    from .training import validate_answers,_preferences
    patch=validate_answers(answers)
    if 'week_schedule' in patch:patch.pop('weekly_minutes',None)
    b=validate_brief(brief);now=datetime.now(timezone.utc)
    if b['ftp_selection']=='garmin':
        from .training_ftp import resolve
        with connect(path) as ftp_connection:ftp=resolve(ftp_connection,now.date())
        b['ftp_watts']=ftp['watts'];b['calibration']['ftp_confirmed_on']=ftp['measurement_date'];b['calibration']['ftp_source']=ftp['source'] or 'Garmin cycling FTP'
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');current=_preferences(c)
        stored=c.execute('SELECT revision FROM training_coach_brief WHERE id=1').fetchone()
        if current['revision']!=expected_preference_revision or (stored[0] if stored else 0)!=expected_brief_revision:raise ValueError('Training context changed; ask the coach for a fresh proposal')
        if patch:
            from .training_constraints import merge_answers,schedule
            merged=merge_answers(current['answers'],patch)
            if 'week_schedule' in merged:merged['week_schedule']=schedule(merged['week_schedule'],complete=True)
            confirmed={**current['confirmed_at'],**{k:now.isoformat() for k in patch}};revision=current['revision']+1
            c.execute('INSERT INTO training_preferences(id,revision,answers_json,confirmed_json) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,answers_json=excluded.answers_json,confirmed_json=excluded.confirmed_json',(revision,encoded(merged),encoded(confirmed)))
            c.execute('INSERT INTO training_preference_revisions(revision,answers_json,confirmed_json) VALUES(?,?,?)',(revision,encoded(merged),encoded(confirmed)))
        _store_brief(c,b,expected_brief_revision+1)
    saved=read_brief(path)
    current=training_context_for_setup(path)
    return {'status':'saved','message':'Training preferences, calibration and direction saved. No workout schedule has been activated.','brief':saved['brief'],'brief_revision':saved['revision'],'preferences':current,'next_action':'review_plan','schedule_activated':False}


def approve(brief,week_start,tz,fingerprint,path=None,now=None,replace_plan_id=None,candidate_answers=None,session_changes=None):
    """Recompute and persist a reviewed program in one transaction; fingerprint is its retry key."""
    now=now or datetime.now(timezone.utc)
    if not isinstance(fingerprint,str) or len(fingerprint)!=64:
        raise ValueError('Preview the plan before approving')
    if not replace_plan_id and brief.get('program_start') and date.fromisoformat(brief['program_start'])!=week_start:raise ValueError('Review the first seven days from the agreed program start date before activating')
    identifier='plan-approved-'+fingerprint
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute('SELECT * FROM training_plans WHERE id=?',(identifier,)).fetchone()
        if previous:
            if previous['deleted_at']:raise ValueError('This approved plan was removed; preview a new proposal')
            saved=json.loads(previous['context_json'])
            if saved.get('approval_input')!=validate_brief(brief) or saved.get('candidate_answers',{})!=validate_answers(candidate_answers or {}) or saved.get('session_changes',[])!=(session_changes or []) or saved['week_start']!=week_start.isoformat() or saved['timezone']!=tz or saved.get('replace_plan_id')!=replace_plan_id:
                raise ValueError('Approval key belongs to a different proposal')
        else:
            if not brief.get('duration_confirmed'):raise ValueError('Confirm how many weeks you would like to train for (4, 8, 12, 16 or custom 4–24)')
            p=_preview(c,brief,week_start,tz,now,replace_plan_id,candidate_answers,session_changes)
            if p['fingerprint']!=fingerprint:raise ValueError('Planning context changed; preview again before approving')
            if p['status']!='ready':raise ValueError('Answer the coaching questions before approving')
            if candidate_answers:
                from .training import _preferences
                old=_preferences(c)
                from .training_constraints import merge_answers,schedule
                merged=merge_answers(old['answers'],candidate_answers)
                if 'week_schedule' in merged:merged['week_schedule']=schedule(merged['week_schedule'],complete=True)
                confirmed={**old['confirmed_at'],**{k:now.isoformat() for k in candidate_answers}};rev=old['revision']+1
                c.execute('INSERT INTO training_preferences(id,revision,answers_json,confirmed_json) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,answers_json=excluded.answers_json,confirmed_json=excluded.confirmed_json',(rev,encoded(merged),encoded(confirmed)))
                c.execute('INSERT INTO training_preference_revisions(revision,answers_json,confirmed_json) VALUES(?,?,?)',(rev,encoded(merged),encoded(confirmed)))
            stored={**p,'approval_input':validate_brief(brief),'preferences':_context(c,now),'rule_version':VERSION,'coaching':True}
            pending=c.execute('SELECT state_json FROM training_questionnaire WHERE id=1').fetchone()
            if pending:stored['accepted_questionnaire']=json.loads(pending[0])
            c.execute("INSERT INTO training_plans(id,name,status,starts_on,ends_on,context_json) VALUES(?,?,'active',?,?,?)",(identifier,GOALS[p['brief']['goal']]+' · '+week_start.isoformat(),week_start.isoformat(),(week_start+timedelta(days=6)).isoformat(),encoded(stored)))
            for session in p['sessions']:
                wid='workout-'+str(uuid.uuid4())
                c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',(wid,identifier,session['sport'],session['title'],session['scheduled_for'],encoded(session['definition'])))
                _revision(c,_snapshot(c,wid))
            row=c.execute('SELECT revision FROM training_coach_brief WHERE id=1').fetchone()
            _store_brief(c,p['brief'],(row[0] if row else 0)+1)
            from .active_training import activate
            activate(c,c.execute('SELECT * FROM training_plans WHERE id=?',(identifier,)).fetchone())
            # Accepted answers now live in the saved preferences/program, not a stale candidate.
            c.execute('DELETE FROM training_questionnaire')
    return list_training(path)
