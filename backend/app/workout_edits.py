"""Explicit block edits for reviewed chat proposals; never writes or infers load."""
import copy
import re
from .training_prescriptions import validate_workout, text as target_text


class EditError(ValueError):
    def __init__(self, message, status='needs_input'):
        super().__init__(message)
        self.status = status


def widening_requested(message):
    return bool(re.search(r'\b(widen|wide(?:r)?|broaden|broader)\b',message,re.I) and re.search(r'\b(power|watts?|target)\b',message,re.I) and re.search(r'\b(range|gap|band|tolerance)\b',message,re.I) and not re.search(r"\b(don't|do not|never)\b",message,re.I))


def widen_power_range(definition,message):
    if re.search(r'\b(step|block|interval|recovery)\s+\d',message,re.I):
        raise EditError('To widen ranges, request the whole session; individual block range changes need explicit watt bounds.')
    if re.search(r'\b(change|reduce|increase|set|replace)\b',message,re.I):
        raise EditError('Request widening the power range separately from other changes so the ERG midpoint is preserved.')
    percent=re.search(r'\bby\s+(\d+(?:\.\d+)?)\s*%',message,re.I)
    if re.search(r'\d',message) and not percent:raise EditError('Specify widening by a percentage, for example: widen the power range by 20%.')
    factor=1+float(percent[1])/100 if percent else 1.25
    if not 1<factor<=2:raise EditError('Widen the current range by more than 0% and at most 100%.')
    result=copy.deepcopy(definition);changed=0
    def visit(steps):
        nonlocal changed
        for step in steps:
            if step.get('steps'):visit(step['steps'])
            t=step.get('target',{})
            if t.get('type')!='power':continue
            mid=(t['lower']+t['upper'])/2;half=(t['upper']-t['lower'])/2*factor
            if half<=0 or mid-half<=0:raise EditError('This target cannot be widened safely while preserving its midpoint.')
            t.update(lower=round(mid-half,2),upper=round(mid+half,2))
            step['effort']=target_text(t)
            refs=step.get('power_reference_fractions')
            if refs:
                center=(refs['lower']+refs['upper'])/2;width=(refs['upper']-refs['lower'])/2*factor
                refs.update(lower=center-width,upper=center+width)
            changed+=1
    visit(result.get('steps',[]))
    if not changed:raise EditError('This session has no numeric power ranges to widen.')
    summary=[f'Widened power ranges by {(factor-1)*100:g}%; ERG midpoints, durations and repetitions are preserved.']
    result.update(user_adjusted=True,edit_summary=summary)
    result['effort_target']={'method':'power','description':'; '.join(f"{s.get('name','Step')}: {s.get('effort','')}" for s in result['steps'])}
    return validate_workout(result),summary


def interval_edit_requested(message):
    """Identify the edited interval clause, not an endurance clause elsewhere."""
    for clause in re.split(r'[.;\n]|\b(?:and|but|while)\b',message.lower()):
        if re.match(r'\s*\d+\s*[x×]\s*\d',clause):return True
        if not re.search(r'\b(?:change|set|use|make|increase|add|replace|progress)\b',clause):continue
        if re.search(r'\d+\s*[x×]\s*\d|\b(?:reps?|repetitions?|interval count|work intervals?|work repetitions?)\b',clause):return True
    return False


def requested(message):
    if interval_edit_requested(message):return True
    if widening_requested(message):return True
    if re.search(r'\b(building blocks?|training blocks?|phases?|weeks?)\b',message,re.I) and not re.search(r'\b(work interval|work block|step)\s+\d',message,re.I):return False
    return bool(re.search(r'\b(set|change|reduce|increase|make|use|replace)\b', message, re.I) and
                re.search(r'\b(reps?|repetitions?|sets?|intervals?|recoveries|recovery between|work target|power target|heart rate target|effort target|load|rest)\b|\b(?:step|block)\s+\d|\d+\s*[x×]\s*\d', message, re.I))


