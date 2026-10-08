"""Find a compact depth-changing target; camera geometry is an optional prior.

Discovery samples locate the stationary wheel envelope. Subsequent extraction
still decodes every scan. Camera angles, RPM and timestamps never enter LiDAR
rotation inference. A failed or ambiguous search does not silently choose a ROI.
"""
import warnings
import json
import cv2
import numpy as np
from scipy import ndimage
from scipy.stats import binned_statistic_2d
from algorithms.support.calibration import load_device, project
from algorithms.support.common import save_json, ROOT, sha256_file


def reference_capture(path, device):
    """The historical phase reference is valid only for exact known-rig inputs."""
    try:
        entries=json.loads((ROOT/'bagfiles'/'manifest.json').read_text())
        return sha256_file(path) in {row['sha256'] for row in entries if row.get('device')==device}
    except (OSError,ValueError,KeyError,TypeError):
        return False


def maps(xyz, offsets, resolution=128):
    valid = np.isfinite(xyz).all(axis=1) & (xyz[:, 0] > .1)
    uv = xyz[valid, 1:3] / xyz[valid, :1]
    if len(uv) < 1000:
        raise ValueError('Too few finite forward rays for target localization.')
    low, high = np.percentile(uv, [.1, 99.9], axis=0)
    if np.any(high - low < .01):
        raise ValueError('Insufficient LiDAR angular coverage for localization.')
    edges = [np.linspace(low[j], high[j], resolution + 1) for j in range(2)]
    images = []
    for lo, hi in zip(offsets[:-1], offsets[1:]):
        p = xyz[lo:hi]; good = np.isfinite(p).all(axis=1) & (p[:, 0] > .1)
        p = p[good]; u, v = (p[:, 1:3] / p[:, :1]).T
        image = binned_statistic_2d(v, u, p[:, 0], statistic='median', bins=[edges[1], edges[0]])[0]
        images.append(image)
    images = np.asarray(images)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        q10, median, q90 = np.nanpercentile(images, [10, 50, 90], axis=0)
    count = np.isfinite(images).sum(axis=0)
    changing = ((count >= max(12, len(images) * .25)) & (q10 > .1) &
                ((q90 - q10) > np.maximum(.12, median * .06)))
    # Thin static depth edges are not a compact rotating aperture envelope.
    changing = ndimage.binary_opening(changing, iterations=1)
    changing = ndimage.binary_closing(changing, iterations=2)
    return {'edges_u': edges[0], 'edges_v': edges[1], 'depth_p10': q10,
            'depth_median': median, 'depth_p90': q90, 'observed_scans': count,
            'changing_mask': changing, 'sample_depth_maps': images}


def candidates(evidence, xyz, offsets):
    mask = evidence['changing_mask'].astype('u1') * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    eu, ev = evidence['edges_u'], evidence['edges_v']
    du, dv = eu[1] - eu[0], ev[1] - ev[0]
    yy, xx = np.indices(mask.shape)
    result = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 35 or len(contour) < 8:
            continue
        (x, y), (a, b), degrees = cv2.fitEllipse(contour)
        if min(a, b) < 5 or max(a, b) / min(a, b) > 1.8:
            continue
        circularity = 4 * np.pi * area / max(cv2.arcLength(contour, True) ** 2, 1)
        if circularity < .45:
            continue
        center = np.array([eu[0] + (x + .5) * du, ev[0] + (y + .5) * dv])
        radius = np.sqrt(a * du * b * dv) / 2
        if not .018 < radius < .4:
            continue
        pixels = ((xx - x) ** 2 / max(a * b / 4, 1) + (yy - y) ** 2 / max(a * b / 4, 1)) < .7 ** 2
        low = float(np.nanmedian(evidence['depth_p10'][pixels]))
        high = float(np.nanmedian(evidence['depth_p90'][pixels]))
        if not np.isfinite(low + high) or high - low < max(.12, low * .06):
            continue
        # Depth support is measured, never a prescribed target distance.
        depth_low, depth_high = max(.1, low - max(.15, low * .08)), (low + high) / 2
        geometry = {'center_uv': center.tolist(), 'radius_uv': float(radius),
                    'depth_bounds_m': [depth_low, depth_high], 'foreground_depth_m': low,
                    'background_depth_m': high, 'circularity': float(circularity),
                    'angular_coordinate_system': 'target-centred y/x, z/x; radius scaled to 0.10'}
        signatures = []
        for lo, hi in zip(offsets[:-1], offsets[1:]):
            points = transform(xyz[lo:hi], geometry)
            near = target_mask(points, geometry)
            p = points[near]; phi = np.arctan2(p[:, 1], p[:, 0])
            signatures.append([np.mean(np.exp(1j * n * phi)) if len(p) else 0j for n in range(1, 7)])
        geometry['_signatures'] = np.asarray(signatures)
        geometry['score_shape'] = float(circularity * np.mean(evidence['changing_mask'][pixels]))
        result.append(geometry)
    return result


