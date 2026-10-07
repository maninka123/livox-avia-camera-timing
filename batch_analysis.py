"""Folder-level metrics and plots, keeping each capture as the timing replicate."""
import csv
import html
import json
from pathlib import Path
import numpy as np
from common import ROOT, save_json, write_csv, native,distinct_captures
from scan_variability import describe
from timing import fit_multi, SIGN


def timing_plot(model, data, path):
    from timing_visualization import timing_figure
    timing_figure(model, data, path)


def summarize_capture(result):
    agreement=result['timing']['agreement'];scans=result['scans']
    return {'bag':result['bag'],'bag_path':result['bag_path'],'run_id':result['id'],
            'group':result['config']['phase_group'],
            'localization_method':(result.get('localization') or {}).get('method','legacy'),
            'localization_review':(result.get('localization') or {}).get('calibration_alignment_review',''),
            'phase_convention':result['livox'].get('phase_convention','legacy_h5_over_3'),'camera_frames':result['flir']['frames'],
            'livox_clouds':result['livox']['frames'],'input_points_total':scans['input_points_total'],
            'camera_rpm':result['flir']['rpm'],'livox_rpm':result['livox']['rpm'],
            'camera_fold_rpm_std':describe(result['flir']['fold_rpm'])['std'],
            'livox_fold_rpm_std':describe(result['livox']['fold_rpm'])['std'],
            'camera_local_rpm_std':scans['flir_local_rpm']['std'],'livox_local_rpm_std':scans['livox_local_rpm']['std'],
            'flir_std_deg':result['flir']['heldout_residual']['std_deg'],
            'livox_std_deg':agreement['heldout_raw']['std_deg'],
            'livox_offline_std_deg':agreement['heldout_offline_smoothed']['std_deg'],
            'target_points_mean':scans['target_point_count']['mean'],'target_points_std':scans['target_point_count']['std'],
            'target_depth_spread_m':scans['target_depth_std_m']['median'],
            'camera_quality':result['flir']['status'],'livox_quality':result['livox']['status'],
            'single_bag_timing_status':result['timing']['single_bag_lag']['status']}


def combined_csv(results, relative_file, destination):
    rows=[]
    for result in results:
        with (ROOT/'results'/result['id']/relative_file).open() as stream:
            rows.extend({'bag':result['bag'],'bag_path':result['bag_path'],'run_id':result['id'],**row} for row in csv.DictReader(stream))
    write_csv(destination,rows)
    return rows


