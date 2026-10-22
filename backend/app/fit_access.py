"""Discover and inspect arbitrary recorded FIT fields through preserved originals."""
import io
import json
import math
import statistics
import zipfile
from functools import lru_cache
from pathlib import Path
from datetime import date
from garmin_fit_sdk import Profile
from .read_cache import versioned_read
from .database import connect
from .activity_metrics import source_payload
from .history import get_activity
from .time_utils import calendar_date,timezone_info


@lru_cache(maxsize=1)
def nested_content(filename,member,modified):
    with zipfile.ZipFile(filename) as outer:return outer.read(member)


def original_messages(identifier,path=None):
    from .fit_import import _decode_fit
    from .sync import _fit_content
    with connect(path) as c:
        row=c.execute('''SELECT s.stored_path FROM fit_import_files f JOIN source_files s ON s.id=f.fit_source_file_id
            WHERE f.activity_id=? AND f.status='completed' ORDER BY f.imported_at DESC LIMIT 1''',(identifier,)).fetchone()
        if row is None:
            row=c.execute('''SELECT s.stored_path FROM activities a JOIN source_files s
                ON s.original_name IN ('activity-'||a.source_record_id||'.fit','activity-'||a.source_record_id||'.zip') WHERE a.id=? LIMIT 1''',(identifier,)).fetchone()
    if row is None:return None
    parts=(row['stored_path'] or '').split('!/')
    try:
        if len(parts)==3:
            content_bytes=nested_content(parts[0],parts[1],Path(parts[0]).stat().st_mtime_ns)
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as inner:content=inner.read(parts[2])
        elif len(parts)==1:content=_fit_content(Path(parts[0]).read_bytes())
        else:return None
        messages,errors=_decode_fit(content)
        if errors:raise ValueError('Original FIT has decoding errors; incomplete data was not used')
        return source_payload(messages)
    except (OSError,KeyError,zipfile.BadZipFile):return None


def discover(arguments,path=None):
    query=arguments.get('query','').strip().lower();timezone=arguments.get('timezone') or 'UTC';timezone_info(timezone)
    if len(query)>100:raise ValueError('Field search is too long')
    start=arguments.get('start_date');end=arguments.get('end_date')
    for value in (start,end):
        if value:date.fromisoformat(value)
    if start and end and start>end:raise ValueError('Start date must precede end date')
    matches=[];field_counts={};scanned=0;unknown=0
    with connect(path) as c:
        for activity in c.execute("SELECT id,name,started_at,raw_json FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' ORDER BY started_at DESC"):
            day=calendar_date(activity['started_at'],timezone).isoformat()
            if (start and day<start) or (end and day>end):continue
            scanned+=1;raw=json.loads(activity['raw_json'] or '{}');inventory=raw.get('fit_field_inventory')
            if inventory is None:unknown+=1;continue
            found={}
            for message,fields in inventory.items():
                selected=[f for f in fields if not query or query in f.lower() or query in message.lower()]
                if selected:
                    found[message]=selected
                    for f in selected:field_counts[(message,f)]=field_counts.get((message,f),0)+1
            if found:matches.append({'id':activity['id'],'name':activity['name'],'date':day,'fields':found,'evidence_url':f"/api/activities/{activity['id']}"})
    return {'tool':'find_fit_fields','query':query,'activities_scanned':scanned,'matching_activities':len(matches),'activities_without_inventory':unknown,
        'field_coverage':[{'message':m,'field':f,'activities':count} for (m,f),count in sorted(field_counts.items())],
        'activities':matches[:100],'truncated':len(matches)>100,'note':'Field presence is not proof of a non-null measurement. Counts cover all matching activities; details show the latest 100. Use get_fit_activity_data for values and units. Uninventoried files are not evidence of absent fields.'}


