"""Apply explicitly requested food corrections to existing meal items only."""
import json
import re
from datetime import date,datetime
from .database import connect
from .nutrition import NUTRIENTS,_meal,_meal_revision,daily_status,encoded,normalize_items,number,text,zone
from .nutrition_logging import add_saved_feedback,nutrient_source,replay,request_hash
from .food_vision import analyze_food


def supplied_nutrition(message):
    return bool(re.search(r'\bvalues?\s+(?:are|is|for)|ערכים|קלוריות',message,re.I) and re.search(r'\d',message))


def correction_intent(message, *, allow_followup=False):
    from .nutrition_logging import consumption_report
    if consumption_report(message):return False
    if re.search(r"\b(don't|do not|never|what if|hypothetically)\b|אל ת|לא לתקן",message,re.I):return False
    explicit=bool(re.search(r'\b(correct|coreect|correction|change|update|replace|instead|actually|wrong|meant)\b|בעצם|תתקן|תקן|תעדכן|עדכן|התכוונתי|במקום',message,re.I)) or supplied_nutrition(message)
    if re.search(r'\b(goal|target|workout|profile|height|weight loss)\b|יעד|מטרה|אימון|גובה',message,re.I):return False
    if re.search(r'^\s*(what|how|why|should|would|is|are|מה|כמה|האם)\b',message,re.I):return False
    # Food descriptions and household units alone are not edit instructions.
    # Short answers such as "raw, 4 spoons" may correct a referenced saved meal.
    return explicit or (allow_followup and len(message.split())<=20 and '?' not in message and
        bool(re.search(r'\b(raw|prepared|cooked|paste|sauce|brand|tablespoons?|teaspoons?|spoons?)\b|גולמי|גולמית|מוכנה|מבושל|כפות|כפיות',message,re.I)))


def correction_response(day,message,reply):
    return {'ingredients':[],'uncertainties':[],'context_date':day,'logged':False,'reply':reply,'advisory':'No meal has been changed.'}


