"""Pinned garminconnect 0.3.17 payloads. Pure conversion; never sends a workout."""
import math
from .training import encoded
import hashlib


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def number(value, label, minimum, maximum):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise ValueError(f'{label} must be between {minimum} and {maximum}')
    return value


def workout_payload(definition, marker):
    sport=definition.get('sport')
    if sport=='strength':
        from .garmin_strength import payload
        return payload(definition,marker)
    if sport not in ('cycling','running'):
        raise ValueError('Supported sports are cycling, running and strength with explicit exercise mappings; other sports are not converted.')
    title=definition.get('title')
    if not isinstance(title,str) or not title.strip() or len(title)>120:raise ValueError('Workout title must be 1–120 characters')
    duration=number(definition.get('duration_minutes'),'Workout minutes',10,720)*60
    sport_type={'sportTypeId':2 if sport=='cycling' else 1,'sportTypeKey':sport}
    steps=[];warnings=[]
    source=definition.get('steps')
    if not isinstance(source,list) or not 1<=len(source)<=100:raise ValueError('Workout needs 1–100 explicit timed steps')
    for step in source:
        if step.get('termination','time')!='time':raise ValueError('Only explicitly timed steps can be sent in this release')
        seconds=number(step.get('duration_seconds'),'Step seconds',1,43200)
        repetitions=step.get('repetitions',1)
        if type(repetitions) is not int or not 1<=repetitions<=50:raise ValueError('Unsupported step repetitions')
        label=str(step.get('name') or step.get('type') or '').lower().replace('-','').replace('_','').replace(' ','')
        kind,key=(1,'warmup') if 'warm' in label else (2,'cooldown') if 'cool' in label else (4,'recovery') if 'recover' in label else (5,'rest') if label=='rest' else (3,'interval')
        target=step.get('target') or {};target_kind=target.get('type')
        target_type={'workoutTargetTypeId':1,'workoutTargetTypeKey':'no.target'}
        values={}
        if target_kind in ('power','heart_rate'):
            if target.get('unit')!=('W' if target_kind=='power' else 'bpm'):raise ValueError('Only prescribed watts or bpm are supported; advisory watt estimates are not targets')
            low=number(target.get('lower'),'Target lower',0,2500 if target_kind=='power' else 240)
            high=number(target.get('upper'),'Target upper',low,2500 if target_kind=='power' else 240)
            target_type={'workoutTargetTypeId':2 if target_kind=='power' else 4,'workoutTargetTypeKey':'power.zone' if target_kind=='power' else 'heart.rate.zone'}
            values={'targetValueOne':low,'targetValueTwo':high}
        elif target_kind not in (None,'perceived_effort'):raise ValueError('This target type has no verified Garmin mapping')
        else:
            warnings.append('Effort-based steps use an open Garmin target with the prescribed effort in step notes; advisory FTP estimates are not exported as watt targets.')
        effort=step.get('effort') or target.get('description')
        if not isinstance(effort,str) or not effort.strip() or len(effort)>800:raise ValueError('Every step needs clear effort guidance of at most 800 characters')
        note=(str(step.get('name') or step.get('type') or 'Step')+': '+effort)
        for _ in range(repetitions):
            steps.append({'type':'ExecutableStepDTO','stepOrder':len(steps)+1,'stepType':{'stepTypeId':kind,'stepTypeKey':key},'endCondition':{'conditionTypeId':2,'conditionTypeKey':'time'},'endConditionValue':seconds,'targetType':target_type,**values,'description':note})
    if len(steps)>100:raise ValueError('Expanded workout exceeds 100 steps')
    if abs(sum(s['endConditionValue'] for s in steps)-duration)>.01:raise ValueError('Step durations do not match the workout total; review the workout before sending')
    payload={'workoutName':title,'sportType':sport_type,'estimatedDurationInSecs':int(round(duration)),'description':f'Created by this training app. [{marker}]','workoutSegments':[{'segmentOrder':1,'sportType':sport_type,'workoutSteps':steps}]}
    from garminconnect.workout import BaseWorkout
    BaseWorkout.model_validate(payload)
    return payload,list(dict.fromkeys(warnings))


def canonical(payload):
    """Compare instructions, targets and ownership, ignoring Garmin-generated IDs."""
    segments=payload.get('workoutSegments')
    if not isinstance(segments,list) or len(segments)!=1:raise ValueError('Unexpected Garmin workout segment schema')
    steps=segments[0].get('workoutSteps')
    if not isinstance(steps,list) or not steps:raise ValueError('Garmin did not return workout steps')
    def numeric(value):return float(value) if type(value) in (int,float) else value
    result={'name':payload.get('workoutName'),'sport':payload.get('sportType',{}).get('sportTypeId'),'description':payload.get('description'),
        'steps':[{'type':s.get('type'),'order':s.get('stepOrder'),'step':s.get('stepType',{}).get('stepTypeId'),'end':s.get('endCondition',{}).get('conditionTypeId'),'seconds':numeric(s.get('endConditionValue')),'target':s.get('targetType',{}).get('workoutTargetTypeId'),'low':numeric(s.get('targetValueOne')) if s.get('targetType',{}).get('workoutTargetTypeId')!=1 else None,'high':numeric(s.get('targetValueTwo')) if s.get('targetType',{}).get('workoutTargetTypeId')!=1 else None,'description':s.get('description')} for s in steps]}

    if payload.get('sportType',{}).get('sportTypeId')==5:
        for output,step in zip(result['steps'],steps):
            output.update(condition=step.get('endCondition',{}).get('conditionTypeId'),category=step.get('category'),exercise=step.get('exerciseName'),weight=numeric(step.get('weightValue')),weight_unit=step.get('weightUnit',{}).get('unitId') if isinstance(step.get('weightUnit'),dict) else None)
    return result
