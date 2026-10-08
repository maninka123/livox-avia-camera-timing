"""Bounded real-bag check of relocated app workers, results and cancellation."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/validation/evidence/package-refactor'
BASE = 'http://127.0.0.1:8766'
sys.path.insert(0, str(ROOT))
from algorithms.support import job_registry


def api(path, payload=None):
    request = Request(BASE + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def process_args(run_id, module):
    directory = ROOT / 'results' / run_id
    saved = json.loads((directory / 'worker_identity.json').read_text())
    tick = job_registry.identity(saved['pid'], directory / 'request.json')
    assert tick and tick == saved['start_tick'], saved
    command = (Path('/proc') / str(saved['pid']) / 'cmdline').read_bytes().split(b'\0')
    assert command[1:3] == [b'-m', module.encode()], command
    return {'pid': saved['pid'], 'start_tick': tick, 'command': [os.fsdecode(arg) for arg in command if arg]}


def main():
    assert api('/api/health')['active_workers'] == 0
    example = json.loads((ROOT / 'example_results.json').read_text())['id']
    summary = ROOT / 'results' / example / 'summary.json'
    before = hashlib.sha256(summary.read_bytes()).hexdigest()
    errors = []
    network_errors = []
    stages = []
    evidence = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path='/home/pasindu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome')
        page = browser.new_page(viewport={'width':1512,'height':1050})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('requestfailed', lambda request: network_errors.append(request.url))
        page.goto(BASE, wait_until='networkidle')
        page.wait_for_function('state.metadata!==null && state.runs.length>=1')
        page.click('#start')
        page.wait_for_function('state.currentJob!==null')
        single = page.evaluate('state.currentJob')
        evidence['single_run_id'] = single
        evidence['single_worker'] = process_args(single, 'algorithms.support.pipeline')
        busy = subprocess.run([str(ROOT / '.venv/bin/python'), 'process_bag.py', 'device_1/rig_20260828_191845_0.bag'],
                              cwd=ROOT, capture_output=True, text=True, timeout=15,
                              env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
        assert busy.returncode == 2 and 'already being processed' in busy.stderr, busy.stderr
        evidence['second_cli_exit'] = busy.returncode
        live_saved = False
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            status = api('/api/jobs/' + single)
            if not stages or stages[-1]['stage'] != status['stage']:
                stages.append({key:status.get(key) for key in ('stage','percent','processed','remaining','total')})
            if not live_saved and status.get('previews', {}).get('localization'):
                page.wait_for_function('document.querySelector("#localization-preview").naturalWidth>0')
                page.screenshot(path=str(OUT / 'live_worker.png'), full_page=True)
                live_saved = True
            if status['status'] in ('complete','failed','cancelled'):
                break
            time.sleep(.3)
        assert status['status'] == 'complete', status
        page.wait_for_function('id=>state.currentResult?.id===id', arg=single)
        result = api('/api/runs/' + single + '/result')
        assert result['flir']['frames'] == 1423 and result['scans']['scans'] == 419
        assert result['scans']['all_recorded_clouds_processed']
        assert abs(result['flir']['rpm'] - 9.999671842705975) < 1e-7
        assert abs(result['livox']['rpm'] - 10.000187120585496) < 1e-7
        assert result['localization']['method'] == 'camera_guided'
        evidence['single_metrics'] = {key:result[key] for key in ('flir','livox','scans')}
        evidence['live_preview'] = live_saved
        page.screenshot(path=str(OUT / 'completed_result.png'), full_page=True)
        page.evaluate('id=>showResult(id,"scans")', single)
        page.wait_for_function('document.querySelector("#scan-preview").naturalWidth>0')
        assert page.locator('#scan-stats h3').inner_text().startswith('Scan 0 /')
        evidence['saved_scan_preview'] = True
        page.click('#nav-workbench')
        page.select_option('#process-scope', 'folder')
        page.click('#start')
        page.wait_for_function('id=>state.currentJob!==null && state.currentJob!==id', arg=single)
        folder = page.evaluate('state.currentJob')
        evidence['folder_run_id'] = folder
        evidence['folder_worker'] = process_args(folder, 'algorithms.support.batch_worker')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = api('/api/jobs/' + folder)
            entries = status.get('batch', {}).get('entries', [])
            if entries and entries[0].get('run_id'):
                child = entries[0]['run_id']
                if (ROOT / 'results' / child / 'worker_identity.json').exists():
                    evidence['folder_child'] = process_args(child, 'algorithms.support.pipeline')
                    break
            time.sleep(.1)
        assert 'folder_child' in evidence, status
        api('/api/jobs/' + folder + '/cancel', {})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = api('/api/jobs/' + folder)
            if status['status'] in ('cancelled','failed','complete'):
                break
            time.sleep(.1)
        assert status['status'] == 'cancelled', status
        # Terminal progress is published just before the parent interpreter exits.
        deadline = time.monotonic() + 5
        for key, request_id in (('folder_worker',folder), ('folder_child',child)):
            while time.monotonic() < deadline and job_registry.identity(evidence[key]['pid'], ROOT / 'results' / request_id / 'request.json') == evidence[key]['start_tick']:
                time.sleep(.05)
            assert job_registry.identity(evidence[key]['pid'], ROOT / 'results' / request_id / 'request.json') != evidence[key]['start_tick']
        assert api('/api/health')['active_workers'] == 0
        evidence['folder_cancelled_without_orphans'] = True
        assert not errors and not network_errors, (errors,network_errors)
        browser.close()
    assert hashlib.sha256(summary.read_bytes()).hexdigest() == before
    evidence.update(passed=True, browser_errors=errors, network_errors=network_errors, observed_stages=stages,
                    example_summary_unchanged=True)
    (OUT / 'browser_checks.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({key:evidence[key] for key in ('passed','single_run_id','folder_run_id','live_preview','saved_scan_preview','folder_cancelled_without_orphans','example_summary_unchanged')},indent=2))


if __name__ == '__main__':
    main()
