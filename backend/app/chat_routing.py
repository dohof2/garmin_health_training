"""One conversation with explicit role selection and conservative automatic routing."""
import re
ROLES=('trainer','assistant','nutrition')

def task_segments(message):
    """Split only explicit task boundaries; never split a food ingredient list."""
    parts=re.split(r'\s*(?:;|\n)+\s*|\s+(?:and\s+)?(?:also|then)\s+(?=(?:log|record|add|plot|graph|show|change|set|reduce|make|skip|cancel|i ate|i had)\b)|\s+and\s+(?=(?:log|record|plot|graph|change|reduce|skip|cancel|i ate|i had)\b)',message,flags=re.I)
    parts=[p.strip(' .') for p in parts if p.strip(' .')]
    if not 2<=len(parts)<=4:return []
    # Each task needs its own explicit instruction/report; fragments stay intact.
    if not all(re.match(r'(?i)^(?:please\s+)?(?:log|record|add|plot|graph|show|change|set|reduce|make|skip|cancel|i ate|i had|what|how|compare)\b',p) for p in parts):return []
    if len({route(p) for p in parts})<2:return []
    return parts

def mixed_edit_request(message):
    """Avoid silently dropping a second task in deterministic edit interception."""
    text=message.lower()
    edit=bool(re.search(r'\b(change|set|reduce|make|skip|cancel)\b.{0,25}\b(workout|ride|cycling|intervals?|strength)\b',text))
    if re.search(r'\bmake (?:a |the |my )?(graph|plot|chart)\b',text):edit=False
    food=bool(re.search(r'\bi (ate|had|eat)\b|\b(log|record|add)\b.{0,30}\b(meal|food|breakfast|lunch|dinner)\b|\b(calorie|nutrition) targets?\b',text))
    plots=bool(re.search(r'\b(plot|graph|chart)\b',text))
    return edit and (food or plots)

def route(message,requested='auto',previous=None):
    if requested not in ('auto',*ROLES):raise ValueError('Choose Auto, Trainer, Assistant or Nutrition')
    if requested!='auto':return requested
    text=message.lower()
    from .nutrition_logging import consumption_report
    if consumption_report(message) and re.search(r'\bi (?:just |already )?(?:ate|had|have eaten)\b|אכלתי',text):
        if not re.search(r'\bhad\b.{0,40}\b(ride|workout|training|sprint)\b',text):return 'nutrition'
    if re.search(r'\b(burned|burnt|plot|graph|uphill|climb|average power)\b',text):return 'assistant'
    if re.search(r'\b(how|what|show|summarize|report)\b',text) and re.search(r'\b(steps|hrv|sleep|heart rate|weight history)\b',text):return 'assistant'
    if re.search(r'\b(food|meal|eat|ate|eaten|breakfast|lunch|dinner|supper|snacks?|protein|macros?|calories?|nutrition|portion|grams?|weight loss|target weight)\b|\d\s*g\b|אכל|ארוחה|נשנוש|גרם|קלורי|חלבון',text):return 'nutrition'
    if re.search(r'\b(compare|what was|how was|analyse|analyze|show my|data)\b',text):return 'assistant'
    if re.search(r'\b(plan|workout|train|training|ride|cycling|strength|readiness|recovery|endurance|edurance|warm.?up|cool.?down|sprint|anaerobic|threshold)\b',text):return 'trainer'
    from .training_adjustments import is_adjustment
    if is_adjustment(message):return 'trainer'
    if previous in ROLES and len(text)<160:return previous
    return 'assistant'
