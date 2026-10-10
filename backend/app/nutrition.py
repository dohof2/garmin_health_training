"""Local food logging. Nutrient and portion estimates retain their source snapshots."""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import connect

NUTRIENTS = ('calories_kcal', 'protein_grams', 'fat_grams', 'carbohydrate_grams')
PORTIONS = ('weighed', 'label_serving', 'estimated', 'photo_estimate')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def number(value, name, low=0, high=100000):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number between {low} and {high}')
    return value


def text(value, name, limit=500, blank=False):
    if not isinstance(value, str) or len(value)>limit or (not blank and not value.strip()):
        raise ValueError(f'{name} must be text, up to {limit} characters')
    return value.strip()


def zone(name):
    try: return ZoneInfo(name)
    except (ZoneInfoNotFoundError, TypeError): raise ValueError('Choose a valid IANA timezone')


def timestamp(value):
    try: result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError, AttributeError): raise ValueError('Meal time must be an ISO timestamp')
    if result.tzinfo is None: raise ValueError('Meal time must include a timezone offset')
    return result.astimezone(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent/'resources/usda-foundation.json').read_text())


def food_search(query):
    query=text(query,'Search',120)
    tokens=query.casefold().split()
    foods=[f for f in catalog()['foods'] if all(t in f['name'].casefold() for t in tokens)]
    return {'foods':foods[:30], 'matches':len(foods), 'source':catalog()['source'], 'release':catalog()['release'],
            'basis':catalog()['basis'], 'coverage':'363 Foundation foods; packaged/regional foods may need label values or recipes.'}


def normalize_items(items):
    if not isinstance(items,list) or not 1<=len(items)<=100: raise ValueError('Add between 1 and 100 food items')
    result=[]
    foods={f['id']:f for f in catalog()['foods']}
    for item in items:
        if not isinstance(item,dict) or set(item)-{'name','quantity','unit','nutrients','nutrient_basis','food_id','portion_basis','source','uncertainty'}:
            raise ValueError('Unknown food item fields')
        quantity=number(item.get('quantity'),'Portion',.01,10000)
        basis=item.get('portion_basis')
        if basis not in PORTIONS: raise ValueError('Choose how the portion was determined')
        uncertainty=text(item.get('uncertainty',''),'Uncertainty',1500,True)
        if item.get('food_id'):
            food=foods.get(str(item['food_id']))
            if not food: raise ValueError('Food not in the offline USDA catalog')
            if item.get('unit')!='g': raise ValueError('USDA portions must use grams of edible food')
            unit='g'
            uncertainty='; '.join([u for u in [uncertainty,*food.get('warnings',[])] if u])
            nutrients={k:None if food[k] is None else food[k]*quantity/100 for k in NUTRIENTS}
            name=food['name'];source=f"{catalog()['source']} {catalog()['release']} · FDC {food['id']}"
            detail={'food_id':food['id'],'per_100g':{k:food[k] for k in NUTRIENTS},'release':catalog()['release'],
                    'url':f"https://fdc.nal.usda.gov/food-details/{food['id']}/nutrients"}
        else:
            name=text(item.get('name'),'Food name')
            unit=item.get('unit')
            if unit not in ('g','serving','ml'): raise ValueError('Use g, ml or serving for a manual item')
            values=item.get('nutrients')
            if not isinstance(values,dict) or set(values)-set(NUTRIENTS): raise ValueError('Provide nutrient values for the entered portion; unknown values may be blank')
            nutrients={k:None if values.get(k) is None else number(values[k],k) for k in NUTRIENTS}
            source=text(item.get('source'),'Nutrient source')
            nutrient_basis=item.get('nutrient_basis','portion')
            if nutrient_basis not in ('portion','per_100g'):raise ValueError('Nutrient basis must be portion or per_100g')
            if nutrient_basis=='per_100g' and unit!='g':raise ValueError('Per-100g nutrients require grams')
            detail={'nutrient_basis':nutrient_basis,'input_values':dict(nutrients)}
            if nutrient_basis=='per_100g':nutrients={k:None if nutrients[k] is None else nutrients[k]*quantity/100 for k in NUTRIENTS}
        result.append({'name':name,'quantity':quantity,'unit':unit,**nutrients,'source':source,
                       'detail':{**detail,'portion_basis':basis,'uncertainty':uncertainty,'nutrition_is_estimated':True}})
    return result


