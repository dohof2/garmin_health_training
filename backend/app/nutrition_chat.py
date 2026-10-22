"""Nutrition-only conversation, current meal context, and explicit lookup tools."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .food_vision import analyze_food
from .food_lookup import portion_reference, search_foods
from .nutrition import daily_status, list_library, text, number


def chat(message, day, timezone_name, history=None, draft_items=None, meal_type='meal', path=None, pending_target=None, pending_foods=None):
    message = text(message, 'Nutrition message', 4000)
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
        if not isinstance(item, dict) or set(item)-{'name','grams_low','grams_high','grams_proposed','question','meal_type'}:
            raise ValueError('Invalid pending food review')
        kind = item.get('meal_type', meal_type)
        if kind not in ('breakfast','lunch','dinner','snack','meal'):
            raise ValueError('Invalid pending meal')
        low = number(item.get('grams_low'), 'Pending portion', 0, 10000)
        high = number(item.get('grams_high'), 'Pending portion', low, 10000)
        pending.append({'name':text(item.get('name'),'Pending food',200),'grams_low':low,'grams_high':high,'question':text(item.get('question',''),'Pending question',1500,True),'meal_type':kind})
        if item.get('grams_proposed') is not None:
            pending[-1]['grams_proposed']=number(item['grams_proposed'],'Pending proposal',low,high)
    status = daily_status(date.fromisoformat(day), timezone_name, path)
    from .nutrition_targets import recorded_context, propose
    context = {'date': day, 'timezone': timezone_name, 'meal_type': meal_type, 'conversation': turns,
               'draft_foods': draft, 'daily_totals': status['totals'], 'remaining': status['remaining'],
               'target': status['target'], 'logged_meals': [{'meal_type': meal['meal_type'], 'foods': [item['name'] for item in meal['items']]} for meal in status['meals'] if not meal['deleted_at']],
               'saved_meals': [item['name'] for item in list_library(path)[:20]],
               'anthropometrics_and_activity': recorded_context(day, path), 'pending_target_request': pending_target, 'pending_food_review': pending}
    result = analyze_food(message=message, path=path, review_context=context, conversational=True)
    if result.get('target_request') is not None:
        request = result['target_request']
        if not isinstance(request, dict) or pending_target is not None and not isinstance(pending_target, dict):
            raise ValueError('Invalid target request')
        request = {**(pending_target or {}), **{key:value for key,value in request.items() if value is not None}}
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
    return result
