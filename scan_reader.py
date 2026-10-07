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
    with np.load(path, allow_pickle=False) as data:
        stamps = data['stamps']; offsets = data['offsets']
        if not 0 <= index < len(stamps):
            raise ValueError('Scan index is outside this capture.')
        if offsets.shape != (len(stamps) + 1,):
            raise ValueError('Saved scan offsets do not match the cloud count.')
        low, high = data['depth_bounds_m'] if 'depth_bounds_m' in data else (1.2, 2.7)
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
