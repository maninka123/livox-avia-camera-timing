"""Live measured-data previews and saved scientific diagnostics."""
from pathlib import Path
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS={'flir':'#15766e','livox':'#dc7937'}

def preview_image(sensor,data,cal,frame,stamp,angle,path):
    if sensor=='flir':
        crop=cv2.cvtColor(data,cv2.COLOR_GRAY2BGR);scale=min(4,460/data.shape[1])
        canvas=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
        if cal is not None:
            cx,cy,a,b,r=cal
            cv2.ellipse(canvas,(round(cx*scale),round(cy*scale)),(round(a*scale),round(b*scale)),np.degrees(r),0,360,(140,235,120),2)
    else:
        canvas=np.full((430,460,3),245,np.uint8)
        u,v,x=data[:,0],data[:,1],data[:,2]
        xx=np.clip(((u+.20)/.40*430+15).astype(int),0,459);yy=np.clip(((.20-v)/.40*400+15).astype(int),0,429)
        lo,hi=cal['depth_bounds_m'] if cal else (1.2,2.7)
        near=(x>=lo)&(x<hi);annulus=(np.hypot(u,v)>.025)&(np.hypot(u,v)<.135)
        for mask,color in ((~near,(199,205,211)),(near,(55,155,223)),(near&annulus,(65,160,32))):
            canvas[yy[mask],xx[mask]]=color
        cv2.circle(canvas,(230,215),round(.135/.40*430),(50,60,70),1)
        cv2.putText(canvas,'Measured rays / green = retained near annulus',(12,413),cv2.FONT_HERSHEY_SIMPLEX,.40,(50,60,70),1)
    footer=np.full((72,canvas.shape[1],3),(35,48,53),np.uint8)
    message=f'{sensor.upper()}  frame {frame}  |  '+('extracting' if angle is None else f'relative angle {angle%360:.2f} deg')
    cv2.putText(footer,message,(10,25),cv2.FONT_HERSHEY_SIMPLEX,.43,(240,248,245),1)
    cv2.putText(footer,f'bag time {stamp:.6f} s',(10,49),cv2.FONT_HERSHEY_SIMPLEX,.41,(188,208,205),1)
    image=np.vstack([canvas,footer]);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.stem+'.tmp.png');cv2.imwrite(str(temporary),image);temporary.replace(path)

def save(fig,path):
    fig.tight_layout();fig.savefig(path,dpi=160,bbox_inches='tight');plt.close(fig)

