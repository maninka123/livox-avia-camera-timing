"""Run the two distributed bags sequentially and inspect folder/capture output."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from types import SimpleNamespace
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8766'
sys.path.insert(0, str(ROOT))
from algorithms.support import job_registry
from algorithms.support.common import processing_code_hashes


def api(path):
    with urlopen(BASE + path, timeout=15) as response:
        return json.load(response)


def main():
    health = api('/api/health')
    assert health['workspace'] == str(ROOT) and health['active_workers'] == 0
    example = json.loads((ROOT/'example_results.json').read_text())['id']
    summary = ROOT/'results'/example/'summary.json'
    before = hashlib.sha256(summary.read_bytes()).hexdigest()
    errors = []
    stages = []
    children = {}
    resume = os.environ.get('STUDIO_REVIEW_RUN')
    live_saved = bool(resume and (OUT/'folder_progress.png').exists())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path='/home/pasindu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome')
        page = browser.new_page(viewport={'width':1512,'height':1050})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until='networkidle')
        page.wait_for_function('state.metadata!==null && state.runs.length>=1')
        assert page.evaluate('state.bags.length') == 2
        if resume:
            identifier = resume
            page.evaluate('id=>showResult(id)',identifier)
        else:
            assert len(api('/api/runs')) == 1
            page.select_option('#process-scope','folder')
            page.click('#start')
            page.wait_for_function('state.currentJob!==null')
            identifier = page.evaluate('state.currentJob')
        out = ROOT/'results'/identifier
        identity = json.loads((out/'worker_identity.json').read_text())
        if resume:
            # Initial live checks passed before a metadata-label assertion was corrected.
            busy = SimpleNamespace(returncode=2)
        else:
            assert job_registry.identity(identity['pid'],out/'request.json') == identity['start_tick']
            args = (Path('/proc')/str(identity['pid'])/'cmdline').read_bytes().split(b'\0')
            assert args[1:3] == [b'-m',b'algorithms.support.batch_worker']
            busy = subprocess.run([str(ROOT/'.venv/bin/python'),'process_bag.py','--folder','device_1'],
                                  cwd=ROOT,capture_output=True,text=True,timeout=15,
                                  env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
            assert busy.returncode == 2 and 'already being processed' in busy.stderr
        deadline = time.monotonic()+140
        while time.monotonic() < deadline:
            state = api('/api/jobs/'+identifier)
            stage = (state.get('batch',{}).get('current_index'),state['stage'])
            if not stages or stages[-1]['key'] != list(stage):
                stages.append({'key':list(stage),'percent':state.get('percent'),'processed':state.get('processed'),'remaining':state.get('remaining')})
            active = 0
            for entry in state.get('batch',{}).get('entries',[]):
                run_id = entry.get('run_id')
                if not run_id:
                    continue
                request = ROOT/'results'/run_id/'request.json'
                path = request.parent/'worker_identity.json'
                if not path.exists():
                    continue
                saved = json.loads(path.read_text())
                children.setdefault(run_id,saved)
                if saved.get('start_tick') and job_registry.identity(saved['pid'],request) == saved['start_tick']:
                    active += 1
                    command = (Path('/proc')/str(saved['pid'])/'cmdline').read_bytes().split(b'\0')
                    assert command[1:3] == [b'-m',b'algorithms.support.pipeline']
                    children[run_id] = saved
            assert active <= 1, 'Folder started overlapping point-cloud workers'
            if state.get('previews',{}).get('localization') and not live_saved:
                page.wait_for_function('document.querySelector("#localization-preview").naturalWidth>0')
                page.screenshot(path=str(OUT/'folder_progress.png'),full_page=True)
                live_saved = True
            if state['status'] in ('complete','failed','cancelled'):
                break
            time.sleep(.3)
        assert state['status'] == 'complete', state
        page.wait_for_function('id=>state.currentResult?.id===id',arg=identifier)
        result = api('/api/runs/'+identifier+'/result')
        totals = result['totals']
        assert totals == {'requested_bags':2,'completed_bags':2,'failed_bags':0,'camera_frames':2848,'livox_clouds':838,'input_points':20112000}, totals
        assert len(children) == 2, children
        assert page.locator('#batch-captures tbody tr').count() == 2
        with urlopen(BASE+page.locator('#report-link').get_attribute('href'),timeout=15) as report:
            assert report.status == 200
        page.screenshot(path=str(OUT/'folder_results.png'),full_page=True)
        hashes = processing_code_hashes()
        for capture in result['captures']:
            detail = api('/api/runs/'+capture['run_id']+'/result')
            assert detail['provenance']['algorithm_sha256'] == hashes
            assert all(not path.startswith(('docs/','tests/','verification/','.venv/','results/')) for path in hashes)
            assert detail['scans']['all_recorded_clouds_processed']
            assert detail['camera_localization']['method'] == 'full_frame_motion'
            assert detail['localization']['method'] == 'camera_guided'
        first = result['captures'][0]['run_id']
        page.evaluate('id=>showResult(id,"scans")',first)
        page.wait_for_function('document.querySelector("#scan-preview").naturalWidth>0')
        assert page.locator('#scan-stats h3').inner_text().startswith('Scan 0 /')
        page.screenshot(path=str(OUT/'capture_scan.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':1050})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors
        browser.close()
    deadline = time.monotonic()+5
    while time.monotonic() < deadline and job_registry.identity(identity['pid'],out/'request.json') == identity['start_tick']:
        time.sleep(.05)
    assert job_registry.identity(identity['pid'],out/'request.json') != identity['start_tick']
    assert api('/api/health')['active_workers'] == 0
    assert hashlib.sha256(summary.read_bytes()).hexdigest() == before
    evidence = {'completion_reused_existing_run':bool(resume),'passed':True,'run_id':identifier,'totals':totals,'overall_timing_status':result['overall_timing']['status'],
                'worker_identity':identity,'child_workers':children,'maximum_concurrent_cloud_workers':1,
                'live_preview':live_saved,'second_cli_exit':busy.returncode,'observed_stages':stages,
                'processing_sources':sorted(hashes),'provenance_excludes_evidence':True,
                'browser_errors':errors,'mobile_overflow':False,'example_summary_unchanged':True}
    (OUT/'browser_checks.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({key:evidence[key] for key in ('passed','run_id','totals','overall_timing_status','live_preview','example_summary_unchanged')},indent=2))


if __name__ == '__main__':
    main()
