"""Read-only plot refinements. Context is a query specification, never factual evidence."""
import calendar
import re
from datetime import date, timedelta


class ClarificationNeeded(ValueError):
    """A question for the user, not an application failure."""


def canonical(message):
    for pattern, replacement in [(r'\bkast\b','last'),(r'\b(?:macthed|mathced|mached)\b','matched'),
                                  (r'\b(?:refferance|refference|referance)\b','reference'),
                                  (r'\b(?:corrkation|corrlation|correleation)\b','correlation'), (r'\blinair\b','linear')]:
        message=re.sub(pattern,replacement,message,flags=re.I)
    message=re.sub(r'\b(last|past)(\d+)',r'\1 \2',message,flags=re.I)
    message=re.sub(r'\b(\d+)(days?|weeks?|months?|years?)\b',r'\1 \2',message,flags=re.I)
    return message


def matched_scope(message):
    return bool(re.search(r'\b(?:matched|matching)\s+(?:cycling\s+)?rides?\b|\brides?\s+matched\b|\bsame (?:course|route)\b',canonical(message),re.I))


def plot_parts(message):
    # Split AND only after a complete date range, so "power and speed" stays intact.
    return [p.strip() for p in re.split(r';|\n|(?<=\d)\s+and\s+(?=(?:plot\s+)?[a-zA-Z])', message) if p.strip()]


def clarification_followup(message, history, today):
    if not history or history[-1]['role']!='assistant': return message
    prompt=history[-1]['content']
    previous=next((h['content'] for h in reversed(history[:-1]) if h['role']=='user'),None)
    if not previous: return message
    if 'Which Body Battery measurement' in prompt:
        chosen=re.fullmatch(r'(?:the\s+)?(?:body battery\s+)?(latest|highest|lowest|charged|drained)(?:\s+please)?[.!? ]*',message,re.I)
        if chosen: return re.sub(r'\bbody battery\b','body battery '+chosen[1].lower(),previous,flags=re.I)
    if 'How many days should the rolling average' in prompt:
        chosen=re.fullmatch(r'(\d{1,3})(?:[ -]days?)?(?:\s+please)?[.!? ]*',message,re.I)
        if chosen: return re.sub(r'\b(?:rolling|moving)\s+(?:average|mean)\b',chosen[1]+'-day rolling average',previous,flags=re.I)
    if 'Choose daily, weekly or monthly median' in prompt:
        chosen=re.fullmatch(r'(daily|weekly|monthly)(?:\s+please)?[.!? ]*',message,re.I)
        if chosen: return re.sub(r'\bmedian\b',chosen[1].lower()+' median',previous,flags=re.I)
    if 'Which period should I summarize:' in prompt and period(message,today):
        return previous+' '+message
    return message


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


def overlays(spec, message):
    if re.search(r'\b(?:remove|without|hide)\b.*\b(?:line|correlation|analysis)\b',message,re.I):
        if re.search(r'mean|average|reference|analysis',message,re.I): spec.pop('reference_lines',None)
        if re.search(r'trend|regression|analysis',message,re.I): spec.pop('trend_line',None)
        if re.search(r'correlation|analysis',message,re.I): spec.pop('correlation',None)
        return
    refs = list(spec.get('reference_lines',[]))
    if re.search(r'\b(?:mean|average)\s+(?:reference\s+)?line\b|\breference line.*\b(?:mean|average)\b',message,re.I):
        if 'mean' not in refs: refs.append('mean')
    for m in re.finditer(r'\b(?:reference|horizontal)\s+line\s+(?:at\s+)?(-?\d+(?:\.\d+)?)',message,re.I):
        value=float(m[1])
        if value not in refs: refs.append(value)
    if re.search(r'\breference line\b',message,re.I) and not refs:
        refs.append('mean')
    if refs: spec['reference_lines']=refs
    if re.search(r'\btrend(?:\s*line)?\b|\bregression\b|\bbest fit\b',message,re.I): spec['trend_line']=True
    if re.search(r'\bcorrel\w*\b|\bpearson\b',message,re.I): spec['correlation']=True


