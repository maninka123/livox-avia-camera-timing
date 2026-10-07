"""Find a complete rotating wheel in full images before choosing a camera crop."""
import cv2
import numpy as np
from algorithms.flir.photometry import calibrate, features, initial_rate
from common import save_json


MAX_EDGE = 640
SAMPLE_COUNT = 128
MAX_PROPOSALS = 12


def sample_frames(path, topic, progress=None):
    """Indexed, deterministic sampling; never retain the full image recording."""
    import rosbag
    import rospy
    from bag_io import grayscale
    frames, stamps = [], []
    original = None
    with rosbag.Bag(str(path)) as bag:
        start, end = bag.get_start_time(), bag.get_end_time()
        targets = np.linspace(start, end, SAMPLE_COUNT, endpoint=False)
        # Irregular sampling reduces aliases in the rotation check.
        rng = np.random.RandomState(42)
        targets[1:] += rng.uniform(-.25, .25, len(targets)-1)*(end-start)/SAMPLE_COUNT
        for index, target in enumerate(targets):
            reader = bag.read_messages(topics=[topic], start_time=rospy.Time.from_sec(float(target)))
            try:
                _, msg, stamp = next(reader)
            except StopIteration:
                continue
            finally:
                reader.close()
            if stamps and stamp.to_sec() <= stamps[-1]:
                continue
            image = grayscale(msg)
            size = (image.shape[1], image.shape[0])
            if original is None:
                original = size
            if size != original:
                raise ValueError('Camera resolution changes within this recording. Use a constant-resolution capture.')
            scale = min(1., MAX_EDGE/max(size))
            if scale < 1:
                image = cv2.resize(image, (round(size[0]*scale), round(size[1]*scale)), interpolation=cv2.INTER_AREA)
            frames.append(image); stamps.append(stamp.to_sec())
            if progress:
                progress('camera_localization', index+1, SAMPLE_COUNT, 'Locating camera flywheel from full-frame motion',
                         counts={'camera_discovery_frames': len(frames)})
        # A camera topic may occupy only a short part of a much longer bag.
        # Resample its own frame sequence instead of using the other topics' duration.
        if len(frames) < 100:
            info = bag.get_type_and_topic_info().topics.get(topic)
            count = info.message_count if info else 0
            if count >= 100:
                frames, stamps = [], []
                indices = np.linspace(0, count-1, min(SAMPLE_COUNT, count))
                indices[1:-1] += rng.uniform(-.25, .25, len(indices)-2)*count/len(indices)
                indices = set(np.clip(np.rint(indices), 0, count-1).astype(int))
                for index, (_, msg, stamp) in enumerate(bag.read_messages(topics=[topic])):
                    if index not in indices or (stamps and stamp.to_sec() <= stamps[-1]):
                        continue
                    image = grayscale(msg)
                    size = (image.shape[1], image.shape[0])
                    if size != original:
                        raise ValueError('Camera resolution changes within this recording. Use a constant-resolution capture.')
                    scale = min(1., MAX_EDGE/max(size))
                    if scale < 1:
                        image = cv2.resize(image, (round(size[0]*scale), round(size[1]*scale)), interpolation=cv2.INTER_AREA)
                    frames.append(image); stamps.append(stamp.to_sec())
                    if progress:
                        progress('camera_localization', len(frames), len(indices), 'Sampling the selected camera topic’s own frame sequence',
                                 counts={'camera_discovery_frames': len(frames)})
    if len(frames) < 100:
        raise ValueError('Automatic camera search needs at least 100 distinct images. Capture more frames or supply a manual camera crop.')
    return np.asarray(frames), np.asarray(stamps), original