def diagnostics(camera,lidar,cr,lr,timing,profile,paired,out,progress):
    figures=out/'figures';figures.mkdir(exist_ok=True)
    origin=min(camera['stamps'][0],lidar['stamps'][0]);ct=camera['stamps']-origin;lt=lidar['stamps']-origin
    progress('export',0,8,'Saving angle and quality diagnostics')
    fig,axes=plt.subplots(3,1,figsize=(12,10))
    axes[0].scatter(ct,camera['angle']%360,s=3,color=COLORS['flir'],label='FLIR observations')
    axes[0].scatter(lt,(lidar['angle']-paired['offset'])%360,s=4,color=COLORS['livox'],label='Livox, constant phase aligned')
    axes[0].set(ylabel='Wrapped angle (deg)',title='Common bag-record time; phase alignment is not a calibrated time correction');axes[0].legend()
    axes[1].plot(ct,camera['cv'],'.',ms=2,color=COLORS['flir']);axes[1].set(ylabel='FLIR held-out residual (deg)')
    keep=paired['keep'];axes[2].plot(lt[keep],paired['cv'][keep],'.',ms=2,color=COLORS['livox'],label='Held-out cloud')
    axes[2].plot(lt[keep],paired['cvs'][keep],color=COLORS['flir'],lw=1,label='Held-out offline smoother')
    axes[2].set(xlabel='Elapsed bag time (s)',ylabel='FLIR disagreement (deg)');axes[2].legend();save(fig,figures/'overview.png')
    progress('export',1,8,'Saving camera detection examples')
    relative=camera['relative']%360;selected=[int(np.argmin(np.abs((relative-a+180)%360-180))) for a in (0,90,180,270)]
    fig,axes=plt.subplots(2,4,figsize=(14,7))
    for column,i in enumerate(selected):
        axes[0,column].imshow(cr['images'][i],cmap='gray');axes[0,column].set_title(f'Frame {i} / {camera["angle"][i]%360:.2f}°\napproximate geometry angle')
        cx,cy,a,b,r=camera['calibration'];phi=np.linspace(0,2*np.pi,200);x=cx+a*np.cos(phi)*np.cos(r)-b*np.sin(phi)*np.sin(r);y=cy+a*np.cos(phi)*np.sin(r)+b*np.sin(phi)*np.cos(r)
        axes[0,column].plot(x,y,color='#52c58e',lw=1);axes[0,column].axis('off')
        axes[1,column].imshow(camera['polar'][i],aspect='auto',cmap='gray',extent=(0,360,.92,.30));axes[1,column].set(xlabel='Sampled angle (deg)',ylabel='Normalized radius')
        preview_image('flir',cr['images'][i],camera['calibration'],i,camera['stamps'][i],camera['relative'][i],out/'intermediates'/f'flir_detection_{i:05d}.png')
    save(fig,figures/'flir_detection_stages.png')
    progress('export',2,8,'Saving camera motion and appearance diagnostics')
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    axes[0,0].plot(ct,camera['relative'],lw=1,color=COLORS['flir']);axes[0,0].set(ylabel='Relative angle (deg)',xlabel='Bag time (s)')
    axes[0,1].hist(camera['cv'],bins=45,color=COLORS['flir']);axes[0,1].set(xlabel='Held-out residual (deg)',ylabel='Frames')
    x=(camera['features']-camera['model']['mean'])@camera['model']['projection']
    axes[1,0].scatter(x[:,0],x[:,1],c=ct,s=3,cmap='viridis');axes[1,0].set(xlabel='Appearance PC1',ylabel='Appearance PC2')
    axes[1,1].plot(ct,camera['residual'],'.',ms=2,color=COLORS['flir']);axes[1,1].set(xlabel='Bag time (s)',ylabel='Per-image residual to batch line (deg)')
    save(fig,figures/'flir_quality.png')
    progress('export',3,8,'Saving Livox measured-ray detection stages')
    selected=[int(np.argmin(np.abs((lidar['relative']%360-a+180)%360-180))) for a in (0,90,180,270)]
    fig,axes=plt.subplots(3,4,figsize=(14,11))
    for column,i in enumerate(selected):
        geometry=lr.get('geometry');lo,hi=geometry['depth_bounds_m'] if geometry else (1.2,2.7)
        upper=geometry['background_depth_m']+1 if geometry else 5
        p=lr['points'][lr['offsets'][i]:lr['offsets'][i+1]];u,v,x=p[:,0],p[:,1],p[:,2];near=(x>lo)&(x<hi);rad=np.hypot(u,v);ann=near&(rad>.025)&(rad<.135)
        axes[0,column].scatter(u,v,c=np.clip(x,lo,upper),s=2,cmap='viridis',vmin=lo,vmax=upper);axes[0,column].set_title(f'Frame {i} / relative {lidar["relative"][i]%360:.2f}°')
        axes[1,column].scatter(u[~near],v[~near],s=2,color='0.8');axes[1,column].scatter(u[ann],v[ann],s=3,color=COLORS['livox'])
        axes[2,column].hist(np.degrees(np.arctan2(v[ann],u[ann])),bins=60,color=COLORS['livox']);axes[2,column].set(xlabel='Measured near-return direction (deg)',ylabel='Returns')
        for a in axes[:2,column]:a.set(xlim=(-.2,.2),ylim=(-.2,.2),xlabel='Target u' if geometry else 'y/x',ylabel='Target v' if geometry else 'z/x',aspect='equal')
        np.savez_compressed(out/'intermediates'/f'livox_detection_{i:05d}.npz',measured_u_v_x_intensity=p,near_mask=near,retained_annulus_mask=ann)
        preview_image('livox',p,geometry,i,lidar['stamps'][i],lidar['relative'][i],out/'intermediates'/f'livox_detection_{i:05d}.png')
    save(fig,figures/'livox_detection_stages.png')
    progress('export',4,8,'Saving Livox quality and return statistics')
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    axes[0,0].plot(lt,lidar['relative'],'.',ms=2,color=COLORS['livox']);axes[0,0].plot(lt,lidar['smooth']-lidar['smooth'][0],lw=1,color=COLORS['flir']);axes[0,0].set(xlabel='Bag time (s)',ylabel='Relative angle (deg)')
    axes[0,1].plot(lt,lidar['counts'],color=COLORS['livox']);axes[0,1].set(xlabel='Bag time (s)',ylabel='Measured near-annulus returns')
    harmonic='H1' if lr.get('geometry') else 'H5'
    axes[1,0].scatter(lidar['h5'].real,lidar['h5'].imag,c=lt,s=4,cmap='viridis');axes[1,0].set(xlabel=harmonic+' real',ylabel=harmonic+' imaginary')
    axes[1,1].hist(paired['cv'][keep],bins=40,alpha=.65,color=COLORS['livox'],label='Held-out raw');axes[1,1].hist(paired['cvs'][keep],bins=40,alpha=.6,color=COLORS['flir'],label='Held-out offline');axes[1,1].set(xlabel='FLIR disagreement (deg)',ylabel='Clouds');axes[1,1].legend()
    save(fig,figures/'livox_quality.png')
    progress('export',5,8,'Saving timing profile and confidence diagnostics')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    axes[0].plot(profile['tau_ms'],profile['rmse_deg'],color=COLORS['flir']);axes[0].axvline(timing['single_bag_lag']['candidate_tau_ms'],color=COLORS['livox'],ls='--')
    axes[0].set(xlabel='Candidate tau (ms)',ylabel='RMSE after fitting constant phase (deg)',title=timing['single_bag_lag']['status'].replace('_',' ').title())
    axes[1].hist(profile['bootstrap_tau_ms'],bins=40,color=COLORS['livox']);axes[1].set(xlabel='Conditional bootstrap tau (ms)',ylabel='1 s block resamples',title='Wide / boundary distribution indicates weak timing evidence')
    save(fig,figures/'timing_profile.png')
    progress('export',6,8,'Saving sensor clock diagnostics')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for ax,sensor,label in ((axes[0],camera,'FLIR'),(axes[1],lidar,'Livox')):
        t=sensor['stamps'];h=sensor['headers'];valid=np.isfinite(h)&(h>0);tx=t[valid]-t[valid][0];hx=h[valid]-h[valid][0]
        fit=np.polyfit(hx,tx,1);residual=tx-np.polyval(fit,hx)
        ax.plot(tx,residual*1000,'.',ms=2,color=COLORS[label.lower()]);ax.set(xlabel='Bag elapsed time (s)',ylabel='Affine clock mapping residual (ms)',title=f'{label}: clock-domain mapping, not physical sensor delay')
    save(fig,figures/'clock_diagnostics.png')
    progress('export',7,8,'Saving repeatability and agreement matrices')
    aligned_camera=paired['reference'][keep];aligned_lidar=lidar['angle'][keep]-paired['offset']
    error=np.column_stack([camera['residual'][np.searchsorted(camera['stamps'],lidar['stamps'][keep]).clip(0,len(camera['stamps'])-1)],paired['cv'][keep],paired['cvs'][keep]])
    matrix=np.corrcoef(error.T);cov=np.cov(error.T);names=['FLIR own-fit residual','Livox held-out disagreement','Livox filtered disagreement']
    from common import write_csv
    write_csv(out/'timing'/'error_correlation.csv',[{'metric':names[i],**{name:matrix[i,j] for j,name in enumerate(names)}} for i in range(3)])
    write_csv(out/'timing'/'error_covariance_deg2.csv',[{'metric':names[i],**{name:cov[i,j] for j,name in enumerate(names)}} for i in range(3)])
    fig,ax=plt.subplots(figsize=(7,5));im=ax.imshow(matrix,vmin=-1,vmax=1,cmap='RdBu_r');ax.set_xticks(range(3));ax.set_yticks(range(3));ax.set_xticklabels(['FLIR residual','Livox error','Filtered error'],rotation=20);ax.set_yticklabels(['FLIR residual','Livox error','Filtered error'])
    for i in range(3):
        for j in range(3):ax.text(j,i,f'{matrix[i,j]:.2f}',ha='center',va='center')
    fig.colorbar(im,ax=ax,label='Correlation of residuals, not raw angular ramps');save(fig,figures/'error_matrix.png')
    progress('export',8,8,'All diagnostic plots saved')
