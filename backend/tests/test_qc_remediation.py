import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from app.database import migrate,connect
from app.charts import chart_data,catalog
from app.ai_chat import chat_stream
from app.ai_tools import execute_tool
from app.garmin_connection import GarminConnectProvider
from app.sync import run_sync,_upsert_activity_detail
from app.exports import original_activity_inventory
from app.main import garmin_import


class QCRemediationTests(unittest.TestCase):
    def test_last_year_wording_clarifies_and_preserves_period(self):
        from app.ride_comparison import comparison_start,comparison_end
        question='how was my last ride compared to the rides in the last year?'
        with patch('app.ai_chat._today',return_value=date(2026,10,11)),patch('app.ai_chat._ollama_request') as model:
            events=[json.loads(e) for e in chat_stream(question,path=self.path)]
            clarification=''.join(e.get('text','') for e in events if e['type']=='delta')
            self.assertIn('compared with',clarification)
            history=[{'role':'user','content':question},{'role':'assistant','content':clarification}]
            followup=[json.loads(e) for e in chat_stream('general records',history=history,path=self.path)]
        model.assert_not_called()
        evidence=next(e['evidence'] for e in followup if e['type']=='tool')
        self.assertEqual(evidence['period'],{'start':'2025-10-11','end':'2026-10-11'})
        self.assertEqual(comparison_start('last year',date(2026,10,11)),date(2025,1,1))
        self.assertEqual(comparison_end('last year',date(2026,10,11)),date(2025,12,31))

    def test_latest_ride_comparison_uses_year_without_gps_matching(self):
        with connect(self.path) as c:
            c.execute("UPDATE activities SET distance_meters=10000,duration_seconds=3600")
            for id, source, deleted, day, distance in [
                ('latest','garmin_connect',None,'2026-10-09',30000),
                ('old','garmin_connect',None,'2025-12-31',999999),
                ('fake','synthetic_fixture',None,'2026-10-10',999999),
                ('removed','garmin_connect','2026-10-10','2026-10-10',999999)]:
                c.execute("INSERT INTO activities(id,source_name,source_record_id,activity_type,name,started_at,distance_meters,deleted_at) VALUES(?,?,?,'mountain_biking','Test ride',?,?,?)",(id,source,id,day+'T10:00:00Z',distance,deleted))
        with patch('app.ai_chat._today',return_value=date(2026,10,11)),patch('app.ai_chat._ollama_request') as model:
            question='How was my last ride compared to other rides this year?'
            first=[json.loads(e) for e in chat_stream(question,path=self.path)]
            clarification=''.join(e.get('text','') for e in first if e['type']=='delta')
            self.assertIn('compared with',clarification)
            self.assertEqual(next(e['evidence']['tool'] for e in first if e['type']=='tool'),'compare_latest_ride')
            history=[{'role':'user','content':question},{'role':'assistant','content':clarification}]
            events=[json.loads(e) for e in chat_stream('All rides',history=history,path=self.path)]
        model.assert_not_called()
        self.assertFalse([e for e in events if e['type']=='error'],events)
        result=next(e['evidence'] for e in events if e['type']=='tool')
        self.assertEqual(result['reference_record']['id'],'latest')
        self.assertEqual(result['candidate_pool_count'],2)
        distance=next(r for r in result['comparisons'] if r['metric']=='distance_meters')
        self.assertEqual(distance['median'],10)
        self.assertEqual(distance['reference'],30)
        answer=''.join(e.get('text','') for e in events if e['type']=='delta')
        self.assertIn('200.0% above',answer)
        self.assertIn('2026-01-01',answer)
        with patch('app.ai_chat._today',return_value=date(2026,10,11)),patch('app.ai_chat.execute_tool',return_value={'dummy':True}) as gps,patch('app.ai_chat._tool_evidence',return_value={'tool':'find_same_course_rides'}),patch('app.ai_chat._deterministic_answer',return_value='GPS comparison'):
            list(chat_stream('Same route',history=history,path=self.path))
        self.assertEqual(gps.call_args.args[1]['candidate_start_date'],'2026-01-01')
        self.assertEqual(gps.call_args.args[1]['candidate_end_date'],'2026-10-11')

    def setUp(self):
        calendar_patch=patch('app.ride_comparison.date',wraps=date)
        calendar=calendar_patch.start();calendar.today.return_value=date(2026,10,11)
        self.addCleanup(calendar_patch.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.sqlite3';migrate(self.path)
        with connect(self.path) as c:
            for i in range(1,15):
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,'manual','weight',?,?,'kg')",(str(i),f'2026-01-{i:02}',float(i)))
            for id,power in [('a',100),('b',200)]:
                c.execute("INSERT INTO activities(id,source_name,source_record_id,activity_type,started_at) VALUES(?,'garmin_connect',?,'cycling','2026-01-01T10:00:00Z')",(id,id))
                c.execute("INSERT INTO activity_metrics(activity_id,metric_type,value,unit,source_method,source_field) VALUES(?,'average_power',?,'W','garmin_summary','averagePower')",(id,power))

    def test_same_date_mixed_pairing_retains_each_activity_in_both_directions(self):
        for y,x in [('activity_power','weight'),('weight','activity_power')]:
            r=chart_data({'metric':y,'x_metric':x,'kind':'scatter'},self.path)
            self.assertEqual(r['count'],2)
            self.assertEqual({p['id'] for p in r['points']},{'a','b'})
            self.assertEqual({p['x'] if x=='weight' else p['y'] for p in r['points']},{1})

    def test_grouped_median_and_trailing_calendar_average(self):
        r=chart_data({'metric':'weight','kind':'line','aggregation':'weekly_median'},self.path)
        self.assertEqual([p['y'] for p in r['points']],[2.5,8,13])
        r=chart_data({'metric':'weight','kind':'line','rolling_days':7},self.path)
        self.assertEqual(r['points'][6]['y'],4)
        self.assertEqual(r['points'][7]['y'],5)
        for spec in [{'rolling_days':True},{'aggregation':'weekly_fake'},{'rolling_days':0}]:
            with self.assertRaises(ValueError):chart_data({'metric':'weight','kind':'line',**spec},self.path)

    def test_assistant_transforms_are_executed(self):
        for text,key,value in [('Plot weekly median weight','aggregation','weekly_median'),('Plot weight with a 7-day rolling average','rolling_days',7)]:
            with patch('app.ai_chat._ollama_request') as model:
                events=[json.loads(e) for e in chat_stream(text,path=self.path)]
            self.assertFalse([e for e in events if e['type']=='error'],events)
            result=next(e['evidence']['plots'][0] for e in events if e['type']=='tool')
            self.assertEqual(result['spec'][key],value)
            model.assert_not_called()

    def test_archive_discovery_is_read_only_and_keeps_numeric_fields(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES('load','garmin_export','acute_training_load','load','2026-01-01',?)",(json.dumps({'dailyTrainingLoadAcute':123,'nested':{'unconsumed':7},'timestamp':111}),))
        ids={m['id'] for m in catalog(self.path)['metrics']}
        self.assertIn('archive:acute_training_load:$.nested.unconsumed',ids)
        self.assertNotIn('archive:acute_training_load:$.timestamp',ids)
        r=chart_data({'metric':'acute_training_load','kind':'line'},self.path)
        self.assertEqual(r['points'][0]['y'],123)
        r=chart_data({'metric':'archive:acute_training_load:$.nested.unconsumed','kind':'line'},self.path)
        self.assertEqual(r['points'][0]['y'],7)

    def test_successful_supplementary_payloads_survive_another_endpoint_failure(self):
        class Client:
            def get_hydration_data(self,day):return {'valueInML':500,'notUsedYet':{'new':42}}
            def get_stress_data(self,day):raise RuntimeError('Temporary unavailable')
        r=run_sync(GarminConnectProvider(Client()),date(2026,1,1),self.path,data_types=['supplementary_metrics'])
        self.assertEqual(r['status'],'failed')
        with connect(self.path) as c:
            raw=json.loads(c.execute("SELECT payload_json FROM garmin_sync_payloads WHERE data_type='supplementary_metrics'").fetchone()[0])
            self.assertIsNone(c.execute("SELECT coverage_end FROM sync_checkpoints WHERE data_type='supplementary_metrics'").fetchone()[0])
        self.assertEqual(raw['endpoints']['get_hydration_data']['notUsedYet']['new'],42)
        self.assertIn('get_stress_data',raw['failures'])
        from app.sync import sync_status
        diagnostics=sync_status(self.path)['additional_data']
        self.assertIn('get_stress_data',diagnostics['failures'])
        self.assertIn('get_hydration_data',diagnostics['successful_endpoints'])

    def test_successful_hydration_sync_normalizes_and_keeps_unused_fields(self):
        class Client:
            def get_hydration_data(self,day):return {'valueInML':500,'unused':7}
        r=run_sync(GarminConnectProvider(Client()),date(2026,1,1),self.path,data_types=['supplementary_metrics'])
        self.assertEqual(r['status'],'completed')
        self.assertEqual(chart_data({'metric':'hydration','kind':'line'},self.path)['points'][0]['y'],500)
        summary=execute_tool('get_health_summary',{'start_date':'2026-01-01','end_date':'2026-01-01','metric_types':['hydration']},self.path)
        self.assertEqual(summary['metrics'][0]['sum'],500)

    def test_original_live_fit_bytes_are_preserved_and_exportable(self):
        payload=b'original with laps events developer fields'
        with connect(self.path) as c,patch('app.sync._decode_fit',return_value=({},[])):
            _upsert_activity_detail(c,'a',payload,self.path)
            row=c.execute("SELECT stored_path FROM source_files WHERE original_name='activity-a.fit'").fetchone()
            self.assertEqual(Path(row[0]).read_bytes(),payload)
        self.assertEqual(original_activity_inventory(self.path)['files'],1)

    def test_import_calls_every_stage_and_reports_partial_failure(self):
        primary={'status':'completed','activities':{},'daily_metrics':{},'sleep_metrics':{}}
        with patch('app.main.import_garmin_export',return_value=primary),patch('app.fit_import.import_fit_activity_samples',return_value={'status':'completed'}) as fit,patch('app.xml_activity_import.import_xml_activity_details',return_value={'status':'completed'}) as xml,patch('app.health_fit_import.import_health_fit_samples',side_effect=ValueError('bad file')) as health,patch('app.main.import_wellness_records',return_value={'status':'completed'}) as wellness,patch('app.main.import_extended_archive',return_value={'status':'completed'}) as extended:
            r=garmin_import(True)
        for stage in [fit,xml,health,wellness,extended]:stage.assert_called_once()
        self.assertEqual(r['status'],'completed_with_failures')
        self.assertEqual(r['stages']['health_fit']['error'],'bad file')
        self.assertEqual(r['stages']['extended']['status'],'completed')

    def test_supplementary_collections_follow_pages_and_children(self):
        from app.supplementary_sync import fetch_supplementary
        class Client:
            profile_id=12
            def get_workouts(self,start=0,limit=100):
                return [{'workoutId':i} for i in range(start,min(start+limit,101))]
            def get_workout_by_id(self,id):return {'workoutId':id,'unused':7}
        result=fetch_supplementary(Client(),'2026-01-01','2026-01-01')
        self.assertFalse(result['failures'])
        self.assertEqual([len(p) for p in result['endpoints']['get_workouts']],[100,1])
        self.assertIn('get_workout_by_id:100',result['endpoints'])
        class Repeating:
            def get_workouts(self,start=0,limit=100):return [{'workoutId':i} for i in range(100)]
        result=fetch_supplementary(Repeating(),'2026-01-01','2026-01-01')
        self.assertIn('pagination repeated',result['failures']['get_workouts'])

    def test_all_installed_read_methods_have_a_collection_path(self):
        import inspect
        from garminconnect import Garmin
        from app.supplementary_sync import fetch_supplementary
        class Client:
            profile_id=12
            def __init__(self):self.called=set()
            def __getattr__(self,name):
                if not name.startswith('get_'):raise AttributeError(name)
                def read(*args,**kwargs):
                    self.called.add(name)
                    if name=='get_devices':return [{'deviceId':1}]
                    if name=='get_training_plans':return {'plans':[{'trainingPlanId':1,'adaptiveTrainingPlanId':2}]}
                    if name=='get_golf_summary':return [{'scorecardId':1}]
                    if name=='get_workouts':return [{'workoutId':1}]
                    if name=='get_scheduled_workouts':return [{'scheduledWorkoutId':1}]
                    if name=='get_gear':return [{'uuid':'00000000-0000-4000-8000-000000000001'}]
                    if name in {'get_activities','get_goals','get_adhoc_challenges','get_available_badge_challenges','get_badge_challenges','get_inprogress_virtual_challenges','get_non_completed_badge_challenges'}:return []
                    return {}
                return read
        client=Client();r=fetch_supplementary(client,'2026-01-01','2026-01-01')
        self.assertFalse(r['failures'],r['failures'])
        primary={'get_activities_by_date','get_activity','get_sleep_data','get_hrv_data','get_max_metrics_range','get_user_summary','get_weigh_ins',
                 'get_activity_details','get_activity_splits','get_activity_typed_splits','get_activity_split_summaries','get_activity_weather','get_activity_gear','get_activity_hr_in_timezones','get_activity_power_in_timezones','get_activity_exercise_sets'}
        expected={name for name,fn in inspect.getmembers(Garmin,inspect.isfunction) if name.startswith('get_')}
        self.assertEqual(expected-(client.called|primary),set())

    def test_activity_pagination_filters_before_offset(self):
        from app.history import list_activities
        first=list_activities(limit=1,path=self.path)
        second=list_activities(limit=1,offset=1,path=self.path)
        self.assertEqual(len(first),1);self.assertEqual(len(second),1)
        self.assertNotEqual(first[0]['id'],second[0]['id'])

    def test_model_catalog_timezone_is_kept_as_request_context(self):
        from app.ai_chat import _execute_calls
        outputs,evidence=_execute_calls([('catalog','get_chart_catalog',{'timezone':'UTC'})],self.path,message='Show available plot metrics',timezone_name='UTC')
        self.assertTrue(outputs)
        self.assertTrue(evidence)

    def test_live_response_contracts_use_correct_arguments(self):
        from app.supplementary_sync import fetch_supplementary
        class Client:
            def get_race_predictions(self,startdate,enddate,_type):
                if _type!='daily':raise ValueError('wrong aggregation')
                return {}
            def get_available_badge_challenges(self,start,limit):
                if start<1:raise ValueError('one based')
                return []
            def get_golf_summary(self,start,limit):return {'totalRows':0,'pageNumber':0,'rowsPerPage':100}
            def get_training_plans(self):return {'trainingPlanList':[{'trainingPlanId':12}]}
            def get_training_plan_by_id(self,id):raise RuntimeError('API Error 400 - Not a phased plan.')
        r=fetch_supplementary(Client(),'2026-01-01','2026-01-01')
        self.assertFalse(r['failures'],r['failures'])
        self.assertIn('get_training_plan_by_id:12',r['unavailable'])
        self.assertIn('get_training_plans',r['endpoints'])
