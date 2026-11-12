"""Whitelisted paginated history reads for user-facing datasets."""
import json,re
from datetime import datetime,time,timedelta,timezone
from .time_utils import timezone_info


def period_filter(column,start,end,tz,naive_utc=False):
 zone=timezone_info(tz)
 a=datetime.combine(start,time.min,zone).astimezone(timezone.utc).isoformat()
 b=datetime.combine(end+timedelta(days=1),time.min,zone).astimezone(timezone.utc).isoformat()
 if naive_utc:return f"(datetime({column})>=datetime(?) AND datetime({column})<datetime(?))",[a,b]
 # Date-only and legacy naive timestamps retain their stored calendar date;
 # aware instants use actual local-day UTC boundaries, including DST.
 naive=f"(instr(substr({column},11),'+')=0 AND instr(substr({column},11),'-')=0 AND substr({column},-1)!='Z')"
 return f"(({naive} AND substr({column},1,10) BETWEEN ? AND ?) OR (NOT {naive} AND datetime({column})>=datetime(?) AND datetime({column})<datetime(?)))",[start.isoformat(),end.isoformat(),a,b]


def page(c,select,source,where,params,order,limit,offset):
 count=c.execute('SELECT COUNT(*) FROM '+source+' WHERE '+where,params).fetchone()[0]
 rows=[dict(r) for r in c.execute('SELECT '+select+' FROM '+source+' WHERE '+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',params+[limit,offset])]
 return {'records':rows,'total_matches':count,'offset':offset,'limit':limit,'truncated':offset+len(rows)<count,
         'next_offset':offset+len(rows) if offset+len(rows)<count else None,'availability':'available' if count else 'no_records_in_period'}


def public_json(raw):
 try:value=json.loads(raw)
 except (ValueError,TypeError):return {'unavailable':'Stored payload is not valid JSON.'},['invalid_json']
 flags=[];budget=[500]
 def clean(item,path='',depth=0):
  budget[0]-=1
  if budget[0]<0 or depth>8:flags.append(path);return '[payload truncated]'
  if isinstance(item,dict):
   result={}
   for key,val in item.items():
    normalized=re.sub(r'[^a-z]','',str(key).lower())
    if normalized in {'password','secret','accesstoken','refreshtoken','authorization','cookie','accountkey','accountlabel','email','username','userid'}:
     flags.append(path+'.'+str(key)+' (redacted)');continue
    if budget[0]<0:flags.append(path);break
    result[key]=clean(val,path+'.'+str(key),depth+1)
   return result
  if isinstance(item,list):
   result=[]
   for index,val in enumerate(item):
    if budget[0]<0 or index>=100:flags.append(path);break
    result.append(clean(val,path+f'[{index}]',depth+1))
   return result
  if isinstance(item,str) and len(item)>4000:flags.append(path);return item[:4000]+'…'
  return item
 return clean(value),list(dict.fromkeys(flags))[:20]


def extended_query(dataset,c,start,end,tz,limit,offset):
 dated={
  'health_samples':('health_samples','recorded_at','id,source_name,recorded_at,heart_rate_bpm,stress_level,respiration_rate','recorded_at DESC,id DESC'),
  'hydration':('hydration_events','calendar_date','id,source_name,calendar_date,recorded_at,hydration_source,value_ml,estimated_sweat_loss_ml,measured_sweat_loss_ml,duration_seconds,capped','recorded_at DESC,id'),
  'abnormal_heart_rate':('abnormal_heart_rate_events','calendar_date','id,source_name,calendar_date,recorded_at,heart_rate_bpm,threshold_bpm','recorded_at DESC,id'),
  'garmin_nutrition':('garmin_nutrition_daily','calendar_date','id,source_name,calendar_date,calories_consumed,calorie_goal','calendar_date DESC,id'),
 }
 if dataset in dated:
  if dataset=='health_samples' and (end-start).days>6:raise ValueError('Choose up to seven local days for continuous wellness samples')
  table,column,fields,order=dated[dataset];where,params=period_filter(column,start,end,tz)
  result=page(c,fields,table,where+" AND source_name!='synthetic_fixture'",params,order,limit,offset)
  units={'heart_rate_bpm':'bpm','threshold_bpm':'bpm','stress_level':'score / 100','respiration_rate':'breaths/min','value_ml':'mL','estimated_sweat_loss_ml':'mL','measured_sweat_loss_ml':'mL','duration_seconds':'s','calories_consumed':'kcal','calorie_goal':'kcal'}
  result['units']={key:value for key,value in units.items() if key in fields.split(',')}
  if dataset=='garmin_nutrition':result['note']='Imported Garmin intake summaries are separate from local meals; never add both as independent food intake.'
  return result
 if dataset=='food_library':
  result=page(c,'id,name,kind,servings,definition_json,revision,updated_at','food_library','1=1',[],'name,id',limit,offset)
  for row in result['records']:row['definition'],row['payload_limits']=public_json(row.pop('definition_json'))
  result['observation_kind']='Current saved recipe/reusable-meal definitions; not a historical as-of snapshot.'
  return result
 if dataset=='goals':
  result=page(c,'id,goal_type,title,target_value,target_unit,target_date,status,notes','goals','1=1',[],'id',limit,offset)
  where,params=period_filter('recorded_at',start,end,tz,naive_utc=True)
  history=page(c,'goal_id,recorded_at,snapshot_json','goal_revisions',where,params,'recorded_at DESC,id DESC',limit,offset)
  for row in history['records']:row['snapshot'],row['payload_limits']=public_json(row.pop('snapshot_json'))
  result['revisions']=history;result['observation_kind']='Current goals (including archived); dated revision history is separate.'
  return result
 if dataset=='training':
  date_expr="COALESCE(CASE WHEN json_valid(w.definition_json) THEN json_extract(w.definition_json,'$.scheduled_date') END,w.scheduled_for)"
  where,params=period_filter(date_expr,start,end,tz)
  source='planned_workouts w LEFT JOIN training_plans p ON p.id=w.training_plan_id'
  fields='w.id,w.training_plan_id,w.sport,w.title,w.scheduled_for,w.revision,w.completion_status,w.publish_status,w.definition_json,p.deleted_at AS plan_deleted'
  result=page(c,fields,source,where+" AND w.completion_status!='missed' AND (p.deleted_at IS NULL OR w.completion_status='completed')",params,'w.scheduled_for DESC,w.id',limit,offset)
  for row in result['records']:
   row['definition'],row['payload_limits']=public_json(row.pop('definition_json'))
   feedback=c.execute('SELECT activity_id,effort,soreness,pain_or_illness,notes,updated_at FROM training_feedback WHERE workout_id=?',(row['id'],)).fetchone()
   row['feedback']=dict(feedback) if feedback else None
   sets=c.execute('SELECT exercise_id,set_index,load_kg,repetitions,repetitions_in_reserve,recorded_at FROM training_strength_performance WHERE workout_id=? ORDER BY exercise_id,set_index LIMIT 101',(row['id'],)).fetchall()
   row['strength_performance']=[dict(r) for r in sets[:100]];row['strength_performance_truncated']=len(sets)>100
  plans=page(c,'id,name,status,starts_on,ends_on','training_plans',"deleted_at IS NULL AND (starts_on IS NULL OR starts_on<=?) AND (ends_on IS NULL OR ends_on>=?)",[end.isoformat(),start.isoformat()],'starts_on DESC,id',limit,0)
  result['plans']=plans;result['note']='Scheduled local dates select workouts; recorded feedback and set timestamps remain visible. Current preferences/active brief use get_training_context.'
  return result
 if dataset=='publication':
  where,params=period_filter("COALESCE(i.scheduled_date,j.created_at)",start,end,tz)
  source='garmin_publication_items i JOIN garmin_publication_jobs j ON j.id=i.job_id'
  fields='i.id,i.workout_id,i.workout_revision,i.scheduled_date,i.action,i.state,i.error,j.status AS job_status,j.created_at,j.approved_at'
  result=page(c,fields,source,where,params,'j.created_at DESC,i.id',limit,offset)
  wwhere,wparams=period_filter('utc_timestamp',start,end,tz)
  result['weight_publications']=page(c,'reading_id,status,local_timestamp,utc_timestamp,updated_at','weight_publications',wwhere,wparams,'utc_timestamp DESC,reading_id',limit,offset)
  result['note']='Local send/verification evidence only. This query does not contact Garmin, retry a send, or prove device delivery.'
  return result
 if dataset=='dashboard':
  result=page(c,'id,card_type,position,is_visible,settings_json,updated_at','dashboard_cards','1=1',[],'position,id',limit,offset)
  for row in result['records']:row['settings'],row['payload_limits']=public_json(row.pop('settings_json'))
  result['layouts']={}
  for name,table in [('dashboard','dashboard_widget_layout'),('health','health_widget_layout')]:
   row=c.execute('SELECT widgets_json,updated_at FROM '+table+' WHERE id=1').fetchone()
   if row:
    widgets,flags=public_json(row['widgets_json']);result['layouts'][name]={'widgets':widgets,'updated_at':row['updated_at'],'payload_limits':flags}
  result['observation_kind']='Current saved chart/card configuration; no chart query or action is executed.'
  return result
 return None
