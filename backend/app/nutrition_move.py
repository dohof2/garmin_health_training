"""Move an existing food log to a corrected date, without copying its items."""
import re
from datetime import date,datetime,timedelta,timezone
from .database import connect
from .nutrition import _meal,_meal_revision,_freeze_target,encoded,zone


def move_request(message):
    from .nutrition_drafts import requested_day
    action=re.search(r'\b(move|reschedule|wrong|mistake|incorrect|change.{0,15}date|should.{0,15}(today|yesterday)|it was|it belongs)\b|טעות|תעביר|להעביר|העבר|שירשמו|לתאריך',message,re.I)
    destination=requested_day(message,'2000-01-02') is not None or re.search(r'\d{1,2}[./]\d{1,2}',message)
    negative=re.search(r"\b(don't|do not|never|what if|not)\b|אל תעביר|לא להעביר",message,re.I)
    other_domain=re.search(r'\b(goal|target|workout|ride|training|plan|weight)\b|אימון|יעד|מטרה',message,re.I)
    followup=re.fullmatch(r'\s*(?:please\s+)?move\s+(?:it|that|the entry)[.!\s]*',message,re.I)
    return bool((action and destination or followup) and not negative and not other_domain and '?' not in message)


def move_logged_meal(message,saved_meals,day,tz,meal_type,operation_id,path=None,now=None,history=None):
    from .nutrition_logging import request_hash,replay,add_saved_feedback
    now=now or datetime.now(timezone.utc);today=now.astimezone(zone(tz)).date()
    from .nutrition_drafts import requested_day
    move_text=message
    if re.fullmatch(r'\s*(?:please\s+)?move\s+(?:it|that|the entry)[.!\s]*',message,re.I):
        # Only human instructions establish a destination; model prose may have
        # hallucinated calendar dates and is never authority for a food move.
        prior=next((turn['content'] for turn in reversed(history or []) if turn.get('role')=='user' and requested_day(turn['content'],today.isoformat())),None)
        if not prior or re.search(r"\b(not|don't|do not|never|what if)\b|אל ת|לא להעביר",prior,re.I):return {'ingredients':[],'uncertainties':[],'context_date':day,'reply':'Which date should I move the saved entry to? Nothing has been changed.'}
        move_text='Move it to '+requested_day(prior,today.isoformat())
    if not move_request(move_text):return None
    dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',move_text)
    requested=requested_day(move_text,today.isoformat())
    if requested:target=date.fromisoformat(requested)
    else:
        short=re.findall(r'(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?(?!\d)',move_text)
        d,m,y=short[-1];target=date(int(y) if y else today.year,int(m),int(d))
    if target>today:raise ValueError('Food logs cannot be moved into the future.')
    kinds=[kind for kind,pattern in {'snack':r'\bsnacks?\b|נשנוש','lunch':r'\blunch\b|צהריים','dinner':r'\b(dinner|supper)\b|ארוחת ערב','breakfast':r'\bbreakfast\b|ארוחת בוקר'}.items() if re.search(pattern,message,re.I)]
    result={'ingredients':[],'uncertainties':[],'context_date':day,'advisory':'No new meal has been added.'}
    fingerprint=request_hash(message,day,tz,meal_type)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        previous=replay(operation_id,fingerprint,c=c)
        if previous:return previous
        candidates=[]
        for ref in saved_meals or []:
            try:meal=_meal(c,ref['id'])
            except ValueError:continue # A removed entry must never be resurrected.
            if meal['deleted_at'] or kinds and meal['meal_type'] not in kinds:continue
            if meal['revision']!=ref['revision']:
                return {**result,'reply':'That meal has changed. Review the current entry before moving it.'}
            candidates.append(meal)
        if not candidates:
            # Fresh daily chats find saved records, rather than importing an
            # old conversation. A named meal type selects its most recent log.
            rows=c.execute('SELECT id FROM meals WHERE deleted_at IS NULL ORDER BY created_at DESC,rowid DESC LIMIT 30').fetchall()
            available=[_meal(c,r['id']) for r in rows]
            if len(dates)>1:available=[m for m in available if datetime.fromisoformat(m['eaten_at']).astimezone(zone(tz)).date().isoformat()==dates[0]]
            named=[m for m in available if any(i['name'].casefold() in message.casefold() for i in m['items'])]
            candidates=named or [m for m in available if kinds and m['meal_type'] in kinds][:1]
            if not candidates and re.fullmatch(r'\s*(?:please\s+)?move\s+(?:it|that|the entry)[.!\s]*',message,re.I):
                # Older clients may have lost the saved ID when changing date.
                # Recover only a unique food named by the human, in the two
                # relevant days. Never select an arbitrary latest meal.
                bounded=[meal for meal in available if datetime.fromisoformat(meal['eaten_at']).astimezone(zone(tz)).date() in (today,target)]
                ignored={'yesterday','today','moved','move','removed','deleted','logged','lunch','dinner','supper','breakfast','entry','please','there','about','that','this','with','from'}
                for turn in reversed((history or [])[-12:]):
                    if turn.get('role')!='user':continue
                    words={word.casefold() for word in re.findall(r'\w+',turn['content']) if len(word)>=4}-ignored
                    matching=[meal for meal in bounded if any(words & {word.casefold() for word in re.findall(r'\w+',item['name']) if len(word)>=4} for item in meal['items'])]
                    if matching:
                        candidates=matching;break
        if dates and len(dates)>1:
            candidates=[m for m in candidates if datetime.fromisoformat(m['eaten_at']).astimezone(zone(tz)).date().isoformat()==dates[0]]
        if len(candidates)!=1:
            return {**result,'reply':'Which saved meal should I move? Specify snacks, breakfast, lunch or dinner and the destination date.'}
        meal=candidates[0];original=datetime.fromisoformat(meal['eaten_at']).astimezone(zone(tz));before=original.date().isoformat()
        if before!=target.isoformat():
            from .chat_access import authorize_nutrition_write
            authorize_nutrition_write(c)
            eaten=datetime.combine(target,original.time(),zone(tz)).astimezone(timezone.utc).isoformat()
            c.execute('UPDATE meals SET eaten_at=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND revision=?',(eaten,meal['id'],meal['revision']))
            _freeze_target(c,target.isoformat(),tz);_meal_revision(c,meal['id'])
        saved=_meal(c,meal['id']);foods=', '.join(i['name'] for i in saved['items'])
        result.update(logged=True,updated=before!=target.isoformat(),moved=True,context_date=target.isoformat(),
            saved_meals=[{'id':saved['id'],'meal_type':saved['meal_type'],'revision':saved['revision']}],
            moved_from=before,moved_to=target.isoformat(),reply=f"Moved {saved['meal_type']}: {foods}, from {before} to {target.isoformat()}. The same entry was updated; no duplicate was added. Both days’ totals now reflect the correction.",
            advisory='Existing food log date corrected with revision history.')
        if re.search('[\u0590-\u05ff]',message):result['reply']=f"העברתי את הרישום הקיים ({foods}) מ־{before} ל־{target.isoformat()}. לא נוצר רישום כפול. הסיכומים של שני הימים עודכנו."
        add_saved_feedback(result,[saved],target.isoformat(),tz,c,message)
        c.execute('INSERT INTO nutrition_chat_operations(operation_id,request_hash,result_json) VALUES(?,?,?)',(operation_id,fingerprint,encoded(result)))
    return result
