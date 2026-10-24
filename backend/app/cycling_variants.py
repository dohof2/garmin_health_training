"""Small source-backed template library; selection never establishes readiness."""
SOURCES={
 'base':'https://support.trainerroad.com/hc/trainerroad-support/articles/115005942786-understanding-power-zones',
 'threshold':'https://www.trainerroad.com/blog/threshold-intervals-for-cyclists-benefits-examples-and-tips-for-success/',
 'sprint':'https://www.trainerroad.com/blog/how-to-improve-your-maximum-sprint-power/',
 'anaerobic':'https://www.trainerroad.com/blog/anaerobic-intervals-for-cyclists-how-they-make-you-faster/'}
VARIANTS={
 'endurance':[
  {'id':'easy_continuous','label':'Comfortable continuous base','ratios':(.55,.65),'rpe':(2,3),'source':SOURCES['base']},
  {'id':'upper_endurance','label':'Upper endurance continuous base','ratios':(.65,.7),'rpe':(3,4),'source':SOURCES['base']}],
 'threshold':[
  {'id':'split_threshold','label':'Two sustained threshold blocks','intervals':(2,480,240),'source':SOURCES['threshold']},
  {'id':'sustained_threshold','label':'One sustained threshold block','intervals':(1,960,0),'source':SOURCES['threshold']}],
 'sprint':[
  {'id':'short_accelerations','label':'Four short accelerations','intervals':(4,8,240),'source':SOURCES['sprint']},
  {'id':'ten_second_sprints','label':'Three ten-second sprints','intervals':(3,10,300),'source':SOURCES['sprint']}],
 'anaerobic':[
  {'id':'thirty_second_repeats','label':'Four thirty-second efforts','intervals':(4,30,240),'source':SOURCES['anaerobic']},
  {'id':'fifteen_second_repeats','label':'Six fifteen-second efforts','intervals':(6,15,180),'source':SOURCES['anaerobic']}],
}


def options(kind):return VARIANTS.get('endurance' if kind=='base' else kind,[])


def tolerated_sessions(c, kind, today, tz):
    """Category-specific recorded completion plus explicit tolerable feedback."""
    import json
    from datetime import datetime,timedelta
    from zoneinfo import ZoneInfo
    from .ride_comparison import training_benefit
    labels={'endurance':{'AEROBIC_BASE'},'threshold':{'THRESHOLD','LACTATE_THRESHOLD'},'sprint':{'SPRINT','SPEED'},'anaerobic':{'ANAEROBIC','ANAEROBIC_CAPACITY'},'tempo':{'TEMPO'},'vo2':{'VO2MAX','VO2_MAX'}}
    rows=[]
    for row in c.execute("SELECT w.definition_json,a.id,a.started_at,f.effort,f.soreness,f.pain_or_illness,f.notes FROM training_feedback f JOIN planned_workouts w ON w.id=f.workout_id JOIN activities a ON a.id=f.activity_id WHERE w.sport='cycling' AND w.completion_status='completed' AND a.deleted_at IS NULL AND a.source_name!='synthetic_fixture' ORDER BY a.started_at"):
        definition=json.loads(row['definition_json'])
        day=datetime.fromisoformat(row['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date()
        if definition.get('workout_kind')!=kind or not today-timedelta(days=42)<=day<today:continue
        if row['effort'] is None or row['effort']>7 or (row['soreness'] or 0)>3 or row['pain_or_illness']:continue
        import re
        if re.search(r'\b(too hard|exhausted|could not finish|couldn.t finish|too tired)\b',row['notes'] or '',re.I):continue
        if training_benefit(c,row['id'])['source_label'] not in labels.get(kind,set()):continue
        rows.append({'activity_id':row['id'],'date':day.isoformat(),'definition':definition})
    return list({r['activity_id']:r for r in rows}.values())


def select(c,kind,today,tz,quality_allowed=True):
    choices=options(kind)
    if not choices:return None,{'reason':'No alternate library structure for this category.'}
    records=tolerated_sessions(c,kind,today,tz)
    chosen=choices[0]
    if quality_allowed and len(records)>=2:
        previous=records[-1]['definition'].get('variant_id')
        index=next((i for i,v in enumerate(choices) if v['id']==previous),-1)
        chosen=choices[(index+1)%len(choices)]
    return chosen['id'],{'tolerated_recordings':len(records),'activity_ids':[r['activity_id'] for r in records[-2:]],'reason':'Alternate structure follows two recent tolerated recordings in this category.' if quality_allowed and len(records)>=2 else 'Consolidate the first structure until category-specific recorded tolerance supports a variation.'}


def preview(arguments,path=None):
    from .training_coach import read_brief
    from .training_prescriptions import endurance
    from datetime import date
    from .time_utils import timezone_info
    from datetime import datetime,timezone
    kind=arguments.get('category');minutes=arguments.get('minutes',60)
    if kind=='base':kind='endurance'
    if not options(kind):raise ValueError('Choose base, threshold, sprint or anaerobic')
    today=datetime.now(timezone.utc).astimezone(timezone_info(arguments.get('timezone') or 'UTC')).date()
    brief=read_brief(path)['brief']
    return {'tool':'get_cycling_workout_variants','category':kind,'templates':[endurance(kind,minutes,brief,today=today,variant=v['id']) for v in options(kind)],'note':'Library previews, not a saved session or clearance for hard training. Selection must respect the active goal/block, recovery, completed tolerance and available time. Source examples inform the structures; these app variants are not copied personalized prescriptions.'}