def figures(captures, scans, camera, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    if not captures:return
    x=np.arange(len(captures));labels=[]
    for row in captures:
        stem=Path(row['bag']).stem;parts=stem.split('_')
        labels.append(parts[-2] if len(parts)>=2 and parts[-2].isdigit() else stem)
    values=lambda key:np.array([row[key] if row[key] is not None else np.nan for row in captures],dtype=float)
    fig,axes=plt.subplots(3,1,figsize=(13,11))
    axes[0].errorbar(x-.08,values('camera_rpm'),yerr=values('camera_fold_rpm_std'),fmt='o',label='FLIR ± fold STD',color='#15766e')
    axes[0].errorbar(x+.08,values('livox_rpm'),yerr=values('livox_fold_rpm_std'),fmt='s',label='Livox ± fold STD',color='#dc7937')
    axes[0].set_ylabel('Signed fitted RPM');axes[0].axhline(0,color='#aaaaaa',lw=.6);axes[0].legend()
    for offset,key,label,color in [(-.25,'flir_std_deg','FLIR repeatability','#15766e'),(0,'livox_std_deg','Livox agreement','#dc7937'),(.25,'livox_offline_std_deg','Livox offline agreement','#526679')]:
        axes[1].bar(x+offset,values(key),width=.23,label=label,color=color)
    axes[1].set_ylabel('Held-out STD (deg)');axes[1].legend(fontsize=9)
    axes[2].plot(x,values('target_points_mean'),'o-',color='#dc7937',label='Mean target returns / scan')
    axes[2].fill_between(x,values('target_points_mean')-values('target_points_std'),values('target_points_mean')+values('target_points_std'),alpha=.17,color='#dc7937')
    axes[2].set_ylabel('Target returns: mean ± STD');axes[2].legend(fontsize=9)
    for ax in axes:ax.set_xticks(x);ax.set_xticklabels(labels,rotation=30,ha='right');ax.grid(axis='y',alpha=.2)
    axes[2].set_xlabel('Capture time from bag filename (see capture_metrics.csv for full names)')
    fig.suptitle('Folder results: independently fitted speed, angular quality and return variability')
    fig.tight_layout(rect=(0,0,1,.97));fig.savefig(output/'batch_overview.png',dpi=150);plt.close(fig)

    fig,axes=plt.subplots(len(captures),2,figsize=(14,max(4,len(captures)*2.3)),squeeze=False)
    fig2,ax2=plt.subplots(figsize=(13,6));distributions=[];matrix=[]
    for i,capture in enumerate(captures):
        rows=[row for row in scans if row['run_id']==capture['run_id']]
        cam=[row for row in camera if row['run_id']==capture['run_id']]
        parse=lambda rows,key:np.array([float(row[key]) if row.get(key) not in ('',None) else np.nan for row in rows])
        t=parse(rows,'time_s');count=parse(rows,'target_point_count');rpm=parse(rows,'local_rpm')
        axes[i,0].plot(t,count,color='#dc7937',lw=.8);axes[i,0].set_ylabel(labels[i]+'\nTarget points')
        axes[i,1].plot(t,rpm,label='Livox',color='#dc7937',lw=.9)
        axes[i,1].plot(parse(cam,'time_s'),parse(cam,'local_rpm'),label='FLIR',color='#15766e',lw=.9)
        axes[i,1].set_ylabel('Local RPM');axes[i,1].legend(fontsize=7,loc='upper right')
        for ax in axes[i]:ax.grid(alpha=.15);ax.set_xlabel('Time in capture (s)')
        distributions.append(count[np.isfinite(count)])
        residual=parse(rows,'heldout_motion_residual_deg');edges=np.linspace(t.min(),t.max()+1e-9,21)
        matrix.append([describe(residual[(t>=lo)&(t<hi)])['std'] for lo,hi in zip(edges[:-1],edges[1:])])
    fig.suptitle('Every scan in each capture: target-return count and local phase slope\nLocal RPM uses a centered 2-second window; scatter includes detection noise',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.97));fig.savefig(output/'batch_scan_traces.png',dpi=130);plt.close(fig)
    boxes=np.empty(len(distributions),dtype=object);boxes[:]=distributions
    ax2.boxplot(boxes,labels=labels,showfliers=False);ax2.set(xlabel='Capture',ylabel='Target points / Livox scan',title='Distribution of retained moving-surface returns across all scans')
    ax2.grid(axis='y',alpha=.2);fig2.tight_layout();fig2.savefig(output/'batch_return_distributions.png',dpi=150);plt.close(fig2)
    matrix=np.array([[v if v is not None else np.nan for v in row] for row in matrix])
    fig,ax=plt.subplots(figsize=(13,max(4,len(captures)*.45)))
    image=ax.imshow(matrix,aspect='auto',origin='upper',extent=(0,100,len(captures)-.5,-.5),cmap='viridis',vmin=0)
    ax.set_yticks(x);ax.set_yticklabels(labels);ax.set(xlabel='Elapsed recording fraction (%)',ylabel='Capture',title='Held-out Livox residual variability: STD in 20 time bins per capture')
    fig.colorbar(image,ax=ax,label='STD to training motion (deg)');fig.tight_layout();fig.savefig(output/'batch_variability_matrix.png',dpi=150);plt.close(fig)
    write_csv(output.parent/'variability_bins.csv',[{'bag':captures[i]['bag'],'bin':j,'start_percent':j*5,'std_deg':matrix[i,j]} for i in range(len(captures)) for j in range(20)])


