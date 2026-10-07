"""Device geometry, with explicit image model, transform direction and units."""
import json
from pathlib import Path
import cv2
import numpy as np
from common import ROOT, sha256_file

METHODS = ('auto', 'camera_guided', 'lidar_only', 'legacy')


def load_device(device):
    if device not in ['device_%d' % i for i in range(1, 6)]:
        raise ValueError('Calibration requires a Device 1–5 folder.')
    path = ROOT / 'calibrations' / (device + '.json')
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    validate(data)
    return {**data, 'file': str(path.relative_to(ROOT)), 'sha256': sha256_file(path)}


def validate(data):
    if not isinstance(data,dict):
        raise ValueError('Calibration must be a JSON object.')
    try:
        k = np.asarray(data['K'], float)
        d = np.asarray(data['D'], float)
        t = np.asarray(data['T_lidar_to_camera'], float)
        size = np.asarray(data['image_size_wh'], float)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Calibration needs K, D, T_lidar_to_camera and image_size_wh.') from exc
    if (k.shape != (3, 3) or t.shape != (4, 4) or size.shape != (2,) or
            not all(np.isfinite(a).all() for a in (k, d, t, size))):
        raise ValueError('Calibration matrix shapes or finite values are invalid.')
    if data.get('camera_model') not in ('fisheye', 'pinhole') or data.get('translation_units') != 'metres':
        raise ValueError('Specify camera_model fisheye/pinhole and translation_units metres.')
    if d.ndim != 1 or (data['camera_model'] == 'fisheye' and len(d) != 4) or (data['camera_model'] == 'pinhole' and len(d) not in (4, 5, 8, 12, 14)):
        raise ValueError('Distortion coefficient count does not match the camera model.')
    if (min(k[0, 0], k[1, 1]) <= 0 or not np.allclose(k[2], [0, 0, 1]) or
            not np.allclose(k[1, 0], 0) or np.any(size < 1) or np.any(size != size.astype(int))):
        raise ValueError('Camera intrinsics or image size are invalid.')
    r = t[:3, :3]
    if not np.allclose(r.T @ r, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(r), 1, atol=1e-5) or not np.allclose(t[3], [0, 0, 0, 1]):
        raise ValueError('Extrinsics must be a rigid LiDAR → camera transform.')
    if 'T_camera_to_lidar' in data:
        try:
            reverse = np.asarray(data['T_camera_to_lidar'], float)
        except (TypeError, ValueError) as exc:
            raise ValueError('The supplied reverse transform needs a finite 4 × 4 matrix.') from exc
        if reverse.shape != (4, 4) or not np.isfinite(reverse).all():
            raise ValueError('The supplied reverse transform needs a finite 4 × 4 matrix.')
        if not np.allclose(reverse @ t, np.eye(4), atol=1e-5):
            raise ValueError('The supplied reverse transform is not the inverse.')
    padding=data.get('localization_padding_px',40)
    if isinstance(padding,bool) or not isinstance(padding,(int,float)) or not np.isfinite(padding) or not 0<=padding<=500:
        raise ValueError('localization_padding_px must be a finite number between 0 and 500.')
    return data


def project(xyz, calibration, image_size_wh=None):
    """Return pixels (NaN behind camera) without silently rescaling intrinsics."""
    if image_size_wh is not None and list(image_size_wh) != list(calibration['image_size_wh']):
        raise ValueError('Image size differs from device calibration. Supply intrinsics for this resolution/crop; automatic scaling is unsafe.')
    xyz = np.asarray(xyz, float)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError('Projection requires an N × 3 point array.')
    t = np.asarray(calibration['T_lidar_to_camera'])
    camera = xyz @ t[:3, :3].T + t[:3, 3]
    front = np.isfinite(camera).all(axis=1) & (camera[:, 2] > 1e-6)
    uv = np.full((len(xyz), 2), np.nan)
    if front.any():
        k = np.asarray(calibration['K'], float); d = np.asarray(calibration['D'], float)
        function = cv2.fisheye.projectPoints if calibration['camera_model'] == 'fisheye' else cv2.projectPoints
        uv[front] = function(camera[front].reshape(-1, 1, 3), np.zeros(3), np.zeros(3), k, d)[0].reshape(-1, 2)
    return uv, front
