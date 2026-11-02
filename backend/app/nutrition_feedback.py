"""Brief meal feedback grounded in saved nutrients and named foods, without another model call."""
import re


def partial_explanation(meal, *, hebrew=False):
    """Name missing stored values without treating estimated portions as missing."""
    labels = {'calories_kcal': ('calories', 'קלוריות'), 'protein_grams': ('protein', 'חלבון'),
              'fat_grams': ('fat', 'שומן'), 'carbohydrate_grams': ('carbs', 'פחמימות')}
    parts = []
    for item in meal['items']:
        missing = [names[1 if hebrew else 0] for key, names in labels.items() if item[key] is None]
        if not missing:
            continue
        source = (item.get('source') or '').lower()
        unknown_source = not source or 'unknown' in source
        if hebrew:
            reason = 'לא נמצאה התאמה תזונתית או הערכה זמינה' if unknown_source else 'הערכים האלה חסרים במידע התזונתי שנשמר'
            parts.append(f"{item['name']}: חסרים {', '.join(missing)}, כי {reason}")
        else:
            reason = 'no usable nutrition match or estimate was available' if unknown_source else 'these values were not supplied in the saved nutrition data'
            parts.append(f"{item['name']} is missing {', '.join(missing)} because {reason}")
    if not parts:
        return ''
    if hebrew:
        return 'רישום חלקי: ' + '; '.join(parts) + '. אפשר למסור בשיחה תווית מוצר או פרטי מתכון, או להשלים את הערכים בעריכת הארוחה.'
    return 'Partial log: ' + '; '.join(parts) + '. Share a product label or recipe details in chat, or add the missing values in Edit meal.'


def meal_feedback(meal, *, hebrew=False):
    names=', '.join(i['name'] for i in meal['items'])
    protein=meal['totals']['protein_grams']
    fiber=bool(re.search(r'\b(oats?|oatmeal|whole.?grain|whole.?wheat|lentils?|beans?|chickpeas?|vegetables?|broccoli|spinach|salad|avocado|berries|apples?|pears?|nuts?|almonds?|seeds?)\b|שיבולת|מלאה|מלאות|עדשים|שעועית|חומוס|ירקות|ברוקולי|תרד|סלט|אבוקדו|תפוח|אגוז|שקדים|זרעים',names,re.I))
    p=protein['known_total']
    if hebrew:
        lines=[f"בארוחה רשומים כ־{p:g} גרם חלבון"+(' לפחות; לחלק מהמזונות חסרים ערכים.' if protein['missing_items'] else '.')]
        if not protein['missing_items']:
            lines.append('כמות החלבון משמעותית לארוחה.' if p>=20 else 'כמות החלבון צנועה; אפשר לשלב מקור חלבון בארוחה הבאה.' if meal['meal_type']!='snack' else 'זו תרומת חלבון קטנה מהנשנוש; האיזון תלוי בשאר היום.')
        lines.append('יש כאן מזונות המספקים סיבים; גרמי סיבים אינם נמדדים ביומן.' if fiber else 'לא זוהה מקור סיבים ברור בשם המזון; ירקות, קטניות או דגן מלא יכולים להשלים את הארוחה.')
        if fiber and not protein['missing_items'] and p>=20:
            lines.append('השילוב של חלבון ומזונות עם סיבים תומך בארוחה מאוזנת.')
    else:
        lines=[f"This meal provides about {p:g} g of recorded protein"+(' at minimum; some foods have missing values.' if protein['missing_items'] else '.')]
        if not protein['missing_items']:
            lines.append('It makes a substantial protein contribution.' if p>=20 else 'Protein is modest for a main meal; include a protein source in your next meal.' if meal['meal_type']!='snack' else 'This snack makes a small protein contribution; balance depends on the rest of your day.')
        lines.append('It includes foods that supply fiber; fiber grams are not tracked in this log.' if fiber else 'No clear fiber source is identifiable from the food names; vegetables, legumes or whole grains could round it out.')
        if fiber and not protein['missing_items'] and p>=20:
            lines.append('The combination of protein and fiber sources supports a balanced meal.')
    return ' '.join(lines)