def parse(message):
    text = message.lower().replace('–', '-').replace('×', 'x')
    if re.search(r"\b(don't|do not|without changing|leave unchanged|no changes)\b",text):raise EditError('No change prepared. State the values you want changed explicitly.')
    values = {}
    def clock(value):
        parts=[int(p) for p in value.split(':')]
        return sum(n*60**i for i,n in enumerate(reversed(parts)))
    # Workout clocks are durations, not a new target or an ambiguous repetition.
    combo_clock=re.search(r'\b(\d+)\s*x\s*(\d+:[0-5]\d(?::[0-5]\d)?)\b',text)
    combo = re.search(r'\b(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?)\b', text)
    if combo_clock:
        values.update(count=int(combo_clock[1]),work_seconds=clock(combo_clock[2]))
    elif combo:
        values['count'] = int(combo[1])
        values['work_seconds'] = float(combo[2]) * (60 if combo[3].startswith('m') else 1)
    elif re.search(r'\b\d+\s*x',text):raise EditError('Specify intervals as a positive count × work time with seconds or minutes.')
    count = re.search(r'\b(?:to|use|make|with)\s+(\d+)\s+(?:work\s+)?(?:intervals?|reps?|repetitions?)\b|\b(?:reps?|repetitions?|interval count)\s+(?:to\s+)?(\d+)\b', text)
    if count: values['count'] = int(count[1] or count[2])
    work_clock=re.search(r'\b(\d+:[0-5]\d(?::[0-5]\d)?)\s*(?:vo[₂2](?:\s*max)?\s+)?work\s+(?:repetition|interval|effort)\b',text)
    if work_clock:values['work_seconds']=clock(work_clock[1])
    recovery_clock=re.search(r'\b(\d+:[0-5]\d(?::[0-5]\d)?)\s*(?:easy\s+)?recover(?:y|ies)\b|\brecovery(?:\s+between\s+(?:intervals|efforts))?\s+(?:to\s+)?(\d+:[0-5]\d(?::[0-5]\d)?)\b',text)
    if recovery_clock:values['recovery_seconds']=clock(recovery_clock[1] or recovery_clock[2])
    for key, noun in [('work_seconds', r'(?:work intervals?|work blocks?|work duration|each interval)'), ('recovery_seconds', r'(?:recovery between intervals|recoveries|recovery|rest)')]:
        match = re.search(r'\b' + noun + r'\s+(?:(?:duration|time)\s+)?(?:to\s+)?(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?)\b', text)
        if match: values[key] = float(match[1]) * (60 if match[2].startswith('m') else 1)
    if re.search(r'\b(?:work intervals?|work blocks?|work duration|each interval)\s+(?:(?:duration|time)\s+)?to\b',text) and 'work_seconds' not in values:raise EditError('Specify work time in seconds or minutes; no partial edit was prepared.')
    sets = re.search(r'\b(?:to|use|make|with)\s+(\d+)\s+sets?\b|\bsets?\s+(?:to\s+)?(\d+)\b', text)
    if sets: values['sets'] = int(sets[1] or sets[2])
    load = re.search(r'\b(?:load|weight)\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*kg\b', text)
    if load: values['load'] = float(load[1])
    target = re.search(r'\b(?:work target|power target|heart rate target|effort target)\s+(?:to\s+)?(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*(watts?|w|bpm|rpe)\b', text)
    if target:
        unit = target[3]
        kind = 'power' if unit in ('w', 'watt', 'watts') else 'heart_rate' if unit == 'bpm' else 'perceived_effort'
        low, high = float(target[1]), float(target[2] or target[1])
        limit = {'power': (1, 2500), 'heart_rate': (30, 230), 'perceived_effort': (1, 10)}[kind]
        if not limit[0] <= low <= high <= limit[1]: raise EditError('Use an ordered, valid target range with W, bpm or RPE units.')
        values['target'] = {'type': kind, 'lower': low, 'upper': high, 'unit': {'power':'W','heart_rate':'bpm','perceived_effort':'RPE / 10'}[kind], 'source':'user_requested'}
    if not values: raise EditError('Specify the interval count, work/recovery time, work target with units, or the strength exercise and its sets, reps, rest or load in kg. For example: change Friday cycling to 2 x 4 minutes, recovery to 3 minutes.')
    # Never apply just one part of a request whose other field was not understood.
    for noun, key in [(r'load|weight', 'load'), (r'power target|heart rate target|effort target|work target', 'target'), (r'sets', 'sets'), (r'recoveries|recovery between intervals|recovery|rest', 'recovery_seconds')]:
        if re.search(r'\b(?:' + noun + r')\b', text) and key not in values: raise EditError('Specify an exact value and units for every requested field; no partial change has been prepared.')
    if 'count' in values and not 1 <= values['count'] <= 20: raise EditError('Choose 1–20 repetitions or intervals.')
    if 'sets' in values and not 1 <= values['sets'] <= 10: raise EditError('Choose 1–10 sets.')
    for key in ('work_seconds','recovery_seconds'):
        if key in values and not (1 if key == 'work_seconds' else 0) <= values[key] <= 3600: raise EditError('Use positive work time and 0–60 minutes of recovery.')
    if 'load' in values and not 0 <= values['load'] <= 1000: raise EditError('Use an explicit load in kg between 0 and 1,000.')
    return values


