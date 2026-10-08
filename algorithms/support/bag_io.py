"""ROS1 bag metadata and vectorized extraction of the two selected sensors."""
import cv2
import numpy as np
import rosbag
from algorithms.livox.extract_cloud import decode

def inspect(path):
    with rosbag.Bag(str(path)) as bag:
        info=bag.get_type_and_topic_info()
        start,end=bag.get_start_time(),bag.get_end_time()
        topics=[{'name':name,'type':item.msg_type,'messages':item.message_count,
                 'frequency_hz':item.message_count/max(end-start,1e-9),
                 'median_arrival_hz':float(item.frequency) if item.frequency else None} for name,item in info.topics.items()]
    cameras=[r['name'] for r in topics if r['type']=='sensor_msgs/Image']
    lidars=[r['name'] for r in topics if r['type']=='sensor_msgs/PointCloud2']
    camera=next((name for name in cameras if 'camera' in name.lower()),cameras[0] if len(cameras)==1 else None)
    livox=next((name for name in lidars if 'livox' in name.lower()),lidars[0] if len(lidars)==1 else None)
    parts=path.stem.split('_')
    red=len(parts)>=2 and parts[-2] in ('192952','193136','193309')
    return {'name':path.name,'size_bytes':path.stat().st_size,'start_s':start,'end_s':end,'duration_s':end-start,
            'topics':topics,'suggested_camera_topic':camera,'suggested_livox_topic':livox,
            'suggested_phase_group':'red' if red else 'normal'}

def grayscale(msg):
    encoding=msg.encoding.lower()
    if msg.height<=0 or msg.width<=0:raise ValueError('Camera image dimensions must be positive.')
    channels=3 if encoding in ('rgb8','bgr8') else 2 if encoding in ('mono16','16uc1') else 1
    if msg.step<msg.width*channels or len(msg.data)!=msg.height*msg.step:
        raise ValueError('Camera image data length or row stride does not match its dimensions.')
    raw=np.frombuffer(msg.data,np.uint8).reshape(msg.height,msg.step)
    if encoding in ('rgb8','bgr8'):
        image=raw[:,:msg.width*3].reshape(msg.height,msg.width,3)
        return cv2.cvtColor(image,cv2.COLOR_RGB2GRAY if encoding=='rgb8' else cv2.COLOR_BGR2GRAY)
    if encoding in ('mono16','16uc1'):
        dtype=np.dtype('>u2' if msg.is_bigendian else '<u2')
        image=np.ndarray((msg.height,msg.width),dtype=dtype,buffer=msg.data,strides=(msg.step,2))
        lo,hi=np.percentile(image,[1,99]);return np.clip((image-lo)*255/max(hi-lo,1),0,255).astype('u1')
    raw=raw[:,:msg.width]
    codes={'bayer_rggb8':cv2.COLOR_BAYER_RG2BGR,'bayer_bggr8':cv2.COLOR_BAYER_BG2BGR,
           'bayer_gbrg8':cv2.COLOR_BAYER_GB2BGR,'bayer_grbg8':cv2.COLOR_BAYER_GR2BGR}
    if encoding in codes:return cv2.cvtColor(cv2.cvtColor(raw,codes[encoding]),cv2.COLOR_BGR2GRAY)
    if encoding!='mono8':raise ValueError('Unsupported camera encoding: '+msg.encoding)
    return raw.copy()