def goal_feedback(status, *, hebrew=False):
    target=status['target'];totals=status['totals'];remaining=status['remaining']
    if not target:
        return {'goal_progress':'לא מוגדר יעד תזונה ליום הזה, ולכן אי אפשר להשוות אליו את היומן.' if hebrew else 'No nutrition target is saved for this day, so goal progress is unavailable.',
                'next_meal_suggestion':'לארוחה הבאה אפשר לשלב מקור חלבון, ירקות ומקור פחמימה לפי התיאבון והאימון.' if hebrew else 'For your next meal, consider a protein source, vegetables and a carbohydrate portion suited to your appetite and training.'}
    labels={'calories_kcal':('kcal','קלוריות'),'protein_grams':('g protein','גרם חלבון'),'fat_grams':('g fat','גרם שומן'),'carbohydrate_grams':('g carbohydrate','גרם פחמימות')}
    parts=[]
    for key,(english,hebrew_label) in labels.items():
        goal=target.get(key)
        if goal is None:continue
        value=totals[key];unit=hebrew_label if hebrew else english
        part=f"{value['known_total']:g}/{goal:g} {unit}"
        if value['missing_items']:part+=' (חלקי)' if hebrew else ' (partial)'
        elif remaining[key]>0:part+=f" — נותרו {remaining[key]:g}" if hebrew else f" — {remaining[key]:g} remaining"
        elif remaining[key]<0:part+=f" — {abs(remaining[key]):g} מעל היעד" if hebrew else f" — {abs(remaining[key]):g} over target"
        else:part+=' — היעד הושג' if hebrew else ' — target met'
        parts.append(part)
    progress=('לפי המזון שנרשם היום: ' if hebrew else 'Based on today’s logged food: ')+'; '.join(parts)+'.'
    protein=remaining.get('protein_grams');calories=remaining.get('calories_kcal');carbs=remaining.get('carbohydrate_grams')
    if any(totals[key]['missing_items'] for key in labels):
        suggestion='חלק מהערכים חסרים; לארוחה הבאה אפשר לשלב מקור חלבון וירקות, בלי לכוון למספר מדויק על בסיס סיכום חלקי.' if hebrew else 'Some nutrients are missing, so consider a protein source and vegetables next meal rather than aiming at an exact gap from partial totals.'
    elif protein is not None and protein>0:
        suggestion='בארוחה הבאה כדאי לתת מקום למקור חלבון כמו טופו, דג או יוגורט, לצד ירקות; התאימו את הכמות ליתרת החלבון ולתיאבון.' if hebrew else 'For your next meal, prioritize a protein source you eat, such as tofu, fish or yogurt, alongside vegetables; size it to your remaining protein and appetite.'
    elif carbs is not None and carbs>0 and (calories is None or calories>0):
        suggestion='בארוחה הבאה אפשר לשלב דגן מלא או פרי וירקות כדי להשלים את יתרת הפחמימות ולהוסיף סיבים.' if hebrew else 'Whole grains or fruit with vegetables could help fill the remaining carbohydrate gap and add fiber next meal.'
    elif protein is None:
        suggestion='לא הוגדר יעד חלבון מלא; בארוחה הבאה אפשר לשלב מקור חלבון וירקות לפי התיאבון וצורכי האימון.' if hebrew else 'A protein target is not available; consider a protein source and vegetables next meal, guided by appetite and training needs.'
    else:
        suggestion='אין צורך להשלים עוד חלבון לפי היעד הרשום; בארוחה הבאה היעזרו ברעב ובצורכי האימון, בלי לדלג על אוכל רק כדי להתאים למספר.' if hebrew else 'There is no recorded protein gap to chase; let appetite and training needs guide your next meal rather than skipping food just to match a number.'
    return {'goal_progress':progress,'next_meal_suggestion':suggestion}