def refine(message, context, parse, today, path):
    if not context:
        return None
    from .charts import validate_spec
    if not isinstance(context,list) or not 1 <= len(context) <= 4:
        raise ValueError('Plot context must contain one to four graphs.')
    specs = [validate_spec(s,path) for s in context]
    # Explicit refinements only. Never interpret unrelated conversation as a chart command.
    if not re.search(r'\b(add|remove|without|hide|instead|same|replace|change|make|show|use|plot it|plot that|correlation|trend|regression|improvement|improving|progress|reference line)\b',message,re.I):
        return None
    fresh = parse('Plot '+message,path)
    is_followup = bool(re.search(r'\b(it|that|them|those|same|instead|replace|change|add|remove|without|hide)\b',message,re.I))
    if fresh and (not is_followup or (re.search(r'\b(plot|graph|chart)\b',message,re.I) and not re.search(r'\b(it|that|them|those|same|instead|replace|change)\b',message,re.I))):
        return None
    if not is_followup and not re.search(r'\b(last|past|correlation|trend|regression|improvement|improving|progress|reference line)\b',message,re.I):
        return None
    if fresh:
        if len(specs) > 1:
            raise ValueError('Which graph should change? Request a named graph separately.')
        replacement=fresh['plots'][0]
        specs[0].update(metric=replacement['metric'])
        if replacement.get('x_metric'):
            specs[0].update(x_metric=replacement['x_metric'],kind='scatter')
        elif re.search(r'\binstead\b|\breplace\b',message,re.I):
            specs[0].pop('x_metric',None); specs[0]['kind']='line'
        specs[0].pop('title',None)
    selected = period(message,today)
    for spec in specs:
        if selected: spec.update(start=selected[0],end=selected[1])
        if re.search(r'\b(?:all|full|entire)\s+(?:history|activities|rides|data)\b',message,re.I):
            spec.pop('start',None);spec.pop('end',None)
        if re.search(r'\ball\s+(?:activities|rides)\b',message,re.I) and not matched_scope(message): spec.pop('gps_reference_id',None)
        if re.search(r'\bbar(?:s| chart)?\b',message,re.I): spec['kind']='bar'
        if re.search(r'\bline chart\b',message,re.I): spec['kind']='line'
        for sport in ('running','cycling'):
            if re.search(r'\b'+sport+r'\b',message,re.I):
                spec['sport']=sport
                for key in ('metric','x_metric'):
                    if str(spec.get(key,'')).startswith('vo2_'): spec[key]='vo2_'+sport
                spec.pop('title',None)
        if re.search(r'\b(?:time|date)\b.*\bx[ -]?axis\b|\bx[ -]?axis\b.*\b(?:time|date)\b|\b(?:against|versus|vs)\s+(?:time|date)\b',message,re.I):
            spec.update(kind='scatter',x_metric='date');spec.pop('title',None)
        overlays(spec,message)
        if re.search(r'\b(improvement|improving|progress)\b',message,re.I):
            if spec['kind']=='scatter' and spec.get('x_metric')!='date':
                raise ValueError('To assess change over time, request a date-versus-speed or date-versus-power graph.')
            spec.update(trend_line=True,correlation=True)
    return {'plots':specs}


