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

    def test_wrong_progress_types_do_not_break_job_views(self):
        out=self.run_folder('damaged','running')
        for field,value in (('percent',None),('percent',101),('total',[]),('previews',[]),
                            ('previews',{'livox':'invalid'}),('trace',{'FLIR':[{'t':0,'angle':'bad'}]}),('batch',{'entries':[]})):
            common.save_json(out/'status.json',{'status':'running',field:value})
            response=self.client.get('/api/jobs/damaged')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json()['status'],'failed')
            self.assertEqual(self.client.get('/api/runs').status_code,200)

    def test_damaged_progress_does_not_release_a_live_worker_reservation(self):
        out=self.run_folder('live','running');(out/'status.json').write_text('{damaged progress')
        stopped=[]
        job_registry.workers['live']=SimpleNamespace(poll=lambda:None,terminate=lambda:stopped.append(True))
        self.assertEqual(job_registry.active_jobs(),['live'])
        state=self.client.get('/api/jobs/live').get_json()
        self.assertEqual(state['status'],'running');self.assertEqual(state['stage'],'recovering')
        self.assertEqual(self.client.post('/api/jobs/live/cancel').status_code,200)
        self.assertEqual(stopped,[True])
        self.assertEqual(self.client.get('/api/jobs/live').get_json()['status'],'cancelling')

    def test_cli_reservation_blocks_app_and_releases_on_initialization_failure(self):
        import process_bag as cli
        (self.bags/'device_1'/'valid.bag').touch()
        request={'id':'cli_reserved','bag':'device_1/valid.bag'}
        def callback(req):
            job_registry.workers[req['id']]=SimpleNamespace(poll=lambda:None)
            with patch.object(server,'inspect_bag',return_value=self.metadata()),patch.object(server,'spawn_worker') as spawn:
                response=self.client.post('/api/jobs',json={'bag':req['bag'],'config':{'camera_topic':'/camera','livox_topic':'/livox'}})
                self.assertEqual(response.status_code,409);spawn.assert_not_called()
            raise ValueError('Intentional startup failure')
        with patch.object(cli,'RESULTS',self.results),patch.object(cli,'remember_current'):
            with self.assertRaisesRegex(ValueError,'startup failure'):cli.execute(request,callback)
        self.assertEqual(common.read_json(self.results/'cli_reserved'/'status.json')['status'],'failed')
        self.assertEqual(job_registry.active_jobs(),[])

    def test_busy_app_blocks_cli_before_a_result_directory_is_created(self):
        import process_bag as cli
        out=self.run_folder('active','running');job_registry.workers['active']=SimpleNamespace(poll=lambda:None)
        with patch.object(cli,'RESULTS',self.results):
            with self.assertRaisesRegex(ValueError,'already being processed'):
                cli.execute({'id':'blocked','bag':'a.bag'},lambda request:self.fail('Overlapping worker started'))
        self.assertFalse((self.results/'blocked').exists())

    def test_cli_reports_folder_failures_with_nonzero_exit_status(self):
        import process_bag as cli
        import batch_worker
        (self.bags/'device_1'/'valid.bag').touch()
        result={'totals':{'failed_bags':1},'overall_timing':{}}
        with patch.object(cli,'RESULTS',self.results),patch.object(cli,'BAGS',self.bags),patch.object(cli,'remember_current'),\
                patch.object(cli.sys,'argv',['process_bag.py','--folder','device_1']),\
                patch.object(batch_worker,'run_batch',return_value=result):
            self.assertEqual(cli.main(),1)

    def test_cli_interruption_during_startup_has_consistent_cancelled_status(self):
        import process_bag as cli
        def interrupt(request):raise KeyboardInterrupt()
        with patch.object(cli,'RESULTS',self.results),patch.object(cli,'remember_current'):
            with self.assertRaises(KeyboardInterrupt):cli.execute({'id':'cancel_start','bag':'valid.bag'},interrupt)
        state=common.read_json(self.results/'cancel_start'/'status.json')
        self.assertEqual((state['status'],state['stage']),('cancelled','cancelled'))

    def test_external_result_folders_are_not_listed_or_changed(self):
        external=self.root/'external';external.mkdir()
        common.save_json(external/'status.json',{'status':'running','bag':'outside.bag'})
        before=(external/'status.json').read_bytes()
        (self.results/'outside').symlink_to(external,target_is_directory=True)
        self.assertEqual(self.client.get('/api/runs').get_json(),[])
        self.assertEqual(job_registry.active_jobs(),[])
        self.assertEqual((external/'status.json').read_bytes(),before)

    def test_broken_result_symlinks_do_not_break_the_library(self):
        (self.results/'broken').symlink_to(self.root/'missing',target_is_directory=True)
        self.run_folder('good',summary=self.good_summary())
        response=self.client.get('/api/runs')
        self.assertEqual(response.status_code,200)
        self.assertEqual([r['id'] for r in response.get_json()],['good'])

    def test_example_label_is_display_metadata_and_new_runs_remain_visible(self):
        self.run_folder('example',summary=self.good_summary('example'))
        self.run_folder('new_run',summary=self.good_summary('new_run'))
        common.save_json(self.root/'example_results.json',{'id':'example','label':'Device 1 · example'})
        original=(self.results/'example'/'summary.json').read_bytes()
        with patch.object(server,'ROOT',self.root):
            rows={r['id']:r for r in self.client.get('/api/runs').get_json()}
            self.assertEqual(set(rows),{'example','new_run'})
            self.assertEqual(rows['example']['display_label'],'Device 1 · example')
            self.assertIsNone(rows['new_run']['display_label'])
            result=self.client.get('/api/runs/example/result').get_json()
            self.assertEqual(result['display_label'],'Device 1 · example')
        self.assertEqual((self.results/'example'/'summary.json').read_bytes(),original)

    def test_malformed_scan_csv_and_missing_array_return_json_errors(self):
        out=self.run_folder();(out/'scans').mkdir();(out/'intermediates').mkdir()
        for content in ('scan_index,local_rpm\n0\n','scan_index\n0,10\n','scan_index\nbad\n'):
            (out/'scans'/'scan_metrics.csv').write_text(content)
            response=self.client.get('/api/runs/capture/scans')
            self.assertEqual(response.status_code,400);self.assertIn('error',response.get_json())
        np.savez_compressed(out/'intermediates'/'livox_extracted.npz',stamps=[0],offsets=[0,1])
        response=self.client.get('/api/runs/capture/scan-preview')
        self.assertEqual(response.status_code,400);self.assertIn('saved scan',response.get_json()['error'])

    def test_resolution_change_is_rejected_even_when_manual_crop_still_fits(self):
        import rosbag
        import rospy
        from sensor_msgs.msg import Image,PointCloud2
        from bag_io import extract
        path=self.bags/'device_1'/'resolution.bag'
        with rosbag.Bag(str(path),'w') as bag:
            for i,width in enumerate((64,65)):
                bag.write('/camera',Image(height=64,width=width,step=width,encoding='mono8',data=b'\0'*(64*width)),rospy.Time(i+1))
            bag.write('/livox',PointCloud2(),rospy.Time(3))
        with self.assertRaisesRegex(ValueError,'resolution changes'):
            extract(path,{'camera_topic':'/camera','livox_topic':'/livox','camera_roi':[0,0,60,60]},self.results,lambda *a,**k:None,lambda *a:None)

    def test_invalid_saved_speeds_and_fractional_counts_are_not_presented(self):
        for section,field,value in (('flir','rpm','wrong'),('livox','rpm',float('nan')),('flir','frames',150.5)):
            result=self.good_summary('invalid');result[section][field]=value
            self.run_folder('invalid',summary=result)
            self.assertEqual(self.client.get('/api/runs/invalid/result').status_code,400)
            self.assertEqual(self.client.get('/api/runs/invalid/files').status_code,200)
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
