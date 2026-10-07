#!/usr/bin/env python3
"""Sequential folder worker with isolated captures, persisted queue and live previews."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
import json
import signal
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from common import ROOT, RESULTS, bag_path, save_json, validate_options, native,file_prefix
from bag_io import inspect
from batch_analysis import aggregate,summarize_capture
from job_registry import remember_current


class Cancelled(Exception):pass


def run_batch(request):
    output=RESULTS/request['id'];output.mkdir(exist_ok=True)
    (output/'captures').mkdir(exist_ok=True);(output/'figures').mkdir(exist_ok=True);(output/'timing').mkdir(exist_ok=True)
    started=time.monotonic();child=None;results=[];last_stage=None
    entries=[{'bag_path':name,'status':'queued'} for name in request['bags']]
    state={'id':request['id'],'kind':'batch','bag':request['dataset'].replace('_',' ').title(),
           'dataset':request['dataset'],'status':'running','stage':'batch_start','percent':0,'message':'Preparing folder queue',
           'processed':0,'remaining':0,'total':0,'elapsed_s':0,'previews':{},'trace':{'FLIR':[],'Livox':[]},
           'batch':{'total':len(entries),'finished':0,'completed':0,'failed':0,'remaining':len(entries),'current_index':0,'current_bag':None,'entries':entries}}
    def publish():
        state['elapsed_s']=round(time.monotonic()-started,2)
        save_json(output/'status.json',state)
    def event():
        with (output/'progress.jsonl').open('a') as stream:stream.write(json.dumps(native({k:v for k,v in state.items() if k not in ('trace','previews')}))+'\n')
    def cancel(*args):raise Cancelled('Folder processing cancelled; completed captures and partial current files are retained.')
    signal.signal(signal.SIGTERM,cancel);remember_current(output);publish()
    try:
        for index,entry in enumerate(entries):
            name=entry['bag_path'];state['batch'].update(current_index=index+1,current_bag=name)
            child_id=file_prefix(Path(name).stem)+'_'+uuid.uuid4().hex[:8];run_id=request['id']+'/captures/'+child_id
            child_out=RESULTS/run_id;child_out.mkdir();entry.update(run_id=run_id,status='running')
            state.update(previews={},trace={'FLIR':[],'Livox':[]},capture_percent=0,metrics={},processed=0,total=0,remaining=0,
                         stage='batch_start',message=f'Preparing capture {index+1}/{len(entries)}: {Path(name).name}')
            publish();event()
            try:
                path=bag_path(name);meta=inspect(path);options=dict(request.get('config',{}))
                if request.get('auto_topics',True):
                    options.update(camera_topic=meta['suggested_camera_topic'],livox_topic=meta['suggested_livox_topic'])
                if request.get('auto_groups',True):options['phase_group']=meta['suggested_phase_group']
                config=validate_options(meta,options)
                child_request={'id':run_id,'bag':name,'config':config,'parent_batch':request['id']}
                save_json(child_out/'request.json',child_request)
                env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
                with (child_out/'worker.log').open('w') as log:
                    child=subprocess.Popen([sys.executable,str(ROOT/'pipeline.py'),str(child_out/'request.json')],cwd=str(ROOT),env=env,stdout=log,stderr=subprocess.STDOUT)
                while True:
                    status_file=child_out/'status.json'
                    if status_file.exists():
                        current=json.loads(status_file.read_text())
                        state.update(stage=current['stage'],processed=current.get('processed',0),remaining=current.get('remaining',0),total=current.get('total',0),
                            percent=round(95*(index+current.get('percent',0)/100)/len(entries),1),
                            message=f'Capture {index+1}/{len(entries)} · {Path(name).name} · {current.get("message","")}',
                            capture_percent=current.get('percent',0),metrics=current.get('metrics',{}),trace=current.get('trace',{'FLIR':[],'Livox':[]}))
                        state['previews']={sensor:{**preview,'path':'captures/'+child_id+'/'+preview['path']} for sensor,preview in current.get('previews',{}).items()}
                        if current['stage']!=last_stage:event();last_stage=current['stage']
                        publish()
                    if child.poll() is not None:break
                    time.sleep(.2)
                if child.returncode!=0 or not (child_out/'summary.json').is_file():
                    reason=json.loads(status_file.read_text()).get('message','Worker failed.') if status_file.exists() else 'Worker exited before starting.'
                    raise ValueError(reason)
                result=json.loads((child_out/'summary.json').read_text())
                metrics=summarize_capture(result);results.append(result)
                entry.update(status='complete',metrics=metrics);child=None
            except Cancelled:
                raise
            except Exception as exc:
                if child is not None and child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=8)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                entry.update(status='failed',error=str(exc));child=None
                if not (child_out/'status.json').exists():save_json(child_out/'status.json',{'id':run_id,'bag':name,'status':'failed','stage':'failed','message':str(exc),'percent':0})
                (child_out/'error.txt').write_text(traceback.format_exc())
            state['batch'].update(finished=index+1,completed=len(results),failed=sum(e['status']=='failed' for e in entries),remaining=len(entries)-index-1)
            publish();event()
        state.update(stage='batch_aggregate',percent=96,message='Saving per-scan summaries, comparison plots and overall timestamp analysis',previews={})
        publish();event()
        result=aggregate(request,results,entries,output)
        state.update(status='complete',stage='complete',percent=100,message=f'Folder complete: {len(results)} succeeded, {len(entries)-len(results)} failed. Overall timing: {result["overall_timing"]["status"]}.',
                     capture_percent=100,processed=len(entries),total=len(entries),remaining=0,previews={},trace={'FLIR':[],'Livox':[]})
        state['batch'].update(current_bag=None,remaining=0)
        publish();event();return result
    except BaseException as exc:
        cancelled=isinstance(exc,(Cancelled,KeyboardInterrupt))
        # Repeated SIGTERM during shutdown must not orphan the current capture.
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=8)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        for entry in entries:
            if entry['status'] in ('running','queued'):entry['status']='cancelled' if cancelled else 'not_processed'
        state.update(status='cancelled' if cancelled else 'failed',stage='cancelled' if cancelled else 'failed',message=str(exc))
        state['batch'].update(remaining=0,current_bag=None,cancelled=sum(e['status']=='cancelled' for e in entries))
        state.update(remaining=0,previews={},trace={'FLIR':[],'Livox':[]})
        save_json(output/'partial_manifest.json',entries);publish();event()
        (output/'error.txt').write_text(traceback.format_exc())
        if not cancelled:raise
        return None


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('request_file');args=parser.parse_args()
    run_batch(json.loads(Path(args.request_file).read_text()))