def detect(images, stamps):
    images = np.asarray(images)
    time = np.asarray(stamps, dtype=float)
    if (images.ndim != 3 or images.dtype != np.uint8 or min(images.shape[1:]) < 60 or
            len(images) < 100 or time.ndim != 1 or len(time) != len(images) or
            not np.all(np.isfinite(time)) or not np.all(np.diff(time) > 0)):
        raise ValueError('Camera discovery needs grayscale images with increasing timestamps.')
    time = time-time[0]
    height, width = images.shape[1:]
    # Remove frame-wide brightness changes before measuring spatial motion.
    stack = images[np.linspace(0, len(images)-1, min(48, len(images))).astype(int)].astype('f4')
    stack -= np.median(stack, axis=(1, 2))[:, None, None]
    lower, upper = np.percentile(stack, [5, 95], axis=0)
    variation = cv2.GaussianBlur((upper-lower).astype('f4'), (5, 5), 0)
    baseline = float(np.median(variation))
    noise = float(np.median(np.abs(variation-baseline)))
    peak = float(np.percentile(variation, 99.5))
    if peak < 10:
        raise ValueError('No clear moving camera target found. Check visibility or use a manual camera crop.')
    proposals = []
    for fraction in (.20, .35, .50):
        threshold = max(8., baseline+4*noise, peak*fraction)
        mask = (variation > threshold).astype('u1')*255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), 'u1'))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            if len(contour) < 20 or cv2.contourArea(contour) < 200:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            # A clipped reflection or moving frame boundary is not a complete wheel.
            if x <= 1 or y <= 1 or x+w >= width-1 or y+h >= height-1:
                continue
            (cx, cy), (a, b), _ = cv2.fitEllipse(contour)
            if min(a, b) < 24 or max(a, b) > min(height, width)*.80 or min(a, b)/max(a, b) < .35:
                continue
            fill = cv2.contourArea(contour)/max(np.pi*a*b/4, 1)
            if not .65 <= fill <= 1.35:
                continue
            side = max(60, int(np.ceil(max(a, b)*1.65)))
            x = int(round(cx-side/2)); y = int(round(cy-side/2))
            if x < 0 or y < 0 or x+side > width or y+side > height:
                continue
            if any(np.linalg.norm(np.array([cx, cy])-p['center']) < max(a, b)*.3 for p in proposals):
                continue
            proposals.append({'roi': [x, y, side, side], 'center': np.array([cx, cy]), 'fill': float(fill)})
    if len(proposals)>MAX_PROPOSALS:
        raise ValueError('Too many moving camera regions to select a unique wheel reliably. Supply a manual camera crop.')
    candidates = []
    for proposal in proposals:
        x, y, w, h = proposal['roi']
        crops = images[:, y:y+h, x:x+w]
        try:
            geometry = calibrate(crops)
            _, z, _ = features(crops, geometry)
            rpm, score = initial_rate(time, z)
        except ValueError:
            continue
        signal = z.mean(axis=1); signal -= signal.mean(axis=0)
        energy = np.sum(np.abs(signal)**2, axis=0)
        orders = np.arange(1, signal.shape[1]+1)
        demod = np.exp(-1j*time[:, None]*(rpm*2*np.pi/60)*orders)
        coherence = np.abs(np.sum(signal*demod, axis=0))**2/np.maximum(len(time)*energy, 1e-12)
        supported = (energy > energy.max()*.02) & (coherence > .20)
        if score < .8 or supported.sum() < 2:
            continue
        candidates.append({'roi': proposal['roi'], 'center_px': (geometry[:2]+[x, y]).tolist(),
                           'ellipse_crop': geometry.tolist(), 'discovery_rpm': float(rpm),
                           'rotation_score': float(score), 'supported_harmonics': orders[supported].tolist()})
    candidates.sort(key=lambda item: item['rotation_score'], reverse=True)
    if not candidates:
        raise ValueError('Automatic camera search found no complete wheel with coherent rotation. Inspect the full image and supply a manual camera crop.')
    if len(candidates) > 1 and candidates[1]['rotation_score'] >= candidates[0]['rotation_score']*.75:
        raise ValueError('Multiple camera wheels have comparable rotation evidence. Select the intended target with a manual camera crop.')
    return candidates[0], candidates, variation


def resolve(path, config, output, progress):
    if config.get('camera_roi') is not None:
        return None
    frames, stamps, original = sample_frames(path, config['camera_topic'], progress)
    selected, candidates, variation = detect(frames, stamps)
    sx, sy = original[0]/frames.shape[2], original[1]/frames.shape[1]
    x, y, w, h = selected['roi']
    roi = [int(np.floor(x*sx)), int(np.floor(y*sy)), int(np.ceil((x+w)*sx)-np.floor(x*sx)), int(np.ceil((y+h)*sy)-np.floor(y*sy))]
    config['resolved_camera_roi'] = roi
    directory = output/'camera_localization'; directory.mkdir(exist_ok=True)
    summary = {'method': 'full_frame_motion', 'roi': roi, 'image_size_wh': list(original),
               'discovery_frames': len(frames), 'discovery_size_wh': [frames.shape[2], frames.shape[1]],
               'selected': selected, 'candidates': candidates,
               'note': 'Full-image motion and multi-harmonic rotation select the crop. Discovery RPM verifies the region only; final camera angle/RPM use all frames. The camera location can guide LiDAR through device calibration.'}
    save_json(directory/'summary.json', summary)
    np.savez_compressed(directory/'sampled_frames.npz', images=frames, bag_stamps_s=stamps, variation=variation)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].imshow(frames[0], cmap='gray'); axes[0].add_patch(Rectangle((x, y), w, h, fill=False, ec='#008f79', lw=2))
    axes[0].plot(*selected['center_px'], '+', color='#008f79', ms=10)
    axes[0].set_title('Automatic camera crop · complete rotating target')
    axes[1].imshow(variation, cmap='magma'); axes[1].set_title('Full-frame motion evidence')
    for ax in axes: ax.axis('off')
    fig.tight_layout(); fig.savefig(directory/'target_localization.png', dpi=145); plt.close(fig)
    progress('camera_localization', len(frames), len(frames), 'Camera flywheel located automatically · crop '+str(roi))
    return summary
