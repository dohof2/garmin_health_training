"""Bound repeated conversational input without changing stored chat history."""

def bounded_history(history, max_chars=12000, max_messages=8):
    # Keep whole messages: cutting JSON, units or a confirmation can change meaning.
    kept=[];size=0
    for item in reversed(history[-max_messages:]):
        length=len(item.get('content',''))
        if kept and size+length>max_chars:break
        kept.append(item);size+=length
    return list(reversed(kept))


def compact_json(value):
    import json
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),default=str)


def compact_active_plan(result, message='', today=None):
    """Remove duplicate SQL/JSON snapshots; expose grounded session summaries."""
    import re
    program=result.get('program')
    if not program:return result
    state=program.get('state') or {}
    def workout(row):
        definition=row.get('definition') or {}
        return {**{key:row[key] for key in ('id','title','sport','scheduled_for','completion_status','publish_status','revision') if key in row},
                **{key:definition[key] for key in ('scheduled_date','duration_minutes','workout_kind','effort_target','training_block','review_hold','schedule_override') if key in definition}}
    rows=sorted(result.get('workouts') or [],key=lambda w:w.get('scheduled_for',''))
    dates=set(re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message))
    if dates:
        chosen=[w for w in rows if (w.get('definition') or {}).get('scheduled_date',w.get('scheduled_for','')[:10]) in dates]
    else:
        chosen=[w for w in rows if not today or (w.get('definition') or {}).get('scheduled_date',w.get('scheduled_for','')[:10])>=today]
    chosen=chosen[:14]
    review=result.get('latest_review') or {}
    return {'tool':result.get('tool','get_active_training_plan'),
            'program':{**{key:program[key] for key in ('plan_id','root_plan_id','name','status','revision','plan_revision') if key in program},
                       'state':{**{key:state[key] for key in ('timezone','starts_on','ends_on','brief') if key in state},'blocks':[{key:block[key] for key in ('week','starts_on','phase','focus') if key in block} for block in state.get('blocks',[])]}},
            'workouts':[workout(w) for w in chosen],
            'planned_workout_count':len(rows),'workouts_truncated':len(chosen)<len(rows),
            'completed_workouts':[workout(w) for w in (result.get('completed_workouts') or [])[-5:]],
            'latest_review':{key:review[key] for key in ('date','reasons','warnings','recovery_context','current_block') if key in review},
            'detail_note':'Summary only; full session instructions and other dates are available through query_app_data. Never infer missing session details.'}


def compact_app_context(context):
    """UI previews are references, not another copy of all planning evidence."""
    result={key:value for key,value in context.items() if key in ('plots','ride','sections') and value is not None}
    coaching=context.get('coaching')
    if isinstance(coaching,dict):
        result['coaching']={key:coaching[key] for key in ('status','question','questions','missing','brief','candidate_answers','week_start','timezone','fingerprint') if key in coaching}
        if isinstance(coaching.get('sessions'),list):
            result['coaching']['sessions']=[{**{key:w[key] for key in ('id','title','sport','scheduled_for') if key in w},'duration_minutes':(w.get('definition') or {}).get('duration_minutes')} for w in coaching['sessions'][:14]]
    return result


def compact_training_context(result, message='', today=None):
    """The preferences tool embeds the same large active-plan snapshot."""
    compact=dict(result)
    if isinstance(result.get('active_plan'),dict):
        compact['active_plan']=compact_active_plan(result['active_plan'],message,today)
    if isinstance(result.get('training'),dict):
        compact['training']={key:value for key,value in result['training'].items() if key not in ('raw_answers','sport_catalog')}
    if isinstance(result.get('coaching_brief'),dict):
        compact['coaching_brief']={key:value for key,value in result['coaching_brief'].items() if not key.endswith('_json')}
    return compact
