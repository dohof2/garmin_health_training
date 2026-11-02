"""Save understood food reports once, without a second review step."""
import copy
import hashlib
import json
import re
from datetime import date,datetime,time,timezone,timedelta
from .database import connect
from .nutrition import NUTRIENTS,encoded,preview_meal,_save_meal,catalog,zone,text,number


def add_saved_feedback(result, meals, day, tz, connection, message):
    from .nutrition import _daily_status
    from .nutrition_feedback import meal_feedback,goal_feedback,partial_explanation
    hebrew=bool(re.search('[\u0590-\u05ff]',message))
    status=_daily_status(connection,date.fromisoformat(day),tz)
    assessments=[meal_feedback(meal,hebrew=hebrew) for meal in meals]
    explanations=[partial_explanation(meal,hebrew=hebrew) for meal in meals]
    result['partial_explanation']=' '.join(explanation for explanation in explanations if explanation)
    if result['partial_explanation']:result['reply']+='\n\n'+result['partial_explanation']
    result['meal_assessment']='\n\n'.join(assessments)
    result.update(goal_feedback(status,hebrew=hebrew))
    result['reply']+='\n\n'+result['meal_assessment']+'\n\n'+result['goal_progress']+' '+result['next_meal_suggestion']


def correct_portion(message, saved_meals, day, tz, meal_type, operation_id, path=None):
    """Correct one explicitly named gram portion in referenced, revision-checked meals."""
    if re.search(r'\b(raw|prepared|cooked|paste|sauce|brand|instead|replace)\b|גולמי|גולמית|מוכנה|במקום',message,re.I):return None
    if re.search(r'\b(goal|target|weight|height|workout|ride|profile|calories|kcal)\b|יעד|מטרה|משקל גוף|פרופיל|קלורי',message,re.I):return None
    if not re.search(r'\b(actually|correct|correction|change|update|instead)\b|בעצם|תתקן|תקן|תעדכן|עדכן',message,re.I):return None
    if re.search(r'\?|\b(what if|could|should|would|don\x27t|do not|not|never|לא)\b|אל ת|האם|אולי',message,re.I):return None
    amounts=re.findall(r'(\d+(?:\.\d+)?)\s*(?:grams?\b|g\b|גרמים|גרם)',message,re.I)
    if not amounts:return None
    hebrew=bool(re.search('[\u0590-\u05ff]',message))
    result={'ingredients':[],'uncertainties':[],'context_date':day,'advisory':'No new meal has been added.'}
    def clarify(english,hebrew_text):
        return {**result,'reply':hebrew_text if hebrew else english}
    if len(amounts)!=1:
        return clarify('Correct one food and gram amount at a time.','אפשר לתקן מזון אחד וכמות אחת בגרמים בכל הודעה.')
    if not saved_meals:
        from .nutrition import daily_status
        saved_meals=[{'id':meal['id'],'revision':meal['revision'],'meal_type':meal['meal_type']} for meal in daily_status(date.fromisoformat(day),tz,path)['meals'] if not meal['deleted_at']][-10:]
    if not saved_meals:
        return clarify('Which saved meal should I correct? Continue from its food report or edit it in Nutrition.','איזו ארוחה לתקן? אפשר להמשיך מהדיווח שלה בשיחה או לערוך אותה בתזונה.')
    if not isinstance(saved_meals,list) or len(saved_meals)>10:raise ValueError('Invalid saved meal references')
    grams=number(float(amounts[0]),'Corrected grams',.01,10000)
    fingerprint=request_hash(message,day,tz,meal_type)
    from .nutrition import _meal
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        previous=replay(operation_id,fingerprint,c=c)
        if previous:return previous
        meals=[]
        for ref in saved_meals:
            if not isinstance(ref,dict) or not isinstance(ref.get('id'),str) or type(ref.get('revision')) is not int:
                raise ValueError('Invalid saved meal reference')
            meal=_meal(c,ref['id'])
            if meal['deleted_at'] or meal['revision']!=ref['revision']:
                return clarify('That meal changed since this conversation. Open Nutrition to review the current entry.','הארוחה השתנתה מאז ההודעה הקודמת. יש לבדוק את הרישום העדכני בתזונה לפני תיקון.')
            meals.append(meal)
        candidates=[(meal,index,item) for meal in meals for index,item in enumerate(meal['items'])]
        named=[entry for entry in candidates if entry[2]['name'].casefold() in message.casefold()]
        chosen=named if named else candidates if len(candidates)==1 else []
        if len(chosen)!=1:
            names=', '.join(item['name'] for _,_,item in candidates)
            return clarify('Which food should I correct? Send its name and gram amount: '+names,'איזה מזון לתקן? יש לשלוח את שמו ואת הכמות בגרמים: '+names)
        meal,index,item=chosen[0]
        if item['unit']!='g':
            return clarify('This entry uses servings or millilitres. Edit it in Nutrition to change its measurement basis.','הרישום הזה משתמש במנות או במיליליטרים. יש לערוך אותו בתזונה כדי לשנות את יחידת המדידה.')
        items=[]
        for i,stored in enumerate(meal['items']):
            detail=stored['detail'];values=detail.get('per_100g')
            if values is None:
                values={k:None if stored[k] is None else stored[k]*100/stored['quantity'] for k in NUTRIENTS} if stored['unit']=='g' else {k:stored[k] for k in NUTRIENTS}
            items.append({'name':stored['name'],'quantity':grams if i==index else stored['quantity'],'unit':stored['unit'],
                'nutrients':values,'nutrient_basis':'per_100g' if stored['unit']=='g' else 'portion',
                'source':stored['source'],'portion_basis':detail.get('portion_basis','estimated'),
                'uncertainty':(detail.get('uncertainty','')+' User corrected quantity in chat.').strip() if i==index else detail.get('uncertainty','')})
        preview=preview_meal({'eaten_at':meal['eaten_at'],'timezone':tz,'meal_type':meal['meal_type'],'notes':meal['notes'],'items':items})
        saved=_save_meal(c,preview,'chat-correction-'+hashlib.sha256(operation_id.encode()).hexdigest(),meal['id'],meal['revision'])
        refs=[{'id':m['id'],'meal_type':m['meal_type'],'revision':saved['revision'] if m['id']==saved['id'] else m['revision']} for m in meals]
        reply=f"Updated {item['name']} to {grams:g} g in the existing meal. Daily calories and macros were recalculated; no duplicate meal was added."
        if hebrew:reply=f"עודכנה הכמות של {item['name']} ל־{grams:g} גרם בארוחה הקיימת. סיכומי הקלוריות והערכים התזונתיים חושבו מחדש."
        result.update(logged=True,updated=True,saved_meals=refs,context_date=preview['local_date'],reply=reply,advisory='Existing meal updated locally with revision history.')
        add_saved_feedback(result,[saved],preview['local_date'],tz,c,message)
        c.execute('INSERT INTO nutrition_chat_operations(operation_id,request_hash,result_json) VALUES(?,?,?)',(operation_id,fingerprint,encoded(result)))
    return result


