"""Local, versioned skill discovery. Catalog search never calls a model."""
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).with_name('skills')


def catalog():
    return _catalog((ROOT / 'catalog.json').stat().st_mtime_ns)


@lru_cache(maxsize=2)
def _catalog(version_stamp):
    data = json.loads((ROOT / 'catalog.json').read_text())
    ids = [item['id'] for item in data['skills']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate skill IDs')
    for item in data['skills']:
        if not re.fullmatch(r'[a-z]+(?:\.[a-z]+)+', item['id']):
            raise ValueError('Invalid skill ID')
        if not (ROOT / (item['id'] + '.md')).is_file():
            raise ValueError('Missing skill instructions: ' + item['id'])
    return data


def card(item):
    return {key: item[key] for key in ('id', 'path', 'summary', 'examples', 'version')}


def branches():
    return catalog()['branches']


def get_skill(identifier):
    item = next((s for s in catalog()['skills'] if s['id'] == identifier), None)
    if item is None:
        raise ValueError('Unknown skill. Search the catalog for a supported ID.')
    return item


def load_skill(identifier):
    item = get_skill(identifier)
    return {**card(item), 'instructions': (ROOT / (identifier + '.md')).read_text(),
            'tools': item['tools']}


def children(path=''):
    if not path:
        return {'branches': branches()}
    parts = [p.strip().casefold() for p in path.strip(' /').split('/')]
    matched = [s for s in catalog()['skills'] if [p.strip().casefold() for p in s['path'].split('/')][:len(parts)] == parts]
    if not matched:
        raise ValueError('Unknown catalog path')
    groups, leaves = {}, []
    for skill in matched:
        components = [p.strip() for p in skill['path'].split('/')]
        if len(components) == len(parts)+1:
            leaves.append(card(skill))
        else:
            child = ' / '.join(components[:len(parts)+1])
            groups.setdefault(child, {'path': child, 'summary': 'Focused ' + components[len(parts)].lower() + ' capabilities', 'skill_count': 0})
            groups[child]['skill_count'] += 1
    return {'branches': list(groups.values()), 'skills': leaves}


def find(query, limit=3):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1500:
        raise ValueError('Describe the capability in 1–1500 characters')
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError('Choose 1–5 candidates')
    words = set(re.findall(r'[\w]+', query.casefold())) - {'the','a','an','my','to','for','it','and','of','in','i'}
    ranked = []
    for item in catalog()['skills']:
        title = set(re.findall(r'[\w]+', item['id'].replace('.', ' ') + ' ' + item['path'].casefold()))
        body = set(re.findall(r'[\w]+', ' '.join([item['summary'], *item['examples'], *item.get('keywords', [])]).casefold()))
        score = 3 * len(words & title) + len(words & body)
        if item['id'] == query.strip():
            score += 100
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    return {'skills': [card(s) for _, s in ranked[:limit]],
            'note': 'Candidate capabilities, not an intent decision. Browse branches if no candidate fits.'}
