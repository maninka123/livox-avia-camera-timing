import csv
import json
import os
import uuid
import hashlib
from functools import lru_cache
from contextlib import contextmanager
import fcntl
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BAGS = ROOT / 'bagfiles'
RESULTS = ROOT / 'results'

def processing_code_hashes(root=None):
    """Snapshot processing sources without traversing datasets or environments."""
    root=ROOT if root is None else Path(root)
    files=[root/'app.py',root/'process_bag.py',*sorted((root/'algorithms').rglob('*.py'))]
    return {file.relative_to(root).as_posix():hashlib.sha256(file.read_bytes()).hexdigest() for file in files}

def file_prefix(value,max_bytes=180):
    """Keep generated filenames below Linux's byte limit, including Unicode names."""
    encoded=value.encode('utf-8')
    if len(encoded)<=max_bytes:return value
    suffix='_'+hashlib.sha256(encoded).hexdigest()[:8]
    return encoded[:max_bytes-len(suffix)].decode('utf-8',errors='ignore')+suffix

@contextmanager
def file_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def native(value):
    if isinstance(value, dict): return {str(k): native(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)): return [native(v) for v in value]
    if isinstance(value, np.ndarray): return native(value.tolist())
    if isinstance(value, np.generic): return native(value.item())
    if isinstance(value, float) and not np.isfinite(value): return None
    return value

def save_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    try:
        temp.write_text(json.dumps(native(data), indent=2, allow_nan=False) + '\n')
        os.replace(str(temp), str(path))
    finally:
        temp.unlink(missing_ok=True)

def read_json(path):
    path=Path(path)
    try:
        data=json.loads(path.read_text())
        if not isinstance(data,dict):raise ValueError('Expected a JSON object.')
        return data
    except (OSError,ValueError) as exc:
        raise ValueError(f'Unable to read {path.name}. Saved files are preserved; inspect the run folder. {exc}') from exc

@lru_cache(maxsize=128)
def _file_hash(path,fingerprint):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    stat=Path(path).stat()
    if (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)!=fingerprint:
        raise ValueError('The source bag changed while it was being read. Retry with a stable recording.')
    return digest.hexdigest()

def sha256_file(path):
    path=Path(path).resolve();stat=path.stat()
    return _file_hash(str(path),(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns))

def capture_identity(result):
    digest=result.get('provenance',{}).get('bag_sha256')
    if isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest):return digest
    try:return sha256_file(bag_path(result.get('bag_path') or result['bag']))
    except (ValueError,OSError) as exc:
        raise ValueError('Cannot verify distinct source captures: '+str(exc)) from exc

def distinct_captures(results):
    unique=[];duplicates=[];seen=set()
    for result in results:
        digest=capture_identity(result)
        if digest in seen:duplicates.append(result)
        else:unique.append(result);seen.add(digest)
    return unique,duplicates

def write_csv(path, rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if not rows: return
    fields=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(native(rows))

def bag_path(name):
    if not isinstance(name,str) or not name.endswith('.bag') or '\\' in name:
        raise ValueError('Select a .bag file from bagfiles.')
    relative=Path(name)
    if relative.is_absolute() or any(part in ('.','..') or part.startswith('.') for part in relative.parts):
        raise ValueError('Select a .bag file from bagfiles.')
    path=(BAGS/name).resolve()
    # Existing single-bag commands keep working after organization into devices.
    if len(relative.parts)==1 and not path.is_file():
        matches=[p.resolve() for p in BAGS.glob('device_*/*.bag') if p.name==name]
        if len(matches)==1:path=matches[0]
        elif len(matches)>1:raise ValueError('This filename occurs in multiple devices. Select its device folder too.')
    if BAGS.resolve() not in path.parents or not path.is_file():raise ValueError('Bag file was not found in bagfiles.')
    return path

def dataset_path(name):
    if name not in [f'device_{i}' for i in range(1,6)]:raise ValueError('Select Device 1 through Device 5.')
    path=(BAGS/name).resolve()
    if path.parent!=BAGS.resolve() or not path.is_dir():raise ValueError('Device folder was not found.')
    return path

def dataset_bags(name):
    return [p for p in sorted(dataset_path(name).glob('*.bag')) if p.is_file() and BAGS.resolve() in p.resolve().parents]

def result_path(run_id):
    if not isinstance(run_id,str) or '\\' in run_id:raise ValueError('Invalid result ID.')
    parts=Path(run_id).parts
    if not parts or Path(run_id).is_absolute() or any(p in ('.','..') or p.startswith('.') for p in parts):raise ValueError('Invalid result ID.')
    if len(parts)!=1 and not (len(parts)==3 and parts[1]=='captures'):raise ValueError('Invalid result ID.')
    path=(RESULTS/run_id).resolve()
    if RESULTS.resolve() not in path.parents or not path.is_dir():raise ValueError('Result folder was not found.')
    return path

def validate_options(metadata, options):
    if not isinstance(options,dict):raise ValueError('Acquisition settings must be an object.')
    defaults=read_json(ROOT/'config.json');config=dict(defaults)
    config.update({k:v for k,v in options.items() if k in config})
    topics={row['name']:row for row in metadata['topics']}
    for key,kind in (('camera_topic','sensor_msgs/Image'),('livox_topic','sensor_msgs/PointCloud2')):
        if not isinstance(config[key],str) or config[key] not in topics or topics[config[key]]['type']!=kind:
            raise ValueError(f'Select a valid {kind} topic for {key}.')
    roi=config['camera_roi']
    if roi is not None:
        if not isinstance(roi,list) or len(roi)!=4 or any(isinstance(x,bool) or not isinstance(x,int) for x in roi):
            raise ValueError('Use null for automatic camera cropping, or four integers: x, y, width, height.')
        if min(roi[:2])<0 or min(roi[2:])<60:raise ValueError('Crop coordinates must be nonnegative and crop dimensions at least 60 pixels.')
    if not isinstance(config['phase_group'],str) or not config['phase_group'].strip() or len(config['phase_group'])>60:
        raise ValueError('Provide a setup/illumination group name of 1–60 characters.')
    config['phase_group']=config['phase_group'].strip()
    if config.get('livox_localization','auto') not in ('auto','camera_guided','lidar_only','legacy'):
        raise ValueError('Unknown target localization method. Use auto, camera_guided, lidar_only or legacy.')
    try:config['timing_search_ms']=float(config['timing_search_ms'])
    except (TypeError,ValueError):raise ValueError('Timing search must be a number between 10 and 2000 ms.')
    if not 10<=config['timing_search_ms']<=2000:raise ValueError('Timing search must be between 10 and 2000 ms.')
    # The shipped validated algorithm settings are fixed; advanced controls concern acquisition only.
    for key in ('camera_order','livox_order','livox_smoothing_frames','validation_folds'):
        config[key]=defaults[key]
    return config