def history_request(message, today, path, timezone):
    """Resolve common read-only questions without free-form model tool selection."""
    from .ai_tools import AI_METRIC_TYPES
    if re.search(r'\b(plot|graph|chart|visualize)\b',message,re.I): return None
    if re.search(r'\bwhat (?:data|records|history)\b.*\b(?:rides|activities)\b',message,re.I):
        return 'list_activities',dict(start_date=(today-timedelta(days=7304)).isoformat(),end_date=today.isoformat(),limit=3,timezone=timezone,activity_type='rides' if re.search(r'\brides\b',message,re.I) else None)
    if re.search(r'\b(?:list|show)\b.*\b(?:recent|latest)\b.*\bactivities\b',message,re.I):
        m=re.search(r'\b(\d{1,3}|one|two|three|four|five|ten)\s+(?:most\s+)?recent',message,re.I)
        token=m[1].lower() if m else 'three'
        limit=int(token) if token.isdigit() else dict(one=1,two=2,three=3,four=4,five=5,ten=10)[token]
        if not 1 <= limit <= 100: raise ValueError('Request between one and 100 recent activities.')
        start=today-timedelta(days=7304)
        return 'list_activities',dict(start_date=start.isoformat(),end_date=today.isoformat(),limit=limit,timezone=timezone)
    if re.search(r'\b(?:summarize|summary|average|total|how many|how much|how was|how were|how has|has my|have I)\b',message,re.I):
        dates=period(message,today)
        from .ai_chat import _explicit_plot_arguments
        plots=_explicit_plot_arguments('Plot '+message,path)
        if plots and all(s['metric'] in AI_METRIC_TYPES and s['kind']!='scatter' for s in plots['plots']):
            if not dates: raise ClarificationNeeded('Which period should I summarize: the last seven days, this month, or another date range?')
            return 'get_health_summary',dict(start_date=dates[0],end_date=dates[1],metric_types=[s['metric'] for s in plots['plots']])
    return None


def history_answer(name,result,message=''):
    if name=='get_health_summary':
        lines=[f"{result['period']['start']}–{result['period']['end']}:"]
        for m in result['metrics']:
            use_sum = m['recommended_aggregation']=='sum' and not re.search(r'\baverage|mean\b',message,re.I)
            value=m['sum'] if use_sum else m['average']
            operation='Total' if use_sum else 'Average'
            coverage=m['coverage']
            label=m['metric_type'].replace('_',' ').capitalize()
            if re.search(r'\b(changed|change|trend)\b',message,re.I) and m.get('first') and m.get('latest'):
                if m['first']['date']==m['latest']['date']:
                    lines.append(f"{label}: only measurements from {m['latest']['date']} are available ({m['latest']['value']:.2f} {m['unit']}); there is not enough dated evidence to assess change.")
                else:
                    lines.append(f"{label}: {m['first']['value']:.2f} {m['unit']} on {m['first']['date']} → {m['latest']['value']:.2f} {m['unit']} on {m['latest']['date']} ({m['change_latest_minus_first']:+.2f} {m['unit']}).")
            else:
                lines.append(f"{label}: {operation.lower()} {value:.2f} {m['unit']} ({coverage['days_with_data']}/{coverage['days_expected']} days recorded).")
        if result['missing_metric_types']: lines.append('No recorded values for: '+', '.join(result['missing_metric_types'])+'.')
        if result['missing_metric_types'] or any(m['coverage']['days_with_data'] < m['coverage']['days_expected'] for m in result['metrics']):
            lines.append('Missing days are excluded, not counted as zero.')
        if re.search(r'\bsleep(?:ing)? enough\b',message,re.I): lines.append('Recorded duration alone does not establish whether sleep meets your individual need.')
        return '\n\n'.join(lines)
    kind='rides' if result.get('filters',{}).get('activity_type')=='rides' else 'activities'
    lines=[f"Latest {result['returned_count']} stored {kind} ({result['period']['start']}–{result['period']['end']})."]
    for a in result['activities']:
        sensor=a['sample_summary']
        summaries={m['metric_type']:m for m in a.get('activity_metrics',[])}
        def val(key,unit):
            summary=summaries.get('average_power' if 'power' in key else 'average_heart_rate')
            v=summary['value'] if summary else sensor.get(key)
            return 'unavailable' if v is None else f'{v:.1f} {unit}'
        lines.append(f"{a['name'] or a['activity_type']} · {a['local_date']} · recorded mean heart rate: {val('average_heart_rate_bpm','bpm')} · recorded mean power: {val('average_power_watts','W')}.")
    lines.append('Summary means are used when available, otherwise recorded sample means.')
    return '\n\n'.join(lines)
