"""One conversation with explicit role selection and conservative automatic routing."""
import re
ROLES=('trainer','assistant','nutrition')

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
    if re.search(r'\b(burned|burnt|plot|graph|compare|uphill|climb|average power|what was|how was|analyse|analyze|show my|data)\b',text):return 'assistant'
    if re.search(r'\b(how|what|show|summarize|report)\b',text) and re.search(r'\b(steps|hrv|sleep|heart rate|weight history)\b',text):return 'assistant'
    if re.search(r'\b(food|meal|eat|ate|eaten|breakfast|lunch|dinner|supper|protein|macros?|calories?|nutrition|portion|grams?|weight loss|target weight)\b|אכל|ארוחה|גרם|קלורי|חלבון',text):return 'nutrition'
    if re.search(r'\b(plan|workout|train|training|ride|cycling|strength|readiness|recovery|endurance|edurance|warm.?up|cool.?down|sprint|anaerobic|threshold)\b',text):return 'trainer'
    from .training_adjustments import is_adjustment
    if is_adjustment(message):return 'trainer'
    if previous in ROLES and len(text)<160:return previous
    return 'assistant'
