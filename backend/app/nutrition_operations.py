"""Structured nutrition actions for the shared agent; no model calls or routing."""
from datetime import date, datetime

from .database import connect
from .nutrition import NUTRIENTS, _meal, _meal_revision, _freeze_target, normalize_items, zone, number, encoded, timestamp


def execute(args, context, operation):
    intent = args['intent']
    path, tz = context['path'], context['timezone']
    retained = context['state'].setdefault('nutrition', {})
    day = args.get('date') or retained.get('day') or context['today']
    date.fromisoformat(day)
    kind = args.get('meal_type') or retained.get('meal_type', 'meal')
    if intent == 'targets':
        from .nutrition_targets import propose
        proposal = propose(args.get('target_request') or {}, day, path)
        retained['pending_target'] = proposal['request']
        return {'logged': False, 'target_saved': False, 'context_date': day, 'ingredients': [],
                'uncertainties': [], 'target_proposal': proposal, 'reply': 'Review the nutrition target proposal or its unresolved inputs.'}
    if intent == 'log':
        from .nutrition_logging import log_result
        foods = args.get('ingredients')
        if not isinstance(foods, list) or not 1 <= len(foods) <= 30:
            raise ValueError('Supply the understood foods and portions, or ask the user about the missing portion first.')
        normalized = []
        from .food_vision import nutrient_estimate
        for food in foods:
            if not isinstance(food, dict):
                raise ValueError('Food ingredients must be objects')
            grams = number(food.get('grams'), 'Food portion in grams', .01, 10000)
            normalized.append({'name': food['name'], 'grams_low': grams, 'grams_high': grams,
                'grams_proposed': grams, 'question': '', 'meal_type': food.get('meal_type', kind),
                'nutrients_per_100g': nutrient_estimate(food.get('nutrients_per_100g')),
                'estimate_assumptions': food.get('assumptions', '')})
        result = log_result({'ingredients': normalized, 'uncertainties': [], 'reply': ''}, 'Food report on ' + day,
            day, tz, kind, operation, path, context['now'])
    elif intent == 'correct':
        identifier, revision = args.get('meal_id'), args.get('expected_revision')
        with connect(path) as c:
            meal = _meal(c, identifier)
        if type(revision) is not int or meal['revision'] != revision:
            raise ValueError('The meal changed. Read its current revision before correcting it.')
        item_id = args.get('item_id')
        if item_id and not any(i['id'] == item_id for i in meal['items']):
            raise ValueError('The selected ingredient does not belong to this meal')
        if (args.get('quantity') is not None or args.get('replacement')) and not item_id:
            raise ValueError('Select the ingredient whose portion should change')
        updated_item = None
        if item_id:
            item = next(i for i in meal['items'] if i['id']==item_id)
            replacement = args.get('replacement')
            if replacement:
                quantity = number(replacement.get('grams', args.get('quantity', item['quantity'])), 'Replacement grams', .01, 10000)
                raw = {'name': replacement.get('name', item['name']), 'quantity': quantity, 'unit': 'g',
                    'nutrients': replacement.get('nutrients_per_100g') or {k: None for k in NUTRIENTS}, 'nutrient_basis': 'per_100g',
                    'source': 'AI nutrition estimate; not a verified label', 'portion_basis': 'estimated', 'uncertainty': replacement.get('assumptions', '')}
                if replacement.get('food_id'):
                    raw['food_id'] = replacement['food_id']
                updated_item = normalize_items([raw])[0]
            else:
                quantity = number(args.get('quantity', item['quantity']), 'Corrected portion', .01, 10000)
                updated_item = {**item, 'quantity': quantity,
                    **{k: None if item[k] is None else item[k]*quantity/item['quantity'] for k in NUTRIENTS}}
        eaten = datetime.fromisoformat(meal['eaten_at']).astimezone(zone(tz))
        if args.get('date'):
            if day > context['today']:
                raise ValueError('A consumed meal cannot be moved into the future')
            eaten = eaten.replace(year=date.fromisoformat(day).year, month=date.fromisoformat(day).month, day=date.fromisoformat(day).day)
        meal_type = args.get('meal_type') or meal['meal_type']
        if meal_type not in ('meal','breakfast','lunch','dinner','snack'):
            raise ValueError('Invalid meal type')
        with connect(path) as c:
            c.execute('BEGIN IMMEDIATE')
            from .chat_access import authorize_nutrition_write
            authorize_nutrition_write(c)
            fresh = _meal(c, identifier)
            if fresh['revision'] != revision or fresh['deleted_at']:
                raise ValueError('The meal changed or was removed. Read its current state again.')
            if updated_item:
                c.execute('UPDATE meal_items SET name=?,quantity=?,unit=?,calories_kcal=?,protein_grams=?,fat_grams=?,carbohydrate_grams=?,source=?,detail_json=? WHERE id=? AND meal_id=?',
                    (updated_item['name'],updated_item['quantity'],updated_item['unit'],*(updated_item[k] for k in NUTRIENTS),updated_item['source'],encoded(updated_item['detail']),item_id,identifier))
            c.execute('UPDATE meals SET eaten_at=?,meal_type=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?', (timestamp(eaten.isoformat()),meal_type,identifier))
            _freeze_target(c, eaten.date().isoformat(), tz)
            saved = _meal_revision(c, identifier)
            result = {'logged': True, 'corrected': True, 'updated': True, 'context_date': eaten.date().isoformat(), 'ingredients': [],
                      'uncertainties': [], 'saved_meals': [{'id': saved['id'], 'revision': saved['revision'], 'meal_type': saved['meal_type']}],
                      'reply': 'The selected meal correction was saved. Other ingredients were retained.'}
            from .nutrition_logging import add_saved_feedback
            add_saved_feedback(result, [saved], eaten.date().isoformat(), tz, c, context['message'])
    else:
        raise ValueError('Choose log, correct, or targets')
    retained['day'] = result.get('context_date', day)
    if result.get('logged'):
        retained['pending_foods'] = []
        retained.pop('pending_correction', None)
    if result.get('saved_meals'):
        retained['saved_meals'] = result['saved_meals']
    return result
