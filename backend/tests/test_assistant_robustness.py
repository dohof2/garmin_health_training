"""Acceptance regressions for numerical correctness and conversational choices."""
import json
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch

from app.ai_chat import chat_stream, _normalize_tool_arguments
from app.database import connect,migrate
from app.plot_requests import canonical,period
from app.ai_tools import execute_tool


class AssistantRobustness(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'qa.sqlite3';migrate(self.path)
        with connect(self.path) as c:
            for metric in ['body_battery_latest','sleep_score']:
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,'garmin_connect',?,'2026-10-09',75,'score')",(metric,metric))
            for i in range(1,8):
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,'garmin_connect','steps',?,?,'steps')",(str(i),f'2026-10-{i+4:02}',100*i))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('fake','synthetic_fixture','steps','2026-10-11',999999,'steps')")
            for identifier,day,kind,distance in [('ride','2026-10-09','mountain_biking',30000),('older','2026-09-01','cycling',10000),('old','2025-09-01','cycling',50000),('hike','2026-10-10','hiking',5000)]:
                c.execute("INSERT INTO activities(id,source_name,name,activity_type,started_at,distance_meters) VALUES(?,'garmin_connect',?,?,?,?)",(identifier,identifier,kind,day+'T10:00:00Z',distance))

    def ask(self,message,history=None):
        with patch('app.ai_chat._today',return_value=date(2026,10,11)),patch('app.ai_chat._ollama_request',side_effect=AssertionError('This common question must not depend on model selection')):
            events=[json.loads(e) for e in chat_stream(message,history=history,path=self.path,timezone_name='Asia/Jerusalem')]
        self.assertFalse([e for e in events if e['type']=='error'],events)
        return ''.join(e.get('text','') for e in events if e['type']=='delta'),[e['evidence'] for e in events if e['type']=='tool']

    def test_period_semantics_include_calendar_and_rolling_boundaries(self):
        for text,expected in [('this year',('2026-01-01','2026-10-11')),('last year',('2025-01-01','2025-12-31')),
            ('the last year',('2025-10-11','2026-10-11')),('past 12 months',('2025-10-11','2026-10-11')),
            ('this week',('2026-10-05','2026-10-11')),('last week',('2026-09-28','2026-10-04')),
            ('last month',('2026-09-01','2026-09-30')),('last five days',('2026-10-07','2026-10-11')),
            ('last30days',('2026-09-12','2026-10-11')),('yesterday',('2026-10-10','2026-10-10'))]:
            with self.subTest(text=text):self.assertEqual(period(canonical(text),date(2026,10,11)),expected)

    def test_average_and_total_are_distinct_and_fixtures_excluded(self):
        average,evidence=self.ask('What was my average steps over the last seven days?')
        total,_=self.ask('Summarize my steps over the last seven days.')
        self.assertIn('400.00',average);self.assertIn('2800.00',total)
        self.assertEqual(evidence[0]['metrics'][0]['count'],7)
        self.assertLess(len(average.split()),60)

    def test_summary_period_clarification_followup_is_used(self):
        question='How were my steps?';prompt,_=self.ask(question)
        self.assertIn('Which period',prompt)
        answer,evidence=self.ask('last seven days',[{'role':'user','content':question},{'role':'assistant','content':prompt}])
        self.assertIn('2800.00',answer)
        self.assertEqual(evidence[0]['period']['start'],'2026-10-05')

    def test_date_filtered_all_rides_scatter_keeps_filter(self):
        with patch('app.ai_chat._today',return_value=date(2026,10,11)):
            spec=_normalize_tool_arguments('create_plots',{'plots':[{'metric':'activity_power','x_metric':'activity_speed','kind':'scatter'}]},'Plot power versus speed across all rides this year','Asia/Jerusalem')['plots'][0]
        self.assertEqual(spec['start'],'2026-01-01')
        self.assertEqual(spec['end'],'2026-10-11')

    def test_ride_inventory_does_not_include_hiking(self):
        answer,evidence=self.ask('What data do you have about my rides?')
        self.assertNotIn('hike',answer)
        self.assertEqual({r['id'] for r in evidence[0]['records']},{'ride','older','old'})

    def test_natural_scope_reply_and_missing_period_do_not_guess(self):
        question='Compare my latest bike ride to other rides.';prompt,_=self.ask(question)
        history=[{'role':'user','content':question},{'role':'assistant','content':prompt}]
        self.assertIn('Which period',prompt)
        answer,evidence=self.ask('this year',history)
        self.assertEqual(evidence[0]['candidate_pool_count'],1)
        self.assertEqual(evidence[0]['reference_record']['id'],'ride')
        self.assertIn('200.0% above',answer)

    def test_body_battery_and_rolling_followups_produce_requested_specs(self):
        for question,reply,field,expected in [('Plot body battery versus sleep score this year.','latest','metric','body_battery_latest'),('Plot weight with a rolling average this year.','7 days','rolling_days',7),('Plot median weight this year.','weekly','aggregation','weekly_median')]:
            with self.subTest(question=question):
                prompt,_=self.ask(question)
                _,evidence=self.ask(reply,[{'role':'user','content':question},{'role':'assistant','content':prompt}])
                spec=evidence[0]['plots'][0]['spec'];self.assertEqual(spec[field],expected)
                self.assertEqual(spec['start'],'2026-01-01')

    def test_single_date_cannot_establish_weight_change(self):
        with connect(self.path) as c:
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('weight','manual','weight','2026-10-09',80,'kg')")
        answer,_=self.ask('Has my weight changed recently?')
        self.assertIn('not enough dated evidence',answer)
        self.assertNotIn('+0.00',answer)

    def test_health_change_uses_real_dated_endpoints(self):
        with connect(self.path) as c:
            for day,value in [('2026-09-20',80),('2026-10-09',78)]:
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,'manual','weight',?,?,'kg')",(day,day,value))
        answer,_=self.ask('Has my weight changed recently?')
        self.assertIn('80.00 kg on 2026-09-20',answer);self.assertIn('78.00 kg on 2026-10-09',answer)
        self.assertIn('-2.00 kg',answer)

    def test_catalog_question_is_answered_without_empty_plot_call(self):
        answer,evidence=self.ask('Can you plot metrics beyond the dashboard presets?')
        self.assertEqual(evidence[0]['tool'],'get_chart_catalog')
        self.assertIn('Which measurements',answer)
        self.assertNotIn('cannot retrieve',answer)

    def test_all_history_includes_older_years(self):
        answer,evidence=self.ask('Compare my latest ride to all rides across my full history.')
        self.assertEqual(evidence[0]['candidate_pool_count'],2)
        self.assertEqual(evidence[0]['period']['start'],'2025-09-01')

    def test_coaching_answer_short_but_retains_warnings(self):
        from app.training_coach import assistant_answer
        from app.ai_tools import execute_tool
        result=execute_tool('preview_training_plan',{'message':'I want to increase FTP.','timezone':'Asia/Jerusalem'},self.path)
        answer=assistant_answer(result)
        self.assertLess(len(answer.split()),120)
        self.assertIn('Nothing has been saved',answer)
        for warning in result['warnings']: self.assertIn(warning,answer)

    def test_personal_ride_interpretation_is_grounded_in_duration_and_power(self):
        with connect(self.path) as c:
            c.execute("UPDATE activities SET duration_seconds=3600 WHERE id IN ('older','old')")
            c.execute("UPDATE activities SET duration_seconds=18000 WHERE id='ride'")
            c.execute("INSERT INTO activities(id,source_name,name,activity_type,started_at,duration_seconds) VALUES('third','garmin_connect','third','cycling','2026-08-01T10:00:00Z',3600)")
            for identifier,power in [('ride',90),('older',180),('old',180),('third',180)]:
                c.execute("INSERT INTO activity_metrics(activity_id,metric_type,value,unit,source_method,source_field) VALUES(?,'average_power',?,'W','qa','average_power')",(identifier,power))
        answer,evidence=self.ask('Compare my latest ride to all rides across my full history.')
        self.assertIn('longer than your typical recorded ride, with lower average power',answer)
        self.assertNotIn('steady',answer);self.assertNotIn('throughout',answer)
        self.assertEqual(next(r for r in evidence[0]['comparisons'] if r['metric']=='average_power')['median'],180)

    def test_recorded_volume_excludes_empty_weeks_and_requires_complete_durations(self):
        from app.ride_comparison import riding_volume_context
        anchor=date(2026,10,9)
        rides=[{'local_date':anchor.isoformat(),'duration_seconds':7200}]
        for week,hours in enumerate([1,2,3,4],1):
            rides.append({'local_date':(anchor-timedelta(days=7*week)).isoformat(),'duration_seconds':hours*3600})
        result=riding_volume_context(rides,rides[0])
        self.assertEqual(result['comparison_week_count'],4)
        self.assertEqual(result['recent_middle_range_hours'],[1.75,3.25])
        self.assertEqual(result['position'],'within')
        self.assertIn('prior weeks with rides',result['interpretation'])
        rides[-1]['duration_seconds']=None
        self.assertIsNone(riding_volume_context(rides,rides[0])['interpretation'])
        rides[-1]['duration_seconds']=14400;rides[0]['duration_seconds']=None
        self.assertIsNone(riding_volume_context(rides,rides[0])['interpretation'])

    def test_multiple_training_commitments_preserve_days_and_do_not_invent_duration(self):
        from app.training_coach import parse_request,validate_brief
        brief,recognized=parse_request('I want two hard rides Tuesday and wedensday. Long ride on firday and I can train today. I want FTP improvement.',validate_brief({}),date(2026,10,12))
        events={e['date']:e for e in brief['fixed_events']}
        self.assertEqual(set(events),{'2026-10-13','2026-10-14','2026-10-16'})
        self.assertEqual(events['2026-10-13']['effort'],'hard')
        self.assertEqual(events['2026-10-14']['effort'],'hard')
        self.assertTrue(all(e['duration_minutes'] is None for e in events.values()))
        self.assertTrue(any('today is separate' in r for r in recognized))
        self.assertEqual(brief['goal'],'ftp')

    def test_training_duration_and_effort_stay_with_their_own_clause(self):
        from app.training_coach import parse_request,validate_brief
        brief,_=parse_request('Hard ride Tuesday for 3.5 hours and easy ride Friday for 45 minutes.',validate_brief({}),date(2026,10,12))
        events={e['date']:e for e in brief['fixed_events']}
        self.assertEqual((events['2026-10-13']['duration_minutes'],events['2026-10-13']['effort']),(210,'hard'))
        self.assertEqual((events['2026-10-16']['duration_minutes'],events['2026-10-16']['effort']),(45,'easy'))

    def test_source_benefit_label_and_fit_scores_are_reported_without_guessing(self):
        payload={'trainingEffectLabel':'AEROBIC_BASE','fit_sessions':[{'total_training_effect':3.3,'total_anaerobic_training_effect':1.1}]}
        with connect(self.path) as c:
            c.execute('UPDATE activities SET raw_json=? WHERE id=?',(json.dumps(payload),'ride'))
            c.execute("INSERT INTO activity_metrics(activity_id,metric_type,value,unit,source_method,source_field) VALUES('ride','average_power',90,'W','qa','average_power')")
        assessment=execute_tool('assess_ride',{},self.path)
        self.assertEqual(assessment['training_benefit']['source_label'],'AEROBIC_BASE')
        self.assertEqual(assessment['recorded_metrics'][0]['value'],90)
        answer,evidence=self.ask('What was the main training benefit of my last ride?')
        self.assertIn('Aerobic base (endurance)',answer)
        self.assertIn('aerobic effect: 3.3',answer);self.assertIn('anaerobic effect: 1.1',answer)
        self.assertEqual(evidence[0]['training_benefit']['scores']['aerobic_training_effect']['source_method'],'fit_session')
        payload.pop('trainingEffectLabel')
        with connect(self.path) as c:c.execute('UPDATE activities SET raw_json=? WHERE id=?',(json.dumps(payload),'ride'))
        answer,_=self.ask('What was the primary benefit of my latest ride?')
        self.assertIn('unavailable',answer);self.assertNotIn('endurance',answer);self.assertNotIn('sprint',answer)

    def test_multisport_fit_sessions_do_not_assign_one_session_effect_to_whole_ride(self):
        with connect(self.path) as c:
            c.execute('UPDATE activities SET raw_json=? WHERE id=?',(json.dumps({'fit_sessions':[{'total_training_effect':3.3},{'total_training_effect':4.0}]}),'ride'))
        answer,evidence=self.ask('What was the main training benefit of my last ride?')
        self.assertEqual(evidence[0]['training_benefit']['scores'],{})
        self.assertIn('unavailable',answer)

    def test_ftp_improvement_with_multiple_rides_routes_to_coaching(self):
        answer,evidence=self.ask('I want two hard rides Tuesday and wedensday. Long ride on firday and I can train today. I want FTP improvement.')
        self.assertEqual(evidence[0]['tool'],'preview_training_plan')
        self.assertIn('Nothing has been saved',answer)

    def test_ordinary_comparison_defaults_to_records_and_never_calls_matching(self):
        for question in ['How was my last ride compared to other rides this year?', 'How was my last ride compared to other rides this year without GPS?', 'Compare my latest ride with a normal comparison this year.', 'how was my ride compared to other rides in the kast 3 months?']:
            with self.subTest(question=question):
                answer,evidence=self.ask(question)
                self.assertEqual(evidence[0]['tool'],'compare_latest_ride')
                self.assertEqual(evidence[0]['candidate_pool_count'],1)
                self.assertNotIn('All rides, or',answer)

    def test_model_cannot_choose_matching_for_an_ordinary_comparison(self):
        from app.ai_chat import _execute_calls
        for name in ['find_same_course_rides','find_similar_rides']:
            with self.assertRaisesRegex(ValueError,'explicit request'):
                _execute_calls([('match',name,{})],self.path,message='How did my ride compare with other rides this year?')

    def test_comparison_timing_accepts_units_and_short_replies(self):
        for phrase,bounds in [('past 10 days',('2026-10-02','2026-10-11')),('over 3 months',('2026-07-11','2026-10-11')),('past 2 years',('2024-10-11','2026-10-11')),('3 months',('2026-07-11','2026-10-11'))]:
            self.assertEqual(period(phrase,date(2026,10,11)),bounds)
        original='Compare my last ride to other rides over the last 3'
        prompt,evidence=self.ask(original)
        self.assertIn('days, weeks, months or years',prompt);self.assertEqual(evidence,[])
        answer,evidence=self.ask('3 months',[{'role':'user','content':original},{'role':'assistant','content':prompt}])
        self.assertEqual(evidence[0]['period'],{'start':'2026-07-11','end':'2026-10-11'})
