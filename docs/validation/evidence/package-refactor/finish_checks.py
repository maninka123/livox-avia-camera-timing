"""Finish read-only checks of the completed real run and cancelled folder."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/validation/evidence/package-refactor'
BASE = 'http://127.0.0.1:8766'
sys.path.insert(0, str(ROOT))
from algorithms.support import job_registry

single = 'rig_20260828_191845_0_20261008T032702Z_3406b666'
folder = 'batch_device_1_20261008T032723Z_5130cabc'


def api(path):
    with urlopen(BASE + path, timeout=15) as response:
        return json.load(response)


def main():
    result = api('/api/runs/' + single + '/result')
    assert result['flir']['frames'] == 1423 and result['scans']['scans'] == 419
    assert result['scans']['all_recorded_clouds_processed']
    assert abs(result['flir']['rpm'] - 9.999671842705975) < 1e-7
    assert abs(result['livox']['rpm'] - 10.000187120585496) < 1e-7
    assert result['localization']['method'] == 'camera_guided'
    status = api('/api/jobs/' + folder)
    assert status['status'] == 'cancelled'
    child = status['batch']['entries'][0]['run_id']
    identities = {}
    for name in (single, folder, child):
        out = ROOT / 'results' / name
        saved = json.loads((out / 'worker_identity.json').read_text())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and job_registry.identity(saved['pid'], out / 'request.json') == saved['start_tick']:
            time.sleep(.05)
        assert job_registry.identity(saved['pid'], out / 'request.json') != saved['start_tick']
        identities[name] = saved
    assert api('/api/health')['active_workers'] == 0
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path='/home/pasindu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome')
        page = browser.new_page(viewport={'width':1512,'height':1050})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until='networkidle')
        page.wait_for_function('state.metadata!==null')
        page.evaluate('id=>showResult(id)', single)
        page.wait_for_function('id=>state.currentResult?.id===id', arg=single)
        page.screenshot(path=str(OUT / 'completed_result.png'), full_page=True)
        page.evaluate('id=>showResult(id,"scans")', single)
        page.wait_for_function('document.querySelector("#scan-preview").naturalWidth>0')
        assert page.locator('#scan-stats h3').inner_text().startswith('Scan 0 /')
        page.screenshot(path=str(OUT / 'scan_preview.png'), full_page=True)
        page.set_viewport_size({'width':390,'height':1050})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors
        browser.close()
    example = json.loads((ROOT / 'example_results.json').read_text())['id']
    relative = 'results/' + example + '/summary.json'
    original = subprocess.check_output(['git','show','HEAD:' + relative],cwd=ROOT)
    assert hashlib.sha256(original).digest() == hashlib.sha256((ROOT / relative).read_bytes()).digest()
    stages = [json.loads(line) for line in (ROOT / 'results' / single / 'progress.jsonl').read_text().splitlines()]
    evidence = {
        'passed':True,'single_run_id':single,'folder_run_id':folder,'folder_child_run_id':child,
        'camera_frames':result['flir']['frames'],'livox_scans':result['scans']['scans'],
        'camera_rpm':result['flir']['rpm'],'livox_rpm':result['livox']['rpm'],
        'camera_roi':result['camera_localization']['roi'],'lidar_method':result['localization']['method'],
        'worker_identities':identities,'observed_stages':list(dict.fromkeys(row['stage'] for row in stages)),
        'package_worker_commands_checked_during_processing':True,
        'second_cli_exit':2,'live_preview':(OUT / 'live_worker.png').is_file(),
        'saved_scan_preview':True,'folder_cancelled_without_orphans':True,
        'browser_errors':errors,'mobile_overflow':False,'example_summary_unchanged':True,
        'check_note':'The initial end-to-end check verified package commands, busy CLI rejection and folder child launch. Final identity checks wait for interpreter exit after terminal progress is published; this read-only completion check reused those results.'
    }
    (OUT / 'browser_checks.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__ == '__main__':
    main()
