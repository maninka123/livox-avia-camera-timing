"""Regression checks for recovery, damaged inputs and concurrent local app requests."""
import io
import json
import tempfile
import threading
import os
import time
import multiprocessing
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import app as server
import common
import job_registry
from bag_io import grayscale
from algorithms.livox.extract_cloud import decode
from sensors import validation_blocks
from timing import fit_multi,lag_profile


class CornerCases(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.results=self.root/'results';self.results.mkdir()
        self.bags=self.root/'bagfiles';self.bags.mkdir()
        for i in range(1,6):(self.bags/f'device_{i}').mkdir()
        self.stack=ExitStack()
        for module in (server,common,job_registry):self.stack.enter_context(patch.object(module,'RESULTS',self.results))
        for module in (server,common):self.stack.enter_context(patch.object(module,'BAGS',self.bags))
        self.stack.enter_context(patch.object(job_registry,'workers',{}))
        self.client=server.app.test_client()
    def tearDown(self):self.stack.close();self.temp.cleanup()
    def run_folder(self,name='capture',state='complete',summary=None):
        out=self.results/name;out.mkdir(parents=True,exist_ok=True)
        common.save_json(out/'status.json',{'id':name,'status':state,'bag':'capture.bag'})
        if summary is not None:common.save_json(out/'summary.json',summary)
        return out
    def metadata(self):
        return {'topics':[{'name':'/camera','type':'sensor_msgs/Image'},{'name':'/livox','type':'sensor_msgs/PointCloud2'}],
                'suggested_camera_topic':'/camera','suggested_livox_topic':'/livox','suggested_phase_group':'normal'}
    def good_summary(self,name='good'):
        metrics={key:.1 for key in ('std_deg','mae_deg','rmse_deg','p95_deg')}
        return {'id':name,'bag':name+'.bag','config':{'camera_topic':'/camera','livox_topic':'/livox'},
                'flir':{'frames':150,'rpm':5,'status':'TRACK_RECOVERED','heldout_residual':metrics},'livox':{'frames':150,'rpm':5,'status':'RELATIVE_TRACK_RECOVERED'},
                'timing':{'agreement':{'heldout_raw':metrics,'heldout_offline_smoothed':metrics},
                          'single_bag_lag':{'status':'NOT_IDENTIFIABLE_FROM_THIS_BAG'},'clocks':{'livox':{'domain':'invalid'}}}}
    def test_json_publication_is_atomic_for_concurrent_writers(self):
        file=self.results/'status.json'
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n:common.save_json(file,{'writer':n,'rows':list(range(100))}),range(100)))
        self.assertEqual(len(common.read_json(file)['rows']),100)
        self.assertEqual(list(self.results.glob('*.tmp')),[])
    def test_corrupt_run_does_not_break_library_or_file_access(self):
        out=self.run_folder('bad_status');(out/'status.json').write_text('{broken')
        out=self.run_folder('bad_summary');(out/'summary.json').write_text('[]')
        good=self.run_folder('good',summary=self.good_summary())
        rows=self.client.get('/api/runs').get_json()
        self.assertEqual({r['id']:r['status'] for r in rows},{'bad_status':'failed','bad_summary':'failed','good':'complete'})
        self.assertEqual(self.client.get('/api/runs/bad_summary/result').status_code,400)
        self.assertEqual(self.client.get('/api/runs/bad_summary/files').status_code,200)
        self.assertEqual(self.client.get('/api/jobs/bad_status').get_json()['status'],'failed')
    def test_interrupted_job_is_terminal_and_cancelled_marker_is_respected(self):
        out=self.run_folder('interrupted','running')
        state=self.client.get('/api/jobs/interrupted').get_json()
        self.assertEqual(state['status'],'failed');self.assertIn('Partial files',state['message'])
        self.assertEqual(self.client.post('/api/jobs/interrupted/cancel').status_code,409)
        out=self.run_folder('cancelled','running');common.save_json(out/'cancel_requested.json',{})
        self.assertEqual(self.client.get('/api/jobs/cancelled').get_json()['status'],'cancelled')
    def test_missing_status_is_inspectable_instead_of_server_error(self):
        (self.results/'partial').mkdir()
        self.assertEqual(self.client.get('/api/jobs/partial').get_json()['status'],'failed')
        self.assertEqual(self.client.get('/api/runs/partial/files').status_code,200)
    def test_unreadable_single_bag_returns_json_error(self):
        (self.bags/'device_1'/'broken.bag').write_bytes(b'broken')
        for route in ('/api/bag-info?name=device_1/broken.bag','/api/bag-preview?name=device_1/broken.bag&topic=/camera'):
            response=self.client.get(route);self.assertEqual(response.status_code,400);self.assertIn('error',response.get_json())
        self.assertEqual(self.client.post('/api/jobs',json={'bag':'device_1/broken.bag'}).status_code,400)
    def test_missing_sensor_in_first_bag_does_not_block_automatic_folder_queue(self):
        for name in ('a_missing.bag','b_valid.bag'):(self.bags/'device_1'/name).touch()
        meta={**self.metadata(),'suggested_livox_topic':None,'topics':[self.metadata()['topics'][0]]}
        with patch.object(server,'inspect_bag',return_value=meta),patch.object(server,'spawn_worker') as spawn:
            response=self.client.post('/api/batches',json={'dataset':'device_1'})
        self.assertEqual(response.status_code,202,response.get_json());self.assertEqual(response.get_json()['bags'],2)
        self.assertEqual(len(spawn.call_args.args[2]['bags']),2)
    def test_missing_sensor_in_first_bag_does_not_block_manual_folder_queue(self):
        for name in ('a_missing.bag','b_valid.bag'):(self.bags/'device_1'/name).touch()
        meta={**self.metadata(),'suggested_livox_topic':None,'topics':[self.metadata()['topics'][0]]}
        with patch.object(server,'inspect_bag',return_value=meta),patch.object(server,'spawn_worker') as spawn:
            response=self.client.post('/api/batches',json={'dataset':'device_1','auto_topics':False,'config':{'camera_topic':'/camera','livox_topic':'/livox'}})
        self.assertEqual(response.status_code,202,response.get_json());self.assertFalse(spawn.call_args.args[2]['auto_topics'])
    def test_concurrent_uploads_keep_both_files_and_no_temporary_files(self):
        barrier=threading.Barrier(2)
        def inspect_uploaded(path):barrier.wait(timeout=5);return self.metadata()
        def upload(contents):
            with server.app.test_client() as client:
                response=client.post('/api/upload',data={'dataset':'device_3','file':(io.BytesIO(contents),'same.bag')})
                self.assertEqual(response.status_code,200,response.get_json());return response.get_json()['name']
        with patch.object(server,'inspect_bag',side_effect=inspect_uploaded),ThreadPoolExecutor(max_workers=2) as pool:
            names=list(pool.map(upload,[b'first upload',b'second upload']))
        self.assertEqual(len(set(names)),2)
        self.assertEqual({(self.bags/name).read_bytes() for name in names},{b'first upload',b'second upload'})
        self.assertEqual(len(list((self.bags/'device_3').iterdir())),2)
    def test_only_one_concurrent_processing_request_starts(self):
        (self.bags/'device_1'/'valid.bag').touch()
        def spawn(identifier,out,req,script):
            common.save_json(out/'status.json',{'id':identifier,'status':'queued'})
            job_registry.workers[identifier]=SimpleNamespace(poll=lambda:None)
        def start(_):
            with server.app.test_client() as client:
                return client.post('/api/jobs',json={'bag':'device_1/valid.bag','config':{'camera_topic':'/camera','livox_topic':'/livox'}}).status_code
        with patch.object(server,'inspect_bag',return_value=self.metadata()),patch.object(server,'spawn_worker',side_effect=spawn) as worker,ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(start,range(2)))
        self.assertEqual(sorted(responses),[202,409]);self.assertEqual(worker.call_count,1)

    def test_two_server_processes_share_one_processing_reservation(self):
        (self.bags/'device_1'/'valid.bag').touch()
        context=multiprocessing.get_context('fork');barrier=context.Barrier(2);answers=context.Queue()
        def spawn(identifier,out,req,script):
            time.sleep(.15)  # Another server must not enter this launch interval.
            common.save_json(out/'status.json',{'id':identifier,'status':'queued'})
            job_registry.workers[identifier]=SimpleNamespace(poll=lambda:None)
        def request_job():
            barrier.wait(timeout=3)
            with server.app.test_client() as client:
                answers.put(client.post('/api/jobs',json={'bag':'device_1/valid.bag','config':{'camera_topic':'/camera','livox_topic':'/livox'}}).status_code)
        with patch.object(server,'inspect_bag',return_value=self.metadata()),patch.object(server,'spawn_worker',side_effect=spawn):
            processes=[context.Process(target=request_job) for _ in range(2)]
            for process in processes:process.start()
            for process in processes:process.join(timeout=5);self.assertEqual(process.exitcode,0)
        self.assertEqual(sorted(answers.get(timeout=2) for _ in processes),[202,409])

    def test_recent_queue_is_not_marked_interrupted_during_worker_launch(self):
        out=self.run_folder('launching','queued')
        self.assertEqual(self.client.get('/api/jobs/launching').get_json()['status'],'queued')
        os.utime(out/'status.json',(time.time()-10,time.time()-10))
        self.assertEqual(self.client.get('/api/jobs/launching').get_json()['status'],'failed')
    def test_worker_spawn_failure_does_not_leave_queued_run(self):
        (self.bags/'device_1'/'valid.bag').touch()
        with patch.object(server,'inspect_bag',return_value=self.metadata()),patch.object(server.subprocess,'Popen',side_effect=OSError('Interpreter unavailable')):
            response=self.client.post('/api/jobs',json={'bag':'device_1/valid.bag','config':{'camera_topic':'/camera','livox_topic':'/livox'}})
        self.assertEqual(response.status_code,400)
        rows=self.client.get('/api/runs').get_json();self.assertEqual(rows[0]['status'],'failed')
        self.assertTrue((self.results/rows[0]['id']/'error.txt').is_file())
    def test_nonfinite_scan_values_are_null_and_bounds_are_checked(self):
        out=self.run_folder();(out/'scans').mkdir();(out/'scans'/'scan_metrics.csv').write_text('scan_index,local_rpm,target_depth_std_m\n0,nan,inf\n1,10,0.01\n')
        response=self.client.get('/api/runs/capture/scans')
        data=json.loads(response.data,parse_constant=lambda value:self.fail('Invalid JSON number: '+value))
        self.assertIsNone(data['rows'][0]['local_rpm']);self.assertIsNone(data['rows'][0]['target_depth_std_m'])
        self.assertEqual(self.client.get('/api/runs/capture/scans?start=100').get_json()['rows'],[])
        for query in ('start=-1','start=nan','limit=0','limit=1001'):
            self.assertEqual(self.client.get('/api/runs/capture/scans?'+query).status_code,400)
    def test_external_symlinks_are_excluded_from_files_and_download(self):
        out=self.run_folder();external=self.root/'private.txt';external.write_text('outside run')
        (out/'outside.txt').symlink_to(external)
        self.assertEqual(self.client.get('/artifacts/capture/outside.txt').status_code,400)
        self.assertNotIn('outside.txt',[row['path'] for row in self.client.get('/api/runs/capture/files').get_json()])
        response=self.client.get('/api/runs/capture/download')
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:self.assertNotIn('capture/outside.txt',archive.namelist())
        response.close()
        (self.bags/'device_1'/'outside.bag').symlink_to(external)
        self.assertEqual(self.client.get('/api/bags?dataset=device_1').get_json(),[])
    def test_http_errors_have_actionable_json(self):
        for route in ('/api/not-a-route','/static/missing.js'):
            response=self.client.get(route);self.assertEqual(response.status_code,404);self.assertIn('error',response.get_json())
        self.assertEqual(self.client.post('/api/compare',json={'runs':[None,{},123,[]]}).status_code,400)
    def test_padded_big_endian_cloud_is_decoded_and_invalid_fields_rejected(self):
        fields=[SimpleNamespace(name=name,datatype=7,count=1,offset=i*4) for i,name in enumerate(('x','y','z'))]
        row=np.array([(1.,2.,3.),(4.,5.,6.)],dtype='>f4').tobytes()+b'padding!'
        msg=SimpleNamespace(fields=fields,height=2,width=2,point_step=12,row_step=32,is_bigendian=True,data=row+row)
        result=decode(msg);self.assertEqual(result['x'].tolist(),[1,4,1,4])
        fields[0].count=2
        with self.assertRaisesRegex(ValueError,'scalar'):decode(msg)
    def test_image_stride_and_buffer_errors_are_explicit(self):
        msg=SimpleNamespace(encoding='mono8',width=3,height=2,step=5,data=bytes([1,2,3,0,0,4,5,6,0,0]))
        self.assertEqual(grayscale(msg).tolist(),[[1,2,3],[4,5,6]])
        msg.step=2
        with self.assertRaisesRegex(ValueError,'stride'):grayscale(msg)
    def test_short_validation_blocks_and_invalid_timing_data_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'too short'):validation_blocks(np.linspace(0,2,150),2,5,12,'Livox')
        with self.assertRaisesRegex(ValueError,'strictly increasing'):lag_profile([0,0],[0,1],[0,1],[0,1],.1)
        with self.assertRaisesRegex(ValueError,'finite'):fit_multi([{'group':'rig','omega_deg_s':float('nan'),'phase_delta_mod120_deg':10}]*4)
        with self.assertRaisesRegex(ValueError,'numeric'):fit_multi([{'group':'rig','omega_deg_s':'broken','phase_delta_mod120_deg':10}]*4)

    def test_different_filenames_with_identical_bag_contents_are_one_capture(self):
        records=[]
        for name in ('original.bag','renamed.bag'):
            (self.bags/'device_1'/name).write_bytes(b'exactly the same recording')
            records.append({'bag':name,'bag_path':'device_1/'+name})
        unique,duplicates=common.distinct_captures(records)
        self.assertEqual(len(unique),1);self.assertEqual(duplicates[0]['bag'],'renamed.bag')
        first=common.sha256_file(self.bags/'device_1'/'original.bag')
        (self.bags/'device_1'/'original.bag').write_bytes(b'a different recording')
        self.assertNotEqual(common.sha256_file(self.bags/'device_1'/'original.bag'),first)

    def test_duplicate_renamed_sources_are_rejected_by_comparison(self):
        identifiers=[]
        for index in range(4):
            name='capture_'+str(index);result=self.good_summary(name)
            result['provenance']={'bag_sha256':'a'*64}
            result['timing']['cross_speed_phase_observation']={'group':'rig','omega_deg_s':30,'phase_delta_mod120_deg':10}
            self.run_folder(name,summary=result);identifiers.append(name)
        response=self.client.post('/api/compare',json={'runs':identifiers})
        self.assertEqual(response.status_code,400);self.assertIn('identical source',response.get_json()['error'])

    def test_valid_json_with_missing_result_fields_is_marked_incomplete(self):
        self.run_folder('incomplete',summary={'id':'incomplete','config':{},'flir':{},'livox':{},'timing':{}})
        self.assertEqual(self.client.get('/api/runs').get_json()[0]['status'],'failed')
        self.assertEqual(self.client.get('/api/runs/incomplete/result').status_code,400)
        self.assertEqual(self.client.get('/api/runs/incomplete/files').status_code,200)

    def test_wrong_types_in_manual_folder_settings_are_rejected_before_queueing(self):
        (self.bags/'device_1'/'valid.bag').touch()
        with patch.object(server,'inspect_bag',return_value=self.metadata()),patch.object(server,'spawn_worker') as worker:
            for value in (None,[],{},123,''):
                response=self.client.post('/api/batches',json={'dataset':'device_1','auto_topics':False,'config':{'camera_topic':value,'livox_topic':'/livox'}})
                self.assertEqual(response.status_code,400,response.get_json())
        worker.assert_not_called()

    def test_long_source_filename_can_start_a_run_without_renaming_the_source(self):
        name='c'*240+'.bag';(self.bags/'device_1'/name).touch()
        with patch.object(server,'inspect_bag',return_value=self.metadata()),patch.object(server,'spawn_worker') as worker:
            response=self.client.post('/api/jobs',json={'bag':'device_1/'+name,'config':{'camera_topic':'/camera','livox_topic':'/livox'}})
        self.assertEqual(response.status_code,202,response.get_json())
        self.assertLess(len(response.get_json()['id'].encode()),255)
        self.assertEqual(worker.call_args.args[2]['bag'],'device_1/'+name)
        self.assertTrue((self.bags/'device_1'/name).exists())

    def test_very_long_upload_names_and_repeat_imports_fit_filesystem_limits(self):
        names=[]
        with patch.object(server,'inspect_bag',return_value=self.metadata()):
            for _ in range(2):
                response=self.client.post('/api/upload',data={'dataset':'device_4','file':(io.BytesIO(b'long-name upload fixture'),'u'*400+'.bag')})
                self.assertEqual(response.status_code,200,response.get_json());names.append(response.get_json()['name'])
        self.assertEqual(len(set(names)),2)
        for name in names:self.assertLess(len(Path(name).name.encode()),255);self.assertEqual((self.bags/name).read_bytes(),b'long-name upload fixture')

    def test_generated_unicode_run_ids_obey_byte_limits(self):
        identifier=server.new_id('測'*80)
        self.assertLess(len(identifier.encode('utf-8')),255)
        self.assertTrue(identifier.startswith('測'))


if __name__=='__main__':unittest.main()