def pending_save_intent(message, pending, history=None):
    """Authorize only a current save instruction about an existing food proposal."""
    if not pending:return False
    value=message.lower().replace('’',"'")
    if re.search(r"\?|\b(what|how|did|was|were|if|maybe|should|could|would|don't|do not|not|never|לא|אם|אולי|האם)\b|אל תשמור|אל תרשום|אל תוסיף|אל תתעד|ששמרת|תאשר ששמר|נשמר|תועד",value):return False
    if re.search(r'\b(goal|target|plan|workout)\b|יעד|מטרה|אימון',value):return False
    last=next((turn['content'] for turn in reversed(history or []) if turn['role']=='assistant'),'')
    if re.fullmatch(r'\s*(?:approved|approve|confirmed|confirm|go ahead|do it|מאשר|מאשרת|מאושר)[.!\s]*',value):
        return not bool(re.search(r'\b(target|goal)\b|יעד|מטרה',last,re.I))
    if re.fullmatch(r'\s*(?:yes|yes please|yep|sure|ok|okay|correct|כן|כן בבקשה|נכון|בטח|אוקיי)[.!\s]*',value):
        if re.search(r'\b(target|goal)\b|יעד|מטרה',last,re.I):return False
        return bool(re.search(r'confirm|approv|log|save|record|add|portion|propos|grams?|\b\d+(?:\.\d+)?\s*g\b|look right|look good|לאשר|אישור|לשמור|לתעד|להוסיף|גרם',last,re.I))
    if re.search(r'\b(log|save|record|add|שמור|תשמור|לשמור|רשום|תרשום|תעד|תתעד|לתעד|הוסף|תוסיף|להוסיף)\b',value):return True
    # A common dictated add-command typo is accepted only with an explicit affirmation and meal destination.
    if 'תוסף' in value and re.search(r'מאה אחוז|מאשר|יש אישור',value) and re.search(r'סנאקס|נשנוש|ארוח',value):return True
    return False