def totals(items):
    return {k:{'known_total':round(sum(i[k] for i in items if i[k] is not None),3),
               'missing_items':sum(i[k] is None for i in items)} for k in NUTRIENTS}


def preview_meal(payload):
    if not isinstance(payload,dict) or set(payload)-{'eaten_at','meal_type','notes','items','timezone'}: raise ValueError('Unknown meal fields')
    items=normalize_items(payload.get('items'))
    timezone_name=payload.get('timezone');tz=zone(timezone_name)
    eaten=timestamp(payload.get('eaten_at'))
    kind=payload.get('meal_type','meal')
    if kind not in ('breakfast','lunch','dinner','snack','meal'): raise ValueError('Invalid meal type')
    return {'eaten_at':eaten,'meal_type':kind,'notes':text(payload.get('notes',''),'Notes',1500,True),
            'timezone':timezone_name,'local_date':datetime.fromisoformat(eaten).astimezone(tz).date().isoformat(),
            'items':items,'totals':totals(items),'advisory':'Nutrition totals are estimates. A weighed portion does not make database nutrients an exact measurement.'}


def _meal(c,identifier):
    row=c.execute('SELECT * FROM meals WHERE id=?',(identifier,)).fetchone()
    if not row: raise ValueError('Meal not found')
    items=[{**dict(r),'detail':json.loads(r['detail_json'])} for r in c.execute('SELECT * FROM meal_items WHERE meal_id=? ORDER BY rowid',(identifier,))]
    return {**dict(row),'items':items,'totals':totals(items)}


def _meal_revision(c,identifier):
    meal=_meal(c,identifier)
    c.execute('INSERT INTO meal_revisions(meal_id,revision,snapshot_json) VALUES (?,?,?)',(identifier,meal['revision'],encoded(meal)))
    return meal


def _target_for_day(c,day,timezone_name):
    existing=c.execute('SELECT snapshot_json FROM nutrition_day_targets WHERE calendar_date=? AND timezone=?',(day,timezone_name)).fetchone()
    if existing: return json.loads(existing[0])
    target=c.execute('SELECT * FROM nutrition_targets WHERE effective_from<=? ORDER BY effective_from DESC,revision DESC,created_at DESC,rowid DESC LIMIT 1',(day,)).fetchone()
    if not target:return None
    result=dict(target);assumptions=json.loads(result['assumptions_json'])
    training=any(datetime.fromisoformat(r['scheduled_for'].replace('Z','+00:00')).astimezone(zone(timezone_name)).date().isoformat()==day for r in c.execute("SELECT scheduled_for FROM planned_workouts WHERE scheduled_for IS NOT NULL AND completion_status NOT IN ('cancelled','skipped') AND training_plan_id IN (SELECT id FROM training_plans WHERE status='active')"))
    result['day_type']='training' if training else 'rest'
    if training and assumptions.get('training_calories_kcal') is not None:result['calories_kcal']=assumptions['training_calories_kcal']
    result['assumptions']=assumptions
    return result


def _freeze_target(c,day,timezone_name):
    if c.execute('SELECT 1 FROM nutrition_day_targets WHERE calendar_date=? AND timezone=?',(day,timezone_name)).fetchone():return
    target=_target_for_day(c,day,timezone_name)
    if target:c.execute('INSERT INTO nutrition_day_targets(calendar_date,timezone,target_id,snapshot_json) VALUES (?,?,?,?)',(day,timezone_name,target['id'],encoded(target)))


