"""Independent sensor inference. No sensor accepts the other sensor's observations."""
import numpy as np
from scipy.signal import savgol_filter
from scipy.ndimage import maximum_filter1d
from algorithms.flir import photometry as photo
from algorithms.flir import periodic as fp
from algorithms.livox import return_features as returns
from algorithms.livox import periodic as lp
from common import save_json, write_csv

def geometry_anchor(polar,angles):
    n=np.arange(1,13)
    z=np.conjugate(np.fft.rfft(polar,axis=2)[:,:,1:13])/polar.shape[2]
    observed=np.mean(z*np.exp(-1j*np.radians(angles)[:,None,None]*n),axis=0)
    r=np.linspace(.30,.92,12)[:,None];phi=np.arange(360)[None,:]
    wrap=lambda a:(a+180)%360-180
    void=((r>.055/.21)&(np.abs(wrap(phi))<30))|((r>.1/.21)&(np.abs(wrap(phi+150))<12.5))
    expected=np.conjugate(np.fft.rfft(1-void.astype(float),axis=1)[:,1:13])/360
    grid=np.arange(0,360,.05)
    scores=np.real(np.sum(observed[None,:,:]*np.exp(-1j*np.radians(grid)[:,None,None]*n)*np.conjugate(expected)[None,:,:],axis=(1,2)))
    return float(grid[np.argmax(scores)])

def camera_clock(raw):
    headers=raw['headers']
    if np.all(np.isfinite(headers)) and np.all(headers>0) and np.all(np.diff(headers)>0):return headers-headers[0],'camera_header'
    if not np.all(np.diff(raw['stamps'])>0):raise ValueError('Camera recording clock is not strictly increasing.')
    return raw['stamps']-raw['stamps'][0],'bag_record_fallback'

def validation_blocks(time,block_seconds,folds,order,sensor):
    fold=np.floor(time/block_seconds).astype(int)%folds
    if len(np.unique(fold))!=folds:
        raise ValueError(f'{sensor} recording is too short for {folds}-fold validation with {block_seconds}-second blocks. Capture a longer sequence.')
    if any((fold!=k).sum()<2*order+3 for k in range(folds)):
        raise ValueError(f'{sensor} has too few training observations in a validation fold. Capture a longer sequence.')
    return fold