def pending_meal_destination(message):
    matches=[kind for kind,pattern in (
        ('breakfast',r'\bbreakfast\b|ארוחת בוקר'),('lunch',r'\blunch\b|ארוחת צהריים'),
        ('dinner',r'\b(dinner|supper)\b|ארוחת ערב'),('snack',r'\bsnacks?\b|סנאקס|נשנוש')) if re.search(pattern,message,re.I)]
    return matches[0] if len(matches)==1 else None


def consumption_report(message):
    value=message.lower().replace('’',"'")
    if re.search(r'^\s*(?:what|how|is|are|does|do|can|should|did|tell me|show|מה|כמה|האם)\b',value):return False
    if re.search(r"\b(if|hypothetically|would|might|will|planning|plan to|didn't|did not|haven't|have not|don't log|do not log|don't save|do not save|אם)\b|לא אכלתי|אל ת(?:שמור|רשום|עד|תעד|וסיף)|לא (?:לשמור|לתעד|להוסיף)",value):return False
    if re.search(r'\bi (?:just |already )?(?:ate|aet|had|have eaten)\b|\b(?:log|record|save)\s+(?:this|that|my|the|a)\s+(?:meal|food|breakfast|lunch|dinner|snack)\b|אכלתי|\b(?:תרשום|תשמור|שמור|רשום|תתעד|תעד)\b',value):return True
    # Meal-led diary entries often omit "I"; a portion or past-tense verb
    # distinguishes a report from a general discussion of breakfast or food.
    if re.search(r'\b(should|could|would|want|suggest|recommend|example|recipe)\b',value):return False
    return bool(re.search(r'(?:^|[;.\n]|\b(?:for|at)\s+)(?:breakfast|lunch|dinner|supper|snacks?)\s*(?::|[-–]|(?:i\s+)?(?:ate|aet|had)\b|\d+\b)',value))


def request_hash(message,day,tz,meal_type):
    return hashlib.sha256(encoded([message,day,tz,meal_type]).encode()).hexdigest()


def replay(operation_id,fingerprint,path=None,c=None):
    if c is None:
        with connect(path) as connection:return replay(operation_id,fingerprint,c=connection)
    row=c.execute('SELECT * FROM nutrition_chat_operations WHERE operation_id=?',(operation_id,)).fetchone()
    if row:
        if row['request_hash']!=fingerprint:raise ValueError('This message identity already belongs to a different nutrition request.')
        result=json.loads(row['result_json']);result['replayed']=True
        return result


def nutrient_source(item):
    """Prefer sourced matches; retain clearly attributed model estimates as fallback."""
    def key(value):return re.sub(r'[^\w]+',' ',value.lower()).strip()
    name=key(item['name'])
    candidates=item.get('lookup',{}).get('foods',[])
    exact=[f for f in candidates if key(f['name'])==name and f.get('basis')=='per_100g']
    if len(exact)==1:return exact[0],''
    references={
        'egg':'Eggs, Grade A, Large, egg whole','eggs':'Eggs, Grade A, Large, egg whole','ביצים':'Eggs, Grade A, Large, egg whole','ביצה':'Eggs, Grade A, Large, egg whole',
        'raw tahini paste':'Sesame butter, creamy','raw tahini':'Sesame butter, creamy','טחינה גולמית':'Sesame butter, creamy',
        'avocado':'Avocado, Hass, peeled, raw','אבוקדו':'Avocado, Hass, peeled, raw'}
    reference=references.get(name)
    food=next((f for f in catalog()['foods'] if key(f['name'])==key(reference or '')),None)
    if food:
        return {'source':catalog()['source'],'source_url':f"https://fdc.nal.usda.gov/food-details/{food['id']}/nutrients",'nutrients':{k:food[k] for k in NUTRIENTS}},'Generic food reference: '+food['name']+'. Preparation, size/variety and added ingredients may differ.'
    from .food_vision import nutrient_estimate
    estimate=nutrient_estimate(item.get('nutrients_per_100g'))
    if estimate and any(v is not None for v in estimate.values()):
        assumptions=text(item.get('estimate_assumptions',''),'Nutrient assumptions',1000,True)
        return {'source':'AI nutrition estimate; not a verified label or database match','source_url':'','nutrients':estimate},'Approximate composition per 100 g. '+assumptions
    return None,'No unambiguous nutrient match or supportable estimate; nutrients remain unknown.'


