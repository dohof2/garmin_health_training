"""Read-only assistant QC against the configured local database.
Run: PYTHONPATH=backend .venv/bin/python scripts/assistant_qc.py
Produces aggregate evidence only; no raw location or health observations.
"""
import json
from pathlib import Path
from unittest.mock import patch
from app.ai_chat import chat_stream

CASES = [
 'Plot my weight over the last year with a mean line',
 'Plot power versus speed across all cycling rides with correlation and a trend line',
 'Plot resting heart rate versus cycling VO2 max with correlation',
 'Plot weight; plot sleep for the last two weeks; plot steps for the past three months; plot resting heart rate',
 'plot the speed of all rides macthed to the ride on oct 6th add a refferance line (all in one plot)',
]

def run(message, context=None):
    with patch('app.ai_chat._ollama_request',side_effect=AssertionError('Basic plot must not depend on model arguments')):
        events=[json.loads(s) for s in chat_stream(message,plot_context=context,timezone_name='Asia/Jerusalem')]
    errors=[e['message'] for e in events if e['type']=='error']
    if errors: raise AssertionError(errors)
    plots=next(e['evidence']['plots'] for e in events if e['type']=='tool')
    return plots

results=[]
for message in CASES:
    plots=run(message)
    results.append({'request':message,'plots':[{'spec':p['spec'],'count':p['count'],'excluded':p['excluded'],'unpaired':p['unpaired'],'analysis':p['analysis']} for p in plots]})
    print(message,[(p['count'],p['analysis']['pearson_r']) for p in plots],flush=True)
# Scope and overlays must survive a follow-up with no textual history.
for message in ['Add a trend line and correlation','Show it for the last year','Show power instead']:
    prior=plots[0]['spec']
    plots=run(message,[prior])
    assert plots[0]['spec']['gps_reference_id']==prior['gps_reference_id']
    results.append({'request':message,'plots':[{'spec':p['spec'],'count':p['count'],'analysis':p['analysis']} for p in plots]})
    print(message,plots[0]['count'],flush=True)
Path('docs/status/assistant-qc-results.json').write_text(json.dumps(results,indent=2)+'\n')
