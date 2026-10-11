"""Exercise the real HTTP chat route on an isolated copy, including live Ollama.

PYTHONPATH=backend:scripts .venv/bin/python scripts/run_assistant_acceptance.py
Detailed output is personal local QC evidence and is excluded from Git.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch
from assistant_question_bank import CASES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='docs/qa/2026-10-11/assistant-acceptance-results.json')
    parser.add_argument('--category',action='append')
    parser.add_argument('--data-dir',default='/private/tmp/garmin-assistant-acceptance')
    parser.add_argument('--reuse',action='store_true')
    args=parser.parse_args()
    directory=Path(args.data_dir);directory.mkdir(parents=True,exist_ok=True)
    db=directory/'health_training.sqlite3'
    if not args.reuse:
        source=Path('data/health_training.sqlite3').resolve()
        with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as src,sqlite3.connect(db) as dst:
            src.backup(dst)
    os.environ['HT_APP_DATA_DIR']=str(directory)
    from fastapi.testclient import TestClient
    from app.main import app
    from app import ai_chat
    results=[]
    counts={'model_requests':0}
    original=ai_chat._ollama_request
    def model(payload,timeout):
        counts['model_requests']+=1
        return original(payload,timeout)
    def ask(client,message,history=None,context=None):
        response=client.post('/api/ai/chat',json={'message':message,'history':history or [],'timezone':'Asia/Jerusalem','plot_context':context})
        if response.status_code!=200: raise AssertionError(f'HTTP {response.status_code}: {response.text}')
        events=[json.loads(line) for line in response.text.splitlines() if line]
        answer=''.join(e.get('text','') for e in events if e['type']=='delta')
        evidence=[e['evidence'] for e in events if e['type']=='tool']
        return events,answer,evidence
    with TestClient(app) as client,patch('app.ai_chat._ollama_request',side_effect=model):
        for case in CASES:
            if args.category and case['category'] not in args.category: continue
            started=time.monotonic();before=counts['model_requests'];failures=[]
            history=[];context=None
            try:
                if case.get('seed'):
                    _,seed_answer,seed_evidence=ask(client,case['seed'])
                    history=[{'role':'user','content':case['seed']},{'role':'assistant','content':seed_answer}]
                    if case.get('plot_context'):
                        context=[p['spec'] for e in seed_evidence for p in e.get('plots',[])]
                events,answer,evidence=ask(client,case['message'],history,context)
                errors=[e['message'] for e in events if e['type']=='error']
                if case.get('clarify'):
                    if case['clarify'].lower() not in (answer+' '.join(errors)).lower(): failures.append('Expected focused clarification missing')
                    if errors and not case.get('controlled_error'): failures.append('Unexpected error')
                else:
                    if errors: failures.extend(errors)
                    if case['tool'] not in [e['tool'] for e in evidence]: failures.append(f"Expected tool {case['tool']}")
                    if not any(e['type']=='complete' for e in events): failures.append('Missing completion')
                plots=[p for e in evidence for p in e.get('plots',[])]
                if case.get('period'):
                    periods=[(p['spec'].get('start'),p['spec'].get('end')) for p in plots] if plots else [(e.get('period',{}).get('start'),e.get('period',{}).get('end')) for e in evidence if e['tool']==case.get('tool')]
                    if not periods or any(list(p)!=case['period'] for p in periods): failures.append(f'Wrong period: {periods}')
                if case.get('metrics'):
                    actual={v for p in plots for v in [p['spec']['metric'],p['spec'].get('x_metric')] if v and v!='date'}
                    if actual!=set(case['metrics']): failures.append(f'Wrong metrics: {sorted(actual)}')
                if case.get('spec'):
                    if not plots or any(p['spec'].get(k)!=v for p in plots for k,v in case['spec'].items()): failures.append('Requested transformation/refinement missing')
                if case.get('oracle')=='ride' and evidence:
                    result=next((e for e in evidence if e['tool']=='compare_latest_ride'),None)
                    if result:
                        with sqlite3.connect(db) as c:
                            rows=c.execute("SELECT id,started_at,activity_type,distance_meters FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture'").fetchall()
                        from datetime import datetime
                        from zoneinfo import ZoneInfo
                        allowed={'cycling','mountain_biking','gravel_cycling','virtual_ride','indoor_cycling'}
                        others=[r for r in rows if r[0]!=result['reference_record']['id'] and r[2] in allowed and case['period'][0]<=datetime.fromisoformat(r[1].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Jerusalem')).date().isoformat()<=case['period'][1]]
                        if len(others)!=result['candidate_pool_count']: failures.append('Independent ride count mismatch')
                        from statistics import median
                        distances=[r[3]/1000 for r in others if r[3] is not None]
                        item=next((r for r in result['comparisons'] if r['metric']=='distance_meters'),None)
                        if item and distances and item['median']!=median(distances): failures.append('Independent distance median mismatch')
                if case.get('oracle')=='summary' and evidence:
                    summary=next((e for e in evidence if e['tool']=='get_health_summary'),None)
                    if summary:
                        metrics=summary.get('metrics',[])
                        if case.get('summary_metric') and case['summary_metric'] not in {m['metric_type'] for m in metrics} and case['summary_metric'] not in summary.get('missing_metric_types',[]): failures.append('Requested health metric missing')
                        for metric in metrics:
                            if metric['metric_type'] in {'hydration','acute_training_load'}: continue
                            with sqlite3.connect(db) as c:
                                values=[r[0] for r in c.execute("SELECT value FROM metric_readings WHERE source_name!='synthetic_fixture' AND metric_type=? AND unit=? AND substr(recorded_at,1,10) BETWEEN ? AND ?",(metric['metric_type'],metric['source_unit'],*case['period']))]
                            if metric['unit']=='hours' and metric['source_unit']=='s': values=[v/3600 for v in values]
                            if not values or len(values)!=metric['count'] or abs(sum(values)-metric['sum'])>1e-7 or abs(sum(values)/len(values)-metric['average'])>1e-7: failures.append('Independent summary arithmetic mismatch')
                            chosen=metric['average'] if 'average' in case['message'].lower() else metric['sum'] if metric['recommended_aggregation']=='sum' else metric['average']
                            if f'{chosen:.2f}' not in answer: failures.append('Expected numeric summary absent from answer')
                if len(answer.split())>220 and not case.get('review_required'): failures.append(f'Answer too long: {len(answer.split())} words')
                if 'no rides exist' in answer.lower(): failures.append('False absence claim requires review')
                if case['message']=='What data do you have about my rides?' and any(r['activity_type'] not in {'cycling','mountain_biking','gravel_cycling','virtual_ride','indoor_cycling'} for e in evidence for r in e.get('records',[])): failures.append('Non-ride included in ride answer')
                if case['message']=='Has my weight changed recently?' and any(m.get('first',{}).get('date')==m.get('latest',{}).get('date') for e in evidence for m in e.get('metrics',[])) and 'not enough dated evidence' not in answer: failures.append('Single date incorrectly presented as a trend')
                status='fail' if failures else 'pass'
            except Exception as error:
                status='fail';failures=[str(error)];answer='';evidence=[];errors=[]
            row={**case,'status':status,'failures':failures,'answer':answer,'evidence':evidence,
                 'seconds':round(time.monotonic()-started,3),'model_requests':counts['model_requests']-before,
                 'word_count':len(answer.split())}
            results.append(row)
            Path(args.output).write_text(json.dumps({'results':results,'model_requests':counts['model_requests']},indent=2))
            print(case['id'],status,round(row['seconds'],1),'s',failures,flush=True)
    print('TOTAL',len(results),'PASS',sum(r['status']=='pass' for r in results),'FAIL',sum(r['status']=='fail' for r in results),flush=True)


if __name__=='__main__':main()