def extract(path,config,output,progress,preview,localization=None):
    meta=inspect(path)
    counts={row['name']:row['messages'] for row in meta['topics']}
    total=counts[config['camera_topic']]+counts[config['livox_topic']]
    images=[];ct=[];ch=[];lt=[];lh=[];points=[];offsets=[0];full=[];point_counts=[];finite_counts=[];reference_h5=[]
    roi=config.get('resolved_camera_roi') or config['camera_roi']
    if roi is None:raise ValueError('Resolve the automatic camera crop before extraction.')
    x,y,w,h=roi;processed=0;camera_size=None
    with rosbag.Bag(str(path)) as bag:
        for topic,msg,ts in bag.read_messages(topics=[config['camera_topic'],config['livox_topic']]):
            if topic==config['camera_topic']:
                image=grayscale(msg)
                size=(image.shape[1],image.shape[0])
                if camera_size is None:camera_size=size
                if size!=camera_size:raise ValueError('Camera resolution changes within this recording. Use a constant-resolution capture.')
                if x+w>image.shape[1] or y+h>image.shape[0]:raise ValueError('Camera crop exceeds this image. Adjust the crop in acquisition settings.')
                crop=image[y:y+h,x:x+w].copy();images.append(crop);ct.append(ts.to_sec());ch.append(msg.header.stamp.to_sec())
                if len(images)==1 or len(images)%350==0:
                    full.append((len(images)-1,image.copy()))
                    preview('flir',crop,None,len(images)-1,ts.to_sec(),None)
            else:
                pc=decode(msg)
                if not all(field in pc.dtype.names for field in ('x','y','z')):raise ValueError('The selected LiDAR topic must contain x, y and z fields.')
                xyz=np.column_stack([pc[field] for field in ('x','y','z')])
                point_counts.append(len(xyz));finite_counts.append(int(np.all(np.isfinite(xyz),axis=1).sum()))
                valid=np.all(np.isfinite(xyz),axis=1)&(xyz[:,0]>(.1 if localization else .5))
                xyz=xyz[valid]
                if localization and localization.get('preserve_reference_timing_phase'):
                    uv=xyz[:,1:3]/xyz[:,:1];rad=np.hypot(uv[:,0],uv[:,1])
                    mask=(rad>.025)&(rad<.135)&(xyz[:,0]>1.2)&(xyz[:,0]<2.7)
                    phi=np.arctan2(uv[mask,1],uv[mask,0]);weight=rad[mask]
                    reference_h5.append(np.sum(weight*np.exp(5j*phi))/max(weight.sum(),1e-9))
                if localization and localization.get('geometry'):
                    from algorithms.support.localization import transform
                    intensity=pc['intensity'][valid] if 'intensity' in pc.dtype.names else None
                    measured=transform(xyz,localization['geometry'],intensity)
                    keep=np.hypot(measured[:,0],measured[:,1])<.20
                    p=measured[keep]
                else:
                    u=xyz[:,1]/xyz[:,0];v=xyz[:,2]/xyz[:,0];keep=np.hypot(u,v)<.20
                    intensity=pc['intensity'][valid][keep] if 'intensity' in pc.dtype.names else np.zeros(keep.sum())
                    p=np.column_stack([u[keep],v[keep],xyz[keep,0],intensity]).astype('f4')
                points.append(p);offsets.append(offsets[-1]+len(p));lt.append(ts.to_sec());lh.append(msg.header.stamp.to_sec())
                if len(lt)==1 or len(lt)%100==0:preview('livox',p,localization.get('geometry') if localization else None,len(lt)-1,ts.to_sec(),None)
            processed+=1
            if processed%50==0 or processed==total:
                progress('extract',processed,total,f'Reading selected topics: {len(images)} camera frames, {len(lt)} Livox clouds',
                         counts={'camera':len(images),'livox':len(lt)})
    if len(images)<150 or len(lt)<150:raise ValueError('At least 150 camera frames and 150 Livox clouds are needed for this calibrated-motion workflow.')
    for sensor,stamps in (('FLIR',ct),('Livox',lt)):
        if not np.all(np.isfinite(stamps)) or not np.all(np.diff(stamps)>0):
            raise ValueError(f'{sensor} bag-record timestamps must be finite and strictly increasing. Duplicate or reset timestamps cannot support this motion workflow.')
    camera={'images':np.asarray(images),'stamps':np.asarray(ct),'headers':np.asarray(ch)}
    lidar={'points':np.concatenate(points),'offsets':np.asarray(offsets),'stamps':np.asarray(lt),'headers':np.asarray(lh),
           'total_point_counts':np.asarray(point_counts),'finite_point_counts':np.asarray(finite_counts)}
    if reference_h5:lidar['reference_timing_h5']=np.asarray(reference_h5)
    intermediate=output/'intermediates';intermediate.mkdir(exist_ok=True)
    np.savez_compressed(intermediate/'camera_extracted.npz',**camera,crop_origin_xy=[x,y])
    geometry=localization.get('geometry') if localization else None
    np.savez_compressed(intermediate/'livox_extracted.npz',**lidar,
                        coordinate_system='target_centred' if geometry else 'sensor_y_over_x_z_over_x',
                        depth_bounds_m=geometry['depth_bounds_m'] if geometry else [1.2,2.7],
                        center_uv=geometry['center_uv'] if geometry else [0.,0.],
                        radius_uv=geometry['radius_uv'] if geometry else .10)
    lidar['geometry']=geometry;lidar['localization']=localization
    for frame,image in full:cv2.imwrite(str(intermediate/f'camera_full_frame_{frame:05d}.png'),image)
    return camera,lidar,meta
