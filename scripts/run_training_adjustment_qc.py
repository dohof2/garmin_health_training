"""Repeat the 50-request chat/save contract in disposable databases and export evidence.

Run from the repository root: .venv/bin/python scripts/run_training_adjustment_qc.py
No remote model or personal workout is modified.
"""
import json
import sqlite3
from contextlib import closing
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend'/'tests')]
from test_training_adjustments import CASES, NOW, TZ, fixture
from app.ai_chat import chat_stream
from app.training import list_training
from app.training_adjustments import save


def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='trainer-adjustment-qc-') as directory:
        base=Path(directory)/'base.sqlite';fixture(base)
        for index,(message,expected) in enumerate(CASES,1):
            path=Path(directory)/f'{index}.sqlite'
            with closing(sqlite3.connect(base)) as source, closing(sqlite3.connect(path)) as target:
                source.backup(target)
            before=list_training(path)
            with patch('app.training_adjustments.datetime',wraps=datetime) as clock, patch('app.ai_chat._chatgpt_stream',side_effect=AssertionError('Unexpected provider fallback')):
                clock.now.return_value=NOW
                events=[json.loads(e) for e in chat_stream(message,path=path,timezone_name=TZ,coaching_context={'ongoing':True})]
            proposal=next(e['evidence']['training_adjustment'] for e in events if e['type']=='tool')
            assert proposal['status']==expected,(message,proposal)
            assert before==list_training(path),'Preview wrote a workout'
            saved=save({'message':message,'fingerprint':proposal['fingerprint']},path,NOW) if expected=='proposal' else None
            results.append({'id':index,'request':message,'expected':expected,'actual':proposal['status'],'answer':proposal['message'],'adjustments':proposal['adjustments'],'save_result':saved,'passed':True})
    output=ROOT/'docs'/'qa'/'2026-10-21-trainer-adjustments';output.mkdir(parents=True,exist_ok=True)
    (output/'results.json').write_text(json.dumps({'scope':'Isolated chat routing, real recovery policy, proposals and save; no remote-model evaluation or personal-data edits.','fixture_date':NOW.isoformat(),'results':results},indent=2)+'\n')
    counts={status:sum(r['actual']==status for r in results) for status in ('proposal','not_recommended','needs_input')}
    lines=['# Casual trainer adjustment QC','',f"50/50 requests passed: {counts['proposal']} reviewable changes, {counts['not_recommended']} reasoned declines, {counts['needs_input']} focused clarifications.",'','Each request ran through `chat_stream`, including an existing coaching context. The isolated fixture has consistent cycling history and an easy-only week so the positive intensity branch can be tested. Proposal cases were actually saved in disposable copies. Previews made no workout changes. Separate regression tests cover poor recorded sleep, existing quality sessions, recovery weeks, stale revisions and forged proposals.','', 'These are deterministic chat/tool tests, not 50 remote-model generations. The test fixture is invented; the personal plan was not changed. Saving a weekly change adapts materialized sessions in the next seven days, while retaining the program goal and blocks. Requests to increase volume require a reviewed replacement week; strength load changes require exercise details; schedule moves require a clear source and destination.','', 'Repeat: `.venv/bin/python scripts/run_training_adjustment_qc.py`','', '| # | Request | Expected and observed |','|---|---|---|']
    for r in results:lines.append(f"| {r['id']} | {r['request']} | {r['actual']} |")
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'passed':len(results),'outcomes':counts,'report':str(output/'REPORT.md')}))


if __name__=='__main__':main()
