import json
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from pathlib import Path

from app.charts import add_weight, chart_data, read_layout, save_layout
from app.database import connect, migrate
from app.ai_chat import _tool_evidence, _normalize_tool_arguments, chat_stream
from app.ai_tools import execute_tool


class ChartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'charts.sqlite3'
        migrate(self.path)
        with connect(self.path) as c:
            for i, day in enumerate(('2026-09-01', '2026-09-03')):
                payload = json.dumps({'sport': 'CYCLING', 'vo2MaxValue': 44+i, 'calendarDate': day})
                c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES(?, 'garmin_export','max_met_fitness',?,?,?)", (str(i),str(i),day,payload))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('hr','garmin_export','resting_heart_rate','2026-09-01',52,'bpm')")

    def test_matched_speed_plot_and_plot_it_use_full_gps_set_not_all_rides(self):
        with connect(self.path) as c:
            for index in range(32):
                ident = 'reference' if index == 30 else 'unrelated' if index == 31 else f'match-{index}'
                day = '2026-10-06' if index == 30 else (date(2026,8,1)+timedelta(days=index)).isoformat()
                c.execute("INSERT INTO activities(id,source_name,name,activity_type,started_at,duration_seconds,distance_meters,raw_json) VALUES(?,'synthetic',?,'cycling',?,3600,20000,?)", (ident,ident,day+'T06:00:00Z',json.dumps({'averageSpeed':5+index/10})))
                c.executemany("INSERT INTO activity_samples(activity_id,recorded_at,latitude,longitude) VALUES(?,?,?,?)", [(ident,day+f'T06:00:{i:02d}Z',32+i*.001+(1 if ident=='unrelated' else 0),34+i*.001) for i in range(12)])
        question = 'can you generate a plot of date and speed of those matched rides?'
        history = [{'role':'user','content':'What rides match my ride on September 27th?'}, {'role':'user','content':'and for the ride on OC 6th?'}]
        with patch('app.ai_chat._today',return_value=date(2026,10,10)), patch('app.ai_chat._ollama_request') as model:
            for message, context in ((question,history), ('plot it',history+[{'role':'user','content':question}])):
                events = [json.loads(line) for line in chat_stream(message,history=context,timezone_name='Asia/Jerusalem',path=self.path)]
                self.assertFalse(any(e['type']=='error' for e in events),events)
                plot = next(e['evidence']['plots'][0] for e in events if e['type']=='tool')
                self.assertEqual(plot['count'],31)
                self.assertEqual(plot['spec']['gps_reference_id'],'reference')
                self.assertNotIn('unrelated',{p['id'] for p in plot['points']})
                self.assertIn('match-29',{p['id'] for p in plot['points']})
                self.assertEqual(plot['unit'],'km/h')
                self.assertAlmostEqual(plot['latest']['y'],28.8)
                self.assertEqual(plot['spec']['size'],'full')
                save_layout([{**plot['spec'],'id':'pinned'}], self.path)
                self.assertEqual(chart_data(read_layout(self.path)[0],self.path)['count'],31)
            followup = [json.loads(line) for line in chat_stream('Plot speed of those matched rides with correlation',
                history=[], plot_context=[plot['spec']], timezone_name='Asia/Jerusalem',path=self.path)]
            self.assertFalse(any(e['type']=='error' for e in followup),followup)
            carried = next(e['evidence']['plots'][0] for e in followup if e['type']=='tool')
            self.assertEqual(carried['count'],31)
            self.assertEqual(carried['spec']['gps_reference_id'],'reference')
        model.assert_not_called()
        with self.assertRaisesRegex(ValueError,'activity metric'):
            chart_data({'metric':'vo2_cycling','kind':'line','gps_reference_id':'reference'},self.path)

    def test_sparse_vo2_is_paired_only_on_real_dates(self):
        result = chart_data({'metric':'vo2_cycling','x_metric':'resting_heart_rate','kind':'scatter'},self.path)
        self.assertEqual(result['count'],1)
        self.assertEqual(result['unpaired'],1)
        self.assertEqual((result['points'][0]['x'],result['points'][0]['y']),(52,44))
        self.assertEqual(chart_data({'metric':'vo2_running','kind':'line'},self.path)['count'],0)

    def test_layout_replacement_removal_and_empty_layout_survive_reload(self):
        one = {'id':'a','metric':'vo2_cycling','kind':'dial'}
        save_layout([one],self.path)
        replacement = {**one,'metric':'vo2_running','kind':'line'}
        save_layout([replacement],self.path)
        self.assertEqual(read_layout(self.path),[replacement])
        save_layout([],self.path)
        self.assertEqual(read_layout(self.path),[])
        with self.assertRaises(ValueError):
            save_layout([one,one],self.path)

    def test_weight_conversion_preserves_garmin_and_filters_period(self):
        add_weight('2026-09-02',165,'lb',self.path)
        r=chart_data({'metric':'weight','kind':'line','start':'2026-09-02','end':'2026-09-02'},self.path)
        self.assertEqual(r['count'],1)
        self.assertAlmostEqual(r['points'][0]['y'],74.84274105)
        self.assertEqual(r['points'][0]['source'],'manual')

    def test_archived_weight_history_merges_converts_and_deduplicates(self):
        with connect(self.path) as c:
            samples = [
                ('old', '2025-01-02', {'weight': {'weight': 79000}}),
                ('scale', '2026-09-01', {'weight': {'weight': 82000, 'timestampGMT': '2026-08-31T22:30:00.0'}}),
                ('duplicate', '2026-09-01', {'weight': {'weight': 82000}}),
                ('null', '2026-09-02', {'weight': {'weight': 83000}, 'userSetNullForWeight': True}),
                ('missing', '2026-09-03', {'height': 170}),
                ('bad', '2026-09-04', {'weight': {'weight': '84000'}}),
            ]
            for ident, day, payload in samples:
                c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES(?,'garmin_export','biometrics_history',?,?,?)", (ident,ident,day,json.dumps(payload)))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('live','garmin_connect','weight','2026-09-01',82,'kg')")
        add_weight('2026-09-01',81.5,'kg',self.path)
        r = chart_data({'metric':'weight','kind':'line','timezone':'Asia/Jerusalem'},self.path)
        self.assertEqual(r['unit'],'kg')
        self.assertEqual([(p['date'],p['y']) for p in r['points']], [('2025-01-02',79),('2026-09-01',82),('2026-09-01',81.5)])
        self.assertEqual(r['latest']['source'],'manual')
        self.assertEqual(r['excluded'],1)
        filtered = chart_data({'metric':'weight','kind':'line','timezone':'Asia/Jerusalem','start':'2026-09-01'},self.path)
        self.assertEqual(filtered['count'],2)

    def test_activity_pairing_uses_recorded_mean_speed(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,duration_seconds,distance_meters,raw_json) VALUES('ride','garmin_export','cycling','2026-09-01T23:00:00Z',3600,10000,?)",(json.dumps({'averageSpeed':8}),))
            c.execute("INSERT INTO activity_metrics(activity_id,metric_type,value,unit,source_method,source_field) VALUES('ride','average_power',200,'W','garmin_summary','averagePower')")
        r=chart_data({'metric':'activity_speed','x_metric':'activity_power','kind':'scatter','sport':'cycling','timezone':'Asia/Jerusalem','start':'2026-09-02'},self.path)
        self.assertEqual(r['count'],1)
        self.assertEqual(r['points'][0]['x'],200)
        self.assertAlmostEqual(r['points'][0]['y'],28.8)

    def test_validation_and_assistant_evidence(self):
        with self.assertRaises(ValueError):
            chart_data({'metric':'vo2_cycling','kind':'scatter','x_metric':'activity_power'},self.path)
        with self.assertRaises(ValueError):
            chart_data({'metric':'vo2_cycling','kind':'line','sql':'DROP TABLE activities'},self.path)
        r=execute_tool('create_plots',{'plots':[{'metric':'vo2_cycling','kind':'line'}]},self.path)
        self.assertEqual(_tool_evidence('create_plots',r)['plots'][0]['count'],2)
        args=_normalize_tool_arguments('create_plots',{'plots':[{'metric':'vo2_cycling','kind':'line'}]},'Plot VO2 in the last year','Asia/Jerusalem')
        self.assertEqual(args['plots'][0]['timezone'],'Asia/Jerusalem')
        self.assertIn('start',args['plots'][0])
        all_history=_normalize_tool_arguments('create_plots',{'plots':[{'metric':'activity_power','x_metric':'activity_speed','kind':'scatter','start':'2025-10-10','end':'2026-10-10'}]},'Plot power vs speed across all my cycling rides','Asia/Jerusalem')
        self.assertNotIn('start',all_history['plots'][0])
        self.assertEqual(all_history['plots'][0]['x_metric'],'activity_power')
        mixed=_normalize_tool_arguments('create_plots',{'plots':[
            {'metric':'weight','kind':'line','start':'2024-10-09','end':'2025-10-09'},
            {'metric':'vo2_running','x_metric':'resting_heart_rate','kind':'scatter','start':'2025-01-01'}]},
            'Plot weight over the last year; plot resting HR versus cycling VO2 max across all history','Asia/Jerusalem')
        self.assertEqual(mixed['plots'][0]['start'],args['plots'][0]['start'])
        self.assertNotIn('start',mixed['plots'][1])
        self.assertEqual(mixed['plots'][1]['metric'],'vo2_cycling')

    def test_four_explicit_plots_stream_without_model_or_invented_dates(self):
        add_weight('2026-09-02',76,'kg',self.path)
        events=[json.loads(line) for line in chat_stream(
            'Create four plots: weight over the last year; power versus speed across all my cycling rides; resting heart rate versus cycling VO2 max on matching dates; resting heart rate history over the last year.',
            timezone_name='Asia/Jerusalem',path=self.path)]
        self.assertFalse(any(e['type']=='error' for e in events),events)
        plots=next(e['evidence']['plots'] for e in events if e['type']=='tool')
        self.assertEqual(len(plots),4)
        self.assertEqual(plots[0]['count'],1)
        self.assertNotIn('start',plots[1]['spec'])
        self.assertEqual(plots[2]['spec']['metric'],'vo2_cycling')
        self.assertEqual(plots[2]['count'],1)
        self.assertEqual(plots[0]['spec']['start'],plots[3]['spec']['start'])