def save_meal(payload,operation_id,identifier=None,expected_revision=None,path=None):
    preview=preview_meal(payload);operation_id=text(operation_id,'Operation identity',100)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        if identifier is None:
            old=c.execute('SELECT id,operation_payload_json FROM meals WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old['operation_payload_json']!=encoded(preview):raise ValueError('Operation identity already used for a different meal')
                return _meal(c,old['id'])
            identifier='meal-'+str(uuid.uuid4())
            c.execute('INSERT INTO meals(id,eaten_at,meal_type,notes,operation_id,operation_payload_json) VALUES (?,?,?,?,?,?)',(identifier,preview['eaten_at'],preview['meal_type'],preview['notes'],operation_id,encoded(preview)))
        else:
            old=_meal(c,identifier)
            if type(expected_revision) is not int or old['revision']!=expected_revision:raise ValueError('Meal changed; reload before saving')
            if old['deleted_at']:raise ValueError('Restore the meal before editing')
            c.execute('UPDATE meals SET eaten_at=?,meal_type=?,notes=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(preview['eaten_at'],preview['meal_type'],preview['notes'],identifier))
            c.execute('DELETE FROM meal_items WHERE meal_id=?',(identifier,))
        for item in preview['items']:
            c.execute('INSERT INTO meal_items(id,meal_id,name,quantity,unit,calories_kcal,protein_grams,fat_grams,carbohydrate_grams,source,detail_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                      ('item-'+str(uuid.uuid4()),identifier,item['name'],item['quantity'],item['unit'],*[item[k] for k in NUTRIENTS],item['source'],encoded(item['detail'])))
        _freeze_target(c,preview['local_date'],preview['timezone'])
        return _meal_revision(c,identifier)


def remove_meal(identifier,expected_revision,removed,path=None):
    if type(removed) is not bool:raise ValueError('Removal must be yes or no')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');old=_meal(c,identifier)
        if type(expected_revision) is not int or old['revision']!=expected_revision:raise ValueError('Meal changed; reload before saving')
        c.execute('UPDATE meals SET deleted_at=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(datetime.now(timezone.utc).isoformat() if removed else None,identifier))
        return _meal_revision(c,identifier)


def daily_status(day,timezone_name,path=None):
    tz=zone(timezone_name)
    with connect(path) as c:
        meals=[]
        # UTC storage; local calendar boundaries (including DST) determine intake.
        for row in c.execute('SELECT id,eaten_at FROM meals ORDER BY eaten_at'):
            if datetime.fromisoformat(row['eaten_at'].replace('Z','+00:00')).astimezone(tz).date()==day:meals.append(_meal(c,row['id']))
        active=[m for m in meals if not m['deleted_at']];items=[i for m in active for i in m['items']]
        logged=totals(items);target=_target_for_day(c,day.isoformat(),timezone_name)
        remaining={k:round(target[k]-logged[k]['known_total'],3) if target and target[k] is not None and not logged[k]['missing_items'] else None for k in NUTRIENTS}
        return {'date':day.isoformat(),'timezone':timezone_name,'meals':meals,'totals':logged,'target':target,'remaining':remaining,
                'estimated_portions':sum(i['detail'].get('portion_basis') in ('estimated','photo_estimate') for i in items),
                'advisory':'Logged intake only; Garmin expenditure and Garmin intake summaries are not added to these totals. An empty log is not evidence of no intake.'}


def save_library(payload,identifier=None,expected_revision=None,path=None):
    if not isinstance(payload,dict) or set(payload)-{'name','kind','servings','items'}:raise ValueError('Unknown saved meal fields')
    name=text(payload.get('name'),'Recipe/meal name');kind=payload.get('kind')
    if kind not in ('recipe','meal'):raise ValueError('Choose recipe or reusable meal')
    servings=number(payload.get('servings'),'Recipe yield in servings',.01,1000);items=normalize_items(payload.get('items'))
    definition={'items':items,'totals':totals(items),'note':'Ingredients are the entire recipe; serving yield controls scaling. Cooking changes water weight; serving fractions do not assume raw/cooked mass equality.'}
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        if identifier:
            old=c.execute('SELECT revision FROM food_library WHERE id=?',(identifier,)).fetchone()
            if not old or type(expected_revision) is not int or old[0]!=expected_revision:raise ValueError('Saved meal changed; reload')
            c.execute('UPDATE food_library SET name=?,kind=?,servings=?,definition_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(name,kind,servings,encoded(definition),identifier))
        else:
            identifier='recipe-'+str(uuid.uuid4());c.execute('INSERT INTO food_library(id,name,kind,servings,definition_json) VALUES (?,?,?,?,?)',(identifier,name,kind,servings,encoded(definition)))
        row=dict(c.execute('SELECT * FROM food_library WHERE id=?',(identifier,)).fetchone())
        c.execute('INSERT INTO food_library_revisions(library_id,revision,snapshot_json) VALUES (?,?,?)',(identifier,row['revision'],encoded(row)))
        return row


def list_library(path=None):
    with connect(path) as c:return [{**dict(r),'definition':json.loads(r['definition_json'])} for r in c.execute('SELECT * FROM food_library ORDER BY name')]


def scale_library(identifier,servings,path=None):
    servings=number(servings,'Servings to log',.01,1000)
    with connect(path) as c:
        row=c.execute('SELECT * FROM food_library WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('Saved meal not found')
        factor=servings/row['servings'];items=[]
        for item in json.loads(row['definition_json'])['items']:
            quantity=item['quantity']*factor;number(quantity,'Scaled portion',.01,10000)
            # Use the stored recipe nutrient snapshot rather than a new catalog result.
            items.append({'name':item['name'],'quantity':quantity,'unit':item['unit'],
                          'nutrients':{k:None if item[k] is None else item[k]*factor for k in NUTRIENTS},
                          'portion_basis':'estimated','source':f"{item['source']} · saved {row['kind']} {row['name']} revision {row['revision']}",
                          'uncertainty':item['detail'].get('uncertainty','')})
        return {'items':items,'servings':servings,'library_revision':row['revision'],'name':row['name']}


def target_preview(payload):
    allowed={'method','age','weight_kg','height_cm','equation_sex','activity_factor','calories_kcal','protein_grams','fat_grams','carbohydrate_grams','training_calories_kcal','notes','effective_from'}
    if not isinstance(payload,dict) or set(payload)-allowed:raise ValueError('Unknown target fields')
    try:day=date.fromisoformat(payload.get('effective_from',''))
    except (ValueError,TypeError):raise ValueError('Choose an effective date')
    method=payload.get('method');assumptions={'method':method,'notes':text(payload.get('notes',''),'Target notes',1500,True),
                                           'exercise_policy':'Usual activity factor includes exercise. No Garmin calories are added. A training-day calorie value is a manual override, not an exercise addition.'}
    if method=='mifflin':
        age=number(payload.get('age'),'Adult age',18,100);weight=number(payload.get('weight_kg'),'Weight kg',30,350);height=number(payload.get('height_cm'),'Height cm',100,250)
        sex=payload.get('equation_sex')
        if sex not in ('male','female'):raise ValueError('Explicitly choose the equation coefficient; it is not inferred from identity')
        factor=number(payload.get('activity_factor'),'Usual activity multiplier including training',1,2.5)
        resting=10*weight+6.25*height-5*age+(5 if sex=='male' else -161)
        calories=round(resting*factor);assumptions.update({k:payload[k] for k in ('age','weight_kg','height_cm','equation_sex','activity_factor')})
        assumptions.update(resting_kcal=resting,formula='10*kg + 6.25*cm - 5*age + sex coefficient; multiply by explicitly chosen usual activity factor',source='https://pubmed.ncbi.nlm.nih.gov/2305711/',scope='Adult maintenance estimate; not an automatic deficit, surplus or clinical prescription.')
    elif method=='manual':calories=number(payload.get('calories_kcal'),'Manual calories',0,20000)
    else:raise ValueError('Choose manual or mifflin target method')
    macros={k:None if payload.get(k) is None else number(payload[k],k,0,2000) for k in NUTRIENTS[1:]}
    training=payload.get('training_calories_kcal')
    if training is not None:assumptions['training_calories_kcal']=number(training,'Manual training-day calories',0,20000)
    warnings=['All targets are estimates. Macro targets are entered explicitly; none are inferred.']
    if all(v is not None for v in macros.values()) and abs(4*macros['protein_grams']+9*macros['fat_grams']+4*macros['carbohydrate_grams']-calories)>max(100,calories*.1):warnings.append('Entered macros and calories differ by more than 10% / 100 kcal; review before saving.')
    return {'effective_from':day.isoformat(),'calories_kcal':calories,**macros,'assumptions':assumptions,'warnings':warnings}


def save_target(payload,expected_revision,path=None):
    preview=target_preview(payload)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');revision=c.execute('SELECT COALESCE(MAX(revision),0) FROM nutrition_targets').fetchone()[0]
        if type(expected_revision) is not int or revision!=expected_revision:raise ValueError('Nutrition targets changed; reload before saving')
        identifier='target-'+str(uuid.uuid4())
        c.execute('INSERT INTO nutrition_targets(id,effective_from,calories_kcal,protein_grams,fat_grams,carbohydrate_grams,assumptions_json,revision) VALUES (?,?,?,?,?,?,?,?)',
                  (identifier,preview['effective_from'],*[preview[k] for k in NUTRIENTS],encoded(preview['assumptions']),revision+1))
        return {**preview,'id':identifier,'revision':revision+1}


def target_history(path=None):
    with connect(path) as c:return [{**dict(r),'assumptions':json.loads(r['assumptions_json'])} for r in c.execute('SELECT * FROM nutrition_targets ORDER BY revision DESC,effective_from DESC')]
