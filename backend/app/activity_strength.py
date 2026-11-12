"""Decode recorded Garmin exercises without dropping unfamiliar protocol values."""
import json
import math
from garmin_fit_sdk import Profile
from .database import connect
from .garmin_strength_catalog import SPECS, ADDITIONAL_SPECS

IDS = {(category, exercise): identifier for identifier, _, _, category, exercise in (*SPECS, *ADDITIONAL_SPECS)}
MISSING = {'', 'unknown', 'invalid', 'none'}


def _token(value, enum=None):
    """Garmin JSON uses names; FIT may use enum codes or already decoded names."""
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in MISSING:
            return None
        if value.isdecimal():
            value = int(value)
        else:
            return value.upper()
    if type(value) is int:
        if value == 65535:
            return None
        decoded = (enum or {}).get(value)
        if decoded is not None:
            return None if str(decoded).lower() in MISSING else str(decoded).upper()
        return f'UNRECOGNIZED_{value}'
    return None


def identity(category, subtype):
    category = _token(category, Profile['types'].get('exercise_category', {})) or 'UNKNOWN'
    subtype = _token(subtype, Profile['types'].get(category.lower() + '_exercise_name', {}))
    # The category itself identifies a generic calf raise; no weight/variation is inferred.
    if category == 'CALF_RAISE' and subtype is None:
        subtype = 'CALF_RAISE'
    status = 'exact' if subtype and not subtype.startswith('UNRECOGNIZED_') else 'category_only'
    if category == 'UNKNOWN' or category.startswith('UNRECOGNIZED_'):
        status = 'unrecognized'
    if subtype:
        name = subtype.replace('_', ' ').title()
        if subtype.startswith('UNRECOGNIZED_'):
            name = f"{category.replace('_', ' ').title()} · {name} variation"
    else:
        name = (category.replace('_', ' ').title() + ' · variation not specified') if category != 'UNKNOWN' else 'Unidentified exercise'
    return (category, subtype), {'id': IDS.get((category, subtype)), 'name': name,
                                'category': category, 'exercise': subtype, 'identity_status': status}


def _count(value):
    return int(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 and value == int(value) else 0


def _add(target, category, subtype, sets, reps):
    key, item = identity(category, subtype)
    item = target.setdefault(key, {**item, 'sets': 0, 'repetitions': 0})
    item['sets'] += _count(sets)
    item['repetitions'] += _count(reps)


def exercises(activity_id, path=None):
    with connect(path) as c:
        row = c.execute("SELECT raw_json FROM activities WHERE id=? AND deleted_at IS NULL AND source_name!='synthetic_fixture'", (activity_id,)).fetchone()
    if row is None:
        raise KeyError('Activity not found')
    raw = json.loads(row['raw_json'] or '{}')
    summary, fit = {}, {}
    additional = raw.get('additional_details')
    summaries = raw.get('summarizedExerciseSets') or (additional.get('summarizedExerciseSets') if isinstance(additional, dict) else []) or []
    ignored = 0
    for item in summaries if isinstance(summaries, list) else []:
        if not isinstance(item, dict):
            continue
        category, subtype = item.get('category'), item.get('subCategory', item.get('category_subtype'))
        key, _ = identity(category, subtype)
        if key[0] == 'UNKNOWN' and key[1] is None and not _count(item.get('reps')):
            ignored += _count(item.get('sets')); continue
        _add(summary, category, subtype, item.get('sets'), item.get('reps'))

    messages = raw.get('fit_messages') or {}
    if not isinstance(messages, dict):
        messages = {}
    if not messages.get('set_mesgs'):
        from .fit_access import original_messages
        messages = original_messages(activity_id, path) or messages
    for item in messages.get('set_mesgs', []):
        if not isinstance(item, dict) or item.get('set_type') not in ('active', 'ACTIVE', 1):
            continue
        categories, subtypes = item.get('category', []), item.get('category_subtype', [])
        categories = categories if isinstance(categories, list) else [categories]
        subtypes = subtypes if isinstance(subtypes, list) else [subtypes]
        # The arrays contain candidate identities for ONE set, not separate sets.
        choices = [(category, subtypes[i] if i < len(subtypes) else None) for i, category in enumerate(categories)] or [(None, None)]
        # The first candidate is Garmin's selected identity. Do not promote an
        # alternative guess merely because our catalog happens to recognise it.
        chosen = choices[0]
        key, _ = identity(*chosen)
        if key[0] == 'UNKNOWN' and key[1] is None and not _count(item.get('repetitions')):
            continue  # Device warm-up placeholders are not identifiable exercises.
        _add(fit, *chosen, 1, item.get('repetitions'))

    found = dict(summary)
    filled = False
    warnings = []
    for key, item in fit.items():
        if key in found:
            continue  # Recorded summary counts take precedence; never sum both sources.
        generic = (key[0], None)
        variants = [k for k in fit if k[0] == key[0]]
        if generic in found and key[1] is not None:
            if len(variants) == 1:
                counts = found.pop(generic)
                found[key] = {**item, 'sets': counts['sets'], 'repetitions': counts['repetitions']}
                filled = True
            else:
                found[generic]['recorded_variants'] = [{field: fit[k][field] for field in ('id','name')} for k in variants]
            continue
        # A category-only FIT set can be the same exercise as a named summary.
        if key[1] is None and any(k[0] == key[0] for k in found):
            continue
        summary_sets = sum(v['sets'] for k,v in summary.items() if k[0] == key[0])
        fit_sets = sum(v['sets'] for k,v in fit.items() if k[0] == key[0])
        if summary_sets and summary_sets >= fit_sets:
            # Garmin allows users to correct exercise names after recording.
            # An older FIT name must not create extra sets in an edited summary.
            warnings.append(f"FIT also names {item['name']}; Garmin's recorded summary is used for this category to avoid duplicate sets.")
            continue
        found[key] = item
        filled = True
    source = 'Garmin recorded exercise summary' if summary else 'Recorded FIT active sets'
    if summary and filled:
        source += ' with FIT exercise details'
    return {'activity_id': activity_id, 'exercises': list(found.values()), 'source': source,
            'unidentified_zero_rep_sets': ignored, 'warnings': warnings}