def rotation_rate(time, signatures):
    """Coherent spatial harmonics; no supplied physical speed or camera phase."""
    from scipy.optimize import minimize_scalar
    time = np.asarray(time)
    if not np.isfinite(time).all() or not np.all(np.diff(time)>0):
        raise ValueError('Discovery timestamps must be finite and strictly increasing.')
    time = time - time[0]
    signal = np.asarray(signatures); signal = signal - signal.mean(axis=0)
    energy = np.sum(abs(signal) ** 2, axis=0)
    if len(time) < 24 or np.ptp(time) < 6 or energy.max() < 1e-5:
        raise ValueError('Too little repeated rotation for independent LiDAR localization.')
    orders = np.arange(1, signal.shape[1] + 1)
    selected = np.argsort(energy)[-min(4, len(energy)):]
    def score(rpm):
        demod = np.exp(-1j * time[:, None] * rpm * 2 * np.pi / 60 * orders[selected])
        return float(np.sum(abs(np.sum(signal[:, selected] * demod, axis=0)) ** 2 /
                            np.maximum(energy[selected], 1e-12)) / (len(time) * len(selected)))
    grid = np.arange(-20, 20.001, .05)
    scores = np.array([score(r) if abs(r) > .5 else 0 for r in grid])
    best = grid[np.argmax(scores)]
    opt = minimize_scalar(lambda r: -score(r), bounds=(best - .06, best + .06), method='bounded')
    return float(opt.x), score(opt.x)


def transform(xyz, geometry, intensity=None):
    xyz = np.asarray(xyz)
    uv = (xyz[:, 1:3] / xyz[:, :1] - geometry['center_uv']) * (.10 / geometry['radius_uv'])
    return np.column_stack([uv, xyz[:, 0], np.zeros(len(xyz)) if intensity is None else intensity]).astype('f4')


def target_mask(points, geometry=None):
    radius = np.hypot(points[:, 0], points[:, 1])
    low, high = geometry['depth_bounds_m'] if geometry else (1.2, 2.7)
    return (radius > .025) & (radius < .135) & (points[:, 2] > low) & (points[:, 2] < high)


def select(evidence, xyz, offsets, stamps, calibration=None, camera_center=None):
    options = candidates(evidence, xyz, offsets)
    scored = []
    for geometry in options:
        try:
            rpm, coherence = rotation_rate(stamps, geometry.pop('_signatures'))
        except ValueError:
            continue
        geometry.update(discovery_rpm=rpm, discovery_coherence=coherence)
        if coherence < .15:
            continue
        score = geometry['score_shape'] * coherence
        if calibration is not None:
            u, v = geometry['center_uv']; x = geometry['foreground_depth_m']
            pixel, front = project(np.array([[x, u*x, v*x]]), calibration)
            distance = float(np.linalg.norm(pixel[0] - camera_center)) if front[0] else float('inf')
            geometry['camera_prior_distance_px'] = distance
            if distance > calibration.get('localization_padding_px', 40) + 35:
                continue
            score *= np.exp(-.5 * (distance / max(20, calibration.get('localization_padding_px', 40))) ** 2)
            geometry['projected_center_px'] = pixel[0].tolist()
        geometry['selection_score'] = float(score); scored.append(geometry)
    scored.sort(key=lambda item: item['selection_score'], reverse=True)
    if not scored:
        raise ValueError('No compact, coherently rotating LiDAR region found. Check coverage, duration, camera crop and device calibration; inspect the saved localization map.')
    if len(scored) > 1 and scored[1]['selection_score'] > .75 * scored[0]['selection_score']:
        raise ValueError('Multiple rotating LiDAR regions are plausible. Use camera-guided localization with matching device calibration to disambiguate.')
    return scored[0], scored


