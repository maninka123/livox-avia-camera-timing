import asyncio,json,zipfile,urllib.request
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'verification';BASE='http://127.0.0.1:8765'
async def main():
 batch=(OUT/'automatic_final_batch_id.txt').read_text().strip();summary=json.loads((ROOT/'results'/batch/'summary.json').read_text());run=next(c['run_id'] for c in summary['captures'] if '192028' in c['bag'])
 checks=[];errors=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path='/home/pasindu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',headless=True,args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1512,'height':1100},accept_downloads=True)
  page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(BASE);await page.wait_for_function("state.metadata!==null")
  await page.wait_for_function("!document.getElementById('recorded-camera-preview').hidden")
  assert await page.locator('#crop-overlay').is_visible();checks.append('Recorded camera preview and configured crop overlay render')
  await page.screenshot(path=str(OUT/'automatic_app_preview.png'),full_page=True)
  await page.click('#inspect-frame');assert await page.locator('#full-frame-dialog').is_visible();await page.keyboard.press('Escape');assert not await page.locator('#full-frame-dialog').is_visible();checks.append('Frame modal opens and Escape returns to workspace')
  await page.select_option('#dataset-select','device_2');await page.wait_for_function("state.bags.length===0 && document.getElementById('dataset-hint').textContent.includes('device_2')")
  assert await page.locator('#start').is_disabled();await page.wait_for_function("document.getElementById('calibration-status').textContent.includes('LiDAR-only')");checks.append('Empty device and calibration-free fallback are explained, with processing disabled')
  await page.select_option('#dataset-select','device_1');await page.wait_for_function("state.metadata!==null")
  await page.click('#nav-results');await page.wait_for_function("!document.getElementById('library').hidden")
  await page.screenshot(path=str(OUT/'automatic_library.png'),full_page=True)
  await page.evaluate('id=>showResult(id)',run);assert await page.locator('.localization-result').is_visible();assert 'Camera-guided' in await page.locator('.localization-result').inner_text();checks.append('Saved real-bag result includes selected method, calibration review and decision history')
  await page.screenshot(path=str(OUT/'automatic_bag_results.png'),full_page=True)
  await page.click('.tab[data-tab="livox"]');await page.wait_for_function("Array.from(document.querySelectorAll('.figure-card img')).some(i=>i.src.includes('target_localization')&&i.complete&&i.naturalWidth>0)")
  await page.screenshot(path=str(OUT/'automatic_localization_results.png'),full_page=True);checks.append('LiDAR result shows source-backed target localization and angle diagnostics')
  await page.click('.tab[data-tab="scans"]');await page.wait_for_function("document.getElementById('scan-preview').complete && document.getElementById('scan-preview').naturalWidth>0")
  await page.fill('#scan-index','200');await page.locator('#scan-index').dispatch_event('change');await page.wait_for_function("document.getElementById('scan-stats').textContent.includes('Scan 200 /')")
  await page.wait_for_function("document.getElementById('scan-preview').alt.endsWith('scan 200') && document.getElementById('scan-preview').complete && document.getElementById('scan-preview').naturalWidth>0 && !document.getElementById('scan-preview').hidden")
  assert await page.locator('#scan-preview').is_visible();checks.append('Arbitrary individual scan loads target-centred measured rays and numerical statistics')
  await page.evaluate('id=>showResult(id)',batch);assert await page.locator('#batch-captures tbody tr').count()==10;assert '9 / 10' in await page.locator('#result-body').inner_text();checks.append('All ten captures and the honest old/new quality comparison render')
  await page.click('.tab[data-tab="timing"]');assert '-25.95' in await page.locator('#batch-timing').inner_text();await page.wait_for_function("Array.from(document.querySelectorAll('.figure-card img')).some(i=>i.src.includes('overall_timing')&&i.complete&&i.naturalWidth>0)")
  await page.screenshot(path=str(OUT/'automatic_folder_timing.png'),full_page=True)
  tau=summary['overall_timing']['candidate_tau_ms'];card=page.locator('#timing-explainer');assert abs(float(await card.get_attribute('data-tau-ms'))-tau)<1e-10;checks.append('Timing illustration and plot use the exact saved candidate')
  await page.set_viewport_size({'width':390,'height':844});await page.screenshot(path=str(OUT/'automatic_mobile_results.png'),full_page=True);assert not await page.evaluate('document.documentElement.scrollWidth>window.innerWidth')
  await page.click('#nav-workbench');await page.set_viewport_size({'width':320,'height':720});await page.screenshot(path=str(OUT/'automatic_mobile_workspace.png'),full_page=True);assert not await page.evaluate('document.documentElement.scrollWidth>window.innerWidth');checks.append('Workspace and real results fit 320/390-pixel mobile widths')
  await page.emulate_media(reduced_motion='reduce');assert await page.locator('#progress-fill').evaluate("e=>getComputedStyle(e).transitionDuration==='0s'");checks.append('Reduced-motion preference removes progress transitions and press transforms')
  await browser.close()
 assert not errors,errors
 # Confirm the downloadable bundle includes localization and every new intermediate.
 destination=OUT/'automatic_child_bundle.zip';urllib.request.urlretrieve(BASE+'/api/runs/'+urllib.parse.quote(run,safe='')+'/download',destination)
 with zipfile.ZipFile(destination) as archive:
  names=archive.namelist();assert all(any(n.endswith('/'+required) for n in names) for required in ['localization/summary.json','localization/discovery_samples.npz','intermediates/livox_extracted.npz']);assert archive.testzip() is None
 checks.append('ZIP bundle contains readable localization evidence, extracted arrays and reports')
 result={'batch_id':batch,'run_id':run,'checks':checks,'browser_errors':errors,'bundle_entries':len(names)};(OUT/'automatic_browser_results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
asyncio.run(main())
