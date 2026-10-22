"""Benchmark read paths on a disposable copy, without changing personal records."""
import argparse
import cProfile
import io
import json
import pstats
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import database_path
from app.database import migrate
from app.charts import chart_data,catalog
from app.history import history_summary,list_activities,get_activity,weekly_calories_summary
from app.import_coverage import import_coverage
from app.exports import original_activity_inventory
from app.readiness import readiness_history
from app.readiness_forecast import forecast
from app.training import list_training
from app.active_training import active_view


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--repeat',type=int,default=3);parser.add_argument('--profile',action='store_true');args=parser.parse_args()
    tz='Asia/Jerusalem';today=datetime.now(ZoneInfo(tz)).date();results=[]
    with tempfile.TemporaryDirectory(prefix='garmin-performance-') as directory:
        path=Path(directory)/'snapshot.sqlite'
        with sqlite3.connect(database_path().resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(path) as target:source.backup(target)
        migrate(path)
        with sqlite3.connect(path) as c:latest=c.execute("SELECT id FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' ORDER BY started_at DESC LIMIT 1").fetchone()
        cases={
            'history_summary':lambda:history_summary(path,timezone_name=tz),
            'weekly_calories':lambda:weekly_calories_summary(path),
            'activities_page':lambda:list_activities(path=path,limit=50,timezone_name=tz),
            'import_coverage':lambda:import_coverage(path),
            'original_inventory':lambda:original_activity_inventory(path),
            'chart_catalog':lambda:catalog(path),
            'readiness_14_days':lambda:readiness_history(days=14,timezone_name=tz,path=path),
            'readiness_forecast':lambda:forecast(tz,path),
            'training_history':lambda:list_training(path),
            'training_history_compact':lambda:list_training(path,compact=True),
            'active_plan':lambda:active_view(path,tz),
        }
        specs={
            'weight_all':{'metric':'weight','kind':'line','trend_line':True},
            'power_vs_speed':{'metric':'activity_power','x_metric':'activity_speed','kind':'scatter','correlation':True,'sport':'cycling'},
            'sleep_90_days':{'metric':'sleep_score','kind':'line','start':(today-timedelta(days=89)).isoformat()},
            'load_28_days':{'metric':'acute_training_load','kind':'line','window_days':28,'show_chronic':True,'show_optimal_range':True},
            'vo2_dial':{'metric':'vo2_cycling','kind':'dial'},
        }
        if latest:
            cases['activity_detail']=lambda:get_activity(latest[0],path,timezone_name=tz)
            specs['recorded_power']={'metric':'stream:power','kind':'line','activity_ids':[latest[0]],'x_metric':'elapsed_time'}
        for name,spec in specs.items():cases['plot_'+name]=lambda spec=spec:chart_data({**spec,'timezone':tz},path)
        for name,operation in cases.items():
            samples=[];cpu=[];size=0;profile=cProfile.Profile() if args.profile else None
            try:
                for repeat in range(args.repeat):
                    start=time.perf_counter();cpu_start=time.process_time()
                    if profile and repeat==0:profile.enable()
                    try:result=operation()
                    finally:
                        if profile and repeat==0:profile.disable()
                    samples.append(round((time.perf_counter()-start)*1000,2));cpu.append(round((time.process_time()-cpu_start)*1000,2))
                    size=len(json.dumps(result,default=str).encode())
                row={'case':name,'milliseconds':samples,'cpu_ms':cpu,'response_bytes':size}
                if profile:
                    text=io.StringIO();pstats.Stats(profile,stream=text).strip_dirs().sort_stats('cumulative').print_stats(12);row['profile']=text.getvalue()
            except Exception as error:row={'case':name,'error':type(error).__name__+': '+str(error)}
            results.append(row);print(json.dumps({k:v for k,v in row.items() if k!='profile'}),flush=True)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps({'scope':'Disposable SQLite snapshot; direct function timings, not browser or network timings.','results':results},indent=2)+'\n')


if __name__=='__main__':main()