def plot(evidence, selected, options, image, camera_cal, config, calibration, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Ellipse
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.7))
    extent = [evidence['edges_u'][0], evidence['edges_u'][-1], evidence['edges_v'][0], evidence['edges_v'][-1]]
    axes[0].imshow(evidence['depth_median'], origin='lower', extent=extent, vmin=0,
                   vmax=float(np.nanpercentile(evidence['depth_median'], 95)), cmap='viridis')
    axes[0].set_title('Full LiDAR view · median depth')
    axes[1].imshow(evidence['changing_mask'], origin='lower', extent=extent, cmap='Greys')
    axes[1].set_title('Compact depth-changing regions')
    for ax in axes[:2]:
        ax.set(xlabel='LiDAR y / x', ylabel='LiDAR z / x')
        if selected:
            ax.add_patch(Circle(selected['center_uv'], selected['radius_uv'], fill=False, color='#ff8a3d', lw=2))
            ax.plot(*selected['center_uv'], '+', color='#ff8a3d', ms=10)
    axes[2].imshow(image, cmap='gray'); axes[2].set_title('Camera region / projected LiDAR centre')
    if camera_cal is not None:
        roi = config.get('resolved_camera_roi') or config['camera_roi']
        cx, cy, a, b, angle = camera_cal; cx += roi[0]; cy += roi[1]
        axes[2].add_patch(Ellipse((cx, cy), 2*a, 2*b, angle=np.degrees(angle), fill=False, color='#27b599', lw=2))
    if selected and calibration and 'projected_center_px' in selected:
        axes[2].plot(*selected['projected_center_px'], '+', color='#ff8a3d', ms=12)
    axes[2].axis('off')
    fig.suptitle('Target location is checked before angle estimation; the camera supplies no LiDAR angle or RPM', fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, .92]); fig.savefig(path, dpi=145); plt.close(fig)