def aggregate(request, results, entries, output):
    captures=[summarize_capture(result) for result in results]
    write_csv(output/'capture_metrics.csv',captures)
    write_csv(output/'processing_manifest.csv',entries)
    scan_rows=combined_csv(results,'scans/scan_metrics.csv',output/'all_scan_metrics.csv')
    camera_rows=combined_csv(results,'scans/camera_local_rpm.csv',output/'all_camera_local_rpm.csv')
    for sensor in ('flir','livox'):
        combined_csv(results,sensor+'/angles.csv',output/f'all_{sensor}_angles.csv')
    eligible=[r for r in results if r['flir']['status']!='REVIEW' and r['livox']['status']!='REVIEW']
    eligible,duplicates=distinct_captures(eligible)
    # Each distinct bag is one replicate, irrespective of cloud count.
    observations=[{'bag':r['bag'],'bag_path':r['bag_path'],'run_id':r['id'],**r['timing']['cross_speed_phase_observation']} for r in eligible]
    write_csv(output/'timing'/'phase_observations.csv',observations)
    try:
        model,data=fit_multi(observations)
    except ValueError as exc:
        model={'status':'UNRESOLVED','candidate_tau_ms':None,'physical_offset_calibrated':False,
               'bags':len(observations),'reason':str(exc),'sign_convention':SIGN}
    else:
        timing_plot(model,data,output/'figures'/'overall_timing.png')
        write_csv(output/'timing'/'phase_fit.csv',[{**o,'fitted_phase_deg':data['prediction_deg'][i],
             'unwrapped_phase_deg':data['phase_unwrapped_deg'][i],'residual_deg':data['residual_deg'][i]} for i,o in enumerate(observations)])
        np.savez_compressed(output/'timing'/'parameter_covariance.npz',parameter_covariance=data['parameter_covariance'])
    model['excluded_quality_review_bags']=[r['bag'] for r in results if r['flir']['status']=='REVIEW' or r['livox']['status']=='REVIEW']
    model['excluded_duplicate_source_bags']=[r['bag'] for r in duplicates]
    save_json(output/'timing'/'overall_offset.json',model)
    figures(captures,scan_rows,camera_rows,output/'figures')
    result={'id':request['id'],'kind':'batch','dataset':request['dataset'],'bag':request['dataset'].replace('_',' ').title(),
        'captures':captures,'entries':entries,'overall_timing':model,
        'totals':{'requested_bags':len(entries),'completed_bags':len(results),
                  'failed_bags':sum(e['status']=='failed' for e in entries),
                  'camera_frames':sum(c['camera_frames'] for c in captures),'livox_clouds':sum(c['livox_clouds'] for c in captures),
                  'input_points':sum(c['input_points_total'] for c in captures)},
        'folder_metrics':{key:describe([c[key] for c in captures]) for key in ('flir_std_deg','livox_std_deg','livox_offline_std_deg','livox_local_rpm_std','target_points_std')},
        'interpretation':'Each bag is a separate timing replicate. Local RPM variability includes phase-estimation noise; depth spread describes spatial returns. Held-out angular statistics are repeatability/agreement, not encoder accuracy. Overall time shift assumes stable phase and pose within each setup group and remains physically uncalibrated.'}
    save_json(output/'summary.json',result)
    report(request,result,output)
    return native(result)