def apply_correction(message,day,tz,meal_type,operation_id,selection,replacement,path=None,*,provided_values=False):
    """Revision-check and update one item; preserve every other item and its ID."""
    from .chat_access import authorize_nutrition_write
    fingerprint=request_hash(message,day,tz,meal_type)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');authorize_nutrition_write(c)
        previous=replay(operation_id,fingerprint,c=c)
        if previous:return previous
        meal=_meal(c,selection['meal_id'])
        if type(selection['expected_revision']) is not int or meal['revision']!=selection['expected_revision']:
            raise ValueError('That meal changed; review the current entry before correcting it.')
        if meal['deleted_at'] or datetime.fromisoformat(meal['eaten_at']).astimezone(zone(tz)).date().isoformat()!=day:
            raise ValueError('Choose the meal date explicitly before correcting a different day.')
        item=next((item for item in meal['items'] if item['id']==selection['item_id']),None)
        if item is None:raise ValueError('The selected ingredient is no longer in this meal.')
        if selection.get('keep_quantity'):
            if item['unit']!='g':raise ValueError('Specify the corrected food amount in grams for this entry.')
            grams=item['quantity'];low=high=grams
        else:
            low=number(replacement['grams_low'],'Portion lower',0,10000)
            high=number(replacement['grams_high'],'Portion upper',low,10000)
            grams=number(replacement.get('grams_proposed') if replacement.get('grams_proposed') is not None else (low+high)/2,'Corrected portion',.01,10000)
            if not low<=grams<=high:raise ValueError('Corrected portion is outside its estimated range.')
        source,assumptions=nutrient_source(replacement)
        if provided_values and replacement.get('nutrients_per_100g'):
            from .food_vision import nutrient_estimate
            values=nutrient_estimate(replacement['nutrients_per_100g'])
            source={'source':'User-provided approximate nutrition; converted to per 100 g','source_url':'','nutrients':values}
            assumptions='User-provided ranges/units converted to a central estimate, not independently verified.'
        assumptions=' '.join(filter(None,[text(replacement.get('estimate_assumptions',''),'Correction assumptions',1000,True),assumptions]))
        corrected=normalize_items([{'name':replacement['name'],'quantity':grams,'unit':'g',
            'nutrients':source['nutrients'] if source else {k:None for k in NUTRIENTS},'nutrient_basis':'per_100g' if source else 'portion',
            'source':' · '.join(filter(None,[source['source'],source['source_url']])) if source else 'Corrected food identity; nutrient source unknown',
            'portion_basis':'estimated','uncertainty':f'User corrected ingredient in chat. {low:g}–{high:g} g estimated range; saved {grams:g} g. '+assumptions}])[0]
        c.execute('''UPDATE meal_items SET name=?,quantity=?,unit=?,calories_kcal=?,protein_grams=?,fat_grams=?,carbohydrate_grams=?,source=?,detail_json=? WHERE id=? AND meal_id=?''',
                  (corrected['name'],grams,'g',*[corrected[k] for k in NUTRIENTS],corrected['source'],encoded(corrected['detail']),item['id'],meal['id']))
        c.execute('UPDATE meals SET revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(meal['id'],))
        saved=_meal_revision(c,meal['id'])
        reply=f"Corrected {item['name']} to {corrected['name']} ({grams:g} g, estimated) in your existing {meal['meal_type']}. Calories and macros recalculated; no duplicate meal added."
        if re.search('[\u0590-\u05ff]',message):reply=f"תוקן {item['name']} ל־{corrected['name']} ({grams:g} גרם, הערכה) בארוחה הקיימת. הקלוריות והערכים התזונתיים חושבו מחדש, ללא ארוחה כפולה."
        if assumptions:reply+=' '+assumptions
        if not source:reply+=' Nutrient values remain unknown; totals are partial.'
        result={'ingredients':[],'uncertainties':[],'context_date':day,'logged':True,'updated':True,
                'saved_meals':[{'id':saved['id'],'revision':saved['revision'],'meal_type':saved['meal_type']}],
                'pending_correction':None,'reply':reply,'advisory':'Updated the existing meal item. Portions and nutrients remain estimates.'}
        add_saved_feedback(result,[saved],day,tz,c,message)
        c.execute('INSERT INTO nutrition_chat_operations(operation_id,request_hash,result_json) VALUES(?,?,?)',(operation_id,fingerprint,encoded(result)))
        return result


def correct_ingredient(message,saved_meals,day,tz,meal_type,operation_id,path=None,history=None,*,pending_foods=None,pending_correction=None):
    from .nutrition_logging import consumption_report
    pending=pending_correction if isinstance(pending_correction,dict) and pending_correction.get('day')==day else None
    # A quantity may arrive just after the supplied nutrient values were already
    # committed. Retain that grounded correction's meaning for a short count.
    turns=history or []
    if not pending and saved_meals and turns and turns[-1].get('role')=='assistant' and re.match(r'Corrected |תוקן ',turns[-1].get('content','')) and len(message)<120 and re.search(r'\d',message) and not consumption_report(message):
        original=next((turn['content'] for turn in reversed(turns) if turn.get('role')=='user' and supplied_nutrition(turn['content'])),None)
        if original:pending={'day':day,'request':original,'clarifications':[]}
    if pending and re.fullmatch(r'\s*(?:cancel|forget|stop)(?:\s+(?:it|the correction))?[.!\s]*',message,re.I):
        return {**correction_response(day,message,'Cancelled the pending correction. No saved food was changed.'),'pending_correction':None}
    followup=bool(pending and not consumption_report(message) and not re.search(r'\?|\b(don\x27t|do not|cancel|forget|stop)\b|אל ת|בטל',message,re.I))
    if not followup and not correction_intent(message,allow_followup=bool(saved_meals) and not pending_foods):return None
    from .nutrition_logging import pending_meal_destination
    selected_type=pending_meal_destination(message) or (pending.get('meal_type') if followup else None)
    meals=[meal for meal in daily_status(date.fromisoformat(day),tz,path)['meals'] if not meal['deleted_at'] and (not selected_type or meal['meal_type']==selected_type)]
    refs={ref['id']:ref for ref in saved_meals or [] if isinstance(ref,dict) and 'id' in ref}
    if followup and pending.get('candidates'):
        allowed={(item.get('meal_id'),item.get('item_id')) for item in pending['candidates'] if isinstance(item,dict)}
        meals=[{**meal,'items':[item for item in meal['items'] if (meal['id'],item['id']) in allowed]} for meal in meals]
        refs={}
    if refs and not selected_type:meals=[meal for meal in meals if meal['id'] in refs]
    # Conversation references scope the meal, but current tool data supplies the
    # revision. Protect against changes during inference at the write boundary.
    candidates=[{'meal_id':meal['id'],'expected_revision':meal['revision'],'meal_type':meal['meal_type'],
                 'item_id':item['id'],'name':item['name'],'grams':item['quantity'] if item['unit']=='g' else None,
                 'nutrients_missing':any(item[k] is None for k in NUTRIENTS)} for meal in meals for item in meal['items']]
    if not candidates or len(candidates)>60:return {**correction_response(day,message,'I could not find that existing food on '+day+'. If you removed it, say what to add and which meal/date; nothing has been changed.'),'pending_correction':None}
    original=pending['request'] if followup else message
    clarifications=[*(pending.get('clarifications',[]) if followup else []),*([{'role':'user','content':message}] if followup else [])][-8:]
    result=analyze_food(message=message,path=path,conversational=True,review_context={'date':day,'timezone':tz,'meal_type':meal_type,
        'conversation':history or [],'correction_candidates':candidates,'correction_request':original,'correction_clarifications':clarifications})
    selection=result.get('food_correction')
    if not selection or len(result.get('ingredients',[]))!=1:
        return {**correction_response(day,message,'Correction not saved yet. '+(result.get('reply') or 'Which ingredient should I correct, and what should it be?')),
            'pending_correction':{'day':day,'request':original,'meal_type':selected_type,'clarifications':clarifications,
                                  'candidates':[{'meal_id':item['meal_id'],'item_id':item['item_id']} for item in candidates]}}
    if not isinstance(selection,dict):raise ValueError('Invalid ingredient correction; nothing was changed.')
    match=next((item for item in candidates if item['meal_id']==selection.get('meal_id') and item['item_id']==selection.get('item_id') and item['expected_revision']==selection.get('expected_revision')),None)
    if not match:raise ValueError('The correction did not identify an existing meal ingredient; nothing was changed.')
    if type(selection.get('keep_quantity')) is not bool:raise ValueError('The correction must say whether the existing portion is retained.')
    return apply_correction(message,day,tz,meal_type,operation_id,selection,result['ingredients'][0],path,provided_values=supplied_nutrition(original))