def flir(raw,config,out,progress,preview):
    out.mkdir(exist_ok=True);images=raw['images'];time,clock=camera_clock(raw);n=len(time)
    fold=validation_blocks(time,1,config['validation_folds'],config['camera_order'],'FLIR')
    progress('flir_calibration',0,3,'Calibrating the moving rotor ellipse')
    cal=photo.calibrate(images);f,z,polar=photo.features(images,cal)
    progress('flir_calibration',1,3,'Searching signed camera rotation rate')
    initial,coherence=photo.initial_rate(time,z)
    model=fp.learn(time,f,np.ones(n,bool),initial,config['camera_order'])
    progress('flir_calibration',3,3,'Camera appearance template calibrated',metrics={'flir_rpm':model['rpm']})
    angles=np.empty(n);sigma=np.empty(n);noise=np.empty(n);boundary=np.empty(n,bool)
    first_phase=None
    for start in range(0,n,160):
        stop=min(start+160,n)
        a,s,r,b=fp.register(time[start:stop],f[start:stop],model)
        angles[start:stop]=a;sigma[start:stop]=s;noise[start:stop]=r;boundary[start:stop]=b
        if first_phase is None:first_phase=a[0]
        index=stop-1
        preview('flir',images[index],cal,index,raw['stamps'][index],angles[index]-first_phase)
        progress('flir_detection',stop,n,'Registering grayscale camera observations',
                 detections={'sensor':'FLIR','frame':index,'angle_deg':float((angles[index]-first_phase)%360),'stamp_s':raw['stamps'][index],
                             'trace':[{'t':float(t),'angle':float((v-first_phase)%360)} for t,v in zip(time[start:stop:8],a[::8])]})
    fitted,beta=fp.line(time,angles)
    cv=np.empty(n);cvb=np.zeros(n,bool);rates=[]
    for k in range(config['validation_folds']):
        train=fold!=k
        progress('flir_validation',k,config['validation_folds']+1,f'Camera held-out validation fold {k+1}/{config["validation_folds"]}')
        c=photo.calibrate(images[train]);ff,zz,_=photo.features(images,c)
        rate,_=photo.initial_rate(time[train],zz[train]);m=fp.learn(time,ff,train,rate,config['camera_order'])
        a,_,_,b=fp.register(time[~train],ff[~train],m)
        cv[~train]=a-time[~train]*m['rpm']*6;cvb[~train]=b;rates.append(m['rpm'])
        np.savez_compressed(out/f'validation_model_{k}.npz',**m,calibration=c)
    train=time<time.max()*.6
    c=photo.calibrate(images[train]);ff,zz,_=photo.features(images,c)
    rate,_=photo.initial_rate(time[train],zz[train]);m=fp.learn(time,ff,train,rate,config['camera_order'])
    a,_,_,cb=fp.register(time[~train],ff[~train],m)
    chronological=a-time[~train]*m['rpm']*6
    np.savez_compressed(out/'chronological_model.npz',**m,calibration=c)
    progress('flir_validation',config['validation_folds']+1,config['validation_folds']+1,'Camera validation complete')
    phase=geometry_anchor(polar,angles)+np.degrees(cal[4]);absolute=angles+phase
    smooth=savgol_filter(absolute,11,2)
    summary={'frames':n,'rpm':model['rpm'],'line_rpm':beta[1]/6,'clock_source':clock,'calibration':cal,
             'geometry_anchor_deg':phase,'coherence_sum_0_to_5':coherence,'raw_residual':fp.metrics(angles-fitted),
             'heldout_residual':fp.metrics(cv),'chronological_residual':fp.metrics(chronological),
             'fold_rpm':rates,'boundary_hits':int(boundary.sum()),'heldout_boundary_hits':int(cvb.sum()),
             'status':'TRACK_RECOVERED' if not cvb.any() and fp.metrics(cv)['p95_deg']<3 else 'REVIEW',
             'absolute_accuracy':'Absolute angle accuracy is not established by repeatability statistics.'}
    rows=[{'frame':i,'bag_stamp_s':raw['stamps'][i],'header_stamp_s':raw['headers'][i],
           'angle_deg':absolute[i]%360,'angle_unwrapped_deg':absolute[i],
           'relative_angle_deg':angles[i]-angles[0],'smoothed_angle_unwrapped_deg':smooth[i],
           'batch_angle_unwrapped_deg':fitted[i]+phase,'raw_residual_deg':angles[i]-fitted[i],
           'heldout_residual_deg':cv[i],'photometric_proxy_sigma_deg':sigma[i],'photometric_residual':noise[i],
           'status':'REJECTED_BRANCH_BOUNDARY' if boundary[i] else 'registered'} for i in range(n)]
    write_csv(out/'angles.csv',rows);save_json(out/'summary.json',summary)
    np.savez_compressed(out/'model.npz',**model,calibration=cal,geometry_phase_deg=phase)
    np.savez_compressed(out/'features.npz',features=f,spatial_coefficients=z,polar=polar,time_s=time,
                        raw_phase_deg=angles,heldout_residual_deg=cv,boundary=boundary)
    return {'summary':summary,'stamps':raw['stamps'],'headers':raw['headers'],'time':time,'angle':absolute,
            'relative':angles-angles[0],'smooth':smooth,'batch':fitted+phase,'residual':angles-fitted,
            'cv':cv,'calibration':cal,'polar':polar,'features':f,'model':model,'boundary':boundary}

def harmonic_phase(time,h5,winding=3):
    # Restore the SAME empirical harmonic phase convention in each bag, rather
    # than using the unrelated time-zero phase of each learned motion template.
    from scipy.ndimage import gaussian_filter1d
    h=gaussian_filter1d(h5.real,1)+1j*gaussian_filter1d(h5.imag,1)
    xy=np.column_stack([h.real,h.imag]);xy-=np.median(xy,axis=0)
    val,vec=np.linalg.eigh(np.cov(xy.T));xy=xy@(vec@np.diag(1/np.sqrt(np.maximum(val,1e-10)))@vec.T)
    return np.degrees(np.unwrap(np.angle(xy[:,0]+1j*xy[:,1])))/winding

