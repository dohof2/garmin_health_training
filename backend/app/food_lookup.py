"""Bounded, read-only food lookup. Public food names only; never meal history."""
import json
import math
import re
import copy
import time
import ssl
import certifi
from collections import OrderedDict, deque
from threading import RLock
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PORTION_SOURCE = 'https://www.gov.il/BlobFolder/guide/dietary-guidelines/he/files_publications_food_food-groups-reg.pdf'
YOGURT_SOURCE = 'https://www.foodsdictionary.co.il/Recipes/18635'
_CACHE = OrderedDict()
_REQUESTS = deque()
_LOCK = RLock()


def finite(value, maximum=10000):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum


def portion_reference(food, description):
    """A named container is a proposal, never a universal gram conversion."""
    if not re.search(r'גביע|גביעים|\b(tubs?|pots?|containers?)\b', description, re.I):
        return None
    if re.search(r'קוטג|cottage', food, re.I):
        grams = 250
    elif re.search(r'יוגורט|yog[hu]*urt', food, re.I):
        grams = 150
    else:
        return None
    count = .5 if re.search(r'חצי\s*גביע|half\s+(?:a\s+)?(?:tub|pot)', description, re.I) else 2 if re.search(r'שני\s*גביעים|שתי\s*גביעים|two\s+(?:tubs|pots)', description, re.I) else 1
    numeric = re.search(r'(\d+(?:\.\d+)?)\s*(?:גביעים|גביע|tubs?|pots?)', description, re.I)
    if numeric:
        count = float(numeric[1])
    if not 0 < count <= 30:
        return None
    return {'grams': grams * count, 'container_grams': grams, 'count': count,
            'source': PORTION_SOURCE, 'additional_source': YOGURT_SOURCE if grams == 150 else None,
            'basis': 'Common Israeli portion reference; package sizes vary. Confirm the actual product and amount.',
            'confirmed': False}


def search_foods(query):
    query = str(query).strip()[:120]
    if not query:
        return {'status': 'no_matches', 'foods': [], 'source': 'Open Food Facts'}
    generic = r'(?:bananas?|בננה|בננות|apples?|תפוח(?:י)?(?: עץ)?|(?:cooked |raw )?rice|אורז(?: מבושל)?|chicken(?: breast)?|עוף|חזה עוף|eggs?|ביצה|ביצים|(?:plain |natural |greek |nonfat )?yogurt(?: plain| natural| greek| nonfat)?|יוגורט(?: טבעי| יווני)?)'
    if re.fullmatch(r'(?:(?:plain|fresh|ripe|raw|cooked)\s+)?'+generic, query, re.I):
        return _offline_candidates(query, 'Using food-composition data for this unbranded food.')
    key = query.casefold()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            _CACHE.move_to_end(key)
            return copy.deepcopy(cached[1])
        while _REQUESTS and _REQUESTS[0] <= now - 60:
            _REQUESTS.popleft()
        if len(_REQUESTS) >= 8:
            return _offline_candidates(query, 'Online lookup is taking a short pause.')
        _REQUESTS.append(now)
    result = _search_foods(query)
    if result['status'] in ('unavailable', 'no_matches'):
        result = _offline_candidates(query, result.get('message') or 'No matching online product was found.')
    with _LOCK:
        _CACHE[key] = (time.monotonic() + (3600 if result['status'] == 'available' else 30), copy.deepcopy(result))
        _CACHE.move_to_end(key)
        while len(_CACHE) > 128:
            _CACHE.popitem(last=False)
    return result


