#!/usr/bin/env python3
"""Isolated processing worker; one selected bag creates one immutable run folder."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
import hashlib
import json
import signal
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from common import ROOT, save_json, write_csv, bag_path, native,sha256_file
from bag_io import extract
from sensors import flir,livox
from timing import analyze
from visuals import preview_image,diagnostics
from scan_variability import analyze_scans,plot_scans
from job_registry import remember_current

STAGES={'localization':(0,7),'extract':(7,18),'flir_calibration':(18,22),'flir_detection':(22,40),'flir_validation':(40,55),
        'livox_features':(55,60),'livox_detection':(60,74),'livox_validation':(74,87),
        'scan_variability':(87,89),'timing':(89,94),'export':(94,99)}

class Cancelled(Exception):pass

class Job:
    def __init__(self,request):
        self.request=request;self.out=ROOT/'results'/request['id'];self.out.mkdir(exist_ok=True)
        self.started=time.monotonic();self.state={'id':request['id'],'bag':request['bag'],'status':'running','percent':0,
            'pid':os.getpid(),'stage':'starting','message':'Starting isolated Python worker','processed':0,'total':0,'remaining':0,
            'elapsed_s':0,'metrics':{},'previews':{},'detections':{},'trace':{'FLIR':[],'Livox':[]}}
        signal.signal(signal.SIGTERM,self.cancel)
        remember_current(self.out)
        self.code_hashes={str(file.relative_to(ROOT)):hashlib.sha256(file.read_bytes()).hexdigest() for file in ROOT.rglob('*.py') if not any(part in ('tests','verification','.venv','.git') for part in file.parts)}
        self.publish()
    def cancel(self,*args):raise Cancelled('Processing cancelled. Partial artifacts are preserved.')
    def publish(self):
        self.state['elapsed_s']=round(time.monotonic()-self.started,2)
        self.state['updated_at']=datetime.now(timezone.utc).isoformat()
        save_json(self.out/'status.json',self.state)
    def progress(self,stage,processed,total,message,**extras):
        lower,upper=STAGES[stage];percent=lower+(upper-lower)*processed/max(total,1)
        self.state.update(stage=stage,processed=int(processed),total=int(total),remaining=max(0,int(total-processed)),
                          message=message,percent=max(self.state['percent'],round(percent,1)))
        if 'metrics' in extras:self.state['metrics'].update(native(extras['metrics']))
        if 'counts' in extras:self.state['counts']=extras['counts']
        if 'detections' in extras:
            detection=extras['detections'];sensor=detection['sensor'];self.state['detections'][sensor]={k:v for k,v in detection.items() if k!='trace'}
            self.state['trace'][sensor]=(self.state['trace'][sensor]+detection.get('trace',[]))[-500:]
        self.publish()
        with (self.out/'progress.jsonl').open('a') as stream:stream.write(json.dumps(native({k:v for k,v in self.state.items() if k not in ('trace','previews')}))+'\n')
    def preview(self,sensor,data,cal,frame,stamp,angle):
        file=self.out/'live'/f'{sensor}.png';preview_image(sensor,data,cal,frame,stamp,angle,file)
        self.state['previews'][sensor]={'path':str(file.relative_to(self.out)),'frame':frame,'bag_stamp_s':float(stamp),'relative_angle_deg':float(angle%360) if angle is not None else None}
        self.publish()

def report(result,out):
    c=result['flir'];l=result['livox'];t=result['timing'];lag=t['single_bag_lag'];a=t['agreement'];clock=t['clocks']
    text=f'''# Livox / FLIR processing report

Bag: `{result['bag']}`. Selected camera topic: `{result['config']['camera_topic']}`. Selected Livox topic: `{result['config']['livox_topic']}`.
Run ID: `{result['id']}`. Setup group: `{result['config']['phase_group']}`.

## Detection results

| Quantity | FLIR | Livox |
|---|---:|---:|
| Recorded observations | {c['frames']} | {l['frames']} |
| Independently estimated signed RPM | {c['rpm']:+.6f} | {l['rpm']:+.6f} |
| Held-out residual STD to training motion, degrees | {c['heldout_residual']['std_deg']:.4f} | {l['heldout_raw_training_motion_residual']['std_deg']:.4f} |
| Branch boundary detections rejected | {c['boundary_hits']} | {l['boundary_hits']} |
| Held-out branch boundary detections | {c['heldout_boundary_hits']} | {l['heldout_boundary_hits']} |

Livox agreement with new FLIR observations, after one constant phase calibration on the first half of common recording time:

| Metric | Held-out raw clouds | Held-out offline filtered clouds |
|---|---:|---:|
| STD, degrees | {a['heldout_raw']['std_deg']:.4f} | {a['heldout_offline_smoothed']['std_deg']:.4f} |
| MAE, degrees | {a['heldout_raw']['mae_deg']:.4f} | {a['heldout_offline_smoothed']['mae_deg']:.4f} |
| RMSE, degrees | {a['heldout_raw']['rmse_deg']:.4f} | {a['heldout_offline_smoothed']['rmse_deg']:.4f} |
| P95 absolute disagreement, degrees | {a['heldout_raw']['p95_deg']:.4f} | {a['heldout_offline_smoothed']['p95_deg']:.4f} |

The Livox {l['filter_frames']}-cloud smoother spans {l['filter_span_s']:.3f} s and uses approximately {l['future_lookahead_s']:.3f} s of future data. Raw, offline-filtered and batch-trajectory angles are separately exported. No encoder reference exists; these statistics describe repeatability and cross-modal agreement, not absolute angle accuracy. Camera physical zero is only approximately geometry anchored; Livox physical zero remains uncalibrated.

## Every-scan variability

All {result['scans']['scans']} recorded Livox clouds were decoded, containing {result['scans']['input_points_total']:,} input points. Target-return count: mean {result['scans']['target_point_count']['mean']:.1f}, STD {result['scans']['target_point_count']['std']:.1f} per scan. Livox local phase-derived RPM STD: {result['scans']['livox_local_rpm']['std']:.5f}. FLIR local phase-derived RPM STD: {result['scans']['flir_local_rpm']['std']:.5f}.

`scans/scan_metrics.csv` contains every scan's original/central/target point counts, depth mean and spatial spread, centroid, relative angles, held-out motion residuals, quality flags and local RPM. Local RPM is a centered 2-second phase slope using up to one second of future data; its variability includes estimation noise and periodic-model effects. It is not an independent measurement of mechanical speed fluctuation. Spatial point-depth spread is not angular error. Full raw clouds remain in the source bag; motion inference uses measured returns in the rotating target region.

## Timestamp analysis

**Status: {lag['status']}**. {lag['reason']}

The conditional profile minimum is {lag['candidate_tau_ms']:+.1f} ms. The phase-profile 95% range is [{lag['profile_95_low_ms']:+.1f}, {lag['profile_95_high_ms']:+.1f}] ms; the 1 s block-bootstrap range is [{lag['block_bootstrap_95_low_ms']:+.1f}, {lag['block_bootstrap_95_high_ms']:+.1f}] ms. These intervals are conditional on the fitted observation model; they do not remove systematic scan/exposure/phase uncertainty.

The model is `{lag['sign_convention']}`. A free constant phase is fitted for every candidate time shift. The apparent time-shift minimum must **not** be reported as the actual sensor offset when status is NOT_IDENTIFIABLE_FROM_THIS_BAG. The app displays physical offset as unresolved in that case.

Camera nonconstant-motion scatter is {lag['camera_nonconstant_motion_std_deg']:.4f}°, versus estimated camera observation scatter {lag['camera_noise_floor_deg']:.4f}°. Effective samples: {lag['effective_samples']:.1f}. RMSE at zero time shift: {lag['rmse_at_zero_deg']:.4f}°; RMSE at the conditional minimum: {lag['rmse_at_candidate_deg']:.4f}°.

FLIR header-clock domain: `{clock['flir']['domain']}`. Livox header-clock domain: `{clock['livox']['domain']}`. Clock/header differences and affine mappings are in `timing/clock_metrics.csv`. Device uptime cannot be subtracted from Unix time to obtain a physical offset. The affine mapping residual is recording-clock behavior, not exposure-to-ray delay.

Cross-speed timing is available after processing multiple distinct bags. New-scene target-centred runs use the empirical H1 convention modulo 360°. Exact SHA256-verified known-rig inputs preserve their original H5/3 convention modulo 120° from the original sensor-coordinate rays, independently of target-centred angle tracking. Different conventions cannot be mixed; independently learned template time-zero phases are not compared directly. A stable phase within each setup group remains an assumption. Different signed speeds within shared groups are required; the comparison reports confidence bounds and setup-dependent systematic risk. The previous −66.7 ms candidate is not reused or assumed.

## Algorithms and validation

FLIR: grayscale subpixel polar sampling, 12 radial rings, 12 spatial orders, 24-component appearance representation, 32-order periodic template, and continuous per-image phase registration. Camera-header time is used when valid; bag time is the fallback. The camera uses its own data only.

Livox: real measured returns from the automatically localized region (or explicitly selected reference fixed region), four depth bands, four radial weight windows, angular harmonics 0–10 (336 features), 48-component representation, 12-order periodic template, regularized correlated-noise precision and generalized-least-squares rate refinement. Directions for missing returns are never invented. The Livox angle estimator accepts no camera angle or RPM observations; optional camera geometry guides localization only.

The estimators infer RPM from data; commanded 5/10/15 RPM values are not supplied. Estimated RPM calibrates the periodic appearance model and initializes a ±40° camera / ±20° Livox phase search. Observations determine the registration within that branch. These offline models assume repeated, approximately constant-speed motion in a fixed scene and are not validated for abrupt reversals.

Five-fold held-out validation and a chronological first-60%/last-40% test are saved. Automatic LiDAR localization uses discovery samples across the whole recording; these angle metrics are conditional on that shared ROI, not a fully held-out test of localization. Camera ellipse calibration and template fitting use training images only. Livox holds out 2 s blocks and purges the smoothing half-window around test observations. Parameters were developed on these hardware recordings; this is internal validation, not a benchmark on unseen rigs.

## Saved artifacts

- `metadata.json`, `request.json`, `summary.json`, `metrics.csv`: acquisition, settings, provenance and final metrics.
- `flir/angles.csv`, `livox/angles.csv`: all observations with bag and header timestamps, quality flags and separate output types.
- `flir/model.npz`, `livox/model.npz`, `validation_model_*.npz`: final and held-out appearance models.
- `flir/features.npz`, `livox/features.npz`: all measured feature/signature intermediates.
- `intermediates/camera_extracted.npz`, `livox_extracted.npz`: every extracted crop and measured selected-region ray used by the algorithms. Full source observations remain in `bagfiles/{result['bag_path']}`.
- `scans/scan_metrics.csv`, `camera_local_rpm.csv`, `summary.json`: every Livox scan's statistics, independent local RPM traces and variability summaries.
- `intermediates/*detection*`: selected annotated crops, measured cloud arrays and masks. Full camera example images are also saved.
- `timing/paired_detections.csv`, `lag_profile.csv`, `bootstrap_lags.csv`, `summary.json`: all timing calculations and diagnostics.
- `timing/error_covariance_deg2.csv`, `error_correlation.csv`: residual matrices, not misleading correlations of angular ramps.
- `figures/*.png`: detection stages, angle traces, residual distributions, clock plots, lag profile, bootstrap distribution and error matrix.
- `live/*.png`, `progress.jsonl`, `status.json`, `worker.log`: processing previews and execution trace.

Every run has its own folder; reprocessing creates a fresh run and preserves earlier results. Original captures and pre-existing algorithms are untouched.
'''
    localization=result.get('localization')
    if localization:
        attempts='\n'.join('- '+a['method']+': '+a['status']+' — '+a['reason'] for a in localization['attempts'])
        coordinates='target-centred and radius-normalized' if localization.get('geometry') else 'original sensor y/x, z/x for the verified reference-rig fallback'
        text+='\n## Automatic target localization\n\nSelected method: **'+localization['method']+'**. Geometry: `'+json.dumps(native(localization['geometry']))+'`.\n\n'+attempts+'\n\n'+localization['note']+'\n\n'+localization.get('calibration_alignment_review','')+'\n\nThe camera supplies a spatial prior only; LiDAR angle and RPM remain independently inferred. `localization/` saves sampled full-scene rays, depth maps, decision history, calibration snapshot and figure. Original metre depth is preserved; exported angular coordinates are '+coordinates+'.\n'
    (out/'REPORT.md').write_text(text)
    import html
    # Standalone shareable report with local images and a readable plain-text narrative.
    body='<h1>Livox / FLIR processing report</h1><pre>'+html.escape(text)+'</pre>'
    for name in ('overview','flir_detection_stages','livox_detection_stages','scan_variability','timing_profile','clock_diagnostics','error_matrix'):
        body+=f'<figure><img src="figures/{name}.png" alt="{name.replace("_"," ")}"></figure>'
    if localization:body+='<figure><img src="localization/target_localization.png" alt="Automatic target localization"></figure>'
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Livox / FLIR report</title><style>body{max-width:1100px;margin:40px auto;padding:0 24px;font:16px system-ui;color:#233b3a}pre{white-space:pre-wrap;line-height:1.6;font:14px system-ui}img{max-width:100%}figure{margin:32px 0}</style>'+body)

def run(request):
    job=Job(request);out=job.out
    try:
        config=request['config'];path=bag_path(request['bag']);source_stat=path.stat()
        job.progress('localization',0,1,'Checking source recording identity before target localization')
        source_hash=sha256_file(path)
        from localization import discover
        localization=discover(path,config,out,job.progress)
        if localization:
            job.state['previews']['localization']={'path':'localization/target_localization.png','frame':0,'bag_stamp_s':None,'relative_angle_deg':None,'method':localization['method'],'attempts':localization['attempts']}
            job.publish()
        cr,lr,meta=extract(path,config,out,job.progress,job.preview,localization);save_json(out/'metadata.json',meta)
        c=flir(cr,config,out/'flir',job.progress,job.preview)
        l=livox(lr,config,out/'livox',job.progress,job.preview)
        job.progress('scan_variability',0,1,'Calculating every cloud’s point statistics and local RPM variability')
        scans,scan_rows,camera_rpm=analyze_scans(c,l,lr,out/'scans')
        job.progress('scan_variability',1,1,'All recorded Livox clouds have scan statistics and RPM estimates')
        job.progress('timing',0,2,'Profiling time shift with a separate angular phase; checking sensor clocks')
        t,p,paired=analyze(c,l,config,out/'timing')
        job.progress('timing',2,2,'Timing confidence and cross-modal agreement calculated')
        diagnostics(c,l,cr,lr,t,p,paired,out,job.progress)
        plot_scans(scan_rows,c['time'],camera_rpm,out/'figures'/'scan_variability.png',lr.get('geometry'))
        current_stat=path.stat()
        if (current_stat.st_size,current_stat.st_mtime_ns,current_stat.st_ino)!=(source_stat.st_size,source_stat.st_mtime_ns,source_stat.st_ino):
            raise ValueError('The source bag changed during processing. Partial files are preserved; retry with a stable recording.')
        result={'id':request['id'],'bag':path.name,'bag_path':str(path.relative_to(ROOT/'bagfiles')),
                'device':path.parent.name if path.parent!=ROOT/'bagfiles' else None,'parent_batch':request.get('parent_batch'),
                'config':config,'metadata':meta,'flir':c['summary'],'livox':l['summary'],'scans':scans,
                'timing':t,'localization':localization,'provenance':{'bag_size':source_stat.st_size,'bag_mtime_ns':source_stat.st_mtime_ns,'bag_sha256':source_hash,
                                      'algorithm_sha256':job.code_hashes,'python':sys.version,'only_selected_topics_processed':True},
                'elapsed_s':time.monotonic()-job.started}
        save_json(out/'summary.json',result);report(result,out)
        rows=[{'sensor':'FLIR','metric':key,'value':value,'units':'degrees' if key.endswith('_deg') else 'count'} for key,value in c['summary']['heldout_residual'].items()]
        rows+=[{'sensor':'Livox vs FLIR heldout raw','metric':key,'value':value,'units':'degrees' if key.endswith('_deg') else 'count'} for key,value in t['agreement']['heldout_raw'].items()]
        rows+=[{'sensor':'Livox vs FLIR heldout offline','metric':key,'value':value,'units':'degrees' if key.endswith('_deg') else 'count'} for key,value in t['agreement']['heldout_offline_smoothed'].items()]
        write_csv(out/'metrics.csv',rows)
        files=[{'path':str(file.relative_to(out)),'size_bytes':file.stat().st_size} for file in sorted(out.rglob('*')) if file.is_file()]
        save_json(out/'artifacts.json',files)
        job.state.update(status='complete',percent=100,stage='complete',processed=1,total=1,remaining=0,message='Detection, validation, timing and all saved reports are complete.',
                         metrics={'flir_rpm':c['summary']['rpm'],'livox_rpm':l['summary']['rpm'],
                                  'flir_std_deg':c['summary']['heldout_residual']['std_deg'],
                                  'livox_std_deg':t['agreement']['heldout_raw']['std_deg'],
                                  'livox_filtered_std_deg':t['agreement']['heldout_offline_smoothed']['std_deg'],
                                  'timing_status':t['single_bag_lag']['status']})
        job.publish();return result
    except BaseException as exc:
        cancelled=isinstance(exc,Cancelled)
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        job.state.update(status='cancelled' if cancelled else 'failed',stage='cancelled' if cancelled else 'failed',message=str(exc))
        job.publish();(out/'error.txt').write_text(traceback.format_exc())
        if not cancelled:raise
        return None

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('request_file');args=parser.parse_args()
    run(json.loads(Path(args.request_file).read_text()))
