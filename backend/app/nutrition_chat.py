"""Nutrition conversation; app callers also save clear food reports directly."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .food_vision import analyze_food
from .food_lookup import portion_reference, search_foods
from .nutrition import daily_status, list_library, text, number


def calorie_preference(message, pending_target):
    """Keep explicit target corrections even if the model drops the new field."""
    if re.search(r"\b(?:ate|eaten|burned|burnt|remaining|don't|do not|not change)\b|אכלתי|שרפתי|אל תשנה",message,re.I):return None
    amount=r'((?:\d{1,2},\d{3}|\d{3,5})(?:\.\d+)?)'
    match=re.search(amount+r'\s*(?:kcal\b|calories\b|קלוריות)',message,re.I)
    target_intent=re.search(r'\b(?:target|goal|aim|set|change|go to|switch|try)\b|יעד|מטרה|תגדיר|תשנה',message,re.I)
    if not match and pending_target:
        match=re.search(r'\b(?:go|switch|change|set|try|make)\s+(?:it\s+)?(?:to\s+)?'+amount+r'(?!\d)',message,re.I)
    if not match and target_intent:
        match=re.search(r'\b(?:goal|target)\s+(?:(?:should|will)\s+)?(?:to|at|be|is)\s+'+amount+r'(?!\d)',message,re.I)
    if match and target_intent:return float(match[1].replace(',',''))
    return None


def target_save_intent(message, pending_target, turns):
    if re.search(r"\b(?:don't|do not|not yet|maybe|could|should|would|think|what if)\b|\?|אל תשמור|אולי",message,re.I):return False
    if re.search(r'^\s*(?:(?:please|now)\s+|i (?:want|would like) (?:you )?to\s+|let[’\x27]s\s+)?(?:set|save|apply|update|change)\b.*\b(?:goal|target|calories)\b|^\s*(?:בבקשה\s+)?(?:תשמור|תגדיר|תעדכן).*?(?:יעד|מטרה|קלוריות)',message,re.I):return True
    if pending_target and re.fullmatch(r'\s*(?:yes|yes please|confirm|confirmed|ok|okay|save it|apply it|set it|כן|מאשר|מאשרת|תשמור)[.!\s]*',message,re.I):
        if turns and re.search(r'\b(meal|foods?|portions?)\b|ארוחה|מזון|מנה',turns[-1]['content'],re.I) and not re.search(r'\b(target|goal)\b|יעד|מטרה',turns[-1]['content'],re.I):return False
        return bool(turns and turns[-1]['role']=='assistant' and re.search(r'review|before saving|confirm|לא נשמר|אישור',turns[-1]['content'],re.I))
    return False


def save_chat_target(result, proposal, message, day, tz, meal_type, operation_id, path):
    """Save target, selected day's snapshot and retry receipt in one transaction."""
    from .database import connect
    from .nutrition import persist_target, encoded
    from .nutrition_logging import replay, request_hash
    fingerprint=request_hash(message,day,tz,meal_type)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        previous=replay(operation_id,fingerprint,c=c)
        if previous:return previous
        saved=persist_target(proposal['preview'],proposal['expected_revision'],path,connection=c)
        saved['day_type']='manual'
        c.execute('INSERT INTO nutrition_day_targets(calendar_date,timezone,target_id,snapshot_json) VALUES(?,?,?,?) ON CONFLICT(calendar_date,timezone) DO UPDATE SET target_id=excluded.target_id,snapshot_json=excluded.snapshot_json',(day,tz,saved['id'],encoded(saved)))
        result.update(target_saved=True,saved_target=saved,target_proposal={**proposal,'status':'saved','saved':True})
        kcal=saved['calories_kcal']
        result['reply']=f"Saved your daily target from {day}: {kcal:g} kcal, {saved['protein_grams']} g protein, {saved['fat_grams']} g fat and {saved['carbohydrate_grams']} g carbohydrate. Your daily goal and remaining intake have been updated."
        if re.search('[\u0590-\u05ff]',message):result['reply']=f"נשמר יעד יומי מתאריך {day}: {kcal:g} קלוריות, {saved['protein_grams']} גרם חלבון, {saved['fat_grams']} גרם שומן ו־{saved['carbohydrate_grams']} גרם פחמימות. היעד והיתרה היומית עודכנו."
        if proposal['preview']['assumptions'].get('requested_calories_kcal') is not None:
            for warning in saved.get('warnings',[]):
                if 'more aggressive' in warning:result['reply']+=' '+warning.replace('before saving','as you follow this target')
        result['advisory']='Target saved locally; calories and macros remain estimates.'
        c.execute('INSERT INTO nutrition_chat_operations(operation_id,request_hash,result_json) VALUES(?,?,?)',(operation_id,fingerprint,encoded(result)))
    return result


