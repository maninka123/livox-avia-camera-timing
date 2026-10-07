'use strict';
const $ = id => document.getElementById(id);
const state = {metadata: null, datasets: [], bags: [], currentJob: null, busy: false, starting: false, comparing: false, importing: false, poll: null, previewKeys: {}, runs: [], currentResult: null, resultVersion: 0, inspectVersion: 0};
window.__consoleErrors = [];
window.addEventListener('error', e => window.__consoleErrors.push(e.message));
window.addEventListener('unhandledrejection', e => window.__consoleErrors.push(String(e.reason)));
const number = (value, digits=3) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);
const bytes = value => value > 1e9 ? `${(value/1e9).toFixed(2)} GB` : `${(value/1e6).toFixed(1)} MB`;
const artifact = (id, file) => `/artifacts/${id.split('/').map(encodeURIComponent).join('/')}/${file.split('/').map(encodeURIComponent).join('/')}`;
function element(tag, text, className) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(className)e.className=className; return e; }
function notify(message) { $('notice').textContent=message; $('notice').hidden=!message; }
async function api(url, options={}) {
  const response=await fetch(url, options); let data;
  try { data=await response.json(); } catch { throw new Error(`Unable to read server response (${response.status}).`); }
  if(!response.ok)throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function page(name) {
  for(const id of ['workbench','library','results-panel'])$(id).hidden=id!==name;
  $('nav-workbench').classList.toggle('active',name==='workbench');
  $('nav-results').classList.toggle('active',name!=='workbench');
}
function topicSelect(id,topics,type,suggested) {
  const select=$(id); select.replaceChildren();
  select.append(new Option('Select a compatible topic…',''));
  for(const row of topics.filter(t=>t.type===type))select.append(new Option(row.name,row.name));
  select.value=suggested || '';select.disabled=false;
}
function markTopics() {
  for(const row of $('topic-table').children)row.classList.toggle('selected-topic',[ $('camera-topic').value,$('livox-topic').value ].includes(row.dataset.name));
  const folder=$('process-scope').value==='folder';
  $('start').disabled=state.busy || state.starting || state.importing || !state.bags.length || (!folder && !state.metadata) || (!(folder && $('batch-auto-topics').checked) && (!state.metadata || !$('camera-topic').value || !$('livox-topic').value));
  $('start').textContent=folder?`Process entire folder · ${state.bags.length} bags →`:'Run detection & timing →';
}
async function loadDatasets(preferred) {
  const atStart=$('dataset-select').value;const selected=preferred || atStart || 'device_1';
  const version=state.datasetVersion=(state.datasetVersion || 0)+1;
  const datasets=await api('/api/datasets');if(version!==state.datasetVersion)return;
  const keep=$('dataset-select').value===atStart?selected:$('dataset-select').value;
  state.datasets=datasets;$('dataset-select').replaceChildren();
  for(const device of state.datasets)$('dataset-select').append(new Option(`${device.label} · ${device.bags} bags`,device.id));
  $('dataset-select').value=keep;
}
function scopeView() {
  const folder=$('process-scope').value==='folder';$('batch-options').hidden=!folder;
  $('bag-select-label').textContent=folder?'Preview recording · every bag below will be processed':'Recording';markTopics();
}
async function loadBags(preferred) {
  const dataset=$('dataset-select').value;const version=state.catalogueVersion=(state.catalogueVersion || 0)+1;
  state.bags=[];state.metadata=null;markTopics();
  const bags=await api(`/api/bags?dataset=${encodeURIComponent(dataset)}`);
  if(version!==state.catalogueVersion || dataset!==$('dataset-select').value)return;
  state.bags=bags;
  const select=$('bag-select');select.replaceChildren(new Option('Choose a recording…',''));
  for(const bag of bags)select.append(new Option(`${bag.filename} · ${bytes(bag.size_bytes)}`,bag.name));
  $('dataset-hint').textContent=`bagfiles/${dataset}/ · ${bags.length} recordings · ${bytes(bags.reduce((total,b)=>total+b.size_bytes,0))}${bags.length?'':' · Import a .bag to begin.'}`;
  const defaultName=preferred || bags.find(b=>b.name.includes('192433'))?.name || bags[0]?.name;
  if(defaultName){select.value=defaultName;await inspectBag();}
  else {state.metadata=null;$('topic-table').replaceChildren();$('bag-facts').replaceChildren(element('span','This device folder is empty.'));$('recorded-at').textContent='';for(const id of ['camera-topic','livox-topic']){$(id).replaceChildren();$(id).disabled=true;}}
  scopeView();
}
async function inspectBag() {
  const name=$('bag-select').value;const version=++state.inspectVersion;state.metadata=null;notify('');
  for(const id of ['camera-topic','livox-topic']){$(id).replaceChildren();$(id).disabled=true;}
  $('topic-table').replaceChildren();$('bag-facts').replaceChildren();$('recorded-at').textContent='';markTopics();
  if(!name)return;
  $('topic-hint').textContent='Reading the recording metadata…';
  try {
    const meta=await api(`/api/bag-info?name=${encodeURIComponent(name)}`);
    if($('bag-select').value!==name || version!==state.inspectVersion)return;
    state.metadata=meta;
    topicSelect('camera-topic',meta.topics,'sensor_msgs/Image',meta.suggested_camera_topic);
    topicSelect('livox-topic',meta.topics,'sensor_msgs/PointCloud2',meta.suggested_livox_topic);
    $('phase-group').value=meta.suggested_phase_group;
    $('bag-facts').replaceChildren(element('span',`${meta.duration_s.toFixed(1)} s duration`),element('span',bytes(meta.size_bytes)),element('span',`${meta.topics.length} topics`));
    $('topic-table').replaceChildren();
    for(const topic of meta.topics) {
      const tr=element('tr');tr.dataset.name=topic.name;
      const nameCell=element('td',topic.name);nameCell.append(element('small',topic.type));
      tr.append(nameCell,element('td',topic.messages.toLocaleString()),element('td',number(topic.frequency_hz,1)));$('topic-table').append(tr);
    }
    $('recorded-at').textContent=`Recorded ${new Intl.DateTimeFormat('en-AU',{dateStyle:'medium',timeStyle:'short',timeZone:'Australia/Sydney'}).format(new Date(meta.start_s*1000))} · Sydney time`;
    $('topic-hint').textContent=meta.suggested_camera_topic && meta.suggested_livox_topic ? 'Camera and Livox Avia topics matched automatically. Change either selection if needed.' : 'Automatic selection is incomplete. Choose both compatible topics before processing.';
    markTopics();
  }catch(error){if($('bag-select').value===name && version===state.inspectVersion){notify(error.message);$('topic-hint').textContent='Recording metadata could not be read. Automatic folder processing can report this bag as failed and continue.';markTopics();}}
}
function config() {
  for(const id of ['roi-x','roi-y','roi-w','roi-h','timing-range']){
    if(!$(id).value.trim() || !$(id).checkValidity())throw new Error('Check the camera crop and timing search settings. All fields need values within their displayed limits.');
  }
  if(!($('process-scope').value==='folder' && $('batch-auto-groups').checked) && !$('phase-group').value.trim())throw new Error('Enter a shared setup / illumination group.');
  return {camera_topic:$('camera-topic').value,livox_topic:$('livox-topic').value,phase_group:$('phase-group').value,
    camera_roi:['roi-x','roi-y','roi-w','roi-h'].map(id=>Number($(id).value)),timing_search_ms:Number($('timing-range').value)};
}
async function start() {
  if(state.starting || state.busy)return;
  state.starting=true;notify('');markTopics();
  try {
    const folder=$('process-scope').value==='folder';
    const payload=folder?{dataset:$('dataset-select').value,config:config(),auto_topics:$('batch-auto-topics').checked,auto_groups:$('batch-auto-groups').checked}:{bag:$('bag-select').value,config:config()};
    const result=await api(folder?'/api/batches':'/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    state.currentJob=result.id;state.busy=true;state.previewKeys={};resetPreviews();$('preview-note').textContent='Measured data appears here as the run progresses.';$('progress-panel').hidden=false;$('cancel').disabled=false;
    $('batch-progress').hidden=!folder;
    page('workbench');await poll();
  }catch(error){notify(error.message);}finally{state.starting=false;markTopics();}
}
function resetPreviews(){
  for(const sensor of ['flir','livox']){$(`${sensor}-preview`).hidden=true;$(`${sensor}-preview`).removeAttribute('src');$(`${sensor}-placeholder`).hidden=false;$(`${sensor}-live-label`).textContent='Awaiting capture';delete state.previewKeys[sensor];}
  $('trace-panel').hidden=true;
}
const stageNames={queued:'Preparing your recording',starting:'Preparing your recording',batch_start:'Preparing the next recording',batch_aggregate:'Comparing all captures and scans',extract:'Reading selected sensor data',flir_calibration:'Calibrating camera appearance',flir_detection:'Detecting camera angles',flir_validation:'Validating camera detections',livox_features:'Measuring Livox return patterns',livox_detection:'Detecting Livox angles',livox_validation:'Validating Livox detections',scan_variability:'Calculating scan variability and local RPM',timing:'Analyzing sensor timing',export:'Saving reports and figures',complete:'Capture processing complete',cancelled:'Run cancelled',failed:'Processing stopped',cancelling:'Cancelling run'};
function drawTrace(trace) {
  const canvas=$('live-chart');const ratio=window.devicePixelRatio || 1;const width=Math.max(canvas.clientWidth-36,400);canvas.width=width*ratio;canvas.height=240*ratio;
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,width,240);
  const all=[...trace.FLIR,...trace.Livox];if(!all.length)return;
  const maxT=Math.max(...all.map(p=>p.t),1);const left=40,top=14,h=180,w=width-65;
  ctx.font='10px system-ui';ctx.fillStyle='#82978a';ctx.strokeStyle='#e5eee4';
  for(const value of [0,90,180,270,360]){const y=top+h-value/360*h;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(left+w,y);ctx.stroke();ctx.fillText(`${value}°`,3,y+3);}
  for(const [sensor,color] of [['FLIR','#15766e'],['Livox','#dc7937']]){
    ctx.fillStyle=color;for(const p of trace[sensor]){ctx.beginPath();ctx.arc(left+p.t/maxT*w,top+h-p.angle/360*h,1.8,0,Math.PI*2);ctx.fill();}
  }
  ctx.fillStyle='#82978a';ctx.fillText('0 s',left,223);ctx.fillText(`${maxT.toFixed(1)} s`,left+w-32,223);
  ctx.fillStyle='#15766e';ctx.fillText('● Camera',width/2-55,223);ctx.fillStyle='#dc7937';ctx.fillText('● Livox',width/2+5,223);
}
function progressView(job) {
  $('progress-panel').hidden=false;$('stage-title').textContent=stageNames[job.stage] || job.stage;$('stage-message').textContent=job.message;
  $('percent').textContent=`${number(job.percent,0)}%`;$('progress-fill').style.width=`${job.percent}%`;$('progress-track').setAttribute('aria-valuenow',job.percent);
  $('processed').textContent=(job.processed || 0).toLocaleString();$('remaining').textContent=(job.remaining || 0).toLocaleString();
  $('elapsed').textContent=job.elapsed_s<60?`${number(job.elapsed_s,0)}s`:`${Math.floor(job.elapsed_s/60)}m ${Math.floor(job.elapsed_s%60)}s`;
  const limits={extract:[0,18],flir:[18,55],livox:[55,89],timing:[89,94],export:[94,100]};
  const capturePercent=job.capture_percent ?? job.percent;
  for(const [stage,[lo,hi]] of Object.entries(limits)){const e=$(`step-${stage}`);e.classList.toggle('done',capturePercent>=hi);e.classList.toggle('current',capturePercent>=lo && capturePercent<hi);}
  $('batch-progress').hidden=!job.batch;
  if(job.batch){
    const batch=job.batch;$('batch-progress-summary').textContent=`${batch.finished} / ${batch.total} finished · ${batch.completed} completed · ${batch.failed} failed · ${batch.remaining} remaining${batch.current_bag?` · Current: ${batch.current_bag.split('/').pop()} (${number(capturePercent,0)}%)`:''}`;
    $('batch-queue').replaceChildren();
    for(const entry of batch.entries){const row=element('tr');const m=entry.metrics || {};row.append(element('td',entry.bag_path.split('/').pop()),element('td',entry.status),element('td',number(m.camera_rpm,4)),element('td',number(m.livox_rpm,4)),element('td',`${number(m.livox_std_deg)}°`));if(entry.error)row.title=entry.error;$('batch-queue').append(row);}
  }
  for(const sensor of ['flir','livox']){
    const preview=job.previews?.[sensor];if(!preview){$(`${sensor}-preview`).hidden=true;$(`${sensor}-preview`).removeAttribute('src');$(`${sensor}-placeholder`).hidden=false;$(`${sensor}-live-label`).textContent='Awaiting capture';delete state.previewKeys[sensor];continue;}
    const key=`${preview.path}/${preview.frame}/${preview.relative_angle_deg}`;
    if(state.previewKeys[sensor]!==key){$(`${sensor}-preview`).src=artifact(job.id,preview.path)+`?v=${encodeURIComponent(key)}`;state.previewKeys[sensor]=key;}
    $(`${sensor}-preview`).hidden=false;$(`${sensor}-placeholder`).hidden=true;
    $(`${sensor}-live-label`).textContent=`Frame ${preview.frame} · ${preview.relative_angle_deg===null?'raw data':`${number(preview.relative_angle_deg,2)}° relative`}`;
  }
  const trace={FLIR:job.trace?.FLIR || [],Livox:job.trace?.Livox || []};$('trace-panel').hidden=!trace.FLIR.length && !trace.Livox.length;drawTrace(trace);
}
async function poll() {
  clearTimeout(state.poll);if(!state.currentJob)return;
  const identifier=state.currentJob;
  try {
    const job=await api(`/api/jobs/${encodeURIComponent(identifier)}`);if(identifier!==state.currentJob)return;progressView(job);
    if(['running','queued','cancelling'].includes(job.status)){state.busy=true;markTopics();state.poll=setTimeout(poll,700);}
    else{
      state.busy=false;state.currentJob=null;$('cancel').disabled=true;markTopics();
      try{await loadRuns();}catch(error){notify(error.message);}
      if(job.status==='complete'){$('preview-note').textContent='Processing complete. Open the saved result for all detections and figures.';if(!$('workbench').hidden)await showResult(job.id);else notify(job.message);}
      else{notify(job.message);$('preview-note').textContent='Partial files remain in the saved run folder.';}
    }
  }catch(error){if(identifier===state.currentJob){notify(error.message);if(state.busy)state.poll=setTimeout(poll,2000);}}
}
async function loadRuns() {
  const version=state.runsVersion=(state.runsVersion || 0)+1;const selected=new Set(Array.from(document.querySelectorAll('.run-check:checked')).map(e=>e.value));
  const runs=await api('/api/runs');if(version!==state.runsVersion)return;state.runs=runs;$('run-count').textContent=state.runs.length;$('run-table').replaceChildren();
  for(const run of state.runs) {
    const tr=element('tr');const checkCell=element('td');
    if(run.status==='complete' && run.kind==='detection'){const checkbox=element('input');checkbox.type='checkbox';checkbox.value=run.id;checkbox.checked=selected.has(run.id);checkbox.className='run-check';checkbox.setAttribute('aria-label',`Select ${run.bag} run ${run.id}`);checkbox.dataset.bag=run.bag_path || run.bag;checkbox.addEventListener('change',updateCompare);checkCell.append(checkbox);}
    const recording=element('td',run.bag);recording.append(element('small',run.id));const status=element('td');status.append(element('span',run.status,`status-badge ${run.status}`));
    const action=element('td');const button=element('button',run.status==='complete'?'View results':'View progress','secondary small');
    if(run.message)tr.title=run.message;
    button.addEventListener('click',async()=>{try{if(run.status==='complete')await showResult(run.id);else if(['queued','running','cancelling'].includes(run.status)){state.currentJob=run.id;state.busy=true;$('cancel').disabled=run.status==='cancelling';page('workbench');await poll();}else await showPartial(run.id);}catch(error){notify(error.message);}});action.append(button);
    if(run.status==='failed' || run.status==='cancelled')button.textContent='Inspect saved files';
    tr.append(checkCell,recording,status,element('td',run.flir_std_deg===null?'—':`${number(run.flir_std_deg)}°`),element('td',run.livox_std_deg===null?'—':`${number(run.livox_std_deg)}°`),action);$('run-table').append(tr);
  }
  if(!state.runs.length){const tr=element('tr');const td=element('td','Your first completed recording will appear here.','empty-cell');td.colSpan=6;tr.append(td);$('run-table').append(tr);}
  updateCompare();
}
function updateCompare(){
  const checks=Array.from(document.querySelectorAll('.run-check'));const selected=checks.filter(c=>c.checked);const bags=new Set(selected.map(c=>c.dataset.bag));
  $('compare-runs').disabled=state.comparing || selected.length<4 || bags.size!==selected.length;
  $('select-latest').checked=selected.length>0 && bags.size===new Set(checks.map(c=>c.dataset.bag)).size && bags.size===selected.length;
  $('select-latest').indeterminate=selected.length>0 && !$('select-latest').checked;
}
function metric(label,value,unit,foot) {
  const card=element('div',undefined,'card metric-card');card.append(element('div',label,'metric-label'));
  const big=element('div',value,'metric-value');big.append(element('span',` ${unit}`,'metric-unit'));card.append(big,element('div',foot,'metric-foot'));return card;
}
function figure(id,name,caption) {
  const fig=element('figure',undefined,'card figure-card');const img=element('img');img.src=artifact(id,`figures/${name}.png`);img.alt=caption;img.loading='lazy';fig.append(img,element('figcaption',caption));return fig;
}
function metricTable(result) {
  const card=element('div',undefined,'card result-table');card.append(element('h2','Repeatability and cross-modal agreement'));
  const table=element('table');const head=element('thead');const hr=element('tr');for(const name of ['Metric','Camera held-out repeatability','Livox held-out agreement','Livox held-out offline agreement'])hr.append(element('th',name));head.append(hr);table.append(head);
  const body=element('tbody');const a=result.timing.agreement;
  for(const [label,key] of [['STD','std_deg'],['MAE','mae_deg'],['RMSE','rmse_deg'],['95th percentile','p95_deg']]){const row=element('tr');row.append(element('td',label),element('td',`${number(result.flir.heldout_residual[key],4)}°`),element('td',`${number(a.heldout_raw[key],4)}°`),element('td',`${number(a.heldout_offline_smoothed[key],4)}°`));body.append(row);}
  table.append(body);card.append(table);return card;
}
function timingBox(result) {
  const lag=result.timing.single_bag_lag;const box=element('div',undefined,'card timing-box');box.append(element('h2',lag.status==='NOT_IDENTIFIABLE_FROM_THIS_BAG'?'Actual sensor offset: unresolved':'Time-shift candidate from varying motion'));
  box.append(element('p',lag.reason));box.append(element('p',`Conditional profile minimum ${number(lag.candidate_tau_ms,1)} ms · phase-profile 95% range [${number(lag.profile_95_low_ms,1)}, ${number(lag.profile_95_high_ms,1)}] ms · block-bootstrap 95% range [${number(lag.block_bootstrap_95_low_ms,1)}, ${number(lag.block_bootstrap_95_high_ms,1)}] ms.`));
  box.append(element('p','A constant phase is fitted separately for every time shift. A conditional minimum is not an established physical offset. Positive tau means Livox content leads camera on bag-record time; negative tau means Camera leads.'));
  box.append(element('p',`Camera nonlinear-motion scatter ${number(lag.camera_nonconstant_motion_std_deg,3)}°; estimated camera scatter ${number(lag.camera_noise_floor_deg,3)}°. Livox header clock: ${result.timing.clocks.livox.domain.replaceAll('_',' ')}. Different clock epochs cannot be subtracted directly.`));
  return box;
}
function renderDetection(result, initialTab='overview') {
  const root=$('result-body');root.replaceChildren();const agreement=result.timing.agreement;const lag=result.timing.single_bag_lag;
  const grid=element('div',undefined,'metric-grid');grid.append(
    metric('Camera · held-out STD',number(result.flir.heldout_residual.std_deg),'°',`${result.flir.frames.toLocaleString()} native camera frames`),
    metric('Livox · held-out STD',number(agreement.heldout_raw.std_deg),'°','Per-cloud disagreement with camera'),
    metric('Livox · offline STD',number(agreement.heldout_offline_smoothed.std_deg),'°',`${number(result.livox.future_lookahead_s,1)} s of future data used`),
    metric('Actual sensor offset',lag.status==='NOT_IDENTIFIABLE_FROM_THIS_BAG'?'Unresolved':'Candidate','',lag.status==='NOT_IDENTIFIABLE_FROM_THIS_BAG'?'Constant phase and time delay cannot be separated reliably.':'Conditional estimate; physical synchronization uncalibrated.'));
  root.append(grid);
  const note=element('div',undefined,'card result-note');note.append(element('strong',`Camera ${number(result.flir.rpm,5)} RPM · Livox ${number(result.livox.rpm,5)} RPM. `));note.append(document.createTextNode('Each sensor infers its own speed. These metrics measure repeatability and agreement; no encoder validates absolute accuracy. Livox angles are relative, and the camera geometry zero is approximate.'));
  if(result.flir.status==='REVIEW' || result.livox.status==='REVIEW')note.append(element('p','Detection quality requires review. Inspect branch flags and validation plots before using these results.'));
  root.append(note);
  root.append(TimingExplanation.mount(result));
  if(result.parent_batch){const back=element('button','← Back to device folder results','secondary');back.addEventListener('click',()=>showResult(result.parent_batch).catch(e=>notify(e.message)));root.append(back);}
  const tabs=element('div',undefined,'tabs');const content=element('div');const choices=[['overview','Overview'],['flir','Camera detection'],['livox','Livox detection']];if(result.scans)choices.push(['scans','Individual scans']);choices.push(['timing','Timing evidence']);
  for(const [key,label] of choices){const button=element('button',label,'tab');button.dataset.tab=key;button.addEventListener('click',()=>selectTab(key));tabs.append(button);}root.append(tabs,content);
  function selectTab(key){
    for(const button of tabs.children)button.classList.toggle('active',button.dataset.tab===key);content.replaceChildren();
    if(key==='overview'){content.append(figure(result.id,'overview','Both sensors on bag-record time, with one constant angular phase alignment. This alignment does not establish a physical time offset.'),metricTable(result),figure(result.id,'error_matrix','Correlation of detection residuals; the shared angular ramp is excluded.'));}
    if(key==='flir'){content.append(figure(result.id,'flir_detection_stages','Measured grayscale rotor crops, fitted ellipse and subpixel polar intensity samples. Geometry angle is approximate.'),figure(result.id,'flir_quality','Relative motion, held-out residual distribution, appearance features and per-image residuals.'));}
    if(key==='livox'){content.append(figure(result.id,'livox_detection_stages','Only real returned rays are displayed. Depth filtering and annulus selection retain the moving near-surface evidence.'),figure(result.id,'livox_quality','Relative cloud detections, optional offline smoothing, retained return counts, harmonic evidence and disagreement distributions.'));}
    if(key==='scans'){content.append(figure(result.id,'scan_variability','Every Livox scan: point counts, target depth spread, angle residuals and independent local RPM. Local slopes use up to one second of future data.'));scanExplorer(result,content);}
    if(key==='timing'){content.append(timingBox(result),figure(result.id,'timing_profile','Joint phase/time profile and block-bootstrap timing distribution. A broad or boundary result is weak evidence.'),figure(result.id,'clock_diagnostics','Affine mapping of recorded header and bag clocks. These mapping residuals are not exposure-to-ray delay.'));}
  }
  selectTab(choices.some(([key])=>key===initialTab)?initialTab:'overview');
}
function renderComparison(result) {
  const model=result.multi_timing;const root=$('result-body');root.replaceChildren();const grid=element('div',undefined,'metric-grid');
  grid.append(metric('Cross-speed candidate',number(model.candidate_tau_ms,1),'ms','Stable per-setup phase is assumed.'),metric('Standard error',number(model.standard_error_ms,1),'ms','Student-t interval reported below.'),metric('Phase-fit residual STD',number(model.phase_residual_std_deg),'°',`${model.degrees_of_freedom} residual degrees of freedom`),metric('Independent captures',String(model.bags),'bags',`${model.groups.length} setup / illumination groups`));root.append(grid);
  const box=element('div',undefined,'card timing-box');box.append(element('h2',model.status.replaceAll('_',' ').toLowerCase()),element('p',`95% interval: [${number(model.student_t_95_low_ms,1)}, ${number(model.student_t_95_high_ms,1)}] ms. ${model.reason}`),element('p','This remains a timing candidate, not calibrated physical synchronization. Positive tau means Livox content leads camera on bag-record time. No encoder or native per-ray acquisition timing is available.'));root.append(box,TimingExplanation.mount(result),figure(result.id,'cross_speed_timing','Separate fixed phase per setup, shared time-shift slope across signed rotation rates.'));
}
function scanExplorer(result, root) {
  const card=element('section',undefined,'card scan-explorer');card.id='scan-explorer';
  card.append(element('h2','Inspect any individual Livox scan'),element('p',result.scans.explanation,'field-hint'));
  const controls=element('div',undefined,'scan-controls');const label=element('label','Scan index · starts at zero');
  const index=element('input');index.id='scan-index';index.type='number';index.min=0;index.max=result.scans.scans-1;index.value=0;label.htmlFor=index.id;
  const slider=element('input');slider.id='scan-slider';slider.type='range';slider.min=0;slider.max=result.scans.scans-1;slider.value=0;slider.setAttribute('aria-label','Choose Livox scan');
  const download=element('a','Download every scan as CSV ↓','text-button');download.href=artifact(result.id,'scans/scan_metrics.csv')+'?download=1';
  controls.append(label,index,slider,download);card.append(controls);
  const detail=element('div',undefined,'scan-detail');const image=element('img');image.id='scan-preview';image.alt='Measured Livox returns from the selected scan';
  const stats=element('div',undefined,'scan-stats');stats.id='scan-stats';detail.append(image,stats);card.append(detail);
  const tableWrap=element('div',undefined,'table-scroll');const table=element('table');const head=element('thead');const hr=element('tr');
  for(const title of ['Scan','Time (s)','Input points','Target points','Relative angle','Local RPM','Depth STD (m)','Status'])hr.append(element('th',title));head.append(hr);table.append(head);
  const body=element('tbody');body.id='scan-table';table.append(body);tableWrap.append(table);card.append(tableWrap);
  const pager=element('div',undefined,'scan-pager');const prev=element('button','← Previous scans','secondary small');prev.id='scans-previous';const info=element('span',undefined,'subtle');const next=element('button','Next scans →','secondary small');next.id='scans-next';pager.append(prev,info,next);card.append(pager);root.append(card);
  let pageStart=0,selected=-1,selectionVersion=0,pageVersion=0;
  image.addEventListener('error',()=>{if(card.isConnected){image.hidden=true;stats.append(element('p','The measured scan preview could not be loaded. Its numeric data and saved arrays remain available.','field-hint'));}});
  image.addEventListener('load',()=>{image.hidden=false;});
  async function selectScan(value) {
    const n=Number(value);if(String(value).trim()==='' || !Number.isInteger(n) || n<0 || n>=result.scans.scans){index.value=selected<0?0:selected;notify(`Choose a whole scan index between 0 and ${result.scans.scans-1}.`);return;}
    const version=++selectionVersion;selected=n;index.value=n;slider.value=n;image.hidden=true;image.removeAttribute('src');stats.textContent='Loading measured scan data…';
    try {
      const data=await api(`/api/runs/${encodeURIComponent(result.id)}/scans?start=${n}&limit=1`);
      if(!card.isConnected || version!==selectionVersion)return;
      const row=data.rows[0];if(!row)throw new Error('This scan was not found.');
      image.alt=`Measured Livox returns from scan ${n}`;image.src=`/api/runs/${encodeURIComponent(result.id)}/scan-preview?scan=${n}`;
      stats.replaceChildren(element('h3',`Scan ${n} / ${result.scans.scans-1}`));
      for(const [label,value] of [['Recording time',`${number(row.time_s,3)} s`],['Input points',Math.round(row.input_point_count).toLocaleString()],['Target returns',Math.round(row.target_point_count).toLocaleString()],['Relative angle',`${number(row.relative_angle_deg,3)}°`],['Local phase-derived RPM',number(row.local_rpm,5)],['Target depth mean ± STD',`${number(row.target_depth_mean_m,4)} ± ${number(row.target_depth_std_m,4)} m`],['Held-out motion residual',`${number(row.heldout_motion_residual_deg,4)}°`],['Detection quality',row.rejected_branch_boundary?'Rejected: branch boundary':'Registered']]){
        const pair=element('div',undefined,'scan-stat');pair.append(element('span',label),element('strong',value));stats.append(pair);
      }
      for(const tr of body.children)tr.classList.toggle('selected-topic',Number(tr.dataset.index)===n);
    }catch(error){if(card.isConnected && version===selectionVersion)stats.textContent=error.message;}
  }
  async function loadPage() {
    const version=++pageVersion;const start=pageStart;prev.disabled=true;next.disabled=true;
    try {
      const data=await api(`/api/runs/${encodeURIComponent(result.id)}/scans?start=${start}&limit=100`);if(!card.isConnected || version!==pageVersion)return;body.replaceChildren();
      for(const row of data.rows){const tr=element('tr');tr.dataset.index=row.scan_index;tr.classList.toggle('selected-topic',row.scan_index===selected);const cell=element('td');const button=element('button',String(row.scan_index),'text-button');button.addEventListener('click',()=>selectScan(row.scan_index));cell.append(button);tr.append(cell);
        for(const value of [number(row.time_s,2),Math.round(row.input_point_count).toLocaleString(),Math.round(row.target_point_count).toLocaleString(),`${number(row.relative_angle_deg,2)}°`,number(row.local_rpm,4),number(row.target_depth_std_m,4),row.rejected_branch_boundary?'Rejected':'Registered'])tr.append(element('td',value));body.append(tr);}
      info.textContent=`Scans ${start}–${Math.min(start+99,data.total-1)} of ${data.total}`;
    }catch(error){if(card.isConnected && version===pageVersion)notify(error.message);}
    finally{if(card.isConnected && version===pageVersion){prev.disabled=start===0;next.disabled=start+100>=result.scans.scans;}}
  }
  index.addEventListener('change',()=>selectScan(index.value));slider.addEventListener('change',()=>selectScan(slider.value));
  prev.addEventListener('click',()=>{pageStart=Math.max(0,pageStart-100);loadPage();});next.addEventListener('click',()=>{pageStart+=100;loadPage();});
  selectScan(0);loadPage();
}
function renderBatch(result) {
  const root=$('result-body');root.replaceChildren();const totals=result.totals;const model=result.overall_timing;
  const grid=element('div',undefined,'metric-grid');grid.append(
    metric('Completed captures',`${totals.completed_bags} / ${totals.requested_bags}`,'bags',`${totals.failed_bags} failures; individual outputs retained.`),
    metric('Every Livox scan',totals.livox_clouds.toLocaleString(),'clouds','All recorded clouds in successful captures.'),
    metric('Decoded LiDAR points',`${(totals.input_points/1e6).toFixed(2)}`,'million','Motion inference uses the measured target region.'),
    metric('Overall time-shift candidate',model.candidate_tau_ms===null?'Unresolved':number(model.candidate_tau_ms,1),model.candidate_tau_ms===null?'':'ms','Physical sensor synchronization remains uncalibrated.'));root.append(grid);
  const note=element('div',undefined,'card result-note');note.append(element('strong',`${totals.camera_frames.toLocaleString()} camera frames · ${totals.livox_clouds.toLocaleString()} Livox scans. `),document.createTextNode(result.interpretation));root.append(note);
  root.append(TimingExplanation.mount(result));
  const issues=result.entries.filter(e=>e.status!=='complete');if(issues.length){const warning=element('div',undefined,'card timing-box');warning.append(element('h2','Captures requiring attention'));for(const entry of issues)warning.append(element('p',`${entry.bag_path}: ${entry.error || entry.status}`));root.append(warning);}
  const tableCard=element('section',undefined,'card result-table');tableCard.append(element('h2','Each capture: speed, scan variability and agreement'),element('p','Local RPM STD includes estimation noise. Target-point STD measures variation across clouds. All angular STDs below are held-out repeatability or disagreement.','field-hint'));
  const wrap=element('div',undefined,'table-scroll');const table=element('table');table.id='batch-captures';const head=element('thead');const hr=element('tr');
  for(const title of ['Capture','Scans','Camera RPM','Livox RPM','Local RPM STD','Target points ± STD','Camera STD','Livox STD','Offline STD','Inspect'])hr.append(element('th',title));head.append(hr);table.append(head);const body=element('tbody');
  for(const capture of result.captures){const tr=element('tr');tr.append(element('td',capture.bag));for(const value of [String(capture.livox_clouds),number(capture.camera_rpm,4),number(capture.livox_rpm,4),number(capture.livox_local_rpm_std,4),`${number(capture.target_points_mean,0)} ± ${number(capture.target_points_std,0)}`,`${number(capture.flir_std_deg)}°`,`${number(capture.livox_std_deg)}°`,`${number(capture.livox_offline_std_deg)}°`])tr.append(element('td',value));const cell=element('td');const button=element('button','View scans →','text-button');button.addEventListener('click',()=>showResult(capture.run_id,'scans').catch(e=>notify(e.message)));cell.append(button);tr.append(cell);body.append(tr);}
  table.append(body);wrap.append(table);tableCard.append(wrap);root.append(tableCard);
  const tabs=element('div',undefined,'tabs');const content=element('div');
  for(const [key,label] of [['overview','Folder overview'],['variability','Scan variability'],['timing','Overall timing']]){const button=element('button',label,'tab');button.dataset.tab=key;button.addEventListener('click',()=>selectTab(key));tabs.append(button);}root.append(tabs,content);
  function selectTab(key){
    for(const button of tabs.children)button.classList.toggle('active',button.dataset.tab===key);content.replaceChildren();
    if(key==='overview' && result.captures.length)content.append(figure(result.id,'batch_overview','Every capture: independent signed RPM, held-out angular scatter, and target-return count variability. RPM error bars show fold sensitivity.'),figure(result.id,'batch_return_distributions','Point-count distributions use every scan from each successful capture.'));
    if(key==='variability' && result.captures.length)content.append(figure(result.id,'batch_variability_matrix','Within-capture held-out residual STD in 20 time bins; colors reveal periods with noisier detection.'),figure(result.id,'batch_scan_traces','Each recording has its own scan-count and local RPM traces. A centered two-second slope uses future data; its variability includes estimation noise.'));
    if(key==='timing'){
      const box=element('section',undefined,'card timing-box');box.id='batch-timing';box.append(element('h2',model.candidate_tau_ms===null?'Overall sensor offset: unresolved':`Overall time-shift candidate: ${number(model.candidate_tau_ms,2)} ms`),element('p',model.reason));
      if(model.candidate_tau_ms!==null)box.append(element('p',`95% Student-t interval [${number(model.student_t_95_low_ms,2)}, ${number(model.student_t_95_high_ms,2)}] ms · standard error ${number(model.standard_error_ms,2)} ms · phase-fit residual STD ${number(model.phase_residual_std_deg,3)}° · ${model.bags} distinct captures.`));
      box.append(element('p','This is not a calibrated physical offset. The model assumes stable empirical phase and sensor pose within each setup group. Individual constant-speed lag minima are not averaged.'),element('p',model.sign_convention));content.append(box);
      if(model.excluded_duplicate_source_bags?.length)box.append(element('p',`Identical source copies excluded from timing replicates: ${model.excluded_duplicate_source_bags.join(', ')}. Their individual detections remain available.`));
      if(model.candidate_tau_ms!==null)content.append(figure(result.id,'overall_timing','A shared slope across signed rotation rates separates time shift from a fitted fixed phase within each setup group. Statistical uncertainty excludes systematic calibration errors.'));
    }
  }
  selectTab('overview');
}
async function showResult(id, initialTab) {
  const version=++state.resultVersion;notify('');
  let result;try{result=await api(`/api/runs/${encodeURIComponent(id)}/result`);}catch(error){if(version===state.resultVersion)throw error;return;}
  if(version!==state.resultVersion)return;state.currentResult=result;page('results-panel');$('file-list').replaceChildren();$('report-link').hidden=false;$('download-link').hidden=false;
  $('result-title').textContent=result.kind==='comparison'?'Cross-speed timing comparison':result.kind==='batch'?`${result.bag} · folder results`:result.bag;
  $('result-subtitle').textContent=result.kind==='comparison'?`${result.multi_timing.bags} distinct recordings · inspectable phase and timing evidence`:result.kind==='batch'?`${result.totals.completed_bags} completed recordings · every scan and overall timestamp analysis`:`${result.config.camera_topic} + ${result.config.livox_topic} · saved run ${result.id}`;
  $('report-link').href=artifact(id,'report.html');$('download-link').href=`/api/runs/${encodeURIComponent(id)}/download`;
  try{if(result.kind==='comparison')renderComparison(result);else if(result.kind==='batch')renderBatch(result);else renderDetection(result,initialTab);}
  catch(error){$('result-body').replaceChildren(element('p','The saved result has missing or unsupported fields. Inspect its files below or rerun this capture.','notice'));notify(error.message);}
  await loadFileList(id,version);
  if(version===state.resultVersion)window.scrollTo({top:0,behavior:'smooth'});
}
async function loadFileList(id,version){
  let files;try{files=await api(`/api/runs/${encodeURIComponent(id)}/files`);}catch(error){if(version===state.resultVersion)throw error;return;}
  if(version!==state.resultVersion)return;$('file-list').replaceChildren();
  for(const file of files){const link=element('a',file.path);link.href=artifact(id,file.path)+'?download=1';link.append(element('span',file.size_bytes<1e6?`${(file.size_bytes/1000).toFixed(1)} KB`:bytes(file.size_bytes)));$('file-list').append(link);}
}
async function showPartial(id){
  const version=++state.resultVersion;const job=await api(`/api/jobs/${encodeURIComponent(id)}`);if(version!==state.resultVersion)return;page('results-panel');state.currentResult=null;notify('');
  $('result-title').textContent=`${job.bag || id} · saved files`;$('result-subtitle').textContent=`${job.status} · ${id}`;$('file-list').replaceChildren();
  $('report-link').removeAttribute('href');$('download-link').removeAttribute('href');
  $('report-link').hidden=true;$('download-link').hidden=true;
  const note=element('section',undefined,'card timing-box');note.append(element('h2','This run did not produce a complete result'),element('p',job.message || 'Inspect the preserved files for details.'),element('p','You can download individual files below. Start a new run to retry processing.'));
  $('result-body').replaceChildren(note);await loadFileList(id,version);$('file-list').parentElement.open=true;
}
async function compare() {
  if(state.comparing)return;const ids=Array.from(document.querySelectorAll('.run-check:checked')).map(e=>e.value);state.comparing=true;updateCompare();notify('');
  $('compare-runs').textContent='Checking source captures and fitting offset…';
  try {const answer=await api('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({runs:ids})});await loadRuns();await showResult(answer.id);}
  catch(error){notify(error.message);}finally{state.comparing=false;$('compare-runs').textContent='Compare selected runs →';updateCompare();}
}
function importBag(event) {
  const file=event.target.files[0];if(!file || state.importing)return;
  if(file.size>8*1024**3 || !file.name.endsWith('.bag')){notify('Choose a ROS1 .bag file of at most 8 GB.');event.target.value='';return;}
  state.importing=true;event.target.disabled=true;markTopics();notify('');const dataset=$('dataset-select').value;const progress=$('import-progress');progress.hidden=false;progress.textContent='Uploading recording…';
  const data=new FormData();data.append('file',file);data.append('dataset',dataset);const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload');
  const finish=()=>{state.importing=false;event.target.value='';event.target.disabled=false;markTopics();};
  xhr.upload.onprogress=e=>{if(e.lengthComputable)progress.textContent=`Importing ${file.name} · ${Math.round(e.loaded/e.total*100)}%`;};
  xhr.onload=async()=>{try{const response=JSON.parse(xhr.responseText);if(xhr.status>=400)throw new Error(response.error || 'The recording could not be imported.');progress.textContent='Recording imported.';const current=$('dataset-select').value;await loadDatasets(current);if($('dataset-select').value===dataset)await loadBags(response.name);}catch(error){progress.textContent='Import failed.';notify(error.message);}finally{finish();}};
  xhr.onerror=()=>{progress.textContent='Import connection failed.';notify('Upload connection failed. Check the device folder before retrying.');finish();};xhr.onabort=()=>{progress.textContent='Import cancelled.';finish();};xhr.send(data);
}
$('bag-select').addEventListener('change',inspectBag);$('camera-topic').addEventListener('change',markTopics);$('livox-topic').addEventListener('change',markTopics);$('start').addEventListener('click',start);
$('dataset-select').addEventListener('change',()=>loadBags().catch(e=>notify(e.message)));$('process-scope').addEventListener('change',scopeView);$('batch-auto-topics').addEventListener('change',markTopics);
$('nav-workbench').addEventListener('click',()=>{state.resultVersion++;page('workbench');});$('nav-results').addEventListener('click',async()=>{state.resultVersion++;page('library');try{await loadRuns();}catch(e){notify(e.message);}});
$('refresh-runs').addEventListener('click',()=>loadRuns().catch(e=>notify(e.message)));$('compare-runs').addEventListener('click',compare);$('bag-upload').addEventListener('change',importBag);
$('select-latest').addEventListener('change',event=>{const bags=new Set();for(const checkbox of document.querySelectorAll('.run-check')){checkbox.checked=event.target.checked && !bags.has(checkbox.dataset.bag);if(checkbox.checked)bags.add(checkbox.dataset.bag);}updateCompare();});
$('cancel').addEventListener('click',async()=>{if(!state.currentJob)return;try{await api(`/api/jobs/${encodeURIComponent(state.currentJob)}/cancel`,{method:'POST'});$('cancel').disabled=true;$('stage-message').textContent='Cancellation requested; preserving partial artifacts.';}catch(error){notify(error.message);}});
$('show-full-frame').addEventListener('click',()=>{if(!state.metadata || !$('camera-topic').value){notify('Select a readable recording and camera topic first.');return;}$('full-frame').hidden=true;$('frame-status').textContent='Loading the recorded camera frame…';$('full-frame').src=`/api/bag-preview?name=${encodeURIComponent($('bag-select').value)}&topic=${encodeURIComponent($('camera-topic').value)}`;if(!$('full-frame-dialog').open)$('full-frame-dialog').showModal();});
$('full-frame').addEventListener('load',()=>{$('full-frame').hidden=false;$('frame-status').textContent='Use this image to check the target location before adjusting the crop.';});
$('full-frame').addEventListener('error',()=>{$('full-frame').hidden=true;$('frame-status').textContent='This frame could not be decoded or loaded. Check the camera encoding and selected topic.';});
$('close-dialog').addEventListener('click',()=>$('full-frame-dialog').close());
async function initialize(){try{await loadDatasets();await Promise.all([loadBags(),loadRuns()]);const active=state.runs.find(r=>['queued','running','cancelling'].includes(r.status));if(active){state.currentJob=active.id;state.busy=true;$('cancel').disabled=false;await poll();}}catch(error){notify(error.message);}}
initialize();
