"""Subpixel grayscale polar sampling and data-only motion initialisation."""
import cv2
import numpy as np
from scipy.optimize import minimize_scalar

def calibrate(images):
    stack = images[np.linspace(0, len(images)-1, min(120,len(images))).astype(int)].astype(float)
    variation = np.percentile(stack,95,axis=0)-np.percentile(stack,5,axis=0)
    yy,xx=np.indices(variation.shape)
    prior=(xx-images.shape[2]/2)**2+(yy-images.shape[1]/2)**2<(min(images.shape[1:])*.43)**2
    values=np.clip(variation*4,0,255).astype('u1')
    threshold,_=cv2.threshold(values[prior],0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    mask=(prior & (values>threshold)).astype('u1')*255
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    if not contours:raise ValueError('No moving rotor found. Check the camera topic, crop and illumination.')
    contour=max(contours,key=cv2.contourArea)
    if len(contour)<5:raise ValueError('Too little rotor contour evidence to calibrate the camera.')
    (cx,cy),(a,b),rotation=cv2.fitEllipse(contour)
    if not (12<(a+b)/4<min(images.shape[1:])*.45): raise ValueError('Rotor calibration outside plausible size; adjust the camera crop.')
    # Preserve ellipse angle even for nearly circular silhouettes.
    return np.array([cx,cy,a/2,b/2,np.radians(rotation)])

def features(images,calibration):
    cx,cy,a,b,rotation=calibration
    radii=np.linspace(.30,.92,12)
    phase=np.arange(360)*np.pi/180
    u=-radii[:,None]*np.cos(phase); v=-radii[:,None]*np.sin(phase)
    c,s=np.cos(rotation),np.sin(rotation)
    mapx=(cx+c*a*u-s*b*v).astype('f4'); mapy=(cy+s*a*u+c*b*v).astype('f4')
    polar=np.asarray([cv2.remap(im,mapx,mapy,cv2.INTER_LINEAR) for im in images],dtype=float)
    # Per-frame gain and offset robustness; preserve spatial detail and soft edges.
    lo=np.percentile(polar,10,axis=(1,2)); hi=np.percentile(polar,90,axis=(1,2))
    polar=(polar-lo[:,None,None])/np.maximum(hi-lo,10)[:,None,None]
    coefficients=np.fft.rfft(polar,axis=2)/360
    z=np.conjugate(coefficients[:,:,1:13])
    return np.concatenate([z.real.reshape(len(images),-1),z.imag.reshape(len(images),-1)],axis=1), z, polar

def initial_rate(time,z):
    # Score coherent rotation across multiple spatial orders, no prescribed RPM.
    orders=np.arange(1,z.shape[-1]+1)
    signal=z.mean(axis=1)
    signal=signal-signal.mean(axis=0)
    energy=np.sum(np.abs(signal)**2,axis=0)
    if len(time)<100 or not np.all(np.diff(time)>0) or np.max(energy)<1e-8:
        raise ValueError('Insufficient rotating camera evidence or non-monotonic clock')
    selected=np.argsort(energy)[-5:]
    def score(rpm):
        demod=np.exp(-1j*time[:,None]*(rpm*2*np.pi/60)*orders[selected])
        return np.sum(np.abs(np.sum(signal[:,selected]*demod,axis=0))**2 / np.maximum(energy[selected],1e-12))
    grid=np.linspace(-20,20,1601)
    scores=np.asarray([score(r) if abs(r)>.5 else 0 for r in grid])
    best=grid[np.argmax(scores)]
    opt=minimize_scalar(lambda r:-score(r),bounds=(best-.04,best+.04),method='bounded',options={'xatol':1e-8})
    return opt.x, scores.max()/len(time)
