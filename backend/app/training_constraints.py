"""Canonical date-only sport slots, optional caps and compatibility adapters."""
import math
from copy import deepcopy

SPORT_CATALOG={
 'cycling':{'id':'cycling','label':'Cycling','prescription':'cycling'},
 'running':{'id':'running','label':'Running','prescription':'running'},
 'strength':{'id':'strength','label':'Strength','prescription':'strength'},
 'hiking':{'id':'hiking','label':'Hiking','prescription':'duration'},
 'other':{'id':'other','label':'Other activity','prescription':'duration'},
}
SPORTS=tuple(SPORT_CATALOG)

def integer(value,label,low=1,high=1440):
 if type(value) is not int or not low<=value<=high:raise ValueError(f'{label} must be whole minutes between {low} and {high}')
 return value

def schedule(value,complete=False):
 if not isinstance(value,list) or len(value)>7:raise ValueError('Weekly schedule must contain up to seven weekdays')
 result=[];days=set();ids=set()
 for row in value:
  if not isinstance(row,dict) or set(row)-{'weekday','mode','total_limit_minutes','activities','remove_slot_ids','replace_activities'}:raise ValueError('Unsupported weekly schedule fields')
  day=integer(row.get('weekday'),'Weekday',0,6)
  if day in days:raise ValueError('Each weekday must appear once')
  days.add(day);mode=row.get('mode');activities=row.get('activities',[])
  if mode not in ('rest','training'):raise ValueError('Choose rest or training for each answered day')
  if not isinstance(activities,list) or len(activities)>3:raise ValueError('Use at most three activities per day')
  if mode=='rest' and activities:raise ValueError('A rest day cannot contain sport activities; remove the activities or choose training')
  if mode=='training' and not activities:raise ValueError('A training day needs one to three activities')
  cap=row.get('total_limit_minutes')
  if cap is not None:integer(cap,'Shared daily limit')
  slots=[]
  for slot in activities:
   if not isinstance(slot,dict) or set(slot)-{'slot_id','sport','label','min_minutes','max_minutes'}:raise ValueError('Unsupported activity slot fields')
   identifier=slot.get('slot_id');sport=slot.get('sport')
   if not isinstance(identifier,str) or not identifier or len(identifier)>100 or identifier in ids:raise ValueError('Each activity slot needs a unique stable ID')
   if sport not in SPORT_CATALOG:raise ValueError('Choose cycling, running, strength, hiking or other')
   maximum=integer(slot.get('max_minutes'),'Activity maximum',1,720);minimum=slot.get('min_minutes')
   if minimum is not None:
    integer(minimum,'Activity minimum',1,720)
    if minimum>maximum:raise ValueError('Activity minimum cannot exceed its maximum')
   label=slot.get('label')
   if label is not None and (not isinstance(label,str) or not label.strip() or len(label)>100):raise ValueError('Activity label must be text up to 100 characters')
   if sport=='other' and not label:raise ValueError('Give the other activity a name')
   ids.add(identifier);slots.append({'slot_id':identifier,'sport':sport,'label':label or SPORT_CATALOG[sport]['label'],'min_minutes':minimum,'max_minutes':maximum})
  result.append({'weekday':day,'mode':mode,'total_limit_minutes':cap,'activities':slots})
 if complete and days!=set(range(7)):raise ValueError('Answer the missing weekdays: '+', '.join(str(day) for day in sorted(set(range(7))-days))+'. Omitted days are unanswered, not rest.')
 return sorted(result,key=lambda row:row['weekday'])

def merge_schedule(previous,patch):
 current={row['weekday']:deepcopy(row) for row in previous or []}
 if not isinstance(patch,list):raise ValueError('Weekly schedule patch must be a list')
 for row in patch:
  if not isinstance(row,dict) or 'weekday' not in row:raise ValueError('A day patch needs its weekday')
  old=current.get(row['weekday'],{});merged={**old,**row}
  if row.get('mode')=='rest':
   if row.get('activities'):raise ValueError('A rest day cannot contain activity slots')
   merged['activities']=[]
  elif 'activities' in row and old and not row.get('replace_activities'):
   slots={slot['slot_id']:slot for slot in old.get('activities',[])}
   for slot in row['activities']:slots[slot['slot_id']]={**slots.get(slot['slot_id'],{}),**slot}
   for identifier in row.get('remove_slot_ids',[]):slots.pop(identifier,None)
   merged['activities']=list(slots.values())
  elif 'remove_slot_ids' in row:merged['activities']=[slot for slot in old.get('activities',[]) if slot['slot_id'] not in row['remove_slot_ids']]
  merged.pop('remove_slot_ids',None);merged.pop('replace_activities',None);current[row['weekday']]=merged
 return schedule(list(current.values()))

