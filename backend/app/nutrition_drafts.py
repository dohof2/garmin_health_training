"""Daily food context. Unfinished requests never migrate to another day."""
import re
from datetime import date,timedelta


def new_day(context,today):
    return {'day':today}


def mentions_yesterday(message):
    if re.search(r'\b(?:yesterday|yestarday|yetarday|yesyerday|yesterdya|esterady|yestareday)\b|אתמול',message,re.I):return True
    # Bound typo tolerance to plausible date words, rather than maintaining a
    # separate spelling list in every logging/move/confirmation route.
    for word in re.findall(r'[a-z]+',message.lower()):
        if not 6<=len(word)<=10 or not word.startswith(('ye','es')):continue
        distances=list(range(len('yesterday')+1))
        for i,char in enumerate(word,1):
            next_row=[i]
            for j,target in enumerate('yesterday',1):
                next_row.append(min(next_row[-1]+1,distances[j]+1,distances[j-1]+(char!=target)))
            distances=next_row
        if distances[-1]<=2:return True
    return False


def requested_day(message,today):
    """Use the same explicitly requested food date for analysis and storage."""
    explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)
    if explicit:return explicit[-1]
    if re.search(r'\btoday\b|להיום|היום',message,re.I):return today
    if mentions_yesterday(message):return (date.fromisoformat(today)-timedelta(days=1)).isoformat()
    return None


def select_context(context,message,today,history=None):
    if context.get('chat_day') and context['chat_day']!=today:context=new_day(context,today)
    requested=requested_day(message,today)
    from .nutrition_logging import consumption_report,pending_save_intent
    from .nutrition_move import move_request
    same_chat_day=context.get('chat_day')==today
    pending=bool(context.get('pending_foods') or context.get('pending_correction'))
    # Repair an older client's incorrectly dated pending proposal using the
    # human's original date instruction. Never derive a date from model prose.
    if not requested and same_chat_day and not context.get('date_selected') and pending_save_intent(message,context.get('pending_foods'),history):
        bound=next((requested_day(turn['content'],today) for turn in reversed(history or []) if turn.get('role')=='user' and requested_day(turn['content'],today)),None)
        if bound:context={**context,'day':bound}
    if not requested:requested=context.get('day') if context.get('date_selected') or (same_chat_day and (pending or context.get('saved_meals')) and not consumption_report(message)) else today
    active=dict(context) if context.get('day')==requested else new_day(context,requested)
    # A date correction must keep the identity of the source entry. Other date
    # changes still discard unfinished drafts, never importing an older day.
    if move_request(message) and (same_chat_day or context.get('day')==today) and context.get('saved_meals'):
        active['saved_meals']=context['saved_meals']
    active.pop('pending_drafts',None)
    active['day']=requested
    return active,[]


def cancel_pending(message,foods):
    if not re.search(r'\b(forget|discard|remove|delete|skip)\b|תשכח|שכח|תמחק|להתעלם',message,re.I):return foods,False
    all_foods=bool(re.search(r'\b(all|everything)\b|הכל|הכול',message,re.I))
    meals=[kind for kind,pattern in {'breakfast':r'breakfast|בוקר','lunch':r'lunch|צהריים','dinner':r'dinner|supper|ערב','snack':r'snack|נשנוש'}.items() if re.search(pattern,message,re.I)]
    words={word.casefold() for word in re.findall(r'[\w]+',message) if len(word)>=4}
    stems={word[:-2] if word.endswith('ים') else word[:-1] if word.endswith('s') else word for word in words}
    def remove(food):
        return all_foods or food.get('meal_type') in meals or any(stem in food['name'].casefold() for stem in stems if len(stem)>=4)
    retained=[food for food in foods if not remove(food)]
    return retained,len(retained)!=len(foods)