def work_step(step):
    name = step.get('name', '').lower()
    return any(key in name for key in ('work lap', 'sprint', 'anaerobic effort', 'work interval'))


def work_seconds(definition):
    return sum(s['duration_seconds'] * s.get('repetitions', 1) for s in definition.get('steps', []) if work_step(s))


def duration_label(seconds):
    whole=int(seconds);tail=f'{whole%60:02d}'
    if seconds!=whole:tail+=f'{seconds-whole:.3f}'[1:].rstrip('0')
    return f'{whole//3600}:{whole//60%60:02d}:{tail}' if whole>=3600 else f'{whole//60}:{tail}'


def expanded_steps(steps,path=(),depth=0):
    """Flatten explicitly repeated groups without inventing targets or rests."""
    if depth>5 or not isinstance(steps,list):raise EditError('Use at most six levels of explicitly timed blocks.')
    result=[]
    for index,step in enumerate(steps,1):
        if not isinstance(step,dict):raise EditError('Each block must contain explicit timed steps.')
        here=path+(index,);repeats=step.get('repetitions',1)
        if type(repeats) is not int or not 1<=repeats<=50:raise EditError('Use 1–50 explicit repetitions per block.')
        if 'steps' in step:
            children=expanded_steps(step['steps'],here,depth+1)
            for _ in range(repeats):result.extend(copy.deepcopy(children))
        else:
            leaf=copy.deepcopy(step);leaf['_edit_path']='.'.join(map(str,here));result.append(leaf)
        if len(result)>100:raise EditError('The expanded workout exceeds 100 steps; review a smaller structure.')
    return result