def discover(path, config, output, progress):
    import rosbag
    from algorithms.support.bag_io import inspect, grayscale
    from algorithms.livox.extract_cloud import decode
    from algorithms.flir.photometry import calibrate
    mode = config.get('livox_localization', 'auto')
    if mode == 'legacy':
        return None
    device = path.parent.name
    attempts = []
    calibration = None
    if mode in ('auto', 'camera_guided'):
        try:
            calibration = load_device(device)
            if calibration is None:
                attempts.append({'method': 'camera_guided', 'status': 'unavailable', 'reason': 'No device calibration supplied.'})
        except (ValueError, OSError) as exc:
            if mode != 'auto':
                raise
            attempts.append({'method': 'camera_guided', 'status': 'unavailable', 'reason': str(exc)})
    if mode == 'camera_guided' and calibration is None:
        raise ValueError('Camera-guided localization needs calibrations/%s.json. Add this device calibration or choose LiDAR-only.' % device)
    method = 'camera_guided' if calibration else 'lidar_only'
    supplied_calibration = calibration
    directory = output / 'localization'; directory.mkdir(exist_ok=True)
    meta = inspect(path); counts = {row['name']: row['messages'] for row in meta['topics']}
    cloud_indices = set(np.linspace(0, counts[config['livox_topic']] - 1, min(96, counts[config['livox_topic']])).astype(int))
    camera_indices = set(np.linspace(0, counts[config['camera_topic']] - 1, min(120, counts[config['camera_topic']])).astype(int))
    points = []; offsets = [0]; stamps = []; crops = []; image = None; counter = {config['camera_topic']: 0, config['livox_topic']: 0}
    total = counts[config['camera_topic']] + counts[config['livox_topic']]; read = 0
    progress('localization', 0, total, 'Searching the full LiDAR view · ' + method.replace('_', ' '))
    x, y, w, h = config.get('resolved_camera_roi') or config['camera_roi']
    with rosbag.Bag(str(path)) as bag:
        for topic, msg, ts in bag.read_messages(topics=list(counter)):
            i = counter[topic]; counter[topic] += 1; read += 1
            if topic == config['camera_topic'] and i in camera_indices:
                full = grayscale(msg)
                if x+w > full.shape[1] or y+h > full.shape[0]:
                    raise ValueError('Camera crop exceeds image dimensions.')
                if image is None:
                    image = full
                    if calibration:
                        try:
                            project(np.empty((0, 3)), calibration, [full.shape[1], full.shape[0]])
                        except ValueError as exc:
                            if mode != 'auto':
                                raise
                            attempts.append({'method': 'camera_guided', 'status': 'unavailable', 'reason': str(exc)})
                            calibration = None; method = 'lidar_only'
                crops.append(full[y:y+h, x:x+w])
            elif topic == config['livox_topic'] and i in cloud_indices:
                pc = decode(msg)
                if not all(field in pc.dtype.names for field in ('x', 'y', 'z')):
                    raise ValueError('LiDAR localization requires x, y and z fields.')
                xyz = np.column_stack([pc[f] for f in ('x', 'y', 'z')])
                xyz = xyz[np.isfinite(xyz).all(axis=1) & (xyz[:, 0] > .1)]
                points.append(xyz.astype('f4')); offsets.append(offsets[-1]+len(xyz)); stamps.append(ts.to_sec())
            if read % 100 == 0 or read == total:
                progress('localization', read, total, 'Sampling full-scene evidence to locate the stationary wheel envelope')
    if len(points) < 24 or image is None:
        raise ValueError('Too few scans or no readable image for localization.')
    xyz = np.concatenate(points); offsets = np.asarray(offsets); stamps = np.asarray(stamps)
    np.savez_compressed(directory/'discovery_samples.npz', xyz=xyz, offsets=offsets, stamps=stamps, camera_crops=np.asarray(crops))
    camera_cal = None
    if calibration:
        try:
            camera_cal = calibrate(np.asarray(crops))
        except ValueError as exc:
            if mode != 'auto':
                raise
            attempts.append({'method': 'camera_guided', 'status': 'unavailable', 'reason': str(exc)})
            calibration = None; method = 'lidar_only'
    center = camera_cal[:2]+[x, y] if camera_cal is not None else None
    evidence = maps(xyz, offsets)
    np.savez_compressed(directory/'spatial_evidence.npz', **evidence)
    result = {'requested_method': mode, 'method': method, 'attempts': attempts, 'camera_angles_used': False,
              'sampled_clouds': len(points), 'total_clouds': counts[config['livox_topic']],
              'calibration': calibration, 'supplied_calibration': supplied_calibration, 'camera_geometry_crop': camera_cal,
              'camera_roi': [x, y, w, h],
              'all_scans_used_for_angle_estimation': True}
    result['preserve_reference_timing_phase']=mode in ('auto','camera_guided') and reference_capture(path,device)
    selected = None; options = []
    try:
        try:
            selected, options = select(evidence, xyz, offsets, stamps, calibration, center)
            attempts.append({'method': method, 'status': 'selected', 'reason': 'Compact moving envelope and coherent independent LiDAR rotation verified.'})
        except ValueError as exc:
            attempts.append({'method': method, 'status': 'rejected', 'reason': str(exc)})
            if mode != 'auto' or method != 'camera_guided':
                raise
            progress('localization', total, total, 'Camera-guided search rejected; falling back to full-scene LiDAR-only detection')
            try:
                selected, options = select(evidence, xyz, offsets, stamps)
                method = 'lidar_only'; result['method'] = method
                attempts.append({'method': method, 'status': 'selected', 'reason': 'Full-scene LiDAR rotation verified without the rejected calibration prior.'})
            except ValueError as lidar_exc:
                attempts.append({'method': 'lidar_only', 'status': 'rejected', 'reason': str(lidar_exc)})
                raise
        result.update(status='LOCATED', geometry=selected, candidates=options,
                      timing_convention='legacy_h5_over_3' if result['preserve_reference_timing_phase'] else 'target_centred_h1_v1',
                      note='Coarse camera geometry is optional; periodic LiDAR evidence selects the target. Geometry was learned using the full discovery sequence, so downstream validation is conditional on this ROI.')
        if calibration and selected.get('camera_prior_distance_px', 0) > 10:
            result['calibration_alignment_review'] = 'Projected centre differs from the detected image centre by %.1f px. Calibration is a coarse prior; confirm pose and enclosure state.' % selected['camera_prior_distance_px']
        progress('localization',total,total,'Target verified using '+method.replace('_',' ')+'; independent LiDAR rotation %.3f RPM' % selected['discovery_rpm'],metrics={'localization_method':method})
        return result
    except ValueError as exc:
        # Only exact reference recordings qualify for the known-rig fallback.
        # Renamed copies qualify by content; arbitrary new bags do not.
        reference = False
        if mode == 'auto' and 'Multiple rotating' not in str(exc):
            reference = reference_capture(path,device)
        if reference:
            from algorithms.livox import return_features as returns
            u, v = (xyz[:, 1:3] / xyz[:, :1]).T
            measured = np.column_stack([u,v,xyz[:,0],np.zeros(len(xyz))])
            _, signature, counts = returns.features(measured, offsets)
            try:
                rpm, coherence = returns.initial_rate(stamps-stamps[0], signature,minimum_observations=24)
                if coherence >= .6 and np.median(counts) >= 100:
                    attempts.append({'method':'legacy_checked','status':'selected','reason':'Exact known-rig bag verified by SHA256; fixed-region coherent rotation %.3f and median %.0f near returns.' % (coherence,np.median(counts))})
                    result.update(status='LOCATED_WITH_REFERENCE_FALLBACK',method='legacy_checked',geometry=None,
                                  timing_convention='legacy_h5_over_3',
                                  note='Reference-data fallback: fixed region is supported only for this SHA256-verified original rig recording. It does not locate arbitrary new scenes.',
                                  fallback_review=str(exc))
                    progress('localization',total,total,'Using SHA256-verified reference-rig fallback after automatic localization was rejected',metrics={'localization_method':'legacy_checked'})
                    return result
            except ValueError as backup_exc:
                attempts.append({'method':'legacy_checked','status':'rejected','reason':str(backup_exc)})
        result.update(status='UNRESOLVED', reason=str(exc))
        raise
    finally:
        save_json(directory/'summary.json', result)
        plot(evidence, selected, options, image, camera_cal, config, calibration, directory/'target_localization.png')
