"""Periodic observation manifold with strictly held-out-template registration.

Neither angle references nor another sensor are accepted by these functions.
Per-frame registration has no penalty toward a constant-speed trajectory.
The trajectory initializes the branch; boundary hits are explicitly rejected.
"""
import numpy as np
from scipy.optimize import minimize_scalar

def basis(phase, order=10, derivative=0):
    k=np.arange(1,order+1) if np.isscalar(order) else np.asarray(order)
    arg=np.asarray(phase)[:,None]*k
    if derivative==0:
        return np.column_stack([np.ones(len(arg)),np.cos(arg),np.sin(arg)])
    if derivative==1:
        return np.column_stack([np.zeros(len(arg)),-np.sin(arg)*k,np.cos(arg)*k])
    return np.column_stack([np.zeros(len(arg)),-np.cos(arg)*k*k,-np.sin(arg)*k*k])

def learn(time, features, train, initial_rpm, order=10, search_rate=True):
    train=np.asarray(train,dtype=bool)
    mean=features[train].mean(axis=0)
    centered=features-mean
    _, singular, vt=np.linalg.svd(centered[train],full_matrices=False)
    rank=min(24, len(singular))
    # Retain channel energy. Whitening low-variance channels magnifies noise.
    projection=vt[:rank].T
    x=centered@projection
    def fit(rpm):
        b=basis(time*(rpm*2*np.pi/60),order)
        gram=b[train].T@b[train]+np.eye(b.shape[1])*.02
        beta=np.linalg.solve(gram,b[train].T@x[train])
        residual=x[train]-b[train]@beta
        return np.mean(residual**2),beta
    if search_rate:
        fit_result=minimize_scalar(lambda rpm:fit(rpm)[0],bounds=(initial_rpm-.12,initial_rpm+.12),
                                  method='bounded',options={'xatol':1e-8})
        rpm=float(fit_result.x)
    else:
        rpm=float(initial_rpm)
    _,beta=fit(rpm)
    return {'rpm':rpm,'beta':beta,'mean':mean,'projection':projection,'order':order}

def register(time,features,model,halfwidth_deg=40):
    x=(features-model['mean'])@model['projection']
    phase=time*model['rpm']*2*np.pi/60
    offsets=np.radians(np.arange(-halfwidth_deg,halfwidth_deg+.01,.5))
    cost=np.empty((len(time),len(offsets)))
    for j,offset in enumerate(offsets):
        prediction=basis(phase+offset,model['order'])@model['beta']
        cost[:,j]=np.sum((x-prediction)**2,axis=1)
    index=np.argmin(cost,axis=1)
    phase=phase+offsets[index]
    branch_center=time*model['rpm']*2*np.pi/60
    for _ in range(6):
        prediction=basis(phase,model['order'])@model['beta']
        first=basis(phase,model['order'],1)@model['beta']
        second=basis(phase,model['order'],2)@model['beta']
        residual=prediction-x
        gradient=np.sum(residual*first,axis=1)
        curvature=np.sum(first**2+residual*second,axis=1)
        step=gradient/np.maximum(curvature,1e-8)
        phase=phase-np.clip(step,-np.radians(.5),np.radians(.5))
        phase=np.clip(phase,branch_center-np.radians(halfwidth_deg),branch_center+np.radians(halfwidth_deg))
    residual=x-basis(phase,model['order'])@model['beta']
    norm=np.sqrt(np.mean(residual**2,axis=1))
    derivative=basis(phase,model['order'],1)@model['beta']
    sigma=np.degrees(norm/np.maximum(np.linalg.norm(derivative,axis=1),1e-8))
    boundary=np.abs(phase-branch_center)>np.radians(halfwidth_deg-1)
    return np.degrees(phase), sigma, norm, boundary

def line(time,angle):
    design=np.column_stack([np.ones(len(time)),time])
    weights=np.ones(len(time))
    for _ in range(12):
        beta=np.linalg.lstsq(design*np.sqrt(weights[:,None]),angle*np.sqrt(weights),rcond=None)[0]
        residual=angle-design@beta
        scale=max(.05,1.4826*np.median(np.abs(residual-np.median(residual))))
        weights=np.minimum(1.,1.5*scale/np.maximum(np.abs(residual),1e-9))
    return design@beta,beta

def metrics(error):
    error=np.asarray(error); error=error[np.isfinite(error)]
    return {'n':len(error),'mae_deg':float(np.mean(np.abs(error))),
            'std_deg':float(np.std(error,ddof=1)), 'rmse_deg':float(np.sqrt(np.mean(error**2))),
            'p95_deg':float(np.percentile(np.abs(error),95)), 'bias_deg':float(np.mean(error))}
