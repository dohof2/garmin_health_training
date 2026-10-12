"""Live assistant overlay QA with invented recordings only; never real Garmin data."""
import json
import os
import tempfile
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import patch
from app import chatgpt_auth as auth
from app.ai_chat import chat_stream
from app.ai_providers import get_ai_settings, save_ai_settings
from app.config import database_path
from app.database import connect, migrate
from app.time_utils import calendar_date

production = database_path()
settings = get_ai_settings(production)
original_models, original_token = auth.models, auth.access_token
results = []
with tempfile.TemporaryDirectory(prefix='overlay-qc-') as directory:
    os.environ['HT_APP_DATA_DIR'] = directory
    path = Path(directory) / 'health_training.sqlite3'
    migrate(path)
    save_ai_settings({**settings, 'active_provider': 'chatgpt'}, path)
    day = calendar_date(datetime.now(UTC).isoformat(), 'Asia/Jerusalem').isoformat()
    with connect(path) as c:
        for identifier, name, kind, minute in [('qa-indoor', 'Invented Indoor Cycling', 'indoor_cycling', 0), ('qa-virtual', 'Invented Virtual Ride', 'virtual_ride', 1)]:
            origin = datetime.fromisoformat(day + f'T08:{minute:02d}:00+00:00')
            c.execute('INSERT INTO activities(id,source_name,name,activity_type,started_at,duration_seconds) VALUES(?,?,?,?,?,?)', (identifier, 'garmin_connect', name, kind, origin.isoformat(), 180))
            for second in range(181):
                c.execute('INSERT INTO activity_samples(activity_id,recorded_at,power_watts,heart_rate_bpm) VALUES(?,?,?,?)', (identifier, (origin + timedelta(seconds=second)).isoformat(), 150 + (second % 40) + minute * 10, 120 + second % 10 + minute))
    history, context = [], None
    with patch.object(auth, 'models', side_effect=lambda path=None: original_models(production)), patch.object(auth, 'access_token', side_effect=lambda path=None: original_token(production)):
        for question in ['take my two activities I did today and plot both power by time on one plot each one in different colour', 'Now show heart rate from those same two activities on one plot instead.']:
            events = [json.loads(event) for event in chat_stream(question, history, 'Asia/Jerusalem', path, plot_context=context)]
            answer = ''.join(e.get('text', '') for e in events if e['type'] == 'delta')
            evidence = [e['evidence'] for e in events if e['type'] == 'tool']
            plots = [p for e in evidence for p in e.get('plots', [])]
            errors = [e['message'] for e in events if e['type'] == 'error']
            expected = 'stream:power' if not history else 'stream:heart_rate'
            passed = not errors and len(plots) == 1 and plots[0]['spec']['metric'] == expected and {s['id'] for s in plots[0].get('series', [])} == {'qa-indoor', 'qa-virtual'}
            results.append({'question': question, 'passed': passed, 'answer': answer, 'errors': errors, 'tools': [e['tool'] for e in evidence], 'plots': [{'metric': p['spec']['metric'], 'traces': len(p.get('series', [])), 'count': p['count']} for p in plots]})
            history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer}]
            context = [p['spec'] for p in plots] or context
output = Path('docs/qa/2026-10-11/activity-overlay-live.json')
output.write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
