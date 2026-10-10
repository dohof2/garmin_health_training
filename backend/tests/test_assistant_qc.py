"""Conversation-level QC: assertions cover selected data and computed results."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
from app.database import migrate, connect
from app.charts import analyze_points, chart_data, validate_spec
from app.ai_chat import chat_stream
from app.plot_requests import period


class AssistantQC(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'qc.sqlite'
        migrate(self.path)
        with connect(self.path) as c:
            for i in range(5):
                day=f'2026-10-0{i+1}'
                for metric,value,unit in [('weight',70+i,'kg'),('resting_heart_rate',50+2*i,'bpm'),('steps',1000+i,'steps'),('sleep_duration',400+i,'min')]:
                    c.execute('INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,?,?,?,?,?)',(metric+str(i),'synthetic',metric,day,value,unit))
                c.execute("INSERT INTO garmin_archive_records(id,source_name,category,source_record_id,record_date,payload_json) VALUES(?,'synthetic','max_met_fitness',?,?,?)",(str(i),str(i),day,json.dumps({'sport':'CYCLING','vo2MaxValue':40+i})))

    def ask(self,message,context=None,history=None):
        with patch('app.ai_chat._today',return_value=date(2026,10,10)), patch('app.ai_chat._ollama_request') as model:
            events=[json.loads(s) for s in chat_stream(message,history=history,plot_context=context,path=self.path,timezone_name='UTC')]
        self.assertFalse([e for e in events if e['type']=='error'],events)
        model.assert_not_called()
        return next(e['evidence']['plots'] for e in events if e['type']=='tool')

    def test_multiturn_overlay_period_metric_and_removal(self):
        plots=self.ask('Plot my weight over the last year')
        self.assertEqual(plots[0]['count'],5)
        for question in ['Add a mean reference line', 'Add a trend line and correlation', 'Show it for the last six months']:
            plots=self.ask(question,[p['spec'] for p in plots])
        s=plots[0]['spec']
        self.assertEqual(s['start'],'2026-04-10'); self.assertEqual(s['reference_lines'],['mean'])
        self.assertAlmostEqual(plots[0]['analysis']['pearson_r'],1)
        self.assertAlmostEqual(plots[0]['analysis']['reference_lines'][0]['value'],72)
        plots=self.ask('Show resting heart rate instead',[s])
        self.assertEqual(plots[0]['spec']['metric'],'resting_heart_rate')
        self.assertEqual(plots[0]['spec']['start'],'2026-04-10')
        plots=self.ask('Is there improvement?',[plots[0]['spec']])
        self.assertTrue(plots[0]['spec']['trend_line'])
        plots=self.ask('Remove all analysis',[plots[0]['spec']])
        self.assertNotIn('reference_lines',plots[0]['spec']);self.assertNotIn('correlation',plots[0]['spec'])

    def test_four_plots_and_plain_two_metrics(self):
        plots=self.ask('Plot weight; plot steps; plot sleep; plot resting heart rate')
        self.assertEqual(len(plots),4)
        self.assertTrue(all(p['count']==5 for p in plots))
        shared=self.ask('Plot weight, resting heart rate, steps and sleep for the last two weeks')
        self.assertEqual(len(shared),4)
        self.assertTrue(all(p['spec']['start']=='2026-09-27' for p in shared))
        plots=self.ask('Plot weight and resting heart rate')
        self.assertEqual({p['spec']['metric'] for p in plots},{'weight','resting_heart_rate'})

    def test_pairing_correlation_and_numeric_reference(self):
        plots=self.ask('Plot resting heart rate versus cycling VO2 max with correlation and a trend line and reference line at 43')
        p=plots[0]
        self.assertEqual(p['count'],5);self.assertEqual(p['x_unit'],'bpm')
        self.assertAlmostEqual(p['analysis']['pearson_r'],1)
        self.assertAlmostEqual(p['analysis']['trend']['slope'],.5)
        self.assertEqual(p['analysis']['reference_lines'][0]['value'],43)

    def test_context_survives_text_window_and_keeps_gps_scope(self):
        # Scope retained by parser; chart revalidates the reference instead of accepting claims.
        from app.plot_requests import refine
        from app.ai_chat import _explicit_plot_arguments
        spec={'metric':'activity_speed','kind':'line','gps_reference_id':'real-reference','sport':'cycling','start':'2026-01-01','end':'2026-10-10'}
        for message in ['Add a mean line','Add correlation','Show power instead','Show it for the last two weeks']:
            spec=refine(message,[spec],_explicit_plot_arguments,date(2026,10,10),self.path)['plots'][0]
            self.assertEqual(spec['gps_reference_id'],'real-reference')
        self.assertEqual(spec['metric'],'activity_power');self.assertEqual(spec['start'],'2026-09-27')
        spec=refine('Use all rides instead',[spec],_explicit_plot_arguments,date(2026,10,10),self.path)['plots'][0]
        self.assertNotIn('gps_reference_id',spec)

    def test_dates_and_empty_period(self):
        for question,start in [('Plot weight for the last two weeks','2026-09-27'),('Plot weight for the past 3 months','2026-07-10'),('Plot weight from 2026-10-02 to 2026-10-04','2026-10-02')]:
            with self.subTest(question=question):
                plot=self.ask(question)[0];self.assertEqual(plot['spec']['start'],start)
        plot=self.ask('Plot weight from 2020-01-01 to 2020-01-03 with correlation')[0]
        self.assertEqual(plot['count'],0);self.assertIsNone(plot['analysis']['pearson_r'])
        self.assertEqual(period('last year',date(2024,2,29)),('2023-02-28','2024-02-29'))

    def test_analysis_empty_sparse_constant_negative_and_full_set(self):
        spec={'metric':'weight','kind':'scatter','x_metric':'resting_heart_rate','trend_line':True,'correlation':True,'reference_lines':['mean']}
        for xs,ys,expected in [([],[],None),([1,2],[1,2],None),([1,1,1],[2,3,4],None),([1,2,3],[4,4,4],None),([1,2,3],[6,4,2],-1)]:
            a=analyze_points([{'x':x,'y':y,'date':'2026-01-01'} for x,y in zip(xs,ys)],spec)
            self.assertEqual(a['pearson_r'],expected)
        a=analyze_points([{'x':i,'y':2*i,'date':'2026-01-01'} for i in range(2500)],spec)
        self.assertEqual(a['sample_count'],2500);self.assertEqual(a['pearson_r'],1)
        self.assertEqual(a['reference_lines'][0]['value'],2499)

    def test_new_matched_request_with_add_does_not_refine_an_old_plot(self):
        from app.plot_requests import refine, canonical, matched_scope
        from app.ai_chat import _explicit_plot_arguments
        message=canonical('plot the speed of all rides macthed to the ride on oct 6th add a refferance line (all in one plot)')
        self.assertTrue(matched_scope(message))
        self.assertIsNone(refine(message,[{'metric':'activity_speed','kind':'line','gps_reference_id':'old'}],_explicit_plot_arguments,date(2026,10,10),self.path))
        self.assertEqual(_explicit_plot_arguments(message,self.path)['plots'][0]['reference_lines'],['mean'])

    def test_reference_and_trend_are_never_defaults(self):
        plot=self.ask('Plot my weight')[0]
        self.assertFalse(plot['spec'].get('reference_lines'))
        self.assertFalse(plot['spec'].get('trend_line'))
        self.assertEqual(plot['analysis']['reference_lines'],[])
        self.assertIsNone(plot['analysis']['trend'])
        from app.charts import save_layout, read_layout
        save_layout([{**plot['spec'],'id':'weight','trend_line':True}],self.path)
        saved=read_layout(self.path)[0]
        self.assertTrue(saved['trend_line']);self.assertFalse(saved.get('reference_lines'))
        self.assertIsNotNone(chart_data(saved,self.path)['analysis']['trend'])

    def test_common_history_questions_do_not_route_to_maintenance_or_catalog(self):
        for message,tool in [('Summarize my steps and sleep over the last seven days.','get_health_summary'),
                             ('List my three most recent activities and the heart-rate or power data available for each.','list_activities')]:
            with patch('app.ai_chat._today',return_value=date(2026,10,10)),patch('app.ai_chat._ollama_request') as model:
                events=[json.loads(s) for s in chat_stream(message,path=self.path,timezone_name='UTC')]
            self.assertFalse(any(e['type']=='error' for e in events),events)
            self.assertEqual(next(e['evidence']['tool'] for e in events if e['type']=='tool'),tool)
            model.assert_not_called()

    def test_invalid_analysis_cannot_bypass_validation(self):
        base={'metric':'weight','kind':'line'}
        for update in [{'reference_lines':[True]},{'reference_lines':[float('nan')]},{'reference_lines':['median']},{'reference_lines':[1,2,3,4,5]},{'trend_line':'true'},{'kind':'dial','correlation':True}]:
            with self.subTest(update=update),self.assertRaises(ValueError): validate_spec({**base,**update},self.path)
