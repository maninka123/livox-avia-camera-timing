"""Measured-ray depth/radial multichannel signatures for independent Livox tracking."""
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import minimize_scalar

def features(points,offsets,geometry=None):
    channels=[]; h5=[]; counts=[]
    if geometry:
        low,high=geometry['depth_bounds_m'];background=geometry['background_depth_m']
        bands=list(zip(np.linspace(low,high,4)[:-1],np.linspace(low,high,4)[1:]))+[(high,background+max(.5,background*.2))]
    else:
        low,high=1.2,2.7;bands=((1.2,1.7),(1.7,2.2),(2.2,2.7),(2.7,5.))
    for start,stop in zip(offsets[:-1],offsets[1:]):
        p=points[start:stop]
        radius=np.hypot(p[:,0],p[:,1]); phi=np.arctan2(p[:,1],p[:,0])
        mask=(radius>.025)&(radius<.135)&(p[:,2]>low)&(p[:,2]<bands[-1][1])
        p=p[mask];radius=radius[mask];phi=phi[mask]
        near=(p[:,2]<high)
        weight=radius[near]
        h5.append(np.sum(weight*np.exp((1j if geometry else 5j)*phi[near]))/max(weight.sum(),1e-9))
        counts.append(int(near.sum()))
        values=[]
        # Normalize by actual observed-ray count, and include background returns.
        norm=max(len(p),1)
        for band_low,band_high in bands:
            for r0 in (.045,.075,.105,.13):
                w=np.exp(-.5*((radius-r0)/.020)**2)*((p[:,2]>=band_low)&(p[:,2]<band_high))
                z=np.sum(w[:,None]*np.exp(1j*phi[:,None]*np.arange(0,11)),axis=0)/norm
                values.extend(z.real); values.extend(z[1:].imag)
        channels.append(values)
    return np.asarray(channels),np.asarray(h5),np.asarray(counts)

def initial_rate(time,h5,winding=3,minimum_observations=100):
    # H5 winds three times per physical revolution in this recorded rig.
    if len(time)<minimum_observations or not np.all(np.diff(time)>0) or np.std(h5)<1e-5:
        raise ValueError('Insufficient rotating Livox evidence or non-monotonic clock')
    signal=gaussian_filter1d(h5.real,1)+1j*gaussian_filter1d(h5.imag,1)
    xy=np.column_stack([signal.real,signal.imag]);xy-=np.median(xy,axis=0)
    ev,vec=np.linalg.eigh(np.cov(xy.T))
    xy=xy@(vec@np.diag(1/np.sqrt(np.maximum(ev,1e-10)))@vec.T)
    signal=xy[:,0]+1j*xy[:,1]
    def score(rpm):
        return abs(np.mean(signal*np.exp(-1j*winding*time*rpm*2*np.pi/60)))
    grid=np.arange(-20,20.001,.025)
    scores=np.asarray([score(rpm) if abs(rpm)>.5 else 0 for rpm in grid])
    best=grid[np.argmax(scores)]
    result=minimize_scalar(lambda r:-score(r),bounds=(best-.04,best+.04),method='bounded',options={'xatol':1e-9})
    return float(result.x),float(score(result.x)/np.mean(np.abs(signal)))

def localized_rate(time,features):
    """Use several spatial orders to avoid a distorted H1 ellipse biasing speed."""
    from algorithms.support.localization import rotation_rate
    array=np.asarray(features).reshape(len(time),16,21)
    signatures=(array[:,:12,1:7]+1j*array[:,:12,11:17]).sum(axis=1)
    return rotation_rate(time,signatures)
