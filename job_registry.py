"""Persist worker identity so a server restart can reconnect safely to live jobs."""
import os
import signal
import time
from pathlib import Path
from common import ROOT, RESULTS, read_json, save_json

workers={}
ACTIVE=('queued','running','cancelling')

def identity(pid,request_file):
    """Match PID, start tick and exact worker/request arguments; never signal a reused PID."""
    try:
        proc=Path('/proc')/str(pid)
        args=(proc/'cmdline').read_bytes().split(b'\0')
        if len(args)<2:return None
        cwd=(proc/'cwd').resolve()
        script=(cwd/os.fsdecode(args[1])).resolve()
        if script==ROOT/'process_bag.py':
            pass  # CLI workers persist the same PID/start tick in each active run.
        elif script not in (ROOT/'batch_worker.py',ROOT/'pipeline.py') or len(args)<3 or (cwd/os.fsdecode(args[2])).resolve()!=request_file:
            return None
        stat=(proc/'stat').read_text().rsplit(')',1)[1].split()
        if stat[0]=='Z':return None
        return stat[19]  # starttime, field 22; fields after the command start at 3.
    except (OSError,ValueError,IndexError):
        return None

class RecoveredWorker:
    def __init__(self,pid,tick,request_file):
        self.pid=pid;self.tick=tick;self.request_file=request_file;self.returncode=None
    def poll(self):
        if identity(self.pid,self.request_file)==self.tick:return None
        self.returncode=-1;return self.returncode
    def terminate(self):
        if self.poll() is not None:raise ValueError('This worker has already stopped.')
        try:os.kill(self.pid,signal.SIGTERM)
        except ProcessLookupError:raise ValueError('This worker has already stopped.')

def remember(identifier,process,out):
    workers[identifier]=process
    # A newly spawned Python process already has its complete exec arguments.
    tick=identity(process.pid,out/'request.json')
    save_json(out/'worker_identity.json',{'pid':process.pid,'start_tick':tick})

def remember_current(out):
    save_json(out/'worker_identity.json',{'pid':os.getpid(),'start_tick':identity(os.getpid(),out/'request.json')})

def restore(identifier,out):
    process=workers.get(identifier)
    if process is not None:return process
    try:
        saved=read_json(out/'worker_identity.json');pid=saved['pid'];tick=saved['start_tick']
        if isinstance(pid,int) and pid>1 and tick and identity(pid,out/'request.json')==tick:
            process=RecoveredWorker(pid,tick,out/'request.json');workers[identifier]=process;return process
    except (ValueError,KeyError):pass
    return None

def status(identifier,out):
    try:
        state=read_json(out/'status.json')
        if state.get('status') not in (*ACTIVE,'complete','failed','cancelled'):
            raise ValueError('The saved job status is missing or invalid.')
        for key in ('bag','stage','message'):
            if key in state and not isinstance(state[key],str):raise ValueError('The saved job status has an invalid '+key+'.')
        for key in ('percent','processed','remaining','total','elapsed_s','capture_percent'):
            value=state.get(key)
            if key in state and value is None and key!='elapsed_s':raise ValueError('The saved job status has invalid progress data: '+key+'.')
            if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not -float('inf')<value<float('inf') or value<0):
                raise ValueError('The saved job status has invalid progress data: '+key+'.')
        if not 0<=state.get('percent',0)<=100:raise ValueError('The saved job status has invalid progress data: percent.')
        for key in ('previews','trace','metrics','batch'):
            if key in state and not isinstance(state[key],dict):raise ValueError('The saved job status has invalid '+key+' data.')
        for preview in state.get('previews',{}).values():
            if not isinstance(preview,dict) or not isinstance(preview.get('path'),str):raise ValueError('The saved job status has invalid preview data.')
        for trace in state.get('trace',{}).values():
            if not isinstance(trace,list) or any(not isinstance(row,dict) or any(isinstance(row.get(k),bool) or not isinstance(row.get(k),(int,float)) or not -float('inf')<row[k]<float('inf') for k in ('t','angle')) for row in trace):
                raise ValueError('The saved job status has invalid trace data.')
        if 'batch' in state:
            batch=state['batch']
            if any(isinstance(batch.get(key),bool) or not isinstance(batch.get(key),(int,float)) or not 0<=batch[key]<float('inf') for key in ('total','finished','completed','failed','remaining')):
                raise ValueError('The saved job status has invalid folder progress data.')
            entries=batch.get('entries')
            if not isinstance(entries,list) or any(not isinstance(row,dict) or not isinstance(row.get('bag_path'),str) or not isinstance(row.get('status'),str) or ('metrics' in row and not isinstance(row['metrics'],dict)) for row in entries):
                raise ValueError('The saved job status has invalid folder queue data.')
    except ValueError as exc:
        process=restore(identifier,out)
        if process is not None and process.poll() is None:
            cancelling=(out/'cancel_requested.json').exists()
            return {'id':identifier,'bag':identifier,'status':'cancelling' if cancelling else 'running',
                    'stage':'cancelling' if cancelling else 'recovering','percent':0,'processed':0,'remaining':0,'total':0,
                    'message':'The saved progress needs review; the matching worker is still active. '+str(exc),
                    'elapsed_s':None,'previews':{},'trace':{'FLIR':[],'Livox':[]}}
        return {'id':identifier,'bag':identifier,'status':'failed','stage':'failed','percent':0,
                'message':str(exc),'elapsed_s':None}
    state['id']=identifier
    for key,value in {'bag':identifier,'stage':state['status'],'percent':0,'message':'','elapsed_s':None,'previews':{},'trace':{'FLIR':[],'Livox':[]}}.items():
        state.setdefault(key,value)
    if state['status'] in ACTIVE:
        # Nested captures belong to their parent's queue, including the brief interval
        # before a child starts. Do not mark a live queue's children interrupted.
        parent=identifier.split('/captures/',1)[0] if '/captures/' in identifier else None
        process=restore(parent or identifier,RESULTS/parent if parent else out)
        if process is None or process.poll() is not None:
            if process is None and state['status']=='queued' and time.time()-(out/'status.json').stat().st_mtime<3:
                return state  # Allow the launcher to persist its worker identity.
            cancelled=state['status']=='cancelling' or (out/'cancel_requested.json').exists()
            state.update(status='cancelled' if cancelled else 'failed',stage='cancelled' if cancelled else 'failed',
                         message='Worker stopped before completion. Partial files are preserved; start a new run to retry.')
            save_json(out/'status.json',state)
        elif (out/'cancel_requested.json').exists():
            state.update(status='cancelling',stage='cancelling',message='Cancellation requested; preserving partial files.')
    return state

def active_jobs():
    # The filesystem also contains workers launched before this server session.
    active=[]
    for out in RESULTS.iterdir():
        if RESULTS.resolve() not in out.resolve().parents:continue
        if out.is_dir() and not out.name.startswith('.') and (out/'status.json').is_file():
            if status(out.name,out)['status'] in ACTIVE:active.append(out.name)
    return active