def log_result(result,message,day,tz,meal_type,operation_id,path=None,now=None):
    """Atomic multi-meal save and durable receipt; never execute model instructions."""
    result=copy.deepcopy(result)
    fingerprint=request_hash(message,day,tz,meal_type)
    operation_id=text(operation_id,'Nutrition message identity',120)
    now=now or datetime.now(timezone.utc);local=now.astimezone(zone(tz))
    logged_day=date.fromisoformat(day)
    explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)
    if len(set(explicit))>1:raise ValueError('Use one date per food report; nothing was logged.')
    from .nutrition_drafts import requested_day
    selected_day=requested_day(message,local.date().isoformat())
    if selected_day:logged_day=date.fromisoformat(selected_day)
    if logged_day>local.date():raise ValueError('This food report is dated in the future; nothing was logged.')
    eaten=local if logged_day==local.date() else datetime.combine(logged_day,time(12),zone(tz))
    notes='Logged from a nutrition chat food report. Portions are estimates unless specified. Time is the logging time.' if logged_day==local.date() else 'Logged from a nutrition chat food report. Meal time was not supplied; noon is a date placeholder. Portions are estimates unless specified.'
    grouped={}
    for food in result['ingredients']:
        kind=food.get('meal_type',meal_type)
        if kind not in ('breakfast','lunch','dinner','snack','meal'):raise ValueError('Invalid meal type; nothing was logged.')
        low=number(food['grams_low'],'Portion lower',0,10000);high=number(food['grams_high'],'Portion upper',low,10000)
        grams=number(food.get('grams_proposed') if food.get('grams_proposed') is not None else (low+high)/2,'Estimated portion',.01,10000)
        if not low<=grams<=high:raise ValueError('The proposed portion is outside its range; nothing was logged.')
        source,assumptions=nutrient_source(food)
        uncertainty=f'{low:g}–{high:g} g estimated range; logged {grams:g} g. '+assumptions
        grouped.setdefault(kind,[]).append({'name':food['name'],'quantity':grams,'unit':'g','nutrients':source['nutrients'] if source else {k:None for k in NUTRIENTS},'nutrient_basis':'per_100g' if source else 'portion','source':' · '.join(filter(None,[source['source'],source['source_url']])) if source else 'Nutrition chat food identity; nutrient source unknown','portion_basis':'estimated','uncertainty':uncertainty})
    previews=[preview_meal({'eaten_at':eaten.isoformat(),'timezone':tz,'meal_type':kind,'notes':notes,'items':items}) for kind,items in grouped.items()]
    if not previews:return result
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        previous=replay(operation_id,fingerprint,c=c)
        if previous:return previous
        meals=[_save_meal(c,p,'nutrition-chat-'+hashlib.sha256((operation_id+':'+p['meal_type']).encode()).hexdigest()) for p in previews]
        result.update(logged=True,context_date=logged_day.isoformat(),saved_meals=[{'id':m['id'],'meal_type':m['meal_type'],'revision':m['revision']} for m in meals])
        foods='; '.join(p['meal_type']+': '+', '.join(f"{i['name']} ({i['quantity']:g} g)" for i in p['items']) for p in previews)
        partial=any(m['totals'][k]['missing_items'] for m in meals for k in NUTRIENTS)
        from .nutrition import totals
        intake=totals([item for meal in meals for item in meal['items']])
        result['logged_totals']=intake
        kcal=intake['calories_kcal'];calories=f"{kcal['known_total']:g} kcal" if not kcal['missing_items'] else f"{kcal['known_total']:g} kcal known (partial; {kcal['missing_items']} foods need a calorie estimate)"
        result['reply']=f'Logged {foods} for {logged_day.isoformat()}. Added {calories} to your daily intake. Portions and nutrients are estimates.'+(' Some nutrients are unknown; your totals are marked partial.' if partial else '')+' You can edit or remove the entry in Nutrition.'
        if re.search('[\u0590-\u05ff]',message):result['reply']=f"נשמר ביומן לתאריך {logged_day.isoformat()}: {foods}. נוספו לסיכום היומי כ־{kcal['known_total']:g} קלוריות"+(' (סיכום חלקי; חסרה הערכת קלוריות לחלק מהמזונות)' if kcal['missing_items'] else '')+'. הכמויות והערכים התזונתיים הם הערכות. אפשר לערוך או להסיר בתזונה.'+(' חלק מהערכים חסרים והסיכום חלקי.' if partial else '')
        result['advisory']='Saved locally. Estimated portions and nutrient sources remain available in the meal details.'
        add_saved_feedback(result,meals,logged_day.isoformat(),tz,c,message)
        c.execute('INSERT INTO nutrition_chat_operations(operation_id,request_hash,result_json) VALUES(?,?,?)',(operation_id,fingerprint,encoded(result)))
    return result
