"""Reviewable adult nutrition targets from recorded data, not model arithmetic."""
import hashlib
import json
import math
from datetime import date, timedelta
from statistics import mean

from .database import connect
from .nutrition import encoded, number

SOURCES = [
    {'title': 'Mifflin–St Jeor resting-energy equation', 'url': 'https://pubmed.ncbi.nlm.nih.gov/2305711/'},
    {'title': 'CDC: gradual weight loss', 'url': 'https://www.cdc.gov/healthy-weight-growth/losing-weight/index.html'},
    {'title': 'NIH: activity, protein and fat needs', 'url': 'https://ods.od.nih.gov/factsheets/ExerciseAndAthleticPerformance-HealthProfessional/'},
    {'title': 'National Academies: balanced macro ranges', 'url': 'https://www.nationalacademies.org/news/report-offers-new-eating-and-physical-activity-targets-to-reduce-chronic-disease-risk'},
    {'title': 'Energy-surplus trial: faster gain mainly increased fat', 'url': 'https://doi.org/10.1186/s40798-023-00651-y'},
]


def valid(value, low, high):
    return type(value) in (float, int) and math.isfinite(value) and low <= value <= high


def recorded_context(day, path=None):
    today = date.fromisoformat(day)
    begin = today - timedelta(days=28)
    with connect(path) as c:
        profile = dict(c.execute('SELECT * FROM user_profile WHERE id=1').fetchone() or {})
        row = c.execute("SELECT calendar_date,payload_json FROM garmin_sync_payloads WHERE data_type='supplementary_metrics' AND calendar_date<=? ORDER BY calendar_date DESC LIMIT 1", (day,)).fetchone()
        user = {}
        if row:
            payload = json.loads(row['payload_json'])
            remote = payload.get('endpoints', {}).get('get_user_profile', {})
            user = remote.get('userData', {}) if isinstance(remote, dict) else {}
            if not isinstance(user, dict):
                user = {}
        measured = c.execute("""SELECT value,recorded_at,source_name FROM metric_readings
            WHERE metric_type='weight' AND unit='kg' AND source_name!='synthetic_fixture'
            AND substr(recorded_at,1,10)<=? AND value BETWEEN 30 AND 350
            ORDER BY recorded_at DESC,CASE source_name WHEN 'garmin_connect' THEN 1 ELSE 0 END DESC,rowid DESC LIMIT 1""", (day,)).fetchone()
        metrics = c.execute("""SELECT metric_type,substr(recorded_at,1,10) AS day,value,source_name FROM metric_readings
            WHERE metric_type IN ('steps','total_calories','active_calories','resting_calories') AND source_name!='synthetic_fixture'
            AND substr(recorded_at,1,10)>=? AND substr(recorded_at,1,10)<?
            ORDER BY CASE source_name WHEN 'garmin_connect' THEN 1 ELSE 0 END,recorded_at,created_at,rowid""", (begin.isoformat(), day)).fetchall()
        samples = {}
        for metric in metrics:
            if valid(metric['value'], 0, 100000):
                samples.setdefault(metric['day'], {})[metric['metric_type']] = metric['value']
        activity_minutes = sum(r[0] / 60 for r in c.execute("SELECT duration_seconds FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND duration_seconds>0 AND substr(started_at,1,10)>=? AND substr(started_at,1,10)<?", (begin.isoformat(), day)))
        activity_checkpoint = c.execute("SELECT coverage_start,coverage_end FROM sync_checkpoints WHERE data_type='activities'").fetchone()
        covered = bool(activity_checkpoint and activity_checkpoint['coverage_start'] and activity_checkpoint['coverage_end'] and activity_checkpoint['coverage_start'] <= begin.isoformat() and activity_checkpoint['coverage_end'] >= (today-timedelta(days=1)).isoformat())
        complete_days = set()
        for record in c.execute("SELECT calendar_date,payload_json FROM garmin_sync_payloads WHERE data_type='daily_metrics' AND calendar_date>=? AND calendar_date<?", (begin.isoformat(), day)):
            payload = json.loads(record['payload_json'])
            if not isinstance(payload, dict):
                continue
            duration = payload.get('durationInMilliseconds')
            end = str(payload.get('wellnessEndTimeLocal') or '')
            if valid(duration, 20*3600000, 27*3600000) and end[:10] == record['calendar_date'] and len(end) >= 13 and end[11:13] >= '23':
                complete_days.add(record['calendar_date'])
        revision = c.execute('SELECT COALESCE(MAX(revision),0) FROM nutrition_targets').fetchone()[0]
    height = user.get('height') if valid(user.get('height'), 100, 250) else profile.get('height_cm')
    height_source = 'Garmin profile (cm)' if valid(user.get('height'), 100, 250) else 'Saved profile'
    profile_weight = user.get('weight')/1000 if valid(user.get('weight'), 30000, 350000) else profile.get('weight_kg')
    weight = dict(measured) if measured else {'value': profile_weight, 'recorded_at': None, 'source_name': 'Garmin/saved profile; measurement date unknown'}
    birth = user.get('birthDate') or profile.get('birth_date')
    try:
        born = date.fromisoformat(str(birth)[:10])
        age = today.year-born.year-((today.month, today.day) < (born.month, born.day))
    except ValueError:
        age = None
    sex = str(user.get('gender') or profile.get('sex') or '').lower()
    sex = sex if sex in ('male', 'female') else None
    steps = [value['steps'] for value in samples.values() if 'steps' in value]
    totals = [{'date': key, 'kcal': value.get('total_calories', value.get('active_calories', 0)+value.get('resting_calories', 0))} for key, value in samples.items() if key in complete_days and 'active_calories' in value and 'resting_calories' in value and value['resting_calories'] > 0]
    weekly_minutes = round(activity_minutes/4) if covered else None
    average_steps = round(mean(steps)) if len(steps) >= 14 else None
    factor = None
    if covered and activity_minutes > 0 or average_steps is not None:
        minutes = weekly_minutes or 0
        step_count = average_steps or 0
        factor = 1.725 if step_count >= 10000 and minutes >= 300 else 1.55 if step_count >= 7500 or minutes >= 150 else 1.375 if step_count >= 4000 or minutes >= 60 else 1.2
    return {'height_cm': height, 'height_source': height_source, 'weight': weight, 'age': age, 'equation_sex': sex,
            'activity': {'window_start': begin.isoformat(), 'window_end': (today-timedelta(days=1)).isoformat(), 'average_steps': average_steps, 'step_days': len(steps), 'weekly_exercise_minutes': weekly_minutes, 'activity_coverage_complete': covered, 'suggested_factor': factor, 'factor_basis': 'Provisional app heuristic from recorded steps and completed activity, including exercise; not a measured metabolic rate.'},
            'complete_calorie_days': totals, 'target_revision': revision}


