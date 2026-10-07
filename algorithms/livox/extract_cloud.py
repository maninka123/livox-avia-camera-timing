import numpy as np

TYPES={1:'i1',2:'u1',3:'i2',4:'u2',5:'i4',6:'u4',7:'f4',8:'f8'}

def decode(msg):
    if msg.height<0 or msg.width<0 or msg.point_step<0 or msg.row_step<msg.width*msg.point_step:
        raise ValueError('LiDAR cloud dimensions or row stride are invalid.')
    if any(f.datatype not in TYPES or f.count<1 or f.offset<0 for f in msg.fields):
        raise ValueError('LiDAR cloud contains an invalid point field.')
    if any(f.name in ('x','y','z') and f.count!=1 for f in msg.fields):
        raise ValueError('LiDAR x, y and z fields must contain scalar coordinates.')
    if len({f.name for f in msg.fields})!=len(msg.fields):raise ValueError('LiDAR point field names must be unique.')
    endian='>' if msg.is_bigendian else '<'
    dtype=np.dtype({'names':[f.name for f in msg.fields],
                    'formats':[np.dtype(TYPES[f.datatype]).newbyteorder(endian) if f.count==1
                               else (np.dtype(TYPES[f.datatype]).newbyteorder(endian),(f.count,)) for f in msg.fields],
                    'offsets':[f.offset for f in msg.fields],'itemsize':msg.point_step})
    if not msg.height or not msg.width:return np.empty(0,dtype=dtype)
    if msg.point_step<=0 or len(msg.data)<(msg.height-1)*msg.row_step+msg.width*msg.point_step:
        raise ValueError('LiDAR data length does not match the declared cloud dimensions.')
    return np.ndarray((msg.height,msg.width),dtype=dtype,buffer=msg.data,
                      strides=(msg.row_step,msg.point_step)).reshape(-1)