def inspect(arguments,path=None):
    identifier=arguments.get('activity_id')
    if not identifier:
        with connect(path) as c:
            row=c.execute("SELECT id FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' ORDER BY started_at DESC LIMIT 1").fetchone()
        identifier=row['id'] if row else None
    activity=get_activity(identifier,path,arguments.get('timezone')) if identifier else None
    if not activity:raise ValueError('No recorded activity available')
    messages=original_messages(identifier,path)
    original_available=messages is not None
    if messages is None:
        with connect(path) as c:raw=json.loads(c.execute('SELECT raw_json FROM activities WHERE id=?',(identifier,)).fetchone()[0] or '{}')
        messages=raw.get('fit_messages') or {'session_mesgs':raw.get('fit_sessions',[]),'lap_mesgs':raw.get('fit_laps',[])}
    inventory={name:{'count':len(rows),'fields':sorted({str(k) for row in rows if isinstance(row,dict) for k in row})} for name,rows in messages.items() if isinstance(rows,list)}
    name=arguments.get('message_type') or 'session_mesgs'
    if not isinstance(name,str) or len(name)>100:raise ValueError('Invalid FIT message type')
    fields=arguments.get('fields')
    if fields is not None and (not isinstance(fields,list) or len(fields)>20 or any(not isinstance(f,str) or len(f)>100 for f in fields)):raise ValueError('Choose up to 20 recorded FIT fields')
    offset=arguments.get('offset',0);limit=arguments.get('limit',100)
    if not isinstance(offset,int) or isinstance(offset,bool) or offset<0 or not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=200:raise ValueError('Invalid FIT pagination')
    rows=[r for r in messages.get(name,[]) if isinstance(r,dict)]
    available=inventory.get(name,{}).get('fields',[]);selected=fields if fields is not None else available
    stats={}
    definition=next((m for m in Profile['messages'].values() if m.get('name')==name.removesuffix('_mesgs')), {})
    units={f['name']:(', '.join(f['units']) if isinstance(f.get('units'),list) else f.get('units','')) for f in definition.get('fields',{}).values()}
    for field in selected:
        values=[row.get(field) for row in rows]
        numbers=[v for v in values if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)]
        stats[field]={'unit':units.get(field),'non_null_count':sum(v is not None for v in values),'numeric_count':len(numbers),'minimum':min(numbers) if numbers else None,'maximum':max(numbers) if numbers else None,'mean':statistics.fmean(numbers) if numbers else None}
    return {'tool':'get_fit_activity_data','activity_id':identifier,'date':activity['local_date'],'inventory':inventory,'original_available':original_available,'message_type':name,
        'total_records':len(rows),'offset':offset,'records':[{k:v for k,v in row.items() if k in selected or k=='timestamp'} for row in rows[offset:offset+limit]],'truncated':offset+limit<len(rows),
        'missing_fields':[f for f in selected if f not in available],'statistics':stats,'evidence_url':f'/api/activities/{identifier}',
        'note':'All selected-message records contribute to field statistics; returned raw rows are explicitly paginated. Units come from the installed Garmin FIT profile; unknown/developer units are not invented. Values describe recorded fields, not inferred jumps or grit.'}


@versioned_read
def catalog(path=None):
    fields=set()
    with connect(path) as c:
        for row in c.execute("SELECT json_extract(raw_json,'$.fit_field_inventory') AS inventory FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture'"):
            for message,names in json.loads(row['inventory'] or '{}').items():
                fields.update((message,f) for f in names if ':' not in f)
                fields.add((message,'count'))
    definitions={m['name']:{f['name']:(', '.join(f['units']) if isinstance(f.get('units'),list) else f.get('units')) for f in m.get('fields',{}).values()} for m in Profile['messages'].values()}
    return [{'id':f'fit:{m}:{f}','label':f"FIT {m.removesuffix('_mesgs')} · {f}",'unit':'count' if f=='count' else definitions.get(m.removesuffix('_mesgs'),{}).get(f) or 'source units'} for m,f in sorted(fields)]


def observations(metric,spec,path=None):
    _,message,field=metric.split(':',2);points=[];excluded=0
    operation=spec.get('fit_stat','mean')
    unit=next((m['unit'] for m in catalog(path) if m['id']==metric),'source units')
    with connect(path) as c:
        activities=c.execute("SELECT id,started_at,source_name,activity_type,raw_json FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' ORDER BY started_at").fetchall()
    for activity in activities:
        day=calendar_date(activity['started_at'],spec.get('timezone')).isoformat()
        if (spec.get('start') and day<spec['start']) or (spec.get('end') and day>spec['end']):continue
        if spec.get('sport') not in (None,'all',activity['activity_type']):continue
        raw=json.loads(activity['raw_json'] or '{}')
        if message not in raw.get('fit_field_inventory',{}):excluded+=1;continue
        messages=(original_messages(activity['id'],path) if message=='record_mesgs' else None) or raw.get('fit_messages') or {}
        rows=messages.get(message,[])
        values=[r.get(field) for r in rows if isinstance(r,dict)]
        numeric=[v for v in values if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)]
        if field=='count':value=len(rows)
        elif operation=='count':value=sum(v is not None for v in values);unit='count'
        elif numeric:value={'mean':statistics.fmean,'maximum':max,'minimum':min,'sum':math.fsum}[operation](numeric)
        else:excluded+=1;continue
        points.append({'date':day,'value':value,'key':activity['id'],'id':activity['id'],'source':activity['source_name']})
    return points,unit,excluded
