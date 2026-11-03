"""Date ranges for local comparison/query services; no conversational routing."""
import calendar
import re
from datetime import date, timedelta


def period(message, today):
    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', message)
    if len(dates) == 2:
        return tuple(date.fromisoformat(v).isoformat() for v in dates)
    if len(dates) == 1 and re.search(r'\b(since|from)\b', message, re.I):
        return dates[0], today.isoformat()
    if len(dates) == 1 and re.search(r'\b(on|for)\b', message, re.I):
        return dates[0], dates[0]
    if re.search(r'\b(recently|lately)\b',message,re.I):
        return (today-timedelta(days=29)).isoformat(),today.isoformat()
    if re.search(r'\byesterday\b', message, re.I):
        day = today - timedelta(days=1)
        return day.isoformat(), day.isoformat()
    if re.search(r'\btoday\b', message, re.I):
        return today.isoformat(), today.isoformat()
    for unit, start in [('week',today-timedelta(days=today.weekday())),
                        ('month',today.replace(day=1)),('year',today.replace(month=1,day=1))]:
        if re.search(r'\bthis '+unit+r'\b|\b'+unit+r' to date\b',message,re.I):
            return start.isoformat(), today.isoformat()
        if re.search(r'\blast '+unit+r'\b',message,re.I) and not re.search(r'\b(?:the|over|during|for|past)\s+(?:the\s+)?last '+unit+r'\b',message,re.I):
            end = start-timedelta(days=1)
            beginning = end-timedelta(days=6) if unit=='week' else end.replace(day=1) if unit=='month' else end.replace(month=1,day=1)
            return beginning.isoformat(),end.isoformat()
    if re.fullmatch(r'\s*(?:\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|thirty)\s+(?:days?|weeks?|months?|years?)[.!? ]*',message,re.I):
        message='past '+message.strip()
    m = re.search(r'\b(?:last|past|previous|preceding|over|during|for)\s+(?:the\s+)?(?:(\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|thirty)\s+)?(days?|weeks?|months?|years?)\b', message, re.I)
    if not m:
        return None
    words = dict(one=1,two=2,three=3,four=4,five=5,six=6,seven=7,eight=8,nine=9,ten=10,eleven=11,twelve=12,fourteen=14,thirty=30)
    token = m[1] or 'one'
    n = int(token) if token.isdigit() else words[token.lower()]
    unit = m[2].lower()
    maximum=7305 if unit.startswith('day') else 1043 if unit.startswith('week') else 240 if unit.startswith('month') else 20
    if not 1 <= n <= maximum: raise ClarificationNeeded('Choose a period of up to 20 years.')
    if unit.startswith(('day','week')):
        start = today-timedelta(days=n*(7 if unit.startswith('week') else 1)-1)
    else:
        months = n*(12 if unit.startswith('year') else 1)
        index = today.year*12+today.month-1-months
        year, month = divmod(index,12); month += 1
        start = date(year,month,min(today.day,calendar.monthrange(year,month)[1]))
    return start.isoformat(),today.isoformat()