def propose(arguments, day, path=None):
    allowed = {'goal', 'target_weight_kg', 'age', 'height_cm', 'weight_kg', 'equation_sex', 'activity_factor', 'rate_kg_week', 'special_circumstances'}
    if not isinstance(arguments, dict) or set(arguments)-allowed:
        raise ValueError('Unsupported nutrition target inputs')
    data = recorded_context(day, path)
    goal = arguments.get('goal')
    result = {'status': 'needs_input', 'request': arguments, 'effective_from': day, 'context': data, 'questions': [], 'sources': SOURCES, 'saved': False}
    questions = result['questions']
    if goal not in ('lose_weight', 'maintain', 'gain_muscle'):
        questions.append('Would you like gradual weight loss, maintenance, or muscle gain?')
    if arguments.get('special_circumstances'):
        return {**result, 'status': 'needs_professional_review', 'questions': ['A clinician or registered dietitian should set targets for the pregnancy, breastfeeding, eating-disorder, kidney or other clinical situation you mentioned. I can help track a target they provide.']}
    weight = arguments.get('weight_kg') if arguments.get('weight_kg') is not None else data['weight']['value']
    height = arguments.get('height_cm') if arguments.get('height_cm') is not None else data['height_cm']
    age = arguments.get('age') if arguments.get('age') is not None else data['age']
    sex = arguments.get('equation_sex') if arguments.get('equation_sex') is not None else data['equation_sex']
    factor = arguments.get('activity_factor') if arguments.get('activity_factor') is not None else data['activity']['suggested_factor']
    target = arguments.get('target_weight_kg')
    for value, name, low, high in [(weight, 'current weight (kg)', 30, 350), (height, 'height (cm)', 100, 250), (age, 'adult age', 18, 100), (factor, 'usual activity factor including exercise', 1.1, 2.2)]:
        if not valid(value, low, high):
            questions.append('Please confirm your '+name+'.')
    if age is not None and valid(age, 0, 17):
        return {**result, 'status': 'needs_professional_review', 'questions': ['Adult calorie formulas are not appropriate below age 18; use age-specific professional guidance.']}
    if sex not in ('male', 'female'):
        questions.append('Which resting-energy equation coefficient should I use: male or female?')
    if goal in ('lose_weight', 'gain_muscle') and not valid(target, 30, 350):
        questions.append('What target weight in kg would you like to work toward?')
    elif target is not None and not valid(target, 30, 350):
        questions.append('Please confirm a valid target weight in kg.')
    if questions:
        return result
    target = weight if goal == 'maintain' and target is None else target
    if goal == 'lose_weight' and target >= weight or goal == 'gain_muscle' and target <= weight:
        return {**result, 'questions': ['Your target weight points in the opposite direction. Should we change the goal or target weight?']}
    current_bmi = weight/(height/100)**2
    target_bmi = target/(height/100)**2
    if goal == 'lose_weight' and (current_bmi < 18.5 or target_bmi < 18.5):
        return {**result, 'status': 'not_recommended', 'questions': ['That loss goal falls below the usual adult BMI screening range. I will not generate a weight-loss deficit; review the goal with a clinician or dietitian. BMI is a screening measure, not a body-composition diagnosis.']}
    if current_bmi < 18.5 or current_bmi >= 40:
        return {**result, 'status': 'needs_professional_review', 'questions': ['These measurements are outside this general-purpose calculator’s range. A clinician or dietitian should tailor the target; BMI is a screening measure, not a body-composition diagnosis.']}
    rate = arguments.get('rate_kg_week')
    if rate is not None:
        number(rate, 'Requested weekly rate', .01, 20)
        limit = min(.9, weight*.01) if goal == 'lose_weight' else weight*.005
        if rate > limit:
            return {**result, 'status': 'not_recommended', 'questions': ['That requested pace is too aggressive for this conservative planner. Choose a gradual pace; muscle gain cannot be predicted from scale-weight gain.']}
    resting = 10*weight+6.25*height-5*age+(5 if sex == 'male' else -161)
    maintenance = resting*factor
    method = 'Mifflin resting estimate × activity heuristic'
    full = [row for row in data['complete_calorie_days'] if resting*1.05 <= row['kcal'] <= resting*2.5]
    # At least two readings from every one of four weeks, not a single recent week.
    start = date.fromisoformat(data['activity']['window_start'])
    weeks = [sum(start+timedelta(days=7*i) <= date.fromisoformat(row['date']) < start+timedelta(days=7*(i+1)) for row in full) for i in range(4)]
    if len(full) >= 14 and min(weeks) >= 2 and arguments.get('activity_factor') is None:
        maintenance = mean(row['kcal'] for row in full)
        method = 'Mean Garmin expenditure across complete days in the last four weeks'
    adjustment = -min(300, maintenance*.10) if goal == 'lose_weight' else min(250, maintenance*.05) if goal == 'gain_muscle' else 0
    if rate is not None:
        # Use the requested rate only to make the default gentler, never larger.
        adjustment = (-1 if goal == 'lose_weight' else 1 if goal == 'gain_muscle' else 0)*min(abs(adjustment), rate*7700/7)
    calories = round(max(resting, 1500 if sex == 'male' else 1200, maintenance+adjustment))
    if maintenance < (1500 if sex == 'male' else 1200) or goal == 'lose_weight' and calories >= maintenance:
        return {**result, 'status': 'needs_professional_review', 'questions': ['The maintenance estimate is too low to support an automatic deficit within this planner’s safeguards. Review the measurements and target with a dietitian.']}
    protein_factor = 1.6 if goal != 'maintain' or (data['activity']['weekly_exercise_minutes'] or 0) >= 150 else 1.2
    protein = round(weight*protein_factor)
    fat = round(calories*.25/9)
    carbs = round((calories-protein*4-fat*9)/4)
    if carbs < 130 or protein*4 > calories*.35:
        return {**result, 'status': 'needs_professional_review', 'questions': ['These inputs do not fit the conservative balanced calorie/macro defaults. Review a personalized target with a registered dietitian.']}
    warnings = ['Starting estimate, not a measured metabolism or a guaranteed rate of weight change. Review weight trend, hunger, recovery and performance after 2–3 weeks.',
                'No activity calories are added on top of this target: the maintenance estimate already includes exercise.',
                'For long or demanding training days, discuss additional fueling rather than chasing a fixed deficit.',
                'Adult general guidance; pregnancy, breastfeeding and clinician-managed conditions need individualized targets.']
    if goal == 'gain_muscle':
        warnings.append('A small surplus supports a muscle-gain goal alongside progressive resistance training; scale-weight gain is not all muscle.')
    if not data['weight']['recorded_at'] and not arguments.get('weight_kg'):
        warnings.append('Weight comes from the saved profile with no measurement date; confirm it before saving.')
    elif data['weight']['recorded_at'] and data['weight']['recorded_at'][:10] < (date.fromisoformat(day)-timedelta(days=30)).isoformat() and not arguments.get('weight_kg'):
        return {**result, 'questions': ['The latest recorded weight is more than 30 days old. What is your current weight?']}
    weight_source = {'value': weight, 'recorded_at': day, 'source_name': 'User supplied correction'} if arguments.get('weight_kg') is not None else data['weight']
    height_source = 'User supplied correction (cm)' if arguments.get('height_cm') is not None else data['height_source']
    preview = {'effective_from': day, 'calories_kcal': calories, 'protein_grams': protein, 'fat_grams': fat, 'carbohydrate_grams': carbs,
               'assumptions': {'method': 'adaptive_adult', 'goal': goal, 'target_weight_kg': target, 'weight_kg': weight, 'height_cm': height, 'age': age, 'equation_sex': sex, 'resting_kcal': round(resting), 'maintenance_kcal': round(maintenance), 'maintenance_method': method, 'activity_factor': factor, 'garmin_complete_days_used': len(full) if method.startswith('Mean Garmin') else 0, 'adjustment_kcal': calories-round(maintenance), 'protein_g_per_kg': protein_factor, 'fat_energy_percent': 25, 'exercise_policy': 'Exercise is already included. Garmin activity calories are not added again.', 'policy': 'Conservative app defaults: up to 10%/300 kcal deficit or 5%/250 kcal surplus; not a clinical prescription.', 'input_sources': {'height': height_source, 'weight': weight_source, 'activity': data['activity']}, 'sources': SOURCES}, 'warnings': warnings}
    fingerprint = hashlib.sha256(encoded({'preview': preview, 'revision': data['target_revision'], 'request': arguments}).encode()).hexdigest()
    return {**result, 'status': 'proposal', 'questions': [], 'preview': preview, 'fingerprint': fingerprint, 'expected_revision': data['target_revision']}


def save(arguments, day, fingerprint, expected_revision, path=None):
    from .nutrition import persist_target
    proposed = propose(arguments, day, path)
    if proposed['status'] != 'proposal' or proposed['fingerprint'] != fingerprint or proposed['expected_revision'] != expected_revision:
        raise ValueError('Nutrition inputs or targets changed; review a fresh proposal before saving')
    return persist_target(proposed['preview'], expected_revision, path)