def targeted_edit(definition,message,selector,policy,allow_increase,manual_override=False):
    noun,path=selector[1].lower(),selector[2]
    body=message[:selector.start()]+('recovery' if noun.startswith('recovery') else 'work duration')+message[selector.end():]
    values=parse(body)
    if set(values)&{'count','sets','load'}:raise EditError('Target one step’s duration or current-method target; repetition/group-count changes need a separate reviewed structure.')
    result=copy.deepcopy(definition);steps=expanded_steps(definition.get('steps',[]))
    try:validate_workout({**definition,'steps':steps})
    except (ValueError,KeyError,TypeError):raise EditError('The source blocks need a valid timed structure and targets before editing.') from None
    if noun in ('interval','work interval','work block'):
        work=[s for s in steps if work_step(s)]
        selected=[work[int(path)-1]] if '.' not in path and 1<=int(path)<=len(work) else []
    elif noun.startswith('recovery'):
        recoveries=[s for s in steps if s.get('name','').lower().startswith('recovery')]
        selected=[recoveries[int(path)-1]] if '.' not in path and 1<=int(path)<=len(recoveries) else []
    else:selected=[s for s in steps if s['_edit_path']==path]
    if not selected:raise EditError('That step does not exist. Number work intervals or recoveries separately, or use a step path such as step 2.1 for a nested block.')
    if 'recovery_seconds' in values and 'work_seconds' in values:raise EditError('Edit one step duration at a time; no partial change was prepared.')
    old_work=work_seconds({'steps':steps});changed=False;target_increase=False;delta=0
    for step in selected:
        old=copy.deepcopy(step);old_target=step.get('target') or {}
        if 'target' in values:
            target=values['target']
            if target['type']!=old_target.get('type') or target['unit']!=old_target.get('unit'):raise EditError('Keep the current target method and units; review a calibration change separately.')
            target_increase|=target['lower']>old_target['lower'] or target['upper']>old_target['upper']
            if target['lower']>old_target['lower']*1.05 or target['upper']>old_target['upper']*1.05:raise EditError('A target increase over 5% needs a replacement-week review.','not_recommended')
            if any(target[k]!=old_target.get(k) for k in ('type','unit','lower','upper')):
                step.update(target=copy.deepcopy(target),effort=target_text(target),power_reference_fractions=None)
        seconds=values.get('work_seconds',values.get('recovery_seconds'))
        if seconds is not None:
            name=step.get('name','').lower()
            recovery=step.get('name','').lower().startswith('recovery') or step.get('type')=='recovery'
            if not work_step(step) and not recovery and not any(label in name for label in ('warm','cool','steady endurance')):raise EditError('This block has no recognized work/recovery role. Review its structure before changing its duration.')
            if any(label in name for label in ('warm','cool')) and seconds<step['duration_seconds'] and old_work>0:raise EditError('Keep the prescribed warm-up and cool-down for quality work; shortening them needs a replacement-session review.','not_recommended')
            if 'recovery_seconds' in values and not recovery:raise EditError('Select the recovery step you want to change.')
            if recovery and seconds<step['duration_seconds']:raise EditError('Shortening this recovery needs a separate progression review.','not_recommended')
            delta+=(seconds-step['duration_seconds'])*step.get('repetitions',1);step['duration_seconds']=seconds
        changed|=step!=old
    if not changed:raise EditError('Those values already match the saved step.')
    new_work=work_seconds({'steps':steps})
    warnings=[]
    if new_work>old_work*1.2:
        if not manual_override:raise EditError('This exceeds the small-edit work-time limit; review a replacement week.','not_recommended')
        warnings.append(f'Warning: hard interval work increases by {(new_work/old_work-1)*100:.1f}%, above the planner’s 20% limit. This may be too much; Save accepts your explicit manual override.')
    if (new_work>old_work or target_increase) and (not allow_increase or policy['level']!='normal' or not policy['quality_allowed']):
        if not manual_override or policy['level']=='hold':raise EditError('Increasing demand needs two tolerated completed sessions and recovery clearance.','not_recommended')
        warnings.append('Warning: recorded tolerance, the training block or recovery guidance does not support automatic progression; this is a manual edit. '+ '; '.join(policy.get('reasons',[])))
    filler=next((s for s in steps if s.get('name')=='Steady endurance' and not any(s is item for item in selected)),None)
    if delta:
        if filler is None or filler['duration_seconds']*filler.get('repetitions',1)-delta<0:raise EditError('The change cannot preserve total duration with the available steady riding. Review a replacement session.')
        filler['duration_seconds']-=delta/filler.get('repetitions',1)
    result['steps']=[{k:v for k,v in s.items() if k!='_edit_path'} for s in steps if s['duration_seconds']>0]
    validate_workout(result)
    summary=warnings+[f'{noun.title()} {path}: '+('; '.join(f"{s.get('name','Step')} · {duration_label(s['duration_seconds'])} · {target_text(s['target'])}" for s in selected))+'. Other blocks and total duration are preserved.']
    result.update(user_adjusted=True,variant_id=None,variant_label=None,edit_summary=summary)
    result['effort_target']={'method':result['steps'][0]['target']['type'],'description':'; '.join(f"{s.get('name','Step')}: {duration_label(s['duration_seconds'])} · {s['effort']}" for s in result['steps'])}
    return result,summary


