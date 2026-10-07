"""Phase-aware time-shift analysis with explicit identifiability decisions."""
import numpy as np
from scipy import stats
from algorithms.flir.periodic import metrics, line
from common import write_csv, save_json

SIGN='theta_livox(t_bag) = phase + theta_flir(t_bag + tau); positive tau means Livox content leads FLIR on bag time.'

def periodic_mean(values,period=120):
    return float(np.angle(np.mean(np.exp(2j*np.pi*np.asarray(values)/period)))*period/(2*np.pi))

def periodic_residual(values,center=0,period=120):
    return (np.asarray(values)-center+period/2)%period-period/2

def clock_metrics(record,header,name):
    valid=np.isfinite(header)&(header>0)
    if valid.sum()<10:return {'sensor':name,'domain':'invalid','status':'Header clock unavailable'}
    t=record[valid];h=header[valid]
    same_epoch=np.median(h)>1e9 and abs(np.median(t-h))<86400
    x=h-h[0];y=t-t[0];design=np.column_stack([np.ones(len(x)),x])
    beta=np.linalg.lstsq(design,y,rcond=None)[0];residual=y-design@beta
    return {'sensor':name,'domain':'unix_epoch' if same_epoch else 'device_or_other_epoch',
            'samples':len(t),'record_minus_header_mean_ms':float(np.mean(t-h)*1000) if same_epoch else None,
            'record_minus_header_std_ms':float(np.std(t-h,ddof=1)*1000) if same_epoch else None,
            'record_minus_header_p95_ms':float(np.percentile(t-h,95)*1000) if same_epoch else None,
            'affine_rate_ppm':float((beta[1]-1)*1e6),'affine_residual_std_ms':float(np.std(residual,ddof=1)*1000),
            'mapping_header_origin_s':float(h[0]),'mapping_bag_origin_s':float(t[0]+beta[0]),'mapping_slope':float(beta[1]),
            'interpretation':'Observed recording/header difference; not exposure-to-ray synchronization.' if same_epoch else
                             'Different clock epoch. Absolute sensor offset cannot be obtained by header subtraction.'}