def chat(message, day, timezone_name, history=None, draft_items=None, meal_type='meal', path=None, pending_target=None, pending_foods=None, *, auto_log=False, operation_id=None, allow_target_save=True, message_time=None, saved_meals=None, pending_correction=None):
    message = text(message, 'Nutrition message', 4000)
    import uuid
    from .nutrition_logging import consumption_report,replay,request_hash,log_result
    operation_id=operation_id or str(uuid.uuid4())
    replacing_removed=bool(pending_correction and re.search(r'\b(add|log|save)\b',message,re.I) and re.search(r'\b(removed|deleted)\b',message,re.I))
    if auto_log:
        operation_id=text(operation_id,'Nutrition message identity',120)
        previous=replay(operation_id,request_hash(message,day,timezone_name,meal_type),path)
        if previous:return previous
        from .nutrition_move import move_logged_meal
        moved=move_logged_meal(message,saved_meals,day,timezone_name,meal_type,operation_id,path,now=message_time,history=history)
        if moved is not None:return moved
        from .nutrition_logging import correct_portion
        correction=correct_portion(message,saved_meals,day,timezone_name,meal_type,operation_id,path)
        if correction is not None:return correction
        from .nutrition_correction import correct_ingredient
        correction=correct_ingredient(message,saved_meals,day,timezone_name,meal_type,operation_id,path,history,pending_foods=pending_foods,pending_correction=None if replacing_removed else pending_correction)
        if correction is not None:return correction
    history = history or []
    if not isinstance(history, list) or len(history) > 12:
        raise ValueError('Keep at most 12 nutrition conversation turns')
    turns = []
    for turn in history:
        if not isinstance(turn, dict) or set(turn) != {'role', 'content'} or turn['role'] not in ('user', 'assistant'):
            raise ValueError('Invalid nutrition conversation turn')
        turns.append({'role': turn['role'], 'content': text(turn['content'], 'Nutrition turn', 6000)})
    if not isinstance(draft_items or [], list) or len(draft_items or []) > 30:
        raise ValueError('Keep at most 30 draft food descriptions')
    draft = [text(item, 'Draft food', 500) for item in draft_items or []]
    pending = []
    if not isinstance(pending_foods or [], list) or len(pending_foods or []) > 30:
        raise ValueError('Keep at most 30 pending foods')
    for item in pending_foods or []:
        if not isinstance(item, dict) or set(item)-{'name','grams_low','grams_high','grams_proposed','question','meal_type','nutrients_per_100g','estimate_assumptions'}:
            raise ValueError('Invalid pending food review')
        kind = item.get('meal_type', meal_type)
        if kind not in ('breakfast','lunch','dinner','snack','meal'):
            raise ValueError('Invalid pending meal')
        low = number(item.get('grams_low'), 'Pending portion', 0, 10000)
        high = number(item.get('grams_high'), 'Pending portion', low, 10000)
        pending.append({'name':text(item.get('name'),'Pending food',200),'grams_low':low,'grams_high':high,'question':text(item.get('question',''),'Pending question',1500,True),'meal_type':kind})
        if item.get('grams_proposed') is not None:
            pending[-1]['grams_proposed']=number(item['grams_proposed'],'Pending proposal',low,high)
        if 'nutrients_per_100g' in item:
            from .food_vision import nutrient_estimate
            pending[-1]['nutrients_per_100g']=nutrient_estimate(item['nutrients_per_100g'])
        if item.get('estimate_assumptions'):
            pending[-1]['estimate_assumptions']=text(item['estimate_assumptions'],'Pending nutrient assumptions',1000,True)
    from .nutrition_drafts import cancel_pending
    retained,cancelled=cancel_pending(message,pending)
    if cancelled:
        return {'ingredients':retained,'uncertainties':[],'context_date':day,'pending_foods_replaced':True,
                'reply':'Removed the specified food from the pending request. Other pending foods are retained; nothing new was logged.' if not re.search('[\u0590-\u05ff]',message) else 'הסרתי את המזון שביקשת מהבקשה הממתינה. שאר המזונות נשמרו לבדיקה; לא נוסף רישום חדש.'}
    if pending_target is not None and not isinstance(pending_target,dict):raise ValueError('Invalid target request')
    from .nutrition_logging import pending_save_intent,pending_meal_destination,nutrient_source
    if auto_log and not pending and saved_meals and re.search(r'\b(it|them|that|those|again)\b|את זה|אותן|אותם|שוב',message,re.I) and pending_save_intent(message,[True],turns):
        from .database import connect
        from .nutrition import _meal
        if not isinstance(saved_meals,list) or len(saved_meals)>10:raise ValueError('Invalid saved meal references')
        with connect(path) as c:
            meals=[_meal(c,ref['id']) for ref in saved_meals]
        active=[meal for meal in meals if not meal['deleted_at']]
        if len(active)==len(meals):
            refs=[{'id':meal['id'],'meal_type':meal['meal_type'],'revision':meal['revision']} for meal in active]
            reply='The referenced meal is already in the log. No duplicate was added.'
            if re.search('[\u0590-\u05ff]',message):reply='הארוחה שאליה התייחסת כבר שמורה ביומן. לא נוספה ארוחה כפולה.'
            return {'reply':reply,'ingredients':[],'uncertainties':[],'logged':True,'already_logged':True,'saved_meals':refs,'context_date':day}
    log_followup=auto_log and pending_save_intent(message,pending,turns) and not target_save_intent(message,pending_target,turns)
    destination=pending_meal_destination(message) if log_followup else None
    if destination:
        for item in pending:item['meal_type']=destination
    if log_followup and all(nutrient_source(item)[0] is not None for item in pending):
        return log_result({'ingredients':pending,'uncertainties':[],'reply':'','model':'retained_food_proposal'},
            message,day,timezone_name,meal_type,operation_id,path,now=message_time)
    status = daily_status(date.fromisoformat(day), timezone_name, path)
    from .nutrition_targets import recorded_context, propose
    context = {'date': day, 'timezone': timezone_name, 'meal_type': meal_type, 'conversation': turns,
               'draft_foods': draft, 'daily_totals': status['totals'], 'remaining': status['remaining'],
               'target': status['target'], 'logged_meals': [{'meal_type': meal['meal_type'], 'foods': [item['name'] for item in meal['items']]} for meal in status['meals'] if not meal['deleted_at']],
               'saved_meals': [item['name'] for item in list_library(path)[:20]],
               'anthropometrics_and_activity': recorded_context(day, path), 'pending_target_request': pending_target, 'pending_food_review': pending}
    if replacing_removed:context['removed_food_replacement']=pending_correction
    try:
        result = analyze_food(message=message, path=path, review_context=context, conversational=True)
    except ValueError:
        if not log_followup:raise
        # Approval already identifies the meal and quantities. Missing nutrient
        # enrichment must not block saving that approved meal as partial.
        return log_result({'ingredients':pending,'uncertainties':[],'reply':'','model':'retained_food_proposal'},
            message,day,timezone_name,meal_type,operation_id,path,now=message_time)
    if pending and not log_followup and result.get('ingredients'):
        # Provider replies often contain only the clarified food. Preserve the
        # complete unresolved request rather than replacing it with that subset.
        def food_key(item):return (item.get('meal_type',meal_type), ' '.join(item['name'].casefold().split()))
        merged={food_key(item):dict(item) for item in pending}
        for item in result['ingredients']:
            key=food_key(item);merged[key]={**merged.get(key,{}),**item}
        result['ingredients']=list(merged.values())
    if log_followup:
        # An approval confirms retained foods; another model pass cannot substitute different foods or quantities.
        enrich={item['name'].casefold():item for item in result['ingredients']}
        approved=[]
        for item in pending:
            proposed=enrich.get(item['name'].casefold(),{})
            merged={**item}
            for key in ('nutrients_per_100g','estimate_assumptions'):
                if not merged.get(key) and proposed.get(key):merged[key]=proposed[key]
            approved.append(merged)
        return log_result({**result,'ingredients':approved},message,day,timezone_name,meal_type,operation_id,path,now=message_time)
    preference=calorie_preference(message,pending_target or status['target'])
    save_target=target_save_intent(message,pending_target,turns)
    if result.get('target_request') is not None or preference is not None or save_target and pending_target:
        request = result.get('target_request') if result.get('target_request') is not None else {}
        if not isinstance(request, dict) or pending_target is not None and not isinstance(pending_target, dict):
            raise ValueError('Invalid target request')
        current=status['target'] or {}
        previous={k:v for k,v in current.get('assumptions',{}).items() if k in ('goal','target_weight_kg')}
        if current and not pending_target and request.get('goal',previous.get('goal'))==previous.get('goal'):previous['calories_kcal']=current['calories_kcal']
        if save_target and pending_target and re.fullmatch(r'\s*(?:yes|yes please|confirm|confirmed|ok|okay|save it|apply it|set it|כן|מאשר|מאשרת|תשמור)[.!\s]*',message,re.I):request={}
        request = {**previous, **(pending_target or {}), **{key:value for key,value in request.items() if value is not None}}
        if preference is not None:request['calories_kcal']=preference
        result['target_request']=request
        proposal = propose(request, day, path)
        result['target_proposal'] = proposal
        if proposal['questions']:
            result['reply'] = ' '.join(proposal['questions'])
        elif proposal['status'] == 'proposal':
            preview = proposal['preview']
            label = {'lose_weight': 'gradual weight loss', 'maintain': 'maintenance', 'gain_muscle': 'gradual muscle gain'}[request['goal']]
            result['reply'] = f"Here is a starting target for {label}: {preview['calories_kcal']} kcal, {preview['protein_grams']} g protein, {preview['fat_grams']} g fat and {preview['carbohydrate_grams']} g carbohydrate per day. It uses your recorded body measurements and recent activity. Review it before saving. Nothing has been saved."
            if re.search('[\u0590-\u05ff]', message):
                result['reply'] = f"הכנתי הצעה לבדיקה: {preview['calories_kcal']} קלוריות, {preview['protein_grams']} גרם חלבון, {preview['fat_grams']} גרם שומן ו־{preview['carbohydrate_grams']} גרם פחמימות ביום. החישוב משתמש במדידות הגוף ובהיסטוריית הפעילות שלך. ההצעה עדיין לא נשמרה; אפשר לשנות אותה לפני האישור."
            if request.get('calories_kcal') is not None:
                assumptions=preview['assumptions']
                result['reply']=f"At your requested {preview['calories_kcal']:g} kcal/day, the recalculated targets are {preview['protein_grams']} g protein, {preview['fat_grams']} g fat and {preview['carbohydrate_grams']} g carbohydrate. Estimated maintenance is {assumptions['maintenance_kcal']} kcal/day; the calculated starting target is {assumptions['calculated_calories_kcal']} kcal/day. Review this proposal and say 'save it' to save the goal. Nothing has been saved."
                if re.search('[\u0590-\u05ff]',message):result['reply']=f"ליעד שביקשת, {preview['calories_kcal']:g} קלוריות ביום, היעדים המחושבים מחדש הם {preview['protein_grams']} גרם חלבון, {preview['fat_grams']} גרם שומן ו־{preview['carbohydrate_grams']} גרם פחמימות. אומדן התחזוקה הוא {assumptions['maintenance_kcal']} והיעד המחושב ההתחלתי הוא {assumptions['calculated_calories_kcal']}. אפשר לבדוק ולאשר בשיחה כדי לשמור. ההצעה עדיין לא נשמרה."
                result['reply']+=' '+' '.join(w for w in preview['warnings'] if 'more aggressive' in w)
        result['context_date']=day
        result['advisory']='Review the target proposal; nothing has been saved.'
        if auto_log and allow_target_save and save_target and proposal['status']=='proposal':
            return save_chat_target(result,proposal,message,day,timezone_name,meal_type,operation_id,path)
        return result
    # Only the food identity leaves for the product database, never context/history.
    with ThreadPoolExecutor(max_workers=3) as pool:
        lookups = list(pool.map(search_foods, [item['name'] for item in result['ingredients'][:3]]))
    user_context = '\n'.join([turn['content'] for turn in turns if turn['role'] == 'user'] + [message])
    confirmations = []
    hebrew = bool(re.search('[\u0590-\u05ff]', message))
    affirmative = bool(turns and turns[-1]['role'] == 'assistant' and re.fullmatch(r'\s*(כן|נכון|מאשר|מאשרת|בטח|yes|yep|sure|correct|confirmed|ok|okay)[.!\s]*', message, re.I))
    negative = bool(re.fullmatch(r'\s*(לא|no|nope)[.!\s]*', message, re.I))
    for index, item in enumerate(result['ingredients']):
        item['portion_confirmed'] = False
        item['lookup'] = lookups[index] if index < len(lookups) else {'status': 'not_requested', 'foods': [], 'source': 'Open Food Facts'}
        family = r'יוגורט|yog[hu]*urt' if re.search(r'יוגורט|yog[hu]*urt', item['name'], re.I) else r'קוטג|cottage' if re.search(r'קוטג|cottage', item['name'], re.I) else None
        mentions = list(re.finditer(family, user_context, re.I)) if family else []
        portion_context = user_context if len(result['ingredients']) == 1 else user_context[max(0, mentions[-1].start()-24):mentions[-1].end()] if mentions else ''
        reference = portion_reference(item['name'], portion_context)
        if len(result['ingredients']) > 1 and reference and item['grams_low'] == item['grams_high'] and item['grams_low'] != reference['grams']:
            reference = None
        # Explicit grams in a single-food correction take priority over a common tub.
        explicit = re.search(r'(\d+(?:\.\d+)?)\s*(?:גרם|גרמים|ג[\u05f3\u05f4"\']|grams?\b|g\b)', message, re.I)
        if len(result['ingredients']) == 1 and explicit:
            grams = float(explicit[1])
            if 0 < grams <= 10000:
                item['grams_low'] = item['grams_high'] = grams
                item['grams_proposed'] = grams
                item['portion_confirmed'] = True
                reference = None
        elif reference and not affirmative and not negative:
            item['grams_low'] = item['grams_high'] = reference['grams']
            item['grams_proposed'] = reference['grams']
            item['question'] = f"לאשר {reference['grams']:g} גרם של {item['name']}? אפשר לתקן את המשקל או לציין מותג." if hebrew else f"Confirm {reference['grams']:g} g of {item['name']}? You can correct the weight or name the brand."
            confirmations.append(item['question'])
        if affirmative and len(result['ingredients']) == 1 and item['grams_low'] == item['grams_high']:
            item['portion_confirmed'] = True
            if reference and item['grams_low'] == item['grams_high'] == reference['grams']:
                reference['confirmed'] = True
            else:
                reference = None
            item['question'] = ''
            result['reply'] = f"אושר: {item['name']}, {item['grams_low']:g} גרם. אפשר לבחור התאמה למוצר ולהוסיף לארוחה לבדיקה." if hebrew else f"Confirmed: {item['name']}, {item['grams_low']:g} g. Choose the matching product and add it to the meal for review."
        item['portion_reference'] = reference
    if confirmations:
        result['reply'] = '\n'.join(confirmations)
    result['context_date'] = day
    result['advisory'] = 'Review the proposed food, package and amount. Product matches are candidates; select the label that matches what you ate. Nothing has been logged.'
    if auto_log and (consumption_report(message) or log_followup or replacing_removed) and result['ingredients'] and not result.get('target_proposal'):
        result=log_result(result,message,day,timezone_name,meal_type,operation_id,path,now=message_time)
    return result
