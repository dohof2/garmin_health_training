"""Explicit block edits for reviewed chat proposals; never writes or infers load."""
import copy
import re
from .training_prescriptions import validate_workout, text as target_text


class EditError(ValueError):
    def __init__(self, message, status='needs_input'):
        super().__init__(message)
        self.status = status


def requested(message):
    return bool(re.search(r'\b(set|change|reduce|increase|make|use|replace)\b', message, re.I) and
                re.search(r'\b(reps?|repetitions?|sets?|intervals?|recoveries|recovery between|work target|power target|heart rate target|effort target|load|rest)\b|\d+\s*[x×]\s*\d', message, re.I))


def parse(message):
    text = message.lower().replace('–', '-').replace('×', 'x')
    if re.search(r"\b(don't|do not|without changing|leave unchanged|no changes)\b",text):raise EditError('No change prepared. State the values you want changed explicitly.')
    values = {}
    combo = re.search(r'\b(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?)\b', text)
    if combo:
        values['count'] = int(combo[1])
        values['work_seconds'] = float(combo[2]) * (60 if combo[3].startswith('m') else 1)
    elif re.search(r'\b\d+\s*x',text):raise EditError('Specify intervals as a positive count × work time with seconds or minutes.')
    count = re.search(r'\b(?:to|use|make|with)\s+(\d+)\s+(?:work\s+)?(?:intervals?|reps?|repetitions?)\b|\b(?:reps?|repetitions?|interval count)\s+(?:to\s+)?(\d+)\b', text)
    if count: values['count'] = int(count[1] or count[2])
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


def edit(definition, message, policy, allow_increase=False):
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
        if increase and (not allow_increase or policy['level'] != 'normal' or not policy['quality_allowed']): raise EditError('This raises interval demand. Keep the current dose until two recent, completed sessions of this category have tolerated feedback and recovery permits progression.', 'not_recommended')
        if count * seconds > work_seconds(definition) * 1.2 or target['upper'] > old_target['upper'] * 1.05 or target['lower'] > old_target['lower'] * 1.05 or density_increase: raise EditError('This exceeds the app’s small-edit limit or compresses recovery. Review a replacement week for this larger progression.', 'not_recommended')
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
