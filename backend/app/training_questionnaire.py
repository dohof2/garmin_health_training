"""Durable, reviewable trainer answers; conversation facts never activate a program."""
import hashlib
import json
import re
from datetime import date,datetime,timedelta,timezone
from .database import connect
from .training import _context,validate_answers,encoded
from .training_coach import DEFAULT,validate_brief,parse_request,read_brief,preview
from .time_utils import timezone_info
from .training_ftp import resolve
from .training_constraints import merge_answers, merge_schedule, SPORT_CATALOG

DAYS=('monday','tuesday','wednesday','thursday','friday','saturday','sunday')
MONTHS={name:index for index,name in enumerate(('january','february','march','april','may','june','july','august','september','october','november','december'),1)}
MONTHS.update({name[:3]:number for name,number in list(MONTHS.items())})
MONTHS['sept']=9

def _start_date(text,today):
    text=text.lower()
    month='(?:'+ '|'.join(sorted(MONTHS,key=len,reverse=True))+')'
    ordinal=r'\d{1,2}(?:st|nd|rd|th)?'
    token=rf'tomorrow|today|\d{{4}}-\d{{2}}-\d{{2}}|{month}\.?\s+{ordinal}(?:,?\s+\d{{4}})?|{ordinal}\s+{month}\.?(?:,?\s+\d{{4}})?'
    match=re.search(rf'\b(?:start|begin|starting|beginning|from)\b[^.;]{{0,35}}?\b({token})(?!\w)',text)
    if not match:return None
    value=match[1]
    if value in ('today','tomorrow'):return today+timedelta(days=value=='tomorrow')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return date.fromisoformat(value)
    parts=re.sub(r'(?<=\d)(st|nd|rd|th)\b','',value).replace(',','').replace('.','').split()
    if parts[0] in MONTHS:month_number,day=MONTHS[parts[0]],int(parts[1])
    else:day,month_number=int(parts[0]),MONTHS[parts[1]]
    return date(int(parts[2]) if len(parts)>2 else today.year,month_number,day)

def read(path=None):
    with connect(path) as c:
        row=c.execute('SELECT revision,state_json FROM training_questionnaire WHERE id=1').fetchone()
    return {'revision':row['revision'],'state':json.loads(row['state_json'])} if row else {'revision':0,'state':None}


def _history(c,today,sports):
    result={}
    for sport in sports:
        rows=[]
        for row in c.execute("SELECT activity_type,started_at,duration_seconds FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND substr(started_at,1,10) BETWEEN ? AND ?",((today-timedelta(days=84)).isoformat(),today.isoformat())):
            kind=row['activity_type'].lower()
            matches=any(x in kind for x in ('cycl','bik')) if sport=='cycling' else any(x in kind for x in ('strength','weight')) if sport=='strength' else 'run' in kind
            if matches and row['duration_seconds'] and row['duration_seconds']>0:rows.append(dict(row))
        weeks={date.fromisoformat(row['started_at'][:10]).isocalendar()[:2] for row in rows}
        count=len(rows);longest=max((row['duration_seconds']/60 for row in rows),default=0)
        experience='experienced' if count>=12 and len(weeks)>=4 and longest>=90 else 'regular' if count>=6 and len(weeks)>=3 else None
        result[sport]={'activity_count':count,'recorded_weeks':len(weeks),'longest_minutes':longest,'experience':experience,'source':'recorded_history','note':'Recorded experience context; current manageable volume is estimated separately from optional user caps.'}
    return result