def report(request,result,output):
    totals=result['totals'];model=result['overall_timing']
    text=f'''# Device folder processing report

Folder: `bagfiles/{request['dataset']}/`. Batch run: `{request['id']}`.
Requested bags: {totals['requested_bags']}. Completed: {totals['completed_bags']}. Failed: {totals['failed_bags']}.
Camera frames: {totals['camera_frames']:,}. Livox scans: {totals['livox_clouds']:,}. Input LiDAR points decoded: {totals['input_points']:,}.

## Per-capture results

| Bag | Scans | FLIR RPM | Livox RPM | Livox local RPM STD | FLIR STD (deg) | Livox agreement STD (deg) | Offline agreement STD (deg) | Target returns mean ± STD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''
    for c in result['captures']:
        text+=f"| `{c['bag']}` | {c['livox_clouds']} | {c['camera_rpm']:+.5f} | {c['livox_rpm']:+.5f} | {c['livox_local_rpm_std']:.5f} | {c['flir_std_deg']:.4f} | {c['livox_std_deg']:.4f} | {c['livox_offline_std_deg']:.4f} | {c['target_points_mean']:.1f} ± {c['target_points_std']:.1f} |\n"
    text+='\n## Overall timestamp analysis\n\nStatus: **'+model['status']+'**. '+model['reason']+'\n\n'
    if model['candidate_tau_ms'] is not None:
        text+=f"Candidate: **{model['candidate_tau_ms']:+.2f} ms**. Student-t 95% interval: [{model['student_t_95_low_ms']:+.2f}, {model['student_t_95_high_ms']:+.2f}] ms. Standard error: {model['standard_error_ms']:.2f} ms. Phase-fit residual STD: {model['phase_residual_std_deg']:.4f} deg. Residual degrees of freedom: {model['degrees_of_freedom']}.\n\n"
    if model.get('excluded_duplicate_source_bags'):
        text+='Identical source-bag copies excluded from timing replicates: '+', '.join(model['excluded_duplicate_source_bags'])+'. Their individual detections remain saved.\n\n'
    text+=f'''{model['sign_convention']}

This is **not a calibrated physical sensor offset**. The interval is conditional on a stable empirical phase convention and fixed sensor pose within each acquisition group; it excludes systematic scan, geometry and exposure effects. Per-bag conditional lag minima are not averaged. Every scan contributes to its own bag detection, while each distinct bag is one timing replicate. Quality-review captures are excluded from the overall fit. Insufficient bags or signed-speed variation produce an unresolved result.

## Scan variability and reproducibility

Every recorded cloud is decoded. Motion estimation uses measured target-region returns; full raw clouds remain in the selected source bag. `all_scan_metrics.csv` contains every scan's input/target counts, target depth mean/spread, centroid, harmonic magnitude, relative angles, held-out residual, boundary flag and local RPM. `all_camera_local_rpm.csv` contains local camera slopes; combined per-sensor angle CSVs are also saved.

Local RPM is an offline centered 2-second phase slope and uses up to one second of future data. RPM scatter includes angle-estimation noise and periodic-model effects. It is not an independent measurement of mechanical speed variation. Fold RPM STD describes sensitivity to held-out data, not an encoder-validated uncertainty. Spatial depth spread is not angular error. FLIR and Livox independently infer their own speed without supplied motor RPM. There is no encoder truth.

Each capture's complete intermediate arrays, model files, angle CSVs, nine figures and individual reports are in `captures/<capture run>/`. `capture_metrics.csv` summarizes each bag. `variability_bins.csv` contains the plotted within-capture bins. `timing/` saves the overall fit observations, residuals and parameter covariance. `processing_manifest.csv` includes failures and exact source paths; successful results remain available when another bag fails. A downloaded batch ZIP includes all nested capture artifacts.

## Processing issues

'''
    problems=[e for e in result['entries'] if e['status']!='complete']
    text+='\n'.join(f"- `{e['bag_path']}`: {e.get('error',e['status'])}" for e in problems) if problems else 'None.'
    (output/'REPORT.md').write_text(text+'\n')
    body='<h1>'+html.escape(result['bag'])+' folder results</h1><pre>'+html.escape(text)+'</pre>'
    for image in sorted((output/'figures').glob('*.png')):body+=f'<figure><img src="figures/{image.name}" alt="{image.stem.replace("_"," ")}"></figure>'
    body+='<h2>Individual capture reports</h2><ul>'
    for c in result['captures']:
        relative=c['run_id'].split('/captures/',1)[1]
        body+='<li><a href="captures/'+html.escape(relative,quote=True)+'/report.html">'+html.escape(c['bag'])+'</a></li>'
    body+='</ul>'
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Device folder report</title><style>body{max-width:1200px;margin:35px auto;padding:0 20px;font:16px system-ui;color:#233b3a}pre{white-space:pre-wrap;line-height:1.6;font:14px system-ui}img{max-width:100%}figure{margin:30px 0}</style>'+body)