def edit(definition, message, policy, allow_increase=False, *, manual_override=False):
    if widening_requested(message):return widen_power_range(definition,message)
    selector=re.search(r'\b(work interval|work block|interval|recovery block|recovery|step|block)\s+(\d+(?:\.\d+)*)(?![\d.])',message,re.I)
    if selector and definition['sport']!='strength':return targeted_edit(definition,message,selector,policy,allow_increase,manual_override)
    values = parse(message)
    result = copy.deepcopy(definition)
    summary = []
    if definition['sport'] == 'strength':
        if set(values) - {'count','sets','load','recovery_seconds'}: raise EditError('For strength, specify sets, repetitions, rest or load in kg.')
        if values.get('recovery_seconds',0)>1200:raise EditError('Use at most 1,200 seconds of lifting rest so the edit can be represented on Garmin.')
        normalized = message.lower().replace('_',' ').replace('-', ' ')
        matches = [e for e in result.get('exercises', []) if e['name'].lower() in normalized or e['id'].replace('_',' ') in normalized]
        if len(matches) != 1: raise EditError('Name one exact exercise: ' + ', '.join(e['name'] for e in result.get('exercises', [])) + '.')
        exercise = matches[0]
        for key, field in [('count','repetitions'),('sets','sets'),('load','load_target_kg'),('recovery_seconds','rest_seconds')]:
            if key not in values: continue
            old = exercise.get(field)
            if key == 'load' and old is None: raise EditError('Record a known load for this exercise first; an uncalibrated lifting load cannot be added through this edit.')
            if key == 'load' and values[key] > old or key in ('count','sets') and values[key] > (old or 0): raise EditError('An increase in strength dose needs recorded performance and a progression review. You can reduce these values here.', 'not_recommended')
            if key == 'recovery_seconds' and values[key] < (old or 0): raise EditError('Keep the prescribed lifting rest; shortening it requires a progression review.', 'not_recommended')
            exercise[field] = values[key]
            summary.append(f"{exercise['name']} · {field.replace('_', ' ')}: {old} → {values[key]:g}")
        from .training_notes import strength_timing
        strength_timing(result,definition.get('strength_set_policy'))
        if values.get('count', 1) > 100: raise EditError('Choose at most 100 strength repetitions.')
    else:
        if set(values) & {'sets','load'}: raise EditError('Sets and lifting loads require a named strength exercise.')
        work = [s for s in result.get('steps', []) if work_step(s)]
        if not work: raise EditError('This session has no interval blocks. Request a dated quality session first, then review its block edits.')
        if len({(s['duration_seconds'],str(s['target'])) for s in work}) != 1: raise EditError('The session has different work blocks. Whole-session interval editing does not support that structure yet; its saved blocks are unchanged.')
        old_count = sum(s.get('repetitions',1) for s in work)
        count = values.get('count',old_count)
        seconds = values.get('work_seconds',work[0]['duration_seconds'])
        recovery = [s for s in result['steps'] if s['name'].lower().startswith('recovery')]
        if recovery and len({s['duration_seconds'] for s in recovery}) > 1: raise EditError('The session has different recovery blocks. Whole-session interval editing does not support that structure yet; its saved blocks are unchanged.')
        rest = values.get('recovery_seconds',recovery[0]['duration_seconds'] if recovery else 0)
        target = values.get('target',work[0]['target'])
        old_target = work[0]['target']
        if 'target' in values and (target['type'] != old_target['type'] or target['unit'] != old_target['unit']): raise EditError('Keep the current target method and units. Changing sensors or calibration requires a reviewed plan update.')
        density_increase = bool(recovery) and count>1 and rest < recovery[0]['duration_seconds'] * min(1,seconds / work[0]['duration_seconds'])
        increase = count * seconds > work_seconds(definition) or density_increase or target['upper'] > old_target['upper'] or target['lower'] > old_target['lower']
        old_work=work_seconds(definition);new_work=count*seconds
        if new_work>old_work*1.2:
            warning=f'Hard interval work changes from {duration_label(old_work)} to {duration_label(new_work)} (+{(new_work/old_work-1)*100:.1f}%), above the planner’s 20% limit.'
            if not manual_override:raise EditError(warning+' Review an explicit manual override to proceed.','not_recommended')
            summary.append('Warning: '+warning+' This may be too much; Save accepts your explicit manual override.')
        if target['upper'] > old_target['upper'] * 1.05 or target['lower'] > old_target['lower'] * 1.05 or density_increase:raise EditError('This exceeds the target-increase limit or compresses between-effort recovery. Review a larger interval progression separately.','not_recommended')
        if increase and (not allow_increase or policy['level'] != 'normal' or not policy['quality_allowed']):
            reasons=[]
            if not allow_increase:reasons.append('automatic progression requires two recent tolerated completions of this interval category and a suitable training block')
            if policy['level']!='normal' or not policy['quality_allowed']:reasons.append('current recovery guidance recommends against increasing interval demand'+(': '+'; '.join(policy.get('reasons',[])) if policy.get('reasons') else ''))
            if not manual_override or policy['level']=='hold':
                raise EditError('Interval progression blocked: '+'; '.join(reasons)+'.','not_recommended')
            summary.append('Warning: '+ '; '.join(reason.rstrip('.') for reason in reasons)+'. This is a manual edit, not automatic progression.')
        # Preserve all warm-up/cool-down instructions and adjust only the steady filler.
        filler = [s for s in result['steps'] if s['name'] == 'Steady endurance']
        fixed = [s for s in result['steps'] if not work_step(s) and not s['name'].lower().startswith('recovery') and s not in filler]
        if any(not any(label in s['name'].lower() for label in ('warm','cool')) for s in fixed):raise EditError('The session has additional blocks that this editor cannot safely rearrange. Its saved blocks are unchanged.')
        remaining = definition['duration_minutes'] * 60 - sum(s['duration_seconds'] * s.get('repetitions',1) for s in fixed) - count * seconds - (count-1) * rest
        if remaining < 0 or remaining and not filler: raise EditError('Those blocks do not fit the saved session duration with its warm-up and cool-down. Reduce the interval count or work/recovery time.')
        blocks = []
        for index in range(count):
            block = copy.deepcopy(work[0]);block.update(name=f'Work interval {index+1}',duration_seconds=seconds,repetitions=1,target=copy.deepcopy(target),effort=target_text(target)+(' · '+target['description'] if target.get('description') else ''))
            if 'target' in values: block['power_reference_fractions'] = None
            blocks.append(block)
            if index < count-1 and rest:
                template = copy.deepcopy(recovery[0]) if recovery else None
                if template is None: raise EditError('This session has no recovery target to reuse; review a replacement session.')
                template.update(name=f'Recovery {index+1}',duration_seconds=rest,repetitions=1);blocks.append(template)
        warm = [s for s in fixed if 'warm' in s['name'].lower()]
        tail = [s for s in fixed if s not in warm]
        if remaining:
            fill = copy.deepcopy(filler[0]);fill.update(duration_seconds=remaining,repetitions=1);blocks.append(fill)
        result['steps'] = warm + blocks + tail
        validate_workout(result)
        summary.append(f'Work: {old_count} × {work[0]["duration_seconds"]:g}s → {count} × {seconds:g}s; between-block recovery: {rest:g}s; target: {target_text(target)}. Total duration stays {definition["duration_minutes"]:g} minutes.')
        result['effort_target'] = {'method':target['type'],'description':'; '.join(f"{s['name']}: {s['effort']} ({s['duration_seconds']:g}s)" for s in result['steps'])}
        result.update(variant_id=None,variant_label=None)
    if result == definition: raise EditError('Those values already match the saved session.')
    result['user_adjusted'] = True
    result['edit_summary'] = summary
    return result, summary