def _contextual_reply(state,message):
    """Interpret a short reply only against the field actually being asked."""
    target=state.get('awaiting');text=message.strip().lower().strip('.! ')
    answers=state['answers'];brief=state['brief'];partial=state['partial']
    if target=='preferences':
        previous=state.get('next_question','').lower()
        if 'pull-up' in previous or 'pull up' in previous:target='pull_up_reps'
        elif 'dips' in previous:target='dip_reps'
        elif 'week' in previous and ('hours' in previous or 'minutes' in previous):
            sports=[sport for sport in ('cycling','running','strength') if sport in previous]
            if len(sports)==1:target='weekly_minutes:'+sports[0]
    if target and target.startswith('weekly_minutes:'):
        normalized=text.replace('–','-').replace('—','-')
        for word,value in {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}.items():normalized=re.sub(r'\b'+word+r'\b',str(value),normalized)
        match=re.fullmatch(r'(?:about|around|roughly|approximately|maybe)?\s*(\d+(?:\.\d+)?)(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?\s*(hours?|hrs?|h|minutes?|mins?|m)?(?:\s*(?:per week|a week|weekly))?',normalized)
        if match:
            low=float(match[1]);high=float(match[2] or match[1]);unit=match[3]
            if not unit:
                previous=state.get('next_question','').lower()
                inherited=re.search(r'how (?:many|much)\s+(hours?|minutes?)\b',previous)
                unit=state.get('awaiting_unit') or (inherited[1] if inherited else None)
            if not unit:
                state['clarifications'].append('Is that hours or minutes per week? For example, “6–7 hours” or “90 minutes”.')
            else:
                factor=60 if unit.startswith('h') else 1;lower=low*factor;upper=high*factor
                if low>high:state['clarifications'].append('The range is reversed. Give the smaller value first, for example “6–7 hours”.')
                elif not 0<=lower<=upper<=1260 or not lower.is_integer() or not upper.is_integer():state['clarifications'].append('Use a weekly time between 0 and 21 hours (1260 minutes), for example “6–7 hours”.')
                else:
                    sport=target.split(':')[1];answers.setdefault('weekly_caps',{})[sport]={'max_minutes':int(upper),**({'range_min_minutes':int(lower)} if match[2] else {})}
                    if match[2]:state['range_acknowledgment']=f'I kept {sport} at {low:g}–{high:g} {unit} per week. The upper end is a limit, not a required training volume.'
                    brief['weekly_time_ranges']={**brief.get('weekly_time_ranges',{}),sport:[int(lower),int(upper)]}
                    state['provenance']['weekly_minutes.'+sport]={'source':'contextual_user_reply','text':message,'unit':unit,'range_minutes':[int(lower),int(upper)],'approximate':bool(re.search(r'about|around|roughly|approximately|maybe',text)),'planning_rule':'upper bound is a cap, not a required workout volume'}
            return
        state['clarifications'].append('I could not interpret that as weekly time. Give a number or range with units, for example “6–7 hours” or “90 minutes”.')
        return
    numbers={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
    match=re.fullmatch(r'(?:about|around|roughly|approximately|maybe|i can do|i can manage)?\s*(\d+|'+ '|'.join(numbers)+r')\s*(reps?|repetitions?|pull[ -]?ups?|dips?|minutes?|mins?|hours?|hrs?|weeks?)?',text)
    if match:
        raw=match[1];value=numbers[raw] if raw in numbers else int(raw);unit=match[2] or ''
        if target in ('pull_up_reps','dip_reps') and (not unit or unit.startswith(('rep','pull','dip'))):
            named='pull_up_reps' if unit.startswith('pull') else 'dip_reps' if unit.startswith('dip') else target
            if named==target and 0<=value<=50:
                brief['strength_capacity'][target]=value
                state['provenance'][target]={'source':'contextual_user_reply','text':message,'approximate':bool(re.search(r'about|around|roughly|approximately|maybe',text))}
        elif target=='duration' and 4<=value<=24 and (not unit or unit.startswith('week')):
            brief['horizon_weeks']=value;brief['duration_confirmed']=True
    if target and target.startswith('experience:'):
        sport=target.split(':')[1]
        if re.search(r'\b(new|beginner|novice|never|not before)\b',text):answers.setdefault('experience',{})[sport]='new'
        elif re.search(r'\b(experienced|advanced)\b',text):answers.setdefault('experience',{})[sport]='experienced'
        elif re.search(r'\b(regular|regularly|intermediate)\b',text):answers.setdefault('experience',{})[sport]='regular'
    if target in ('restrictions','pain_or_illness') and text in ('no','none','nope','nothing','no restrictions','no pain or restrictions','none at all'):
        answers.update(pain_or_illness=False,blocked_sports=[],blocked_movements=[],restrictions_notes='')
    if target in ('pull_up_reps','dip_reps') and text in ('none','zero',"i can't do any",'cannot do any','not yet'):
        brief['strength_capacity'][target]=0
        state['provenance'][target]={'source':'contextual_user_reply','text':message,'approximate':False}
    if target=='ftp_authorization' and text in ('no','no thanks','skip it','use effort instead'):
        partial['ftp_declined']=True
    if target=='strength_role' and re.search(r'\b(cycling|bike|core|support|secondary)\b',text):
        brief['strength_role']='secondary';brief['strength_purpose']='cycling_support'
    if target=='power_access' and text in ('both','indoors and outdoors','indoor and outdoor'):
        brief['calibration']['power_access']='both'
    # Broad timing is an optional preference, never converted into an exact clock.
    if re.fullmatch(r'(?:in the |mostly |usually )?(morning|afternoon|evening|anytime)',text):partial['time_preference']=text.split()[-1]


def _extract(state,message,today,week):
    text=message.lower().replace('–','-').replace('—','-');text=re.sub(r'\b(?:strengh|strenght)\b','strength',text);text=re.sub(r'\bbegginer\b','beginner',text);partial=state['partial'];answers=state['answers'];brief=state['brief']
    # Typed statements are validated before entering the candidate, and provenance points to user text.
    def put(field,value):
        previous=answers.get(field)
        if previous is not None and previous!=value:state['changes'].append({'field':field,'previous':previous,'value':value})
        answers[field]=value;state['provenance'][field]={'source':'user_message','text':message[:2000]}
    try:start=_start_date(text,today)
    except ValueError:
        start=None;state['clarifications'].append('That start date is invalid; please provide a valid date, including the year.')
    if start:
        selected=start.isoformat()
        if selected<today.isoformat():state['clarifications'].append('The requested start date is past; choose today or a future date.')
        else:
            partial['start_date']=selected;brief['program_start']=selected
            state['provenance']['program_start']={'source':'user_message','text':message[:2000],'resolved_local_date':selected}
    before_events=brief.get('fixed_events',[])
    # Recurring availability is not a one-off fixed ride.
    recurring=bool(re.search(r'\b(?:every|weekdays?|cycling|strength)\b',text) and any(day in text for day in DAYS))
    try:
        parsed,_=parse_request(message,brief,week,today)
        if recurring:parsed['fixed_events']=before_events
        brief.update(parsed)
    except ValueError as error:state['clarifications'].append(str(error))
    if re.search(r'\bftp\b',text) and re.search(r'\bendurance\b',text):brief['goal']='ftp';answers.setdefault('priority','endurance')
    if brief.get('goal') in ('ftp','endurance','race'):answers.setdefault('priority','endurance')
    if re.search(r'\b(?:cycling|bike|rides?)\b',text) and not re.search(r'\b(?:no|without) cycling\b',text):
        put('sports',list(dict.fromkeys(answers.get('sports',[])+['cycling'])))
    if re.search(r'\bstrength\b',text):put('sports',list(dict.fromkeys(answers.get('sports',[])+['strength'])))
    for sport,pattern in [('running',r'\brunn?(?:ing)?\b'),('hiking',r'\bhik(?:e|ing)\b')]:
        if re.search(pattern,text):put('sports',list(dict.fromkeys(answers.get('sports',[])+[sport])))
    for sport,pattern in [('cycling',r'\b(?:cycling|rides?|bike)\b'),('strength',r'\bstrength\b'),('running',r'\b(?:running|runs?)\b'),('hiking',r'\b(?:hiking|hike)\b')]:
        for clause in re.split(r'[;\n.]|,(?=\s*(?:strength|cycling|running)\b)',text):
            if re.search(pattern,clause):
                days=[i for i,day in enumerate(DAYS) if re.search(r'\b'+day+r'\b',clause)]
                if days:
                    old_days=partial.setdefault('sport_days',{}).get(sport,[])
                    if re.search(r'\b(?:only|instead|replace|change)\b',clause):partial['sport_days'][sport]=days
                    else:partial['sport_days'][sport]=sorted(set(old_days)|set(days))
                    state['provenance']['sport_days']={'source':'user_message','text':message[:2000]}
    exclusions=re.search(r'\b(?:ride|rides|cycling)\s+days?[^\n.;]*?\b(?:apart from|except|excluding)\b([^\n.;]*)',text)
    if exclusions:
        excluded=[i for i,day in enumerate(DAYS) if re.search(r'\b'+day+r'\b',exclusions[1])]
        if excluded:
            partial.setdefault('sport_days',{})['cycling']=[i for i in range(7) if i not in excluded]
            if re.search(r'\bstrength\b',exclusions[1]):partial['sport_days']['strength']=excluded
            state['provenance']['sport_days']={'source':'user_message','text':message[:2000]}
    rest=[i for i,day in enumerate(DAYS) if re.search(day+r'[^.;]{0,20}\b(?:off|rest)\b',text)]
    if rest:partial['rest_days']=sorted(set(partial.get('rest_days',[]))|set(rest))
    for sport,days in partial.get('sport_days',{}).items():
        if re.search(r'\b(?:change|instead|only|replace)\b',text) and sport in text:
            corrected=[i for i,day in enumerate(DAYS) if day in text]
            if corrected:
                for other,other_days in partial['sport_days'].items():
                    if other!=sport:partial['sport_days'][other]=[d for d in other_days if d not in corrected]
                partial['rest_days']=[d for d in partial.get('rest_days',[]) if d not in corrected]
    range_match=re.search(r'(\d+)\s*-\s*(\d+)\s*(?:min|minutes)',text)
    if range_match:partial['weekday_minutes_range']=[int(range_match[1]),int(range_match[2])]
    fixed_minutes=re.search(r'\bweekdays?\s*(?:are|of|for|:)?\s*(\d+)\s*(?:min|minutes)',text)
    if fixed_minutes:partial['weekday_minutes']=int(fixed_minutes[1])
    long=re.search(r'(?:up to\s*)?(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)[^.;\n]{0,70}\bfriday\b',text)
    if not long:long=re.search(r'\bfriday\b[^.;\n]{0,70}?(?:up to\s*)?(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)',text)
    if long:partial['friday_minutes']=round(float(long[1])*(60 if long[2].startswith('h') else 1))
    if re.search(r'\b(?:five|5) hours?\b',text) and 'friday' in text:partial['friday_minutes']=300
    if state.get('awaiting')=='weekday_minutes' and re.fullmatch(r'\s*\d+\s*(?:minutes?|mins?)?[.! ]*',text):partial['weekday_minutes']=int(re.search(r'\d+',text)[0])
    choose=re.search(r'\b(?:use|choose|confirm|set)\s+(\d+)\s*(?:min|minutes)\b',text)
    if choose:partial['weekday_minutes']=int(choose[1])
    experience=dict(answers.get('experience',{}))
    for sport in answers.get('sports',[]):
        name='strength' if sport=='strength' else '(?:cycling|bike)' if sport=='cycling' else '(?:running|run)' if sport=='running' else '(?:hiking|hike)' if sport=='hiking' else re.escape(sport)
        found=re.search(r'(?:\b(beginner|new|regular|experienced)\b[^.;]{0,20}\b'+name+r'\b|\b'+name+r'\b[^.;]{0,20}\b(beginner|new|regular|experienced)\b)',text)
        if found:experience[sport]={'beginner':'new','new':'new','regular':'regular','experienced':'experienced'}[found[1] or found[2]]
    if experience:put('experience',experience)
    equipment=list(answers.get('equipment',[]))
    for word,key in [('bodyweight','bodyweight'),('body weight','bodyweight'),('pull-up','pull_up_bar'),('pullup','pull_up_bar'),('pull up','pull_up_bar'),('dip','dip_bars'),('bike','bike'),('trainer','trainer'),('dumbbell','dumbbells')]:
        if word in text and key not in equipment:equipment.append(key)
    if 'cycling' in answers.get('sports',[]) and ('indoor' in text or 'outdoor' in text):
        if 'bike' not in equipment:equipment.append('bike')
    if equipment:put('equipment',equipment)
    if re.search(r'\bno pain\b|\bno (?:pain or )?illness\b|\bwithout pain\b',text):put('pain_or_illness',False)
    if re.search(r'\bno restrictions\b|\bno (?:other )?limitations\b',text):put('restrictions_notes','');put('blocked_sports',[]);put('blocked_movements',[])
    if re.search(r'\b(?:have|use|with|yes)[^.;]{0,25}\b(?:hr|heart.rate) (?:sensor|monitor)\b|\b(?:hr|heart.rate) (?:sensor|monitor)[^.;]{0,15}\byes\b',text):brief['calibration']['hr_sensor']=True
    if 'power' in text or state.get('awaiting')=='power_access':
        if 'indoor' in text and 'outdoor' in text or re.search(r'\bboth\b',text):brief['calibration']['power_access']='both'
        elif 'indoor' in text:brief['calibration']['power_access']='indoor'
        elif 'outdoor' in text:brief['calibration']['power_access']='outdoor'
    budget={}
    for sport,pattern in [('cycling','cycling'),('strength','strength'),('running','running')]:
        match=re.search(r'\b'+pattern+r'\s*(?:weekly(?: budget)?|budget)?\s*(?:is|of|:|=)?\s*(\d+)\s*(?:min|minutes)\s*(?:per week|weekly)?',text)
        if match and re.search(r'\b(?:weekly|per week|budget)\b',text):budget[sport]=int(match[1])
    if budget:put('weekly_caps',{sport:{'max_minutes':minutes} for sport,minutes in budget.items()})
    for sport in SPORT_CATALOG:
        cap_match=re.search(r'\b'+sport+r'\b[^.;]{0,25}?(\d+)\s*(?:-|to)\s*(\d+)\s*(hours?|minutes?)[^.;]{0,15}\b(?:week|weekly)\b',text)
        if cap_match:
            factor=60 if cap_match[3].startswith('hour') else 1
            lower,upper=int(cap_match[1])*factor,int(cap_match[2])*factor
            state['answers']=merge_answers(state['answers'],{'weekly_caps':{sport:{'max_minutes':upper,'range_min_minutes':lower}}});answers=state['answers']
        if re.search(r'\b(?:remove|clear|no)\s+(?:the\s+)?'+sport+r'\s+(?:weekly\s+)?cap\b',text):
            state['answers']=merge_answers(state['answers'],{'weekly_caps':{sport:None}});answers=state['answers']

    for pattern,key in [(r'(\d+)\s*(?:comfortable\s+)?pull[ -]?ups?','pull_up_reps'),(r'(\d+)\s*(?:comfortable\s+)?dips?','dip_reps')]:
        match=re.search(pattern,text)
        if match:brief['strength_capacity'][key]=int(match[1])
    for name,key in [(r'pull[ -]?ups?','pull_up_reps'),(r'dips?','dip_reps')]:
        match=re.search(r'\b'+name+r'\s*(?:(?:i\s+)?(?:can\s+)?do\s*|:\s*|about\s*)?(\d+)\b',text)
        if match:brief['strength_capacity'][key]=int(match[1])
    for sport in answers.get('sports',[]):
        match=re.search(r'\b'+re.escape(sport)+r'\s*(?:for|:)?\s*(\d+)\s*(?:minutes?|mins?)\b',text)
        if match:partial.setdefault('sport_minutes',{})[sport]=int(match[1])
    if 'strength' in answers.get('sports',[]) and ('secondary strength' in text or 'strength secondary' in text or 'cycling support' in text or re.search(r'strength[^.;\n]{0,100}(?:cycling|core)',text)):brief['strength_role']='secondary';brief['strength_purpose']='cycling_support'
    if 'endurance' in text and 'priority' in text:put('priority','endurance')
    if partial.get('sport_days'):brief['sport_days']=partial['sport_days']
    state['answers']=validate_answers(answers);state['brief']=validate_brief(brief);_canonical_schedule(state)


def _canonical_schedule(state):
    """Translate retained user weekday facts without clocks or inventing rest."""
    partial=state['partial'];limit=partial.get('weekday_minutes') or (partial.get('weekday_minutes_range') or [None])[-1]
    if not limit or not partial.get('sport_days'):return
    signature=encoded({key:partial.get(key) for key in ('sport_days','rest_days','weekday_minutes','weekday_minutes_range','friday_minutes','sport_minutes')})
    if state.get('schedule_partial_signature')==signature:return
    rows=[];rest=set(partial.get('rest_days',[]));days=sorted({day for values in partial['sport_days'].values() for day in values}|rest)
    for day in days:
        if day in rest:
            rows.append({'weekday':day,'mode':'rest','activities':[],'total_limit_minutes':None});continue
        slots=[]
        for sport,values in partial['sport_days'].items():
            if day not in values:continue
            maximum=partial.get('sport_minutes',{}).get(sport,partial.get('friday_minutes',limit) if sport=='cycling' and day==4 else limit)
            slots.append({'slot_id':f'user-{day}-{sport}','sport':sport,'min_minutes':(partial.get('weekday_minutes_range') or [None])[0] if maximum==limit else None,'max_minutes':maximum})
        if slots:rows.append({'weekday':day,'mode':'training','activities':slots,'total_limit_minutes':None})
    state['answers']=merge_answers(state['answers'],{'week_schedule':rows})
    state['answers']['sports']=list(dict.fromkeys(state['answers'].get('sports',[])+[slot['sport'] for row in rows for slot in row['activities']]))
    state['schedule_partial_signature']=signature


def turn(message,history=None,tz='UTC',path=None,now=None,structured_facts=None):
    now=now or datetime.now(timezone.utc);today=now.astimezone(timezone_info(tz)).date();week=today+timedelta(days=(7-today.weekday())%7)
    saved=read_brief(path);pending=read(path);state=pending['state'] or {'brief':saved['brief'],'answers':{},'partial':{},'provenance':{},'processed':[]}
    state['changes']=[];state['clarifications']=[];state.pop('range_acknowledgment',None)
    messages=[item['content'] for item in (history or []) if item.get('role')=='user' and isinstance(item.get('content'),str)]
    for text in messages:
        digest=hashlib.sha256(text.encode()).hexdigest()
        if digest in state['processed']:continue
        _extract(state,text,today,week);state['processed'].append(digest)
    # Identical replies can answer different questions (e.g. "about 5" for
    # pull-ups, then dips). Only historical replay is deduplicated.
    _contextual_reply(state,message)
    _extract(state,message,today,week)
    digest=hashlib.sha256(message.encode()).hexdigest()
    if digest not in state['processed']:state['processed'].append(digest)
    if structured_facts:
        candidate_state=json.loads(encoded(state))
        try:
            merge_structured(candidate_state,structured_facts,message);state=candidate_state
            _canonical_schedule(state)
        except ValueError as error:state['clarifications'].append(str(error))
    with connect(path) as c:
        context=_context(c,now,state['answers']);history_evidence=_history(c,today,context['answers'].get('sports',[]));ftp=resolve(c,today)
    for sport,evidence in history_evidence.items():
        if evidence['experience'] and sport not in context['answers'].get('experience',{}):
            state['answers'].setdefault('experience',{})[sport]=evidence['experience'];state['provenance']['experience.'+sport]=evidence
    if state.get('awaiting')=='ftp_authorization' and re.fullmatch(r'\s*(?:yes|yes please|sure|okay|ok|go ahead|use it|use the stored ftp|use garmin ftp|i approve)[.! ]*',message,re.I):
        if ftp.get('watts'):
            state['brief']['ftp_selection']='garmin';state['brief']['ftp_watts']=ftp['watts'];state['brief']['calibration']['ftp_confirmed_on']=ftp['measurement_date'];state['brief']['calibration']['ftp_source']=ftp['source'];state['brief']['ftp_authorization']={'authorized_on':today.isoformat(),'watts':ftp['watts'],'measurement_date':ftp['measurement_date'],'source':ftp['source']}
    if state['partial'].get('sport_days'):state['brief']['sport_days']=state['partial']['sport_days']
    requested=state['partial'].get('start_date')
    if requested:
        if requested in ('today','tomorrow'):requested=(today+timedelta(days=requested=='tomorrow')).isoformat();state['partial']['start_date']=requested
        state['brief']['program_start']=requested;week=date.fromisoformat(requested)
    candidate=preview(state['brief'],week,tz,path,now,candidate_answers=state['answers'])
    effective=candidate['brief'];question=None;awaiting=None
    if not effective['duration_confirmed']:question=candidate['questions'][0];awaiting='duration'
    elif not effective['goal']:question='What is your primary training goal?';awaiting='goal'
    elif ftp.get('watts') and not state['partial'].get('ftp_declined') and not effective.get('ftp_authorization') and effective.get('ftp_watts') is None:
        question=f"Your stored cycling FTP is {ftp['watts']:g} W, recorded {ftp.get('measurement_date') or 'date unknown'} ({ftp['status']}). May I use it as a reference? An old measurement keeps its original date and effort targets until freshly calibrated.";awaiting='ftp_authorization'
    elif effective['calibration']['power_access']=='unknown' and effective.get('ftp_watts'):question='Can you use power indoors, outdoors, both, or neither?';awaiting='power_access'
    else:
        with connect(path) as c:effective_context=_context(c,now,state['answers'])
        capacity=effective.get('strength_capacity',{})
        equipment=effective_context['answers'].get('equipment',[])
        if state['clarifications']:question=state['clarifications'][0];awaiting=state.get('awaiting')
        elif 'strength' in effective_context['answers'].get('sports',[]) and not effective.get('strength_role'):
            question='Should strength mainly support your cycling and core, or be a main goal itself?';awaiting='strength_role'
        elif 'pull_up_bar' in equipment and 'strength' in effective_context['answers'].get('sports',[]) and 'pull_up_reps' not in capacity:
            question='About how many comfortable pull-ups can you do? Zero is fine.';awaiting='pull_up_reps'
        elif 'dip_bars' in equipment and 'strength' in effective_context['answers'].get('sports',[]) and 'dip_reps' not in capacity:
            question='About how many comfortable dips can you do? Zero is fine.';awaiting='dip_reps'
        elif effective_context['questions']:
            field=effective_context['questions'][0]['field'];awaiting=field;question=effective_context['questions'][0]['question']
            missing_sport=next((sport for sport in effective_context['answers'].get('sports',[]) if sport not in effective_context['answers'].get(field,{})),None) if field in ('experience','weekly_minutes') else None
            if field=='experience' and missing_sport:awaiting='experience:'+missing_sport;question=f'Are you new to {missing_sport}, or do you practise it regularly?'
            elif field=='weekly_minutes':question=None;awaiting=None
            elif field in ('blocked_sports','blocked_movements','restrictions_notes','pain_or_illness'):awaiting='restrictions';question='Any pain, illness, sports or movements to avoid, or other training restrictions? Say “none” if there are none.'
        elif candidate['questions']:question=candidate['questions'][0];awaiting='preferences'
    if question and awaiting==state.get('awaiting') and not state['clarifications']:
        examples={'pull_up_reps':'I could not interpret that as a pull-up count. Give an approximate number from 0 to 50, for example “about 5” or “zero”.',
                  'dip_reps':'I could not interpret that as a dip count. Give an approximate number from 0 to 50, for example “about 5” or “zero”.',
                  'duration':'I need one plan length between 4 and 24 weeks. For example, reply “16 weeks”.',
                  'ftp_authorization':f'I could not tell whether you agreed. May I use your stored FTP ({ftp.get("watts")} W) as a reference? Reply “yes” or “no”.',
                  'restrictions':'I could not tell whether you have restrictions. Describe any pain, illness or movements to avoid, or reply “none”.'}
        if awaiting in examples:question=examples[awaiting]
        elif awaiting and awaiting.startswith('weekly_minutes:'):
            question=f'For {awaiting.split(":")[1]}, roughly how much total time per week is manageable—for example, “about 5 hours” or “90 minutes”?'
    state['awaiting']=awaiting;state['awaiting_unit']='hours' if awaiting and awaiting.startswith('weekly_minutes:') and not state['clarifications'] else state.get('awaiting_unit');state['next_question']=question;state['history_evidence']=history_evidence;state['saved_preference_revision']=context['revision']
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');current=c.execute('SELECT revision FROM training_questionnaire WHERE id=1').fetchone()
        if (current[0] if current else 0)!=pending['revision']:raise ValueError('Trainer answers changed; retry your last answer')
        c.execute('INSERT INTO training_questionnaire(id,revision,state_json) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state_json=excluded.state_json,updated_at=CURRENT_TIMESTAMP',(pending['revision']+1,encoded(state)))
    if question:
        if requested and state['provenance'].get('program_start',{}).get('text')==message:question='The plan start date is now '+requested+'. '+question
        candidate={**candidate,'status':'needs_input','questions':[question],'remaining_questions':list(dict.fromkeys(q for q in candidate['questions'] if q!=question))}
    return {'tool':'preview_training_plan',**candidate,'questionnaire_revision':pending['revision']+1,'questionnaire':{'awaiting':awaiting,'partial':state['partial'],'provenance':state['provenance'],'history_evidence':history_evidence,'changes':state['changes']},'recognized':[state['range_acknowledgment']] if state.get('range_acknowledgment') else [],'setup_status':'candidate' if state['answers'] else 'saved_preferences','next_action':'answer_question' if question else 'review_and_activate','saved_plan':False}


def merge_structured(state,facts,message):
    """Schema-validated semantic extraction, backed by exact quotes from the current user only."""
    if not isinstance(facts,list) or len(facts)>30:raise ValueError('Invalid trainer facts')
    for fact in facts:
        if not isinstance(fact,dict) or set(fact)!={'path','value','quote'} or not isinstance(fact['quote'],str) or not fact['quote'].strip() or fact['quote'] not in message:raise ValueError('Trainer facts need an exact user quote')
        path=fact['path'];value=fact['value'];quote=fact['quote']
        if path.startswith('answers.'):
            field=path.split('.',1)[1];patch=validate_answers({field:value})
            if field=='weekly_minutes' and any(str(number) not in quote for number in value.values()):raise ValueError('Weekly budget must be explicitly provided')
            if field=='availability' and any((slot.get('start_time') is not None and slot['start_time'] not in quote) or str(slot['minutes']) not in quote for slot in value):raise ValueError('Exact availability must be explicitly provided')
            old=state['answers'].get(field)
            if old is not None and old!=patch[field]:state['changes'].append({'field':field,'previous':old,'value':patch[field]})
            if field in ('experience','weekly_minutes'):
                patch[field]={**state['answers'].get(field,{}),**patch[field]}
            state['answers']=merge_answers(state['answers'],patch)
            if field=='week_schedule':
                for row in value:
                    day=row['weekday']
                    if row.get('mode')=='rest':
                        state['partial']['rest_days']=sorted(set(state['partial'].get('rest_days',[]))|{day})
                        for sport,days in state['partial'].get('sport_days',{}).items():state['partial']['sport_days'][sport]=[d for d in days if d!=day]
                    elif 'activities' in row:
                        for slot in row['activities']:
                            state['partial'].setdefault('sport_days',{}).setdefault(slot['sport'],[])
                            if day not in state['partial']['sport_days'][slot['sport']]:state['partial']['sport_days'][slot['sport']].append(day)
                state['schedule_partial_signature']=encoded({key:state['partial'].get(key) for key in ('sport_days','rest_days','weekday_minutes','weekday_minutes_range','friday_minutes','sport_minutes')})
        elif path.startswith('brief.'):
            field=path.split('.',1)[1]
            if field in ('ftp_watts','ftp_authorization','ftp_selection','program_start'):raise ValueError('FTP selection and authorization use their dedicated reviewed flow')
            if field=='calibration':
                if not isinstance(value,dict):raise ValueError('Calibration must be an object')
                if value.get('ftp_confirmed_on') and (value['ftp_confirmed_on'] not in quote or not re.search(r'\b(?:measured|tested)\b',quote,re.I)):raise ValueError('FTP measurement date requires explicit measurement evidence')
                value={**state['brief'].get('calibration',{}),**value}
            state['brief']=validate_brief({**state['brief'],field:value})
        elif path.startswith('partial.'):
            field=path.split('.',1)[1]
            if field not in ('sport_days','rest_days','weekday_minutes_range','friday_minutes','weekday_minutes','start_date','time_preference'):raise ValueError('Unsupported partial training fact')
            if field=='sport_days':validate_brief({**DEFAULT,'sport_days':value})
            elif field=='rest_days':validate_brief({**DEFAULT,'sport_days':{'cycling':value}})
            elif field=='weekday_minutes_range':
                if not isinstance(value,list) or len(value)!=2 or any(type(n) is not int or not 15<=n<=720 for n in value) or value[0]>value[1]:raise ValueError('Invalid session range')
            elif field in ('weekday_minutes','friday_minutes'):
                if type(value) is not int or not 15<=value<=720:raise ValueError('Invalid session minutes')
            elif field=='time_preference':
                if value not in ('morning','afternoon','evening','anytime'):raise ValueError('Invalid broad time preference')
            elif field=='start_date':
                if value not in ('today','tomorrow'):date.fromisoformat(value)
            elif not isinstance(value,str) or not re.fullmatch(r'\d{2}:\d{2}',value):raise ValueError('Invalid start time')
            state['partial'][field]={**state['partial'].get(field,{}),**value} if field=='sport_days' else value
        else:raise ValueError('Unsupported trainer fact path')
        state['provenance'][path]={'source':'user_message_structured','quote':quote}


def extract_structured(message,path=None):
    """Ask the selected model for typed facts; no proposed values become saved settings here."""
    from .ai_providers import active_provider
    instructions='''Extract only explicit facts from this user message as JSON {"facts":[{"path":"answers.experience","value":{"strength":"new"},"quote":"exact user substring"}]}. Return facts:[] when there are no new facts. Each quote MUST be a verbatim nonempty substring of the user message. Do not infer absent times, manageable weekly volume, equipment, injury status, measurement dates or abilities. Allowed answers fields: sports (cycling,running,strength,hiking,other), priority (general,endurance,strength,mixed), experience (sport:new,regular,experienced), equipment (bike,trainer,bodyweight,dumbbells,bands,gym,barbell,mat,pull_up_bar,dip_bars), pain_or_illness boolean, blocked_sports,blocked_movements,restrictions_notes,weekly_caps (optional sport:{max_minutes,range_min_minutes?}, null removes cap),week_schedule (partial weekday rows {weekday,mode:rest|training,total_limit_minutes:null|minutes,activities:[{slot_id,sport,label?,min_minutes:null|minutes,max_minutes}]} with up to3 stable slots; preserve siblings and explicit rest; no clocks). Weekly total is never required. Allowed brief fields: goal (ftp,endurance,race,general),goal_sport,strength_role(primary,secondary),strength_purpose(general_fitness,cycling_support,strength_development),strength_capacity(pull_up_reps,dip_reps),calibration(power_access:unknown,none,indoor,outdoor,both;hr_sensor:boolean). Short replies answer the pending question; approximate counts such as about five are valid. Never request clock times for planning. Partial fields: time_preference (morning,afternoon,evening,anytime; optional, never infer an exact clock), sport_days (sport:list weekdays Monday0..Sunday6),rest_days,weekday_minutes_range [minimum,maximum],weekday_minutes,friday_minutes,start_date (today,tomorrow,or explicit YYYY-MM-DD). Distinguish program start DATE from session start CLOCK time. Ranges remain ranges. An authorization to use a saved FTP is NOT a new FTP measurement and never changes calibration dates. Never extract assistant statements. Do not activate or save a plan.'''
    try:
        text=active_provider(path).generate(message,instructions,timeout_seconds=15).strip()
        if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
        result=json.loads(text)
        return result.get('facts',[]) if isinstance(result,dict) else []
    except Exception:
        return []


def candidate_snapshot(path=None,tz='UTC',now=None):
    now=now or datetime.now(timezone.utc);today=now.astimezone(timezone_info(tz)).date()
    pending=read(path);saved=read_brief(path);state=pending['state'] or {}
    brief=state.get('brief') or saved['brief'];answers=state.get('answers',{})
    week=brief.get('program_start') or (today+timedelta(days=(7-today.weekday())%7)).isoformat()
    return {'brief':brief,'answers':answers,'candidate_answers':answers,'week_start':week,'questionnaire_revision':pending['revision'],'partial':state.get('partial',{}),'awaiting':state.get('awaiting'),'next_question':state.get('next_question'),'saved_brief_revision':saved['revision']}
