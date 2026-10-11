"""Independent QA probes. Run only against the disposable QA database snapshot.
HT_APP_DATA_DIR=/private/tmp/garmin-qa/data PYTHONPATH=backend .venv/bin/python docs/qa/2026-10-11/independent_audit.py
No product code changes; report contains aggregate evidence, not personal records.
"""
import json
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.ai_chat import chat_stream
from app.charts import catalog
from app.sync import SYNC_DATA_TYPES
from garminconnect import Garmin

OUT = Path(__file__).parent
assert Path(os.environ['HT_APP_DATA_DIR']).resolve() == Path('/private/tmp/garmin-qa/data')
results = {'api': [], 'assistant': [], 'charts': []}
with TestClient(app, raise_server_exceptions=False) as client:
    paths = ['/api/health','/api/settings','/api/ai/providers/status','/api/ai/tools',
             '/api/charts/catalog','/api/dashboard/widgets','/api/dashboard/cards',
             '/api/history/summary?timezone=Asia/Jerusalem','/api/history/weekly-calories',
             '/api/activities','/api/metrics','/api/imports/coverage',
             '/api/exports/original-activities','/api/sync/status','/api/sync/plan',
             '/api/garmin/connection','/api/readiness?timezone=Asia/Jerusalem',
             '/api/readiness/forecast?timezone=Asia/Jerusalem','/api/readiness/settings',
             '/api/training','/api/training/context','/api/training/coach',
             '/api/training/progression','/api/nutrition/day?day=2026-10-11&timezone=Asia/Jerusalem',
             '/api/nutrition/library','/api/nutrition/targets','/api/nutrition/foods?q=rice',
             '/api/maintenance','/api/maintenance/export.csv']
    for path in paths:
        start=time.monotonic();r=client.get(path)
        results['api'].append({'path':path,'status':r.status_code,'seconds':round(time.monotonic()-start,3)})
        if path=='/api/imports/coverage':results['import_coverage']=r.json()
        if path=='/api/ai/providers/status':results['providers']=r.json()
    invalid=[('/api/activities?timezone=Invalid/Zone',400),('/api/activities?limit=101',422),
             ('/api/activities/nonexistent',404),('/api/exports/csv/nonexistent',404),
             ('/api/sync/plan?through_date=2026-10-01&reconcile_from=2026-10-11',400)]
    for path,expected in invalid:
        r=client.get(path);results['api'].append({'path':path,'status':r.status_code,'expected':expected})
    for metric in catalog()['metrics']+catalog()['activity_fields']:
        start=time.monotonic();r=client.post('/api/charts/query',json={'spec':{'metric':metric['id'],'kind':'line','timezone':'Asia/Jerusalem'}})
        body=r.json();results['charts'].append({'metric':metric['id'],'status':r.status_code,'count':body.get('count'),'seconds':round(time.monotonic()-start,3),'error':body.get('detail')})

cases = [
    'Plot my weight over the last year with a mean line',
    'Plot power versus speed across all cycling rides with correlation and a trend line',
    'Plot resting heart rate versus cycling VO2 max with correlation',
    'Plot weight; plot sleep for the last two weeks; plot steps for the past three months; plot resting heart rate',
    'Plot hydration over time',
    'Plot acute training load over time',
    'Plot body battery versus sleep score for the last three months',
    'Plot cycling power versus sleep duration on the same date',
    'Plot my cycling cadence over time',
    'Plot weekly median weight with a 7-day rolling average',
    'Plot weight from 2026-01-01 to 2026-02-01 and steps from 2026-03-01 to 2026-04-01',
    'Summarize my steps and sleep over the last seven days.',
    'List my three most recent activities and the heart-rate or power data available for each.',
    'I want to increase FTP. Wednesday I have a hard 3-hour trip at 08:00. Adjust the rest of my week.',
    'What was my FTP last year?',
    'What is my training readiness today?',
]
for message in cases:
    start=time.monotonic()
    with patch('app.ai_chat._ollama_request',side_effect=RuntimeError('QA: request requires live model')),patch('app.ai_chat.OpenAI',side_effect=RuntimeError('QA: request requires live model')):
        events=[json.loads(s) for s in chat_stream(message,timezone_name='Asia/Jerusalem')]
    result={'request':message,'seconds':round(time.monotonic()-start,3),
            'events':[e['type'] for e in events],
            'errors':[e['message'] for e in events if e['type']=='error'],
            'answer':''.join(e.get('text','') for e in events if e['type']=='delta'),
            'tools':[e['evidence'].get('tool') for e in events if e['type']=='tool'],
            'plots':[{'spec':p['spec'],'count':p['count']} for e in events if e['type']=='tool' for p in e['evidence'].get('plots',[])]}
    results['assistant'].append(result)
    print(message, result['tools'], result['errors'],flush=True)

db=sqlite3.connect('file:/private/tmp/garmin-qa/data/health_training.sqlite3?mode=ro',uri=True)
results['database']={'integrity':db.execute('PRAGMA integrity_check').fetchone()[0],
                     'foreign_key_violations':len(db.execute('PRAGMA foreign_key_check').fetchall()),
                     'archive_categories':[r[0] for r in db.execute('SELECT DISTINCT category FROM garmin_archive_records ORDER BY category')]}
db.close()
results['sync_streams']=list(SYNC_DATA_TYPES)
results['installed_garmin_read_methods']=[n for n in dir(Garmin) if n.startswith(('get_','download_'))]
(OUT/'independent-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('Results saved',OUT/'independent-results.json')
