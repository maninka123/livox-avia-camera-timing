"""Per-cloud descriptive statistics; motion scatter is distinct from encoder error."""
import numpy as np
from common import save_json, write_csv


def describe(values):
    values=np.asarray(values,dtype=float);values=values[np.isfinite(values)]
    if not len(values):return {'n':0,'mean':None,'std':None,'median':None,'p05':None,'p95':None,'min':None,'max':None}
    return {'n':len(values),'mean':float(values.mean()),'std':float(values.std(ddof=1)) if len(values)>1 else 0.,
            'median':float(np.median(values)),'p05':float(np.percentile(values,5)),
            'p95':float(np.percentile(values,95)),'min':float(values.min()),'max':float(values.max())}


def local_rpm(time, angle, window_s=2.):
    """Local linear fit, centered in time; excludes rejected/invalid observations."""
    time=np.asarray(time,dtype=float);angle=np.asarray(angle,dtype=float)
    values=np.full(len(time),np.nan)
    for i,t in enumerate(time):
        if not np.isfinite(t):continue
        lo=np.searchsorted(time,t-window_s/2);hi=np.searchsorted(time,t+window_s/2,side='right')
        x=time[lo:hi]-t;y=angle[lo:hi];good=np.isfinite(x)&np.isfinite(y)
        if good.sum()<4 or np.ptp(x[good])<window_s*.3:continue
        x=x[good];y=y[good];x=x-x.mean()
        values[i]=np.dot(x,y-y.mean())/max(np.dot(x,x),1e-12)/6.
    return values


def analyze_scans(camera, lidar, raw, output):
    output.mkdir(exist_ok=True)
    angle=lidar['angle'].copy();angle[lidar['boundary']]=np.nan
    cangle=camera['angle'].copy();cangle[camera['boundary']]=np.nan
    lrpm=local_rpm(lidar['time'],angle);crpm=local_rpm(camera['time'],cangle)
    rows=[]
    for i,(start,stop) in enumerate(zip(raw['offsets'][:-1],raw['offsets'][1:])):
        points=raw['points'][start:stop];r=np.hypot(points[:,0],points[:,1])
        from localization import target_mask
        target=points[target_mask(points,raw.get('geometry'))]
        depth=describe(target[:,2]);radial=describe(np.hypot(target[:,0],target[:,1]))
        rows.append({'scan_index':i,'bag_stamp_s':raw['stamps'][i],'header_stamp_s':raw['headers'][i],
            'time_s':lidar['time'][i],'input_point_count':raw['total_point_counts'][i],
            'finite_point_count':raw['finite_point_counts'][i],'central_point_count':stop-start,
            'target_point_count':len(target),'target_depth_mean_m':depth['mean'],'target_depth_std_m':depth['std'],
            'target_depth_p05_m':depth['p05'],'target_depth_p95_m':depth['p95'],
            'target_u_centroid':float(target[:,0].mean()) if len(target) else None,
            'target_v_centroid':float(target[:,1].mean()) if len(target) else None,
            'target_radial_std':radial['std'],'h5_magnitude':abs(lidar['h5'][i]),
            'relative_angle_deg':lidar['relative'][i],'offline_relative_angle_deg':lidar['smooth'][i]-lidar['smooth'][0],
            'local_rpm':lrpm[i],'raw_motion_residual_deg':lidar['residual'][i],
            'heldout_motion_residual_deg':lidar['cv_error'][i],
            'rejected_branch_boundary':bool(lidar['boundary'][i])})
    write_csv(output/'scan_metrics.csv',rows)
    write_csv(output/'camera_local_rpm.csv',[{'frame_index':i,'time_s':camera['time'][i],'local_rpm':crpm[i],
               'rejected_branch_boundary':bool(camera['boundary'][i])} for i in range(len(crpm))])
    summary={'scans':len(rows),'all_recorded_clouds_processed':len(rows)==len(raw['stamps']),
             'input_points_total':int(raw['total_point_counts'].sum()),
             'angular_coordinates':'target-centred, radius-normalized' if raw.get('geometry') else 'sensor y/x, z/x',
             'local_rpm_window_s':2.,'local_rpm_uses_future_s':1.,
             'livox_local_rpm':describe(lrpm),'flir_local_rpm':describe(crpm),
             'input_point_count':describe(raw['total_point_counts']),
             'target_point_count':describe([r['target_point_count'] for r in rows]),
             'target_depth_std_m':describe([r['target_depth_std_m'] if r['target_depth_std_m'] is not None else np.nan for r in rows]),
             'explanation':'Local RPM is a centered 2-second phase slope, using up to 1 second of future data. Its scatter includes detection noise and model effects. Point-depth spread describes spatial returns, not rotor-angle error. Every recorded cloud is decoded; motion inference uses the target region, and the full cloud remains in the source bag.'}
    save_json(output/'summary.json',summary)
    return summary,rows,crpm


def plot_scans(rows, camera_time, camera_rpm, output, geometry=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    time=np.array([r['time_s'] for r in rows]);val=lambda key:np.array([r[key] if r[key] is not None else np.nan for r in rows],dtype=float)
    fig,axes=plt.subplots(3,2,figsize=(13,10))
    axes[0,0].plot(time,val('input_point_count'),label='All input points',color='#526679')
    axes[0,0].plot(time,val('central_point_count'),label='Selected region' if geometry else 'Central region',color='#aa8c53')
    axes[0,0].plot(time,val('target_point_count'),label='Rotating near surface',color='#dc7937');axes[0,0].set_ylabel('Points / cloud');axes[0,0].legend(fontsize=8)
    axes[0,1].plot(time,val('local_rpm'),label='Livox',color='#dc7937')
    axes[0,1].plot(camera_time,camera_rpm,label='FLIR',color='#15766e');axes[0,1].set_ylabel('Signed local RPM');axes[0,1].legend(fontsize=8)
    mean=val('target_depth_mean_m');spread=val('target_depth_std_m')
    axes[1,0].plot(time,mean,color='#15766e');axes[1,0].fill_between(time,mean-spread,mean+spread,alpha=.18,color='#15766e');axes[1,0].set_ylabel('Target depth mean ± spatial STD (m)')
    axes[1,1].plot(time,val('target_u_centroid'),label='Horizontal u');axes[1,1].plot(time,val('target_v_centroid'),label='Vertical v');axes[1,1].set_ylabel('Target centroid (normalized u, v)' if geometry else 'Target centroid (y/x, z/x)');axes[1,1].legend(fontsize=8)
    axes[2,0].plot(time,val('raw_motion_residual_deg'),label='Raw',alpha=.5,color='#dc7937')
    axes[2,0].plot(time,val('heldout_motion_residual_deg'),label='Held-out',color='#15766e',alpha=.7);axes[2,0].set_ylabel('Residual to fitted motion (deg)');axes[2,0].legend(fontsize=8)
    axes[2,1].plot(time,val('h5_magnitude'),color='#526679');axes[2,1].set_ylabel('Measured H1 magnitude' if geometry else 'Measured H5 magnitude')
    for ax in axes.flat:ax.set_xlabel('Time in recording (s)');ax.grid(alpha=.18)
    fig.suptitle('Every Livox scan: return variability, relative motion and phase-derived RPM\nLocal RPM uses a centered 2-second window; spatial spread is not angular error',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(output,dpi=150);plt.close(fig)
