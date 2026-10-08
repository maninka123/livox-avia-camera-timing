"""Read one saved cloud without allocating the recording's entire point array."""
import zipfile
import numpy as np

CHUNK_BYTES = 1024 * 1024


def _skip(stream, count):
    while count:
        block = stream.read(min(count, CHUNK_BYTES))
        if not block:
            raise ValueError('Saved point data ended before the requested scan.')
        count -= len(block)


def read_scan(path, index):
    try:
        return _read_scan(path,index)
    except (OSError,KeyError,EOFError,zipfile.BadZipFile,TypeError) as exc:
        raise ValueError('Unable to read this saved scan. Inspect the extracted cloud file or reprocess the capture. '+str(exc)) from exc


def _read_scan(path, index):
    with np.load(path, allow_pickle=False) as data:
        stamps = data['stamps']; offsets = data['offsets']
        if stamps.ndim!=1 or not np.isfinite(stamps).all():
            raise ValueError('Saved scan timestamps are invalid.')
        if isinstance(index,bool) or not isinstance(index,(int,np.integer)) or not 0 <= index < len(stamps):
            raise ValueError('Scan index is outside this capture.')
        if (offsets.shape != (len(stamps) + 1,) or offsets.dtype.kind not in 'iu' or
                offsets[0]!=0 or np.any(offsets[1:]<offsets[:-1])):
            raise ValueError('Saved scan offsets do not match the cloud count.')
        bounds=np.asarray(data['depth_bounds_m'] if 'depth_bounds_m' in data else (1.2,2.7),float)
        if bounds.shape!=(2,) or not np.isfinite(bounds).all() or bounds[0]>=bounds[1]:
            raise ValueError('Saved target depth bounds are invalid.')
        low,high=bounds
        localized = 'coordinate_system' in data and str(data['coordinate_system']) == 'target_centred'
        lo, hi = int(offsets[index]), int(offsets[index + 1])
    with zipfile.ZipFile(path) as archive, archive.open('points.npy') as stream:
        version = np.lib.format.read_magic(stream)
        reader = {(1, 0): np.lib.format.read_array_header_1_0,
                  (2, 0): np.lib.format.read_array_header_2_0}.get(version)
        if reader is None:
            raise ValueError('Unsupported saved point-array format.')
        shape, fortran, dtype = reader(stream)
        if len(shape) != 2 or shape[1] != 4 or dtype.kind != 'f' or dtype.itemsize not in (4, 8):
            raise ValueError('Saved points require four floating-point coordinates per return.')
        if archive.getinfo('points.npy').file_size-stream.tell()!=shape[0]*shape[1]*dtype.itemsize:
            raise ValueError('Saved point-array size does not match its header.')
        if not 0 <= lo <= hi <= shape[0]:
            raise ValueError('Saved scan offsets exceed the point array.')
        points = np.empty((hi - lo, shape[1]), dtype=dtype)
        if fortran:
            for column in range(shape[1]):
                _skip(stream, (lo if column == 0 else shape[0] - hi + lo) * dtype.itemsize)
                _read_into(stream, points[:, column:column + 1], dtype)
        else:
            _skip(stream, lo * shape[1] * dtype.itemsize)
            _read_into(stream, points, dtype)
    if not np.isfinite(points[:,:3]).all():
        raise ValueError('Saved scan coordinates contain non-finite values.')
    return points, (float(low), float(high)), localized


def _read_into(stream, output, dtype):
    # Each buffer is bounded, including unusually large individual scans.
    values_per_chunk = max(1, CHUNK_BYTES // (output.shape[1] * dtype.itemsize))
    for start in range(0, len(output), values_per_chunk):
        rows = min(values_per_chunk, len(output) - start)
        count = rows * output.shape[1] * dtype.itemsize
        block = stream.read(count)
        if len(block) != count:
            raise ValueError('Saved point data ended inside the requested scan.')
        output[start:start + rows] = np.frombuffer(block, dtype=dtype).reshape(rows, output.shape[1])
