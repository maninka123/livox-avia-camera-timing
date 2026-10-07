#!/usr/bin/env python3
"""Local Flask interface; processing runs in isolated Python subprocesses."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
import csv
import json
import subprocess
import sys
import threading
import uuid
import zipfile
from datetime import datetime,timezone
from pathlib import Path
import cv2
import numpy as np
import rosbag
from flask import Flask,jsonify,render_template,request,send_file,send_from_directory
from werkzeug.utils import secure_filename
from common import ROOT,BAGS,RESULTS,bag_path,save_json,read_json,native,validate_options,write_csv,dataset_path,dataset_bags,result_path,capture_identity,file_lock,file_prefix
from bag_io import inspect,grayscale
from timing import fit_multi
from job_registry import workers,remember,status,active_jobs,restore,ACTIVE
from werkzeug.exceptions import HTTPException

app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=8*1024**3
app.config['TEMPLATES_AUTO_RELOAD']=True
lock=threading.RLock()
scan_preview_lock=threading.Lock()

def folder(run_id):
    return result_path(run_id)

def new_id(prefix):return file_prefix(prefix)+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]

def example_label(identifier):
    try:
        example=read_json(ROOT/'example_results.json')
        label=example.get('label')
        return label if example.get('id')==identifier and isinstance(label,str) and label.strip() else None
    except ValueError:
        return None

@app.errorhandler(ValueError)
def value_error(exc):return jsonify(error=str(exc)),400

@app.errorhandler(413)
def too_large(exc):return jsonify(error='This upload exceeds the 8 GB limit.'),413

@app.errorhandler(HTTPException)
def http_error(exc):
    return jsonify(error=exc.description),exc.code

def inspect_bag(path):
    try:return inspect(path)
    except Exception as exc:raise ValueError('Unable to inspect this ROS1 bag: '+str(exc)) from exc

def summary(out):
    result=read_json(out/'summary.json');kind=result.get('kind','detection')
    fields={'detection':('config','flir','livox','timing'),
            'batch':('totals','overall_timing'), 'comparison':('multi_timing',)}
    if not isinstance(kind,str) or kind not in fields or any(not isinstance(result.get(key),dict) for key in fields[kind]):
        raise ValueError('The saved summary is incomplete or has an unsupported format. Inspect the saved files or rerun this capture.')
    for key in {'batch':('captures','entries'),'comparison':('observations',)}.get(kind,()):
        if not isinstance(result.get(key),list) or any(not isinstance(row,dict) for row in result[key]):raise ValueError('The saved summary is incomplete: '+key)
    required={
        'detection':('id','bag','config.camera_topic','config.livox_topic','flir.frames','flir.rpm','flir.status','flir.heldout_residual',
                     'livox.frames','livox.rpm','livox.status','timing.agreement.heldout_raw','timing.agreement.heldout_offline_smoothed',
                     'timing.single_bag_lag.status','timing.clocks.livox.domain'),
        'batch':('id','bag','totals.requested_bags','totals.completed_bags','totals.failed_bags','totals.camera_frames',
                 'totals.livox_clouds','totals.input_points','overall_timing.status','overall_timing.candidate_tau_ms'),
        'comparison':('id','multi_timing.status','multi_timing.candidate_tau_ms','multi_timing.bags','multi_timing.groups')}
    for field in required[kind]:
        value=result
        for part in field.split('.'):
            if not isinstance(value,dict) or part not in value:raise ValueError('The saved summary is incomplete: '+field)
            value=value[part]
        if field.endswith(('frames','bags','points')) and (isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or value<0 or value!=int(value)):
            raise ValueError('The saved summary has an invalid observation count: '+field)
        if field.endswith('.rpm') and (isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value)):
            raise ValueError('The saved summary has invalid speed data: '+field)
        if field.endswith('candidate_tau_ms') and value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value)):
            raise ValueError('The saved summary has invalid timing data: '+field)
        if field in ('id','bag') or field.endswith(('topic','status','domain')):
            if not isinstance(value,str):raise ValueError('The saved summary has an invalid field: '+field)
        if field.endswith(('heldout_residual','heldout_raw','heldout_offline_smoothed')) and not isinstance(value,dict):
            raise ValueError('The saved summary has invalid metric data: '+field)
        if field.endswith('.groups') and (not isinstance(value,list) or any(not isinstance(group,str) for group in value)):
            raise ValueError('The saved summary has invalid setup groups.')
    if result['id']!=str(out.relative_to(RESULTS)):raise ValueError('The saved summary does not match this run folder.')
    for field in ('bag_path','device'):
        if result.get(field) is not None and not isinstance(result[field],str):raise ValueError('The saved summary has an invalid field: '+field)
    return native(result)

def saved_files(out):
    return [p for p in sorted(out.rglob('*')) if p.is_file() and out in p.resolve().parents and '.tmp' not in p.name]

@app.get('/')
def index():return render_template('index.html')

@app.get('/api/health')
def health():
    with lock:count=len(active_jobs())
    return jsonify(status='ok',pid=os.getpid(),workspace=str(ROOT),active_workers=count)

@app.get('/api/bags')
def bags():
    dataset=request.args.get('dataset')
    paths=dataset_bags(dataset) if dataset else [p for p in sorted(BAGS.rglob('*.bag')) if BAGS.resolve() in p.resolve().parents]
    return jsonify([{'name':str(p.relative_to(BAGS)),'filename':p.name,'device':p.parent.name,
                     'size_bytes':p.stat().st_size} for p in paths if p.is_file()])

@app.get('/api/datasets')
def datasets():
    return jsonify([{'id':f'device_{i}','label':f'Device {i}','bags':len(dataset_bags(f'device_{i}')),
                     'size_bytes':sum(p.stat().st_size for p in dataset_bags(f'device_{i}'))} for i in range(1,6)])

@app.get('/api/bag-info')
def bag_info():
    path=bag_path(request.args.get('name'))
    return jsonify(native(inspect_bag(path)))

@app.get('/api/calibration')
def device_calibration():
    from calibration import load_device
    device=request.args.get('device')
    # Validate the device independently of calibration availability.
    dataset_path(device)
    try:
        data=load_device(device)
        return jsonify(available=data is not None,calibration=data,
                       message='Automatic: camera-guided search, with LiDAR-only fallback.' if data else 'Automatic: LiDAR-only search; add device calibration to enable camera guidance.')
    except (ValueError,OSError) as exc:
        return jsonify(available=False,calibration=None,message='Device calibration needs review; automatic LiDAR-only fallback. '+str(exc))

@app.get('/api/bag-preview')
def bag_preview():
    path=bag_path(request.args.get('name'));topic=request.args.get('topic')
    meta=inspect_bag(path)
    if topic not in [r['name'] for r in meta['topics'] if r['type']=='sensor_msgs/Image']:raise ValueError('Select an image topic to preview.')
    with rosbag.Bag(str(path)) as bag:
        for _,msg,_ in bag.read_messages(topics=[topic]):
            image=grayscale(msg);ok,encoded=cv2.imencode('.png',image)
            if not ok:raise ValueError('Unable to encode the camera preview.')
            from io import BytesIO
            return send_file(BytesIO(encoded.tobytes()),mimetype='image/png')
    raise ValueError('The selected image topic is empty.')

@app.post('/api/upload')
def upload():
    if 'file' not in request.files:raise ValueError('Select a .bag file to import.')
    upload=request.files['file'];name=secure_filename(upload.filename or '')
    if not name.endswith('.bag'):raise ValueError('Only ROS1 .bag recordings are supported.')
    name=file_prefix(Path(name).stem)+'.bag'
    destination=dataset_path(request.form.get('dataset','device_1'))
    if (destination/name).exists():name=file_prefix(Path(name).stem)+'_'+uuid.uuid4().hex[:8]+'.bag'
    temp=destination/('.'+uuid.uuid4().hex+'.upload')
    try:
        upload.save(str(temp));inspect_bag(temp)
        # link() creates a destination atomically and refuses to replace another
        # upload, including one that arrived after the filename check above.
        while True:
            try:os.link(temp,destination/name);break
            except FileExistsError:name=file_prefix(Path(name).stem)+'_'+uuid.uuid4().hex[:8]+'.bag'
    except Exception as exc:
        raise ValueError('Invalid or unreadable ROS1 bag: '+str(exc)) from exc
    finally:temp.unlink(missing_ok=True)
    return jsonify(name=str((destination/name).relative_to(BAGS)))

def spawn_worker(identifier,out,req,script):
    save_json(out/'request.json',req)
    save_json(out/'status.json',{'id':identifier,'bag':req.get('bag',req.get('dataset')),'kind':req.get('kind','detection'),
        'status':'queued','percent':0,'stage':'queued','message':'Starting Python worker','processed':0,'remaining':0,
        'total':0,'elapsed_s':0,'metrics':{},'previews':{},'trace':{'FLIR':[],'Livox':[]}})
    log=(out/'worker.log').open('w')
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    process=None
    try:
        process=subprocess.Popen([sys.executable,str(ROOT/script),str(out/'request.json')],cwd=str(ROOT),stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        remember(identifier,process,out)
    except OSError as exc:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        message='Unable to start Python processing: '+str(exc)
        save_json(out/'status.json',{'id':identifier,'bag':req.get('bag',req.get('dataset')),'kind':req.get('kind','detection'),
                                   'status':'failed','stage':'failed','percent':0,'message':message})
        (out/'error.txt').write_text(message+'\n')
        raise ValueError(message) from exc
    finally:log.close()

@app.post('/api/jobs')
def start_job():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict):raise ValueError('Expected a bag name and acquisition settings.')
    path=bag_path(payload.get('bag'));meta=inspect_bag(path)
    options=payload.get('config',{})
    if not isinstance(options,dict):raise ValueError('Acquisition settings must be an object.')
    config=validate_options(meta,options)
    with lock,file_lock(RESULTS/'.queue.lock'):
        if active_jobs():return jsonify(error='A recording is already being processed. Finish or cancel it first.'),409
        identifier=new_id(path.stem);out=RESULTS/identifier;out.mkdir()
        req={'id':identifier,'bag':str(path.relative_to(BAGS)),'config':config,'created_at':datetime.now(timezone.utc).isoformat()}
        spawn_worker(identifier,out,req,'pipeline.py')
    return jsonify(id=identifier),202

@app.post('/api/batches')
def start_batch():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict):raise ValueError('Select a device folder and acquisition settings.')
    name=payload.get('dataset');paths=dataset_bags(name)
    if not paths:raise ValueError('This device folder contains no .bag files. Import a recording first.')
    options=payload.get('config',{})
    if not isinstance(options,dict):raise ValueError('Acquisition settings must be an object.')
    for key in ('auto_topics','auto_groups'):
        if key in payload and not isinstance(payload[key],bool):raise ValueError(f'{key} must be true or false.')
    # Validate controls independently of the first bag's eligibility. All bags,
    # including the first, get their real topic/type checks in the worker.
    first=dict(options)
    try:meta=inspect_bag(paths[0])
    except Exception:
        # An unreadable first bag belongs in the manifest, rather than preventing
        # all remaining recordings from being processed.
        defaults=json.loads((ROOT/'config.json').read_text())
        camera=options.get('camera_topic') or defaults['camera_topic'];livox=options.get('livox_topic') or defaults['livox_topic']
        meta={'topics':[{'name':camera,'type':'sensor_msgs/Image'},{'name':livox,'type':'sensor_msgs/PointCloud2'}],
              'suggested_camera_topic':camera,'suggested_livox_topic':livox,'suggested_phase_group':'normal'}
    defaults=read_json(ROOT/'config.json')
    camera=(meta.get('suggested_camera_topic') or '/automatic_camera') if payload.get('auto_topics',True) else first.get('camera_topic',defaults['camera_topic'])
    livox=(meta.get('suggested_livox_topic') or '/automatic_livox') if payload.get('auto_topics',True) else first.get('livox_topic',defaults['livox_topic'])
    if not isinstance(camera,str) or not camera.strip() or not isinstance(livox,str) or not livox.strip():
        raise ValueError('Select image and cloud topic names as nonempty text.')
    first.update(camera_topic=camera,livox_topic=livox)
    control_meta={'topics':[{'name':camera,'type':'sensor_msgs/Image'},{'name':livox,'type':'sensor_msgs/PointCloud2'}]}
    if payload.get('auto_groups',True):first['phase_group']=meta['suggested_phase_group']
    validate_options(control_meta,first)
    with lock,file_lock(RESULTS/'.queue.lock'):
        if active_jobs():return jsonify(error='A recording or folder is already being processed. Finish or cancel it first.'),409
        identifier=new_id('batch_'+name);out=RESULTS/identifier;out.mkdir()
        req={'id':identifier,'kind':'batch','dataset':name,'bags':[str(p.relative_to(BAGS)) for p in paths],
             'config':options,'auto_topics':payload.get('auto_topics',True),'auto_groups':payload.get('auto_groups',True),
             'created_at':datetime.now(timezone.utc).isoformat()}
        spawn_worker(identifier,out,req,'batch_worker.py')
    return jsonify(id=identifier,bags=len(paths)),202

@app.get('/api/jobs/<path:run_id>')
def job_status(run_id):
    out=folder(run_id)
    with lock:state=status(run_id,out)
    return jsonify(native(state))

@app.post('/api/jobs/<path:run_id>/cancel')
def cancel_job(run_id):
    out=folder(run_id)
    with lock:
        state=status(run_id,out)
        if state['status'] not in ACTIVE:return jsonify(error='This job has already stopped.'),409
        if '/captures/' in run_id:raise ValueError('Cancel the parent folder job to stop its current capture and queue.')
        process=restore(run_id,out)
        if not process or process.poll() is not None:return jsonify(error='This worker has already stopped.'),409
        if (out/'cancel_requested.json').exists():return jsonify(status='cancelling')
        save_json(out/'cancel_requested.json',{'requested_at':datetime.now(timezone.utc).isoformat()})
        process.terminate()
    return jsonify(status='cancelling')

@app.get('/api/runs')
def runs():
    rows=[]
    paths=(p for p in RESULTS.iterdir() if p.is_dir() and RESULTS.resolve() in p.resolve().parents)
    for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
        if not path.is_dir() or not (path/'status.json').exists():continue
        if path.name.startswith('.'):continue
        with lock:state=status(path.name,path)
        result={}
        if state['status']=='complete':
            try:result=summary(path)
            except ValueError as exc:state={**state,'status':'failed','message':str(exc)}
        rows.append({'id':path.name,'bag':state.get('bag','Cross-speed timing'),'status':state['status'],
                     'display_label':example_label(path.name),'captures':result.get('totals',{}).get('completed_bags'),
                     'bag_path':result.get('bag_path','device_1/'+result['bag'] if result.get('bag','').endswith('.bag') else None),
                     'kind':result.get('kind',state.get('kind','detection')),'elapsed_s':state.get('elapsed_s'),'message':state.get('message'),
                     'flir_std_deg':result.get('flir',{}).get('heldout_residual',{}).get('std_deg'),
                     'livox_std_deg':result.get('timing',{}).get('agreement',{}).get('heldout_raw',{}).get('std_deg')})
    return jsonify(native(rows))

@app.get('/api/runs/<path:run_id>/result')
def run_result(run_id):
    path=folder(run_id)/'summary.json'
    if not path.exists():raise ValueError('The final result is not ready yet.')
    with lock:state=status(run_id,path.parent)
    if state['status']!='complete':raise ValueError('This run has not completed. Inspect its saved files and diagnostic log.')
    return jsonify({**summary(path.parent),'display_label':example_label(run_id)})

@app.get('/api/runs/<path:run_id>/files')
def run_files(run_id):
    out=folder(run_id)
    return jsonify([{'path':str(p.relative_to(out)),'size_bytes':p.stat().st_size} for p in saved_files(out)])

@app.get('/artifacts/<run_id>/<path:name>')
def artifact(run_id,name):
    out=folder(run_id);path=(out/name).resolve()
    if out not in path.parents or not path.is_file():raise ValueError('Artifact not found.')
    response=send_from_directory(str(out),name,as_attachment=request.args.get('download')=='1')
    response.headers['Cache-Control']='no-cache';return response

@app.get('/api/runs/<path:run_id>/download')
def download(run_id):
    out=folder(run_id)
    with lock:state=status(run_id,out)
    if state['status']!='complete':raise ValueError('Wait for completion before downloading all artifacts.')
    bundles=RESULTS/'.bundles';bundles.mkdir(exist_ok=True);bundle=bundles/(run_id.replace('/','__')+'.zip')
    with file_lock(bundle.with_suffix('.lock')):
        files=saved_files(out)
        latest=max((file.stat().st_mtime_ns for file in files),default=0)
        if not bundle.exists() or bundle.stat().st_mtime_ns<latest:
            temp=bundle.with_suffix('.tmp')
            with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=2) as archive:
                for file in files:archive.write(str(file),out.name+'/'+str(file.relative_to(out)))
            temp.replace(bundle)
    return send_file(bundle,as_attachment=True,download_name=bundle.name)

@app.get('/api/runs/<path:run_id>/scans')
def scan_data(run_id):
    out=folder(run_id);file=out/'scans'/'scan_metrics.csv'
    if not file.is_file():raise ValueError('Per-scan statistics are available for new capture runs. Select an individual capture from the folder results.')
    start=int(request.args.get('start',0));limit=int(request.args.get('limit',100))
    if start<0 or not 1<=limit<=1000:raise ValueError('Use a nonnegative scan start and a limit between 1 and 1000.')
    with file.open() as stream:rows=list(csv.DictReader(stream))
    typed=[]
    for offset,row in enumerate(rows[start:start+limit],start=start):
        item={}
        for key,value in row.items():
            if key is None or value is None or not isinstance(value,str):
                raise ValueError(f'Saved scan table is malformed at row {offset+1}. Inspect scan_metrics.csv or reprocess this capture.')
            try:
                if value=='':item[key]=None
                elif value in ('True','False'):item[key]=value=='True'
                else:item[key]=float(value)
            except ValueError as exc:
                raise ValueError(f'Saved scan table has invalid {key} at row {offset+1}. Inspect scan_metrics.csv or reprocess this capture.') from exc
        typed.append(item)
    return jsonify(native({'total':len(rows),'start':start,'rows':typed}))

@app.get('/api/runs/<path:run_id>/scan-preview')
def scan_preview(run_id):
    out=folder(run_id);index=int(request.args.get('scan',0))
    file=out/'intermediates'/'livox_extracted.npz'
    if not file.is_file():raise ValueError('This capture has no extracted cloud data yet.')
    from scan_reader import read_scan
    with scan_preview_lock:
        points,(low,high),localized=read_scan(file,index)
    image=np.full((600,760,3),250,np.uint8)
    radius=np.hypot(points[:,0],points[:,1]);target=(radius>.025)&(radius<.135)&(points[:,2]>low)&(points[:,2]<high)
    for mask,color in ((~target,(183,189,189)),(target,(55,121,220))):
        positions=np.column_stack((380+points[mask,0]*1250,280-points[mask,1]*1250)).astype(int)
        for x,y in positions:
            if 0<=x<760 and 0<=y<530:cv2.circle(image,(x,y),1,color,-1)
    cv2.circle(image,(380,280),169,(145,158,153),1)
    cv2.putText(image,f'Livox scan {index} | selected measured rays {len(points)} | target {target.sum()}',(20,550),cv2.FONT_HERSHEY_SIMPLEX,.50,(40,65,65),1,cv2.LINE_AA)
    cv2.putText(image,'Orange: target returns. '+('Target-centred, radius-normalized view.' if localized else 'Sensor y/x, z/x view.'),(20,577),cv2.FONT_HERSHEY_SIMPLEX,.47,(60,80,80),1,cv2.LINE_AA)
    ok,encoded=cv2.imencode('.png',image)
    if not ok:raise ValueError('Unable to render this scan.')
    from io import BytesIO
    return send_file(BytesIO(encoded.tobytes()),mimetype='image/png')

@app.post('/api/compare')
def compare():
    payload=request.get_json(silent=True)
    ids=payload.get('runs') if isinstance(payload,dict) else None
    if not isinstance(ids,list) or len(ids)<4:raise ValueError('Select at least four completed, distinct bag runs for cross-speed timing.')
    observations=[];used=set();records=[];devices=set();source_hashes=set()
    for identifier in ids:
        out=folder(identifier)
        with lock:state=status(identifier,out)
        if state['status']!='complete':raise ValueError('Only completed runs can be compared.')
        result=summary(out)
        if result.get('kind') in ('comparison','batch'):raise ValueError('Select individual detection runs, not comparisons or folder summaries.')
        capture_key=result.get('bag_path') or 'device_1/'+result['bag']
        if capture_key in used:raise ValueError('Select only one run per bag; repeated processing is not an independent recording.')
        digest=capture_identity(result)
        if digest in source_hashes:raise ValueError('Two selected bags have identical source contents. Copies and renamed uploads are not independent recordings; select each capture only once.')
        source_hashes.add(digest)
        devices.add(result.get('device') or 'device_1')
        if len(devices)>1:raise ValueError('Compare captures from one device folder at a time; different devices need separate timing models.')
        if result['flir'].get('status')!='TRACK_RECOVERED' or result['livox'].get('status')!='RELATIVE_TRACK_RECOVERED':raise ValueError('Resolve detection quality flags before using this run for timing.')
        observation=result['timing'].get('cross_speed_phase_observation')
        if not isinstance(observation,dict):raise ValueError('This saved run has no cross-speed phase observation. Reprocess the capture before comparing it.')
        used.add(capture_key);record={'run_id':identifier,'bag':result['bag'],'source_bag_sha256':digest,**observation}
        observations.append(record);records.append(result)
    model,data=fit_multi(observations)
    identifier=new_id('comparison');out=RESULTS/identifier;out.mkdir();(out/'figures').mkdir()
    write_csv(out/'phase_observations.csv',observations)
    write_csv(out/'phase_fit.csv',[{**record,'unwrapped_phase_deg':data['phase_unwrapped_deg'][i],
                   'fitted_phase_deg':data['prediction_deg'][i],'residual_deg':data['residual_deg'][i]} for i,record in enumerate(observations)])
    save_json(out/'model.json',model);save_json(out/'request.json',{'runs':ids})
    result={'id':identifier,'kind':'comparison','multi_timing':model,'observations':observations};save_json(out/'summary.json',result)
    from timing_visualization import timing_figure
    timing_figure(model, data, out/'figures'/'cross_speed_timing.png')
    report=f'''# Cross-speed timing comparison

Status: **{model['status']}**. Candidate tau: **{model['candidate_tau_ms']:+.2f} ms**.
Student-t 95% interval: [{model['student_t_95_low_ms']:+.2f}, {model['student_t_95_high_ms']:+.2f}] ms.
Standard error: {model['standard_error_ms']:.2f} ms. Phase-fit residual STD: {model['phase_residual_std_deg']:.3f} degrees.
Distinct bags: {model['bags']}. Setup groups: {', '.join(model['groups'])}. Residual degrees of freedom: {model['degrees_of_freedom']}.

Model: `{model['sign_convention']}`. Fixed phase is fitted separately within each acquisition group. Different signed speeds within a group separate the model's phase intercept from its time-shift slope. The saved phase convention is `{model.get('phase_convention','legacy_h5_over_3')}` modulo {model.get('phase_period_deg',120):g} degrees; arbitrary per-bag template time-zero phases are not compared directly.

{model['reason']} These results are **not a calibrated physical sensor offset**, even if the statistical interval excludes zero. Camera exposure midpoint and native per-ray Livox acquisition timing require separate calibration. Group definitions must genuinely share the same sensor pose and phase convention; the copied recordings' normal/red default grouping is editable before processing. The hardware data were also used to develop the observation estimators. Independent repeated captures are required to validate systematic accuracy.

Exact observations and residuals are in `phase_observations.csv` and `phase_fit.csv`. The fitted model, uncertainty and group intercepts are in `model.json`. The figure is `figures/cross_speed_timing.png`. Selected run IDs are recorded in `request.json`.
'''
    (out/'REPORT.md').write_text(report)
    import html
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Cross-speed timing</title><style>body{max-width:1000px;margin:40px auto;font:16px system-ui}pre{white-space:pre-wrap;font:15px system-ui;line-height:1.6}img{max-width:100%}</style><pre>'+html.escape(report)+'</pre><img src="figures/cross_speed_timing.png" alt="Cross-speed timing phase fit">')
    save_json(out/'status.json',{'id':identifier,'bag':'Cross-speed timing','status':'complete','percent':100,'stage':'complete','elapsed_s':None})
    return jsonify(id=identifier,result=result)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    app.run(host='127.0.0.1',port=args.port,threaded=True,debug=False)

if __name__=='__main__':main()
