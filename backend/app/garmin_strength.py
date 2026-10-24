"""Explicit strength mappings to the pinned garminconnect exercise catalog."""
from .garmin_workout_mapping import number

# Exact supported variants only. Near matches must be reviewed rather than substituted.
MAPPINGS={
 'pullup_progression':('PULL_UP','PULL_UP'),
 'dip_progression':('TRICEPS_EXTENSION','BODY_WEIGHT_DIP'),
 'dead_bug':('HIP_STABILITY','DEAD_BUG'),
 'dumbbell_row':('ROW','DUMBBELL_ROW'),
 'band_row':('BANDED_EXERCISES','ROW'),
 'dumbbell_squat':('SQUAT','DUMBBELL_SQUAT'),
 'dumbbell_press':('BENCH_PRESS','DUMBBELL_FLOOR_PRESS'),
 'machine_leg_press':('SQUAT','LEG_PRESS'),
 'barbell_squat':('SQUAT','BARBELL_BACK_SQUAT'),
 'barbell_row':('ROW','BARBELL_ROW'),
}


def payload(definition,marker):
    from garminconnect.workout import StrengthWorkout,create_strength_exercise_step,create_strength_rest_step,ExecutableStep
    from garminconnect.exercises import _RAW
    catalog={(category,exercise) for _,category,exercise in _RAW}
    title=definition.get('title')
    if not isinstance(title,str) or not 1<=len(title.strip())<=120:raise ValueError('Workout title must be 1–120 characters')
    minutes=number(definition.get('duration_minutes'),'Workout minutes',10,720)
    exercises=definition.get('exercises')
    if not isinstance(exercises,list) or not 1<=len(exercises)<=20:raise ValueError('Strength workout needs 1–20 supported exercises')
    steps=[]
    warmup=definition.get('warmup_minutes',0)
    if warmup:
        number(warmup,'Warm-up minutes',0,minutes)
        steps.append(ExecutableStep(stepOrder=1,stepType={'stepTypeId':1,'stepTypeKey':'warmup'},endCondition={'conditionTypeId':2,'conditionTypeKey':'time'},endConditionValue=warmup*60,targetType={'workoutTargetTypeId':1,'workoutTargetTypeKey':'no.target'},description='General strength warm-up; controlled comfortable movement.').model_dump(exclude_none=True))
    warnings=['Strength duration is an estimate; rep-based sets finish on repetitions. Verify exercise instructions on your Garmin device.']
    for exercise in exercises:
        mapping=MAPPINGS.get(exercise.get('id'))
        if not mapping or mapping not in catalog or 'assisted' in str(exercise.get('name','')).lower():raise ValueError('Unsupported exact Garmin exercise mapping: '+str(exercise.get('name') or exercise.get('id'))+'. Review an explicitly supported exercise before sending; it was not substituted.')
        sets=exercise.get('sets');reps=exercise.get('repetitions')
        if type(sets) is not int or not 1<=sets<=10 or type(reps) is not int or not 1<=reps<=100:raise ValueError('Strength sets/repetitions must be explicit positive integers')
        rest=number(exercise.get('rest_seconds'),'Rest seconds',0,1200)
        weight=exercise.get('load_target_kg')
        if weight is not None:number(weight,'Prescribed load kg',0,1000)
        else:warnings.append('No numeric load prescribed for '+str(exercise.get('name'))+'; choose the load using the saved effort guidance.')
        for index in range(sets):
            step=create_strength_exercise_step(mapping[0],len(steps)+1,reps,mapping[1],weight).model_dump(exclude_none=True)
            step['description']=f"{exercise.get('name')}, set {index+1}/{sets}. "+str(exercise.get('load') or 'Controlled technique; use the saved effort guidance.')
            steps.append(step)
            if rest:steps.append(create_strength_rest_step(rest,len(steps)+1).model_dump(exclude_none=True))
    if len(steps)>100:raise ValueError('Strength workout exceeds 100 expanded steps')
    sport={'sportTypeId':5,'sportTypeKey':'strength_training'}
    result={'workoutName':title,'sportType':sport,'estimatedDurationInSecs':round(minutes*60),'description':f'Created by this training app. [{marker}]','workoutSegments':[{'segmentOrder':1,'sportType':sport,'workoutSteps':steps}]}
    StrengthWorkout.model_validate(result)
    return result,warnings