def _offline_candidates(query, reason):
    from .nutrition import food_search
    translations = [('יוגורט','yogurt'), ('אורז','rice'), ('לחם','bread'), ('עוף','chicken'), ('ביצ','egg'), ('בננ','banana'), ('תפוח','apple'), ('קוטג','cottage'), ('חלב','milk')]
    translated = next((english for hebrew, english in translations if hebrew in query), query)
    if translated == query:
        translated = next((word for word in ('yogurt','rice','chicken','bread','banana','apple','cottage','milk','egg') if re.search(r'\b'+word+r's?\b', query, re.I)), query)
    found = food_search(translated)['foods']
    # Do not offer bread flour as bread, or banana peppers as bananas.
    found = [item for item in found if translated.casefold() in item['name'].split(',')[0].casefold() or translated == 'cottage' and 'cottage' in item['name'].casefold()]
    foods = [{'name': item['name'], 'brand': 'Generic USDA food; not a brand match', 'package': '', 'package_grams': None,
              'nutrients': {key:item.get(key) for key in ('calories_kcal','protein_grams','fat_grams','carbohydrate_grams')},
              'source_url': 'https://fdc.nal.usda.gov/food-details/'+item['id']+'/nutrients', 'basis': 'per_100g', 'source': 'USDA Foundation Foods, 2026-04-30; generic match, confirm food and preparation'} for item in found[:4]]
    return {'status': 'offline_candidates' if foods else 'unavailable', 'foods': foods, 'source': 'USDA Foundation Foods',
            'message': reason+' '+('These are generic offline USDA alternatives, not verified packaged products. Choose only if the food and preparation match.' if foods else 'Use your package label or the offline food search; nutrients remain unknown until matched.')}


def _search_foods(query):
    """Candidates from OFF; selecting one is required before using its nutrients."""
    query = str(query).strip()[:120]
    if not query:
        return {'status': 'no_matches', 'foods': [], 'source': 'Open Food Facts'}
    params = {'action': 'process', 'search_terms': query, 'search_simple': 1, 'json': 1,
              'page_size': 4, 'lc': 'he', 'fields': 'code,product_name,product_name_he,brands,quantity,product_quantity,product_quantity_unit,nutriments,nutrition_data_per'}
    request = Request('https://world.openfoodfacts.org/cgi/search.pl?' + urlencode(params),
                      headers={'User-Agent': 'PersonalHealthTraining/0.1 (local nutrition review)', 'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=8, context=ssl.create_default_context(cafile=certifi.where())) as response:
            raw = response.read(500001)
        if len(raw) > 500000:
            raise ValueError('Food lookup response too large')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('products'), list):
            raise ValueError('Invalid food lookup response')
        foods = []
        for product in payload['products'][:4]:
            if not isinstance(product, dict):
                continue
            code = str(product.get('code', ''))
            name = product.get('product_name_he') or product.get('product_name')
            nutrients = product.get('nutriments')
            if not re.fullmatch(r'\d{8,14}', code) or not isinstance(name, str) or not isinstance(nutrients, dict):
                continue
            # A liquid's values per 100 ml must not be silently treated as 100 g.
            if str(product.get('product_quantity_unit', '')).lower() in ('ml', 'l'):
                continue
            values = {}
            for field, key in [('calories_kcal', 'energy-kcal_100g'), ('protein_grams', 'proteins_100g'), ('fat_grams', 'fat_100g'), ('carbohydrate_grams', 'carbohydrates_100g')]:
                value = nutrients.get(key)
                values[field] = value if finite(value, 1000 if field == 'calories_kcal' else 100) else None
            if not any(value is not None for value in values.values()):
                continue
            grams = product.get('product_quantity')
            package_grams = grams if product.get('product_quantity_unit') == 'g' and finite(grams) and grams > 0 else None
            foods.append({'name': name[:200], 'brand': str(product.get('brands', ''))[:120], 'package': str(product.get('quantity', ''))[:120],
                          'package_grams': package_grams, 'nutrients': values, 'source_url': 'https://world.openfoodfacts.org/product/' + code,
                          'basis': 'per_100g', 'source': 'Open Food Facts; community-maintained product label, confirm against your package'})
        return {'status': 'available' if foods else 'no_matches', 'foods': foods, 'source': 'Open Food Facts'}
    except (OSError, ValueError, TypeError):
        return {'status': 'unavailable', 'foods': [], 'source': 'Open Food Facts', 'message': 'Online food lookup is unavailable. Portion references still work; use a label or offline USDA match for nutrients.'}
