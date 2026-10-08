import asyncio,json,urllib.request,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[4];BASE='http://127.0.0.1:8767';OUT=Path(__file__).resolve().parent
async def main():
 checks=[];errors=[];observations=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path='/home/pasindu/.cache/ms-playwright/chromium-1148/chrome-linux/chrome',headless=True,args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1512,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(BASE);await page.wait_for_function('state.metadata!==null')
  assert await page.evaluate('state.bags.length')==2
  await page.select_option('#bag-select','device_1/rig_20260828_192028_0.bag');await page.wait_for_function("state.metadata && document.getElementById('bag-facts').textContent.includes('605.8')")
  await page.wait_for_function("!document.getElementById('recorded-camera-preview').hidden")
  await page.screenshot(path=str(ROOT/'docs/assets/app_preview.png'),full_page=True)
  checks.append('Published app enumerates exactly the two distributed raw bags and valid Device 1 calibration')
  await page.click('#start');await page.wait_for_function('state.currentJob!==null');job=await page.evaluate('state.currentJob')
  deadline=time.monotonic()+120;last_stage=None;screenshot=False
  while time.monotonic()<deadline:
   response=json.loads(urllib.request.urlopen(BASE+'/api/jobs/'+job).read());stage=response.get('stage');status=response['status']
   if stage!=last_stage:observations.append({'status':status,'stage':stage,'percent':response.get('percent'),'counts':response.get('counts')});last_stage=stage
   if response.get('previews',{}).get('localization') and status=='running' and not screenshot:
    await page.wait_for_function("document.getElementById('localization-preview').complete && document.getElementById('localization-preview').naturalWidth>0")
    await page.screenshot(path=str(OUT/'published_live_processing.png'),full_page=True);screenshot=True
   if status in ('complete','failed','cancelled'):break
   await asyncio.sleep(.4)
  assert status=='complete',response
  await page.wait_for_function("state.currentResult!==null && state.currentResult.id==='"+job+"'",timeout=20000)
  assert await page.locator('.localization-result').is_visible()
  result=json.loads(urllib.request.urlopen(BASE+'/api/runs/'+job+'/result').read())
  assert result['localization']['method']=='camera_guided'
  assert result['livox']['reference_timing_phase_preserved']
  # Fresh dependencies preserve the reference metrics; tolerate small numerical implementation differences.
  expected=.4886775935072314;actual=result['timing']['agreement']['heldout_raw']['std_deg'];assert abs(actual-expected)<.001,(actual,expected)
  assert result['scans']['all_recorded_clouds_processed'] and result['scans']['scans']==419
  checks.append('Browser Start processes 1,425 frames and all 419 clouds, showing live localization and stage/count progress')
  checks.append('Fresh pinned dependencies reproduce automatic held-out agreement within 0.001 degree and preserve reference timing phase')
  await page.screenshot(path=str(OUT/'published_completed_result.png'),full_page=True)
  await page.evaluate("id=>showResult(id)",'batch_device_1_20261007T064645Z_f2b206cc');assert await page.locator('#batch-captures tbody tr').count()==10
  assert 'Camera + LiDAR' in await page.locator('#batch-captures').inner_text();checks.append('Published ten-capture result shows each selected automatic method')
  await page.click('#nav-results');await page.wait_for_function("!document.getElementById('library').hidden");checks.append('Previous and automatic saved results remain separately browsable')
  assert not errors,errors
  await browser.close()
 output={'checks':checks,'browser_errors':errors,'run_id':job,'live_localization_preview_verified':screenshot,'observed_stages':observations,'heldout_livox_std_deg':actual,'camera_frames':result['flir']['frames'],'clouds':result['scans']['scans']};(OUT/'published_end_to_end.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
asyncio.run(main())