def livox(raw,config,out,progress,preview):
    out.mkdir(exist_ok=True);time=raw['stamps']-raw['stamps'][0];n=len(time)
    if not np.all(np.isfinite(time)) or not np.all(np.diff(time)>0):raise ValueError('Livox recording clock must be finite and strictly increasing.')
    fold=validation_blocks(time,2,config['validation_folds'],config['livox_order'],'Livox')
    geometry=raw.get('geometry');winding=1 if geometry else 3
    fs=[];hs=[];cs=[]
    for start in range(0,n,40):
        stop=min(start+40,n);lo,hi=raw['offsets'][start],raw['offsets'][stop]
        f,h,c=returns.features(raw['points'][lo:hi],raw['offsets'][start:stop+1]-lo,geometry)
        fs.append(f);hs.append(h);cs.append(c)
        progress('livox_features',stop,n,'Measuring depth, radial and angular return features')
    f=np.concatenate(fs);h5=np.concatenate(hs);counts=np.concatenate(cs)
    initial,coherence=returns.localized_rate(time,f) if geometry else returns.initial_rate(time,h5,winding)
    if np.median(counts)<100 or coherence<(.15 if geometry else .6):raise ValueError('Too few coherent rotating-surface returns. Check the Livox topic and rig geometry.')
    model=lp.learn(time,f,np.ones(n,bool),initial,config['livox_order'],search_rate=False)
    progress('livox_detection',0,n,'Livox appearance template calibrated',metrics={'livox_rpm':model['rpm']})
    angles=np.empty(n);sigma=np.empty(n);noise=np.empty(n);boundary=np.empty(n,bool);first_phase=None
    for start in range(0,n,40):
        stop=min(start+40,n);a,s,r,b=lp.register(time[start:stop],f[start:stop],model,20)
        angles[start:stop]=a;sigma[start:stop]=s;noise[start:stop]=r;boundary[start:stop]=b
        if first_phase is None:first_phase=a[0]
        i=stop-1;p=raw['points'][raw['offsets'][i]:raw['offsets'][i+1]]
        preview('livox',p,geometry,i,raw['stamps'][i],angles[i]-first_phase)
        progress('livox_detection',stop,n,'Registering independent Livox cloud observations',
                 detections={'sensor':'Livox','frame':i,'angle_deg':float((angles[i]-first_phase)%360),'stamp_s':raw['stamps'][i],
                             'trace':[{'t':float(t),'angle':float((v-first_phase)%360)} for t,v in zip(time[start:stop:2],a[::2])]})
    fitted,beta=lp.line(time,angles);window=config['livox_smoothing_frames'];smooth=savgol_filter(angles,window,2)
    cv=np.empty(n);cvs=np.empty(n);cve=np.empty(n);cvse=np.empty(n);cvb=np.zeros(n,bool);rates=[]
    for k in range(config['validation_folds']):
        test=fold==k;train=~maximum_filter1d(test.astype(int),size=window,mode='nearest').astype(bool)
        if train.sum()<2*config['livox_order']+3:raise ValueError('Too few Livox training clouds remain after purging a validation fold. Capture a longer sequence.')
        progress('livox_validation',k,config['validation_folds']+1,f'Livox purged validation fold {k+1}/{config["validation_folds"]}')
        rate,_=returns.localized_rate(time[train],f[train]) if geometry else returns.initial_rate(time[train],h5[train],winding);m=lp.learn(time,f,train,rate,config['livox_order'],search_rate=False)
        a,_,_,b=lp.register(time,f,m,20);s=savgol_filter(a,window,2)
        cv[test]=a[test];cvs[test]=s[test];cve[test]=a[test]-time[test]*m['rpm']*6;cvse[test]=s[test]-time[test]*m['rpm']*6;cvb[test]=b[test];rates.append(m['rpm'])
        np.savez_compressed(out/f'validation_model_{k}.npz',**m)
    train=time<time.max()*.6;rate,_=returns.localized_rate(time[train],f[train]) if geometry else returns.initial_rate(time[train],h5[train],winding);m=lp.learn(time,f,train,rate,config['livox_order'],search_rate=False)
    a,_,_,b=lp.register(time[~train],f[~train],m,20);chronological=a-time[~train]*m['rpm']*6
    np.savez_compressed(out/'chronological_model.npz',**m)
    progress('livox_validation',config['validation_folds']+1,config['validation_folds']+1,'Livox validation complete')
    # Position normalization improves relative angles, but must not redefine the
    # historical cross-speed zero of exact known-rig source recordings.
    timing_signature=raw.get('reference_timing_h5',h5)
    phase_winding=3 if 'reference_timing_h5' in raw else winding
    hp=harmonic_phase(time,timing_signature,phase_winding)
    difference=hp-angles;anchor=np.angle(np.mean(np.exp(1j*np.radians(difference)*phase_winding)))/phase_winding*180/np.pi
    canonical=angles+anchor
    summary={'frames':n,'rpm':model['rpm'],'line_rpm':beta[1]/6,'initial_harmonic_rpm':initial,'coherence':coherence,
             'median_near_returns':float(np.median(counts)),'raw_residual':lp.metrics(angles-fitted),'smoothed_residual':lp.metrics(smooth-fitted),
             'heldout_raw_training_motion_residual':lp.metrics(cve),'heldout_smoothed_training_motion_residual':lp.metrics(cvse),
             'chronological_residual':lp.metrics(chronological),'fold_rpm':rates,
             'boundary_hits':int(boundary.sum()),'heldout_boundary_hits':int(cvb.sum()),
             'status':'RELATIVE_TRACK_RECOVERED' if not cvb.any() and lp.metrics(cve)['p95_deg']<5 else 'REVIEW',
             'harmonic_phase_anchor_deg':anchor,'absolute_phase':'Uncalibrated physical zero; canonical harmonic phase is an empirical convention only.',
             'filter_frames':window,'filter_span_s':float(np.median(raw['stamps'][window-1:]-raw['stamps'][:1-window])),
             'future_lookahead_s':float(np.median(raw['stamps'][window//2:]-raw['stamps'][:-(window//2)])),
             'camera_used_for_estimation':False,'camera_used_for_localization':bool(raw.get('localization') and raw['localization']['method']=='camera_guided'),
             'phase_period_deg':360/phase_winding,'phase_convention':'legacy_h5_over_3' if phase_winding==3 else 'target_centred_h1_v1',
             'motion_harmonic_order':1 if geometry else 5,'reference_timing_phase_preserved':'reference_timing_h5' in raw,
             'localization':raw.get('localization')}
    rows=[{'frame':i,'bag_stamp_s':raw['stamps'][i],'header_device_stamp_s':raw['headers'][i],
           'relative_angle_deg':angles[i]-angles[0],'relative_wrapped_angle_deg':(angles[i]-angles[0])%360,
           'offline_smoothed_relative_angle_deg':smooth[i]-smooth[0],'batch_relative_angle_deg':fitted[i]-fitted[0],
           'canonical_harmonic_phase_deg':canonical[i],'heldout_phase_deg':cv[i],'heldout_smoothed_phase_deg':cvs[i],
           'near_return_count':counts[i],'noise_proxy_sigma_deg':sigma[i],
           'status':'REJECTED_BRANCH_BOUNDARY' if boundary[i] else 'relative_registered'} for i in range(n)]
    write_csv(out/'angles.csv',rows);save_json(out/'summary.json',summary)
    np.savez_compressed(out/'model.npz',**model,harmonic_anchor_deg=anchor)
    np.savez_compressed(out/'features.npz',features=f,h5=h5,counts=counts,time_s=time,phase_deg=angles,
                        canonical_phase_deg=canonical,heldout_phase_deg=cv,heldout_smoothed_phase_deg=cvs,boundary=boundary,
                        timing_harmonic_signature=timing_signature,timing_phase_winding=phase_winding,motion_harmonic_order=1 if geometry else 5)
    return {'summary':summary,'stamps':raw['stamps'],'headers':raw['headers'],'time':time,'angle':angles,
            'relative':angles-angles[0],'smooth':smooth,'batch':fitted,'residual':angles-fitted,
            'cv':cv,'cvs':cvs,'cv_error':cve,'cv_smoothed_error':cvse,'counts':counts,'h5':h5,
            'canonical':canonical,'harmonic_phase':hp,'features':f,'model':model,'boundary':boundary}
