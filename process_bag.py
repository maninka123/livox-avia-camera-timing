#!/usr/bin/env python3
"""Command-line runner using exactly the same pipeline as the browser app."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
import json
import sys
import uuid
from datetime import datetime,timezone
from common import ROOT,BAGS,RESULTS,bag_path,save_json,validate_options,dataset_bags,file_prefix,file_lock,read_json
from bag_io import inspect
from pipeline import run
from job_registry import active_jobs,remember_current


def execute(request, callback):
    """Reserve the same processing slot as the app before allocating sensor data."""
    out=RESULTS/request['id']
    with file_lock(RESULTS/'.queue.lock'):
        if active_jobs():
            raise ValueError('A recording or folder is already being processed. Finish or cancel it first.')
        out.mkdir()
        save_json(out/'request.json',request)
        save_json(out/'status.json',{'id':request['id'],'bag':request.get('bag',request.get('dataset')),
                                   'kind':request.get('kind','detection'),'status':'queued','stage':'queued','percent':0})
        remember_current(out)
    print('Processing',request.get('bag',request.get('dataset')),'->',out,flush=True)
    try:
        return callback(request)
    except BaseException as exc:
        # Failures during worker initialization must release the reserved slot too.
        state=read_json(out/'status.json')
        if state['status'] in ('queued','running','cancelling'):
            terminal='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed'
            state.update(status=terminal,stage=terminal,message=str(exc))
            save_json(out/'status.json',state)
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bag',nargs='?',help='Filename in bagfiles/')
    scopes=parser.add_mutually_exclusive_group();scopes.add_argument('--all',action='store_true',help='Process every nonempty device folder, with folder summaries')
    scopes.add_argument('--folder',choices=[f'device_{i}' for i in range(1,6)],help='Process every bag in one device folder')
    parser.add_argument('--localization',choices=['auto','camera_guided','lidar_only','legacy'],default='auto',help='Automatic fallback by default; advanced override for diagnostics or reproducing old results')
    parser.add_argument('--camera-topic');parser.add_argument('--livox-topic');parser.add_argument('--phase-group')
    parser.add_argument('--camera-roi',nargs=4,type=int,metavar=('X','Y','WIDTH','HEIGHT'),help='Optional manual camera crop; default searches full images automatically')
    args=parser.parse_args()
    if args.bag and (args.all or args.folder):parser.error('Choose one bag or folder mode, not both.')
    if args.all or args.folder:
        from batch_worker import run_batch
        devices=[f'device_{i}' for i in range(1,6) if dataset_bags(f'device_{i}')] if args.all else [args.folder]
        if not devices:parser.error('No device folder contains bags.')
        failures=False
        for device in devices:
            paths=dataset_bags(device)
            if not paths:parser.error('This device folder is empty.')
            identifier='batch_'+device+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
            request={'id':identifier,'kind':'batch','dataset':device,'bags':[str(p.relative_to(BAGS)) for p in paths],
                     'config':{k:v for k,v in {'camera_topic':args.camera_topic,'livox_topic':args.livox_topic,'phase_group':args.phase_group,'livox_localization':args.localization,'camera_roi':args.camera_roi}.items() if v is not None},
                     'auto_topics':not (args.camera_topic or args.livox_topic),'auto_groups':not bool(args.phase_group)}
            result=execute(request,run_batch)
            if result:print('COMPLETE',device,result['totals'],'overall timing',result['overall_timing'],flush=True)
            failures=failures or result is None or result['totals']['failed_bags']>0
        return int(failures)
    names=[args.bag]
    if names==[None]:parser.error('Select a bag filename, --folder device_1 or --all.')
    for name in names:
        path=bag_path(name);meta=inspect(path)
        options={'camera_topic':args.camera_topic or meta['suggested_camera_topic'],'livox_topic':args.livox_topic or meta['suggested_livox_topic'],
                 'phase_group':args.phase_group or meta['suggested_phase_group'],'livox_localization':args.localization}
        if args.camera_roi is not None:options['camera_roi']=args.camera_roi
        config=validate_options(meta,options)
        identifier=file_prefix(path.stem)+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
        request={'id':identifier,'bag':str(path.relative_to(BAGS)),'config':config,'created_at':datetime.now(timezone.utc).isoformat()}
        result=execute(request,run)
        if result:print('COMPLETE',name,'FLIR SD',result['flir']['heldout_residual']['std_deg'],
                        'Livox heldout SD',result['timing']['agreement']['heldout_raw']['std_deg'],
                        'timing',result['timing']['single_bag_lag']['status'],flush=True)
        if result is None:return 1
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError) as exc:
        print('Processing error: '+str(exc),file=sys.stderr);sys.exit(2)
