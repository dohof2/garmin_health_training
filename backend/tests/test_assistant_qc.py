"""Conversation-level QC: assertions cover selected data and computed results."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
from app.database import migrate, connect
from app.charts import analyze_points, chart_data, validate_spec
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


    def test_analysis_empty_sparse_constant_negative_and_full_set(self):
        spec={'metric':'weight','kind':'scatter','x_metric':'resting_heart_rate','trend_line':True,'correlation':True,'reference_lines':['mean']}
        for xs,ys,expected in [([],[],None),([1,2],[1,2],None),([1,1,1],[2,3,4],None),([1,2,3],[4,4,4],None),([1,2,3],[6,4,2],-1)]:
            a=analyze_points([{'x':x,'y':y,'date':'2026-01-01'} for x,y in zip(xs,ys)],spec)
            self.assertEqual(a['pearson_r'],expected)
        a=analyze_points([{'x':i,'y':2*i,'date':'2026-01-01'} for i in range(2500)],spec)
        self.assertEqual(a['sample_count'],2500);self.assertEqual(a['pearson_r'],1)
        self.assertEqual(a['reference_lines'][0]['value'],2499)


    def test_invalid_analysis_cannot_bypass_validation(self):
        base={'metric':'weight','kind':'line'}
        for update in [{'reference_lines':[True]},{'reference_lines':[float('nan')]},{'reference_lines':['median']},{'reference_lines':[1,2,3,4,5]},{'trend_line':'true'},{'kind':'dial','correlation':True}]:
            with self.subTest(update=update),self.assertRaises(ValueError): validate_spec({**base,**update},self.path)
