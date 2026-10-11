import json
import tempfile
import io
import zipfile
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from app.database import connect,migrate
from app.activity_metrics import preserve_fit_summary
from app.fit_access import discover,inspect
from app.charts import chart_data

class FitAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        self.messages={'record_mesgs':[{'grit':2,'flow':1,'custom_sensor':4},{'grit':4,'flow':None,'custom_sensor':8}], 'jump_mesgs':[{'height':1.2,'hang_time':0.4},{'height':1.6,'hang_time':0.6}], 'session_mesgs':[], 'developer_data_id_mesgs':[{'application_id':bytes([1,2]),'serial_number':123}]}
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,activity_type,started_at,raw_json) VALUES('ride','garmin_connect','cycling','2026-01-05T23:30:00Z','{}')")
            preserve_fit_summary(c,'ride',self.messages)
    def tearDown(self):self.tmp.cleanup()
    def test_field_discovery_and_missing_data(self):
        found=discover({'query':'grit'},self.path)
        self.assertEqual(found['matching_activities'],1);self.assertEqual(found['field_coverage'][0]['field'],'grit')
        self.assertEqual(discover({'query':'not_a_field'},self.path)['matching_activities'],0)
        self.assertEqual(discover({'start_date':'2026-01-06','timezone':'Asia/Jerusalem','query':'jump'},self.path)['matching_activities'],1)
    def test_arbitrary_record_fields_stats_use_all_rows_not_page(self):
        with patch('app.fit_access.original_messages',return_value=self.messages):
            result=inspect({'message_type':'record_mesgs','fields':['grit','custom_sensor','absent'],'limit':1},self.path)
        self.assertEqual(result['statistics']['grit']['mean'],3)
        self.assertEqual(result['statistics']['custom_sensor']['mean'],6)
        self.assertIsNone(result['statistics']['custom_sensor']['unit'])
        self.assertEqual(result['missing_fields'],['absent']);self.assertTrue(result['truncated'])
        self.assertEqual(len(result['records']),1)
    def test_jumps_fallback_preserved_metadata_and_units(self):
        with patch('app.fit_access.original_messages',return_value=None):
            result=inspect({'message_type':'jump_mesgs','fields':['height','hang_time']},self.path)
        self.assertEqual(result['total_records'],2);self.assertAlmostEqual(result['statistics']['height']['mean'],1.4)
        self.assertEqual(result['statistics']['height']['unit'],'m')
        self.assertFalse(result['original_available'])
    def test_dynamic_numeric_field_charts_and_missing_values(self):
        with patch('app.fit_access.original_messages',return_value=self.messages):
            plot=chart_data({'metric':'fit:record_mesgs:grit','kind':'line','fit_stat':'maximum'},self.path)
            flow=chart_data({'metric':'fit:record_mesgs:flow','kind':'line'},self.path)
        self.assertEqual(plot['points'][0]['y'],4);self.assertEqual(flow['points'][0]['y'],1)
        jumps=chart_data({'metric':'fit:jump_mesgs:count','kind':'line'},self.path)
        self.assertEqual(jumps['points'][0]['y'],2)
    def test_binary_fields_are_preserved_and_identifiers_scrubbed(self):
        with connect(self.path) as c:raw=json.loads(c.execute('SELECT raw_json FROM activities').fetchone()[0])
        developer=raw['fit_messages']['developer_data_id_mesgs'][0]
        self.assertEqual(developer['application_id']['value'],'0102');self.assertNotIn('serial_number',developer)

    def test_recovery_is_idempotent_and_does_not_reimport_samples(self):
        archive=Path(self.tmp.name)/'outer.zip';nested=io.BytesIO()
        with zipfile.ZipFile(nested,'w') as z:z.writestr('ride.fit',b'original')
        with zipfile.ZipFile(archive,'w') as z:z.writestr('nested.zip',nested.getvalue())
        with connect(self.path) as c:
            c.execute("UPDATE activities SET fit_detail_version=0 WHERE id='ride'")
            c.execute("INSERT INTO activity_samples(activity_id,recorded_at,power_watts) VALUES('ride','2026-01-05T23:30:00Z',100)")
            c.execute("INSERT INTO source_files(id,original_name,content_hash,byte_size,stored_path) VALUES('outer','outer.zip','outer',1,?)",(str(archive),))
            c.execute("INSERT INTO source_files(id,original_name,content_hash,byte_size,stored_path) VALUES('fit','ride.fit','fit',1,?)",(f'{archive}!/nested.zip!/ride.fit',))
            c.execute("INSERT INTO fit_import_files(id,archive_source_file_id,fit_source_file_id,nested_archive,member_name,content_hash,file_type,activity_id,status) VALUES('import','outer','fit','nested.zip','ride.fit','content','activity','ride','completed')")
        spec=importlib.util.spec_from_file_location('lap_recovery',Path(__file__).resolve().parents[2]/'scripts/recover_activity_laps.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module,'_decode_fit',return_value=(self.messages,[])):
            self.assertEqual(module.recover(self.path)['recovered'],1)
            self.assertEqual(module.recover(self.path)['recovered'],0)
        with connect(self.path) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM activity_samples').fetchone()[0],1)