def caps(value):
 if not isinstance(value,dict) or set(value)-set(SPORTS):raise ValueError('Optional weekly caps use known sports')
 result={}
 for sport,cap in value.items():
  if cap is None:result[sport]=None;continue
  if not isinstance(cap,dict) or set(cap)-{'max_minutes','range_min_minutes'}:raise ValueError('A cap needs max_minutes and optional range_min_minutes')
  maximum=integer(cap.get('max_minutes'),'Weekly cap',0,5040);minimum=cap.get('range_min_minutes')
  if minimum is not None:
   integer(minimum,'Weekly range minimum',0,5040)
   if minimum>maximum:raise ValueError('Weekly range is reversed')
  result[sport]={'max_minutes':maximum,**({'range_min_minutes':minimum} if minimum is not None else {})}
 return result

def merge_answers(previous,patch):
 result={**previous,**patch}
 if 'week_schedule' in patch:result['week_schedule']=schedule(patch['week_schedule']) if len(patch['week_schedule'])==7 else merge_schedule(previous.get('week_schedule',[]),patch['week_schedule'])
 if 'weekly_caps' in patch:
  merged={**previous.get('weekly_caps',{}),**caps(patch['weekly_caps'])}
  result['weekly_caps']={sport:cap for sport,cap in merged.items() if cap is not None}
  # An explicit cap edit supersedes that sport's historical legacy limit, including removal.
  if 'weekly_minutes' in result:result['weekly_minutes']={sport:minutes for sport,minutes in result['weekly_minutes'].items() if sport not in patch['weekly_caps']}
 for field in ('experience','weekly_minutes'):
  if field in patch:result[field]={**previous.get(field,{}),**patch[field]}
 return result

def resolve(answers,brief=None):
 if 'week_schedule' in answers:return {'days':schedule(answers['week_schedule']),'issues':[],'legacy':False}
 sport_days=(brief or {}).get('sport_days',{});sports=answers.get('sports',[]);rows=[];issues=[]
 for old in answers.get('availability',[]):
  day=old['weekday'];allowed=[sport for sport,days in sport_days.items() if day in days]
  if not allowed and len(sports)==1:allowed=list(sports)
  if not allowed:
   issues.append('Which sport is allowed on weekday '+str(day)+'? Legacy availability has no unambiguous sport assignment.');continue
  rows.append({'weekday':day,'mode':'training','total_limit_minutes':old['minutes'],'activities':[{'slot_id':f'legacy-{day}-{sport}','sport':sport,'min_minutes':None,'max_minutes':old['minutes']} for sport in allowed[:3]]})
 return {'days':schedule(rows),'issues':issues,'legacy':True}

def availability(days):
 return [{'weekday':row['weekday'],'start_time':None,'minutes':row['total_limit_minutes'] or sum(slot['max_minutes'] for slot in row['activities'])} for row in days if row['mode']=='training']

def capacity(days,sport):
 return sum(min(sum(slot['max_minutes'] for slot in row['activities'] if slot['sport']==sport),row['total_limit_minutes'] or 1440) for row in days if row['mode']=='training')

def slots_for(days,weekday,sport=None):
 row=next((row for row in days if row['weekday']==weekday),None)
 return [slot for slot in row['activities'] if sport is None or slot['sport']==sport] if row and row['mode']=='training' else []

def day_limit(days,weekday):
 row=next((row for row in days if row['weekday']==weekday),None)
 return (row['total_limit_minutes'] or sum(slot['max_minutes'] for slot in row['activities'])) if row and row['mode']=='training' else 0

def optional_cap(answers,sport):
 cap=answers.get('weekly_caps',{}).get(sport)
 if cap is not None:return cap['max_minutes'],'user_optional_cap'
 legacy=answers.get('weekly_minutes',{}).get(sport)
 return (legacy,'legacy_limit') if legacy is not None else (None,None)


def assign_slot(days,weekday,sport,minutes,slot_id=None,used_ids=()):
    """Choose only an explicitly available matching sport slot; never borrow another sport's cap."""
    day=next((row for row in days if row['weekday']==weekday),None)
    candidates=[slot for slot in (day or {}).get('activities',[]) if slot['sport']==sport and slot['max_minutes']>=minutes and slot['slot_id'] not in used_ids]
    selected=next((slot for slot in candidates if slot['slot_id']==slot_id),None)
    if selected is None and len(candidates)==1:selected=candidates[0]
    if selected is None:raise ValueError('Choose an available matching sport slot with enough time; ambiguous slots require an explicit selection')
    return selected