def lag_profile(camera_t,camera_a,lidar_t,lidar_a,noise_floor_deg,search_ms=500):
    """Jointly profile a free constant phase and time shift; test excitation."""
    camera_t,camera_a,lidar_t,lidar_a=[np.asarray(v,dtype=float) for v in (camera_t,camera_a,lidar_t,lidar_a)]
    for sensor,time,angle in (('FLIR',camera_t,camera_a),('Livox',lidar_t,lidar_a)):
        if time.ndim!=1 or angle.shape!=time.shape or len(time)<2 or not np.all(np.isfinite(time)) or not np.all(np.isfinite(angle)) or not np.all(np.diff(time)>0):
            raise ValueError(f'{sensor} timing observations need finite angles and strictly increasing timestamps.')
    if not np.isfinite(noise_floor_deg) or noise_floor_deg<0 or not np.isfinite(search_ms) or not 10<=search_ms<=2000:
        raise ValueError('Timing analysis needs a finite noise floor and a search range between 10 and 2000 ms.')
    origin=min(camera_t[0],lidar_t[0]);ct=camera_t-origin;lt=lidar_t-origin
    limit=search_ms/1000
    keep=(lt>=ct[0]+limit)&(lt<=ct[-1]-limit)
    if keep.sum()<50:raise ValueError('Insufficient overlapping sensor data for the selected timing search range.')
    time=lt[keep];angle=lidar_a[keep]
    grid=np.linspace(-limit,limit,1001)
    prediction=np.interp((time[:,None]+grid).ravel(),ct,camera_a).reshape(len(time),len(grid))
    difference=angle[:,None]-prediction
    phase=difference.mean(axis=0);residual=difference-phase
    mse=np.mean(residual**2,axis=0);best=int(np.argmin(mse));error=residual[:,best]
    correlation=[]
    for k in range(1,min(30,len(error)//4)):
        r=float(np.corrcoef(error[:-k],error[k:])[0,1])
        if not np.isfinite(r) or r<=0:break
        correlation.append(r)
    effective_n=float(np.clip(len(error)/(1+2*sum(correlation)),10,len(error)))
    threshold=mse[best]+stats.chi2.ppf(.95,1)*max(mse[best],noise_floor_deg**2)/effective_n
    accepted=mse<=threshold
    profile_low=float(grid[accepted].min()*1000);profile_high=float(grid[accepted].max()*1000)
    # Resample whole 1 s blocks, re-estimating phase for every shift in each bootstrap.
    blocks=np.floor(time-time[0]).astype(int);unique=np.unique(blocks);rng=np.random.default_rng(42);choices=[]
    sums=np.asarray([difference[blocks==b].sum(axis=0) for b in unique])
    squares=np.asarray([(difference[blocks==b]**2).sum(axis=0) for b in unique]);counts=np.asarray([(blocks==b).sum() for b in unique])
    for _ in range(300):
        sample=rng.integers(0,len(unique),len(unique));n=counts[sample].sum()
        costs=squares[sample].sum(axis=0)/n-(sums[sample].sum(axis=0)/n)**2
        choices.append(grid[np.argmin(costs)]*1000)
    low,high=np.percentile(choices,[2.5,97.5])
    camera_fit,_=line(ct,camera_a);excitation=float(np.std(camera_a-camera_fit,ddof=1))
    identifiable=(excitation>noise_floor_deg and profile_high-profile_low<search_ms and high-low<search_ms
                  and abs(grid[best])<limit*.95)
    result={'status':'NON_CONSTANT_MOTION_CANDIDATE' if identifiable else 'NOT_IDENTIFIABLE_FROM_THIS_BAG',
            'candidate_tau_ms':float(grid[best]*1000),'candidate_phase_deg':float(phase[best]),
            'profile_95_low_ms':profile_low,'profile_95_high_ms':profile_high,
            'block_bootstrap_95_low_ms':float(low),'block_bootstrap_95_high_ms':float(high),
            'search_limit_ms':search_ms,'effective_samples':effective_n,'matched_samples':len(time),
            'camera_nonconstant_motion_std_deg':excitation,'camera_noise_floor_deg':noise_floor_deg,
            'rmse_at_candidate_deg':float(np.sqrt(mse[best])),'rmse_at_zero_deg':float(np.sqrt(mse[len(grid)//2])),
            'profile_rmse_range_deg':float(np.sqrt(mse.max())-np.sqrt(mse.min())),
            'sign_convention':SIGN,'physical_offset_calibrated':False,
            'reason':'Motion beyond a constant-rate line is above the estimated camera scatter, with a localized lag profile; further independent validation is still required.' if identifiable else
                     'Constant-rate motion and an unknown sensor phase are confounded. The fitted minimum is a conditional candidate, not a measured physical offset.',
            'bootstrap_samples':300,'bootstrap_seed':42}
    return result,{'tau_ms':grid*1000,'rmse_deg':np.sqrt(mse),'phase_deg':phase,'bootstrap_tau_ms':np.asarray(choices),
                   'time_s':time,'best_residual_deg':error}

def analyze(camera,lidar,config,out):
    out.mkdir(exist_ok=True)
    cclock=clock_metrics(camera['stamps'],camera['headers'],'FLIR');lclock=clock_metrics(lidar['stamps'],lidar['headers'],'Livox')
    write_csv(out/'clock_metrics.csv',[cclock,lclock])
    valid_camera=~camera['boundary']
    camera_stamp=camera['stamps'][valid_camera];camera_angle=camera['angle'][valid_camera]
    if len(camera_stamp)<50:raise ValueError('Too few accepted camera observations for a cross-modal comparison.')
    keep=(lidar['stamps']>=camera_stamp[0])&(lidar['stamps']<=camera_stamp[-1])&~lidar['boundary']
    keep[:10]=False;keep[-10:]=False
    if keep.sum()<50:raise ValueError('Too few accepted overlapping FLIR and Livox observations for timing and phase calibration.')
    reference=np.interp(lidar['stamps'],camera_stamp,camera_angle)
    mid=np.median(lidar['stamps'][keep]);calibration=keep&(lidar['stamps']<mid)
    def aligned(a):
        delta=a-reference;offset=np.median(delta[calibration]);return delta-offset,float(offset)
    raw,offset=aligned(lidar['angle']);smooth,_=aligned(lidar['smooth']);cv,_=aligned(lidar['cv']);cvs,_=aligned(lidar['cvs'])
    agreement={'raw':metrics(raw[keep]),'offline_smoothed':metrics(smooth[keep]),
               'heldout_raw':metrics(cv[keep]),'heldout_offline_smoothed':metrics(cvs[keep]),
               'second_half_heldout_raw':metrics(cv[keep&(lidar['stamps']>=mid)]),
               'second_half_heldout_offline_smoothed':metrics(cvs[keep&(lidar['stamps']>=mid)]),
               'alignment_phase_deg':offset,'alignment_calibration_samples':int(calibration.sum()),
               'comparison_samples':int(keep.sum()),'rate_difference_rpm':float(lidar['summary']['rpm']-camera['summary']['rpm']),
               'reference':'New per-image FLIR observations; constant phase calibrated on first half.'}
    period=lidar['summary'].get('phase_period_deg',120)
    convention=lidar['summary'].get('phase_convention','legacy_h5_over_3')
    phase_delta=periodic_mean(lidar['canonical'][keep]-reference[keep],period)
    phase_error=periodic_residual(lidar['canonical'][keep]-reference[keep],phase_delta,period)
    phase_summary={'group':config['phase_group'],'omega_deg_s':camera['summary']['rpm']*6,
                   'phase_delta_deg':phase_delta,'phase_period_deg':period,'phase_convention':convention,
                   'phase_residual_std_deg':float(np.std(phase_error,ddof=1)),
                   'physical_zero_calibrated':False,'convention':'Target-centred H1, modulo 360 degrees; empirical sensor phase.' if period==360 else 'Common H5 / 3, modulo 120 degrees; empirical sensor phase.'}
    if period==120:phase_summary['phase_delta_mod120_deg']=phase_delta
    profile,data=lag_profile(camera_stamp,camera['smooth'][valid_camera],lidar['stamps'][~lidar['boundary']],
                             lidar['angle'][~lidar['boundary']],camera['summary']['heldout_residual']['std_deg'],config['timing_search_ms'])
    result={'single_bag_lag':profile,'clocks':{'flir':cclock,'livox':lclock},'agreement':agreement,'cross_speed_phase_observation':phase_summary,
            'absolute_header_offset_status':'NOT_COMPARABLE_CLOCK_EPOCHS' if lclock['domain']!=cclock['domain'] else 'HEADER_DIFFERENCE_ONLY_NOT_PHYSICAL_SYNC',
            'absolute_sensor_offset_ms':None}
    rows=[{'frame':int(i),'bag_stamp_s':lidar['stamps'][i],'camera_angle_deg':reference[i],
           'livox_phase_aligned_deg':lidar['angle'][i]-offset,'raw_difference_deg':raw[i],
           'heldout_difference_deg':cv[i],'heldout_smoothed_difference_deg':cvs[i],
           'included':bool(keep[i])} for i in range(len(lidar['stamps']))]
    write_csv(out/'paired_detections.csv',rows)
    write_csv(out/'lag_profile.csv',[{'tau_ms':t,'rmse_deg':r,'fitted_phase_deg':p} for t,r,p in zip(data['tau_ms'],data['rmse_deg'],data['phase_deg'])])
    write_csv(out/'bootstrap_lags.csv',[{'replicate':i,'conditional_tau_ms':value} for i,value in enumerate(data['bootstrap_tau_ms'])])
    save_json(out/'summary.json',result)
    return result,data,{'keep':keep,'reference':reference,'raw':raw,'cv':cv,'cvs':cvs,'offset':offset}

def fit_multi(observations):
    if not observations or any(not isinstance(o.get('group'),str) or not o['group'].strip() for o in observations):
        raise ValueError('Every timing observation needs a shared setup group.')
    conventions={o.get('phase_convention','legacy_h5_over_3') for o in observations}
    periods={o.get('phase_period_deg',120) for o in observations}
    if len(conventions)!=1 or len(periods)!=1:
        raise ValueError('Different localization/phase conventions cannot share a timing fit. Compare like conventions, or reprocess every bag with --localization lidar_only to start a target-centred analysis. Old reference results are preserved.')
    period=periods.pop()
    if period not in (120,360):raise ValueError('Unsupported empirical phase period.')
    groups=sorted(set(o['group'] for o in observations));n=len(observations);g=len(groups)
    if n<g+3:raise ValueError('Select more distinct bags: each setup needs repeated speeds, and the model needs at least two residual degrees of freedom.')
    try:
        omega=np.asarray([o['omega_deg_s'] for o in observations],dtype=float);phase=np.asarray([o['phase_delta_deg'] if 'phase_delta_deg' in o else o['phase_delta_mod120_deg'] for o in observations],dtype=float)
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('Cross-speed timing requires numeric rotation rates and phase observations.') from exc
    if omega.shape!=(n,) or phase.shape!=(n,):raise ValueError('Every timing observation needs a scalar rate and phase.')
    if not np.all(np.isfinite(omega)) or not np.all(np.isfinite(phase)):
        raise ValueError('Cross-speed timing requires finite rotation rates and phase observations.')
    group_index=np.asarray([groups.index(o['group']) for o in observations])
    design=np.zeros((n,g+1));design[np.arange(n),group_index]=1;design[:,-1]=omega
    if np.linalg.matrix_rank(design)<g+1:raise ValueError('Time delay is not identifiable: vary signed speed within a shared setup group.')
    search=np.linspace(-1,1,4001);costs=[]
    for tau in search:
        beta=np.asarray([periodic_mean(phase[group_index==i]-omega[group_index==i]*tau,period) for i in range(g)])
        residual=periodic_residual(phase-omega*tau,beta[group_index],period);cost=np.sum(residual**2)
        costs.append(cost)
    costs=np.asarray(costs);indices=np.flatnonzero((costs<=np.r_[np.inf,costs[:-1]])&(costs<=np.r_[costs[1:],np.inf]))
    candidates=[];dof=n-g-1
    # Refine every circular branch. A coarse-grid winner alone can hide another
    # equally good phase wrap (for example only +15/-15 RPM observations).
    for index in indices:
        initial=search[index]
        beta=np.asarray([periodic_mean(phase[group_index==i]-omega[group_index==i]*initial,period) for i in range(g)])
        predicted=beta[group_index]+omega*initial
        unwrapped=phase+period*np.round((predicted-phase)/period)
        coefficients=np.linalg.lstsq(design,unwrapped,rcond=None)[0];residual=unwrapped-design@coefficients
        if not any(abs(coefficients[-1]-candidate[1][-1])<1e-6 for candidate in candidates):
            candidates.append((float(np.sum(residual**2)),coefficients,residual,unwrapped))
    candidates.sort(key=lambda c:c[0]);inside=[c for c in candidates if abs(c[1][-1])<1]
    best_cost=candidates[0][0]
    if not inside or inside[0][0]>best_cost+max(1e-10,stats.chi2.ppf(.95,1)*best_cost/dof):
        raise ValueError('The cross-speed timing minimum reaches or exceeds the supported ±1000 ms search. Offset remains unresolved.')
    cost,coefficients,residual,unwrapped=inside[0]
    threshold=cost+max(1e-10,stats.chi2.ppf(.95,1)*cost/dof)
    if any(candidate[0]<=threshold and abs(candidate[1][-1]-coefficients[-1])>.005 for candidate in inside[1:]):
        raise ValueError('Multiple phase-wrap branches fit plausible offsets. Add more distinct signed speeds within the same setup; overall offset remains unresolved.')
    variance=np.sum(residual**2)/dof;covariance=variance*np.linalg.inv(design.T@design);se=np.sqrt(covariance[-1,-1])
    critical=stats.t.ppf(.975,dof);tau=coefficients[-1];low,high=(tau-critical*se)*1000,(tau+critical*se)*1000
    result={'status':'LOW_CONFIDENCE_CANDIDATE' if low<=0<=high or np.std(residual,ddof=g+1)>5 else 'PHASE_MODEL_CANDIDATE',
            'candidate_tau_ms':tau*1000,'standard_error_ms':se*1000,'student_t_95_low_ms':low,'student_t_95_high_ms':high,
            'phase_residual_std_deg':float(np.std(residual,ddof=g+1)),'degrees_of_freedom':dof,'bags':n,'groups':groups,
            'group_phase_intercepts_deg':{name:float(coefficients[i]) for i,name in enumerate(groups)},
            'search_limit_ms':1000,'periodic_branches_checked':len(candidates),'phase_period_deg':period,'phase_convention':next(iter(conventions)),
            'sign_convention':SIGN,'physical_offset_calibrated':False,
            'reason':'Cross-speed separation assumes a stable empirical harmonic phase and fixed sensor phase within each setup. Pose, localization, calibration and scan-phase changes can bias this candidate.'}
    return result,{'omega_deg_s':omega,'phase_unwrapped_deg':unwrapped,'prediction_deg':design@coefficients,
                   'residual_deg':residual,'group_index':group_index,'parameter_covariance':covariance}
