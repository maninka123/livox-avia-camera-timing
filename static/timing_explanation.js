'use strict';
// Schematic constant-speed illustration. It never changes the inferred result.
window.TimingExplanation = (() => {
  const NS='http://www.w3.org/2000/svg';
  const TEAL='#15766e', ORANGE='#dc7937', INK='#193c39', MUTED='#71817b';
  const finite=value=>typeof value==='number' && Number.isFinite(value);
  const fmt=(value,digits=2)=>Math.abs(value)>0 && Math.abs(value)<.01?value.toPrecision(2):value.toFixed(digits);
  const signed=(value,digits=2)=>`${value>0?'+':''}${fmt(value,digits)}`;
  function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
  function svgNode(tag,attrs={},text){const n=document.createElementNS(NS,tag);for(const [key,value] of Object.entries(attrs))n.setAttribute(key,value);if(text!==undefined)n.textContent=text;return n;}
  function text(svg,x,y,value,attrs={}){svg.append(svgNode('text',{x,y,fill:INK,'font-size':12,...attrs},value));}
  function point(cx,cy,r,angle){const rad=angle*Math.PI/180;return [cx-r*Math.sin(rad),cy-r*Math.cos(rad)];}
  function wheel(svg,cx,cy,r,angle,color,opacity=1){
    const g=svgNode('g',{opacity});g.append(svgNode('circle',{cx,cy,r,fill:'#ffffff',stroke:color,'stroke-width':2}));
    const rotor=svgNode('g',{transform:`rotate(${-angle} ${cx} ${cy})`});
    for(let i=0;i<3;i++){
      const spoke=svgNode('rect',{x:cx-r*.12,y:cy-r*.80,width:r*.24,height:r*.63,rx:r*.11,fill:color,'fill-opacity':.12,stroke:color,'stroke-width':1});
      spoke.setAttribute('transform',`rotate(${i*120} ${cx} ${cy})`);rotor.append(spoke);
    }
    rotor.append(svgNode('circle',{cx,cy:cy-r*.86,r:r*.065,fill:color}));g.append(rotor);
    g.append(svgNode('circle',{cx,cy,r:r*.11,fill:'#ffffff',stroke:color,'stroke-width':2}));svg.append(g);
  }
  function arrow(svg,x1,y1,x2,y2,color){
    svg.append(svgNode('line',{x1,y1,x2,y2,stroke:color,'stroke-width':1.7}));
    const angle=Math.atan2(y2-y1,x2-x1),size=7;
    const a=[x2-size*Math.cos(angle-.45),y2-size*Math.sin(angle-.45)];const b=[x2-size*Math.cos(angle+.45),y2-size*Math.sin(angle+.45)];
    svg.append(svgNode('polygon',{points:`${x2},${y2} ${a.join(',')} ${b.join(',')}`,fill:color}));
  }
  function model(tauMs,rpm,recordTime=1){
    return {tauMs,rpm,deltaDeg:6*rpm*tauMs/1000,
      flirSceneTime:recordTime,livoxSceneTime:recordTime+tauMs/1000,
      flirRecordTime:recordTime,livoxRecordTime:recordTime-tauMs/1000,
      leader:tauMs>0?'Livox':tauMs<0?'Camera':'Neither'};
  }
  function context(result){
    let estimate,speeds,source;
    if(result.kind==='batch'){
      estimate=result.overall_timing;source='Folder timing candidate';
      speeds=result.captures.map(c=>({label:c.bag,rpm:c.camera_rpm}));
    }else if(result.kind==='comparison'){
      estimate=result.multi_timing;source='Cross-speed timing candidate';
      speeds=result.observations.map(o=>({label:o.bag,rpm:o.omega_deg_s/6}));
    }else{
      estimate=result.timing.single_bag_lag;
      source=estimate.status==='NOT_IDENTIFIABLE_FROM_THIS_BAG'?'Conditional minimum · actual offset unresolved':'Single-bag timing candidate';
      speeds=[{label:result.bag,rpm:result.flir.rpm}];
    }
    speeds=speeds.filter(s=>finite(s.rpm));
    const exampleSpeed=!speeds.length;if(exampleSpeed)speeds=[{label:'Illustrative speed; no capture available',rpm:10}];
    return {tau:finite(estimate.candidate_tau_ms)?estimate.candidate_tau_ms:null,estimate,source,speeds,exampleSpeed};
  }
  function mount(result){
    const ctx=context(result);let tau=ctx.tau===null?30:ctx.tau;let capture=0,gain=20,step=0;
    const card=node('section',undefined,'card timing-explainer');card.id='timing-explainer';
    const heading=node('div',undefined,'offset-heading');const title=node('div');title.append(node('p','READ THE OFFSET IN A PHYSICAL SCENE','eyebrow'),node('h2','What does this time offset mean?'));
    const badge=node('span',undefined,'offset-badge');badge.id='offset-source';heading.append(title,badge);card.append(heading);
    const explanation=node('p',undefined,'offset-intro');explanation.id='offset-explanation';card.append(explanation);
    const controls=node('div',undefined,'offset-controls');
    const speedLabel=node('label','Capture / signed reference speed');const speed=node('select');speed.id='offset-speed';speedLabel.htmlFor=speed.id;
    ctx.speeds.forEach((s,i)=>speed.append(new Option(`${s.label} · ${signed(s.rpm,4)} RPM`,i)));speedLabel.append(speed);
    const tauBound=Math.max(2000,Math.abs(tau));
    const tauLabel=node('label','Offset to illustrate (ms)');const input=node('input');input.id='offset-delay';input.type='number';input.min=-tauBound;input.max=tauBound;input.step='any';input.value=fmt(tau,3);tauLabel.htmlFor=input.id;tauLabel.append(input);
    const gainLabel=node('label','Visual expansion');const magnify=node('select');magnify.id='offset-gain';gainLabel.htmlFor=magnify.id;
    for(const value of [1,5,10,20,50,100])magnify.append(new Option(value===1?'Real angular scale · ×1':`Exaggerate angular gap · ×${value}`,value));magnify.value=gain;gainLabel.append(magnify);
    controls.append(speedLabel,tauLabel,gainLabel);card.append(controls);
    const inputMessage=node('p',undefined,'field-hint');inputMessage.id='offset-input-message';inputMessage.setAttribute('role','status');inputMessage.hidden=true;card.append(inputMessage);
    const actions=node('div',undefined,'offset-actions');const reset=node('button',ctx.tau===null?'Reset example':'Use this result’s estimate','text-button');reset.id='offset-reset';
    const download=node('button','Download explanation as SVG ↓','text-button');download.id='offset-download';actions.append(reset,download);card.append(actions);
    const panels=node('div',undefined,'offset-panels');const left=node('section',undefined,'offset-panel');const right=node('section',undefined,'offset-panel');
    left.append(node('p','01 · SAME RECORDED TIME','offset-panel-label'),node('h3','Different scenes inside the two streams'));
    right.append(node('p','02 · SAME PHYSICAL SCENE','offset-panel-label'),node('h3','Matching scenes have different timestamps'));
    const leftSvg=svgNode('svg',{viewBox:'0 0 520 430',role:'img','aria-label':'Flywheel observations at the same recorded time'});leftSvg.id='offset-wheel';
    const rightSvg=svgNode('svg',{viewBox:'0 0 520 430',role:'img','aria-label':'Matching flywheel scene on the two bag timelines'});rightSvg.id='offset-scene';left.append(leftSvg);right.append(rightSvg);
    const leftNote=node('p',undefined,'offset-panel-note');leftNote.id='offset-angular-note';const rightNote=node('p',undefined,'offset-panel-note');rightNote.id='offset-scene-note';left.append(leftNote);right.append(rightNote);panels.append(left,right);card.append(panels);
    const stepLabel=node('label','Step through the illustrative scene','offset-step');const slider=node('input');slider.id='offset-step';slider.type='range';slider.min=0;slider.max=1000;slider.step=10;slider.value=0;stepLabel.htmlFor=slider.id;
    const stamp=node('span',undefined,'mono');stamp.id='offset-reference-time';stepLabel.append(slider,stamp);card.append(stepLabel);
    const formulas=node('div',undefined,'offset-equations');formulas.id='offset-equations';card.append(formulas);
    const caveat=node('p','Idealized constant-speed flywheel, with fixed sensor phase removed. The notch is schematic, not a measured angle zero. Positive angles are drawn counterclockwise. Only the angular gap is magnified; printed times and numeric gaps keep their model values. Bag-record time is shown because the sensor header clocks have different epochs. This illustration does not establish physical exposure or per-ray synchronization.','offset-caveat');card.append(caveat);

    function draw(){
      const rpm=ctx.speeds[capture].rpm;const t=3+step/1000;const m=model(tau,rpm,t);
      const hypothetical=ctx.tau===null || Math.abs(tau-ctx.tau)>1e-7;
      const unresolved=ctx.estimate.status==='NOT_IDENTIFIABLE_FROM_THIS_BAG';
      badge.textContent=hypothetical?(ctx.tau===null?'Example only · no offset estimate available':'Hypothetical offset · result unchanged'):ctx.source;
      badge.classList.toggle('conditional',hypothetical || unresolved);
      explanation.textContent=hypothetical?'Explore what this assumed delay would look like. These controls illustrate timing; they do not refit or correct the recorded data.':unresolved?'This constant-speed bag cannot determine the actual time offset. The illustration uses its conditional lag-profile minimum only; a fixed angular phase could explain the same separation.':'This illustration uses the saved timing candidate. It assumes a stable phase convention; the physical sensor offset remains uncalibrated.';
      const effectiveGain=gain!==1 && Math.abs(m.deltaDeg)>0?Math.min(gain,135/Math.abs(m.deltaDeg)):gain;
      const displayDelta=m.deltaDeg*effectiveGain,base=45+6*rpm*(t-3);
      card.dataset.tauMs=tau;card.dataset.rpm=rpm;card.dataset.deltaDeg=m.deltaDeg;card.dataset.sameSceneGapMs=-tau;
      leftSvg.replaceChildren();rightSvg.replaceChildren();
      leftSvg.append(svgNode('title',{},`At the same bag time, modeled Livox minus Camera angle is ${signed(m.deltaDeg,3)} degrees; visual gap expanded ${fmt(effectiveGain,1)} times.`));
      rightSvg.append(svgNode('title',{},`The same flywheel scene is represented at Camera time ${fmt(t,6)} seconds and Livox time ${fmt(m.livoxRecordTime,6)} seconds.`));
      text(leftSvg,260,25,`Both streams at bag t = ${fmt(t,3)} s`,{'text-anchor':'middle',fill:MUTED,'font-size':13});
      wheel(leftSvg,260,177,116,base,TEAL,.72);wheel(leftSvg,260,177,107,base+displayDelta,ORANGE,.55);
      const a=point(260,177,139,base),b=point(260,177,139,base+displayDelta);
      leftSvg.append(svgNode('line',{x1:260,y1:177,x2:a[0],y2:a[1],stroke:TEAL,'stroke-width':3}));
      leftSvg.append(svgNode('line',{x1:260,y1:177,x2:b[0],y2:b[1],stroke:ORANGE,'stroke-width':3}));
      leftSvg.append(svgNode('circle',{cx:a[0],cy:a[1],r:5,fill:TEAL}),svgNode('circle',{cx:b[0],cy:b[1],r:5,fill:ORANGE}));
      if(Math.abs(displayDelta)%360>.01){const arc=svgNode('path',{d:`M ${a.join(' ')} A 139 139 0 ${Math.abs(displayDelta)%360>180?1:0} ${displayDelta<0?1:0} ${b.join(' ')}`,fill:'none',stroke:INK,'stroke-width':2,'stroke-dasharray':'4 4'});leftSvg.append(arc);}
      text(leftSvg,260,329,`Modeled angular gap: ${signed(m.deltaDeg,3)}°`,{'text-anchor':'middle','font-size':17,'font-weight':600});
      text(leftSvg,260,350,`Drawn gap: ${signed(displayDelta,2)}° · expansion ×${fmt(effectiveGain,1)}`,{'text-anchor':'middle',fill:MUTED,'font-size':12});
      text(leftSvg,65,385,`● Camera scene time ${fmt(m.flirSceneTime,6)} s`,{fill:TEAL});
      text(leftSvg,65,407,`● Livox scene time ${fmt(m.livoxSceneTime,6)} s`,{fill:ORANGE});
      wheel(rightSvg,150,111,60,base,TEAL);wheel(rightSvg,370,111,60,base,ORANGE);
      text(rightSvg,260,118,'=',{'text-anchor':'middle','font-size':27,fill:MUTED});
      text(rightSvg,150,197,'Camera: same notch position',{'text-anchor':'middle',fill:TEAL});
      text(rightSvg,370,197,'Livox: same notch position',{'text-anchor':'middle',fill:ORANGE});
      const gap=Math.abs(tau)/1000;const pad=gap>1e-9?gap*.55:.025;
      const lo=Math.min(t,m.livoxRecordTime)-pad,hi=Math.max(t,m.livoxRecordTime)+pad;
      const x=value=>105+(value-lo)/(hi-lo)*360,xF=x(t),xL=x(m.livoxRecordTime);
      text(rightSvg,20,247,'Camera',{fill:TEAL});text(rightSvg,20,305,'Livox',{fill:ORANGE});
      for(const [y,color] of [[243,TEAL],[301,ORANGE]])arrow(rightSvg,100,y,470,y,color);
      rightSvg.append(svgNode('line',{x1:xF,y1:220,x2:xF,y2:340,stroke:TEAL,'stroke-dasharray':'3 4','stroke-opacity':.45}),svgNode('line',{x1:xL,y1:220,x2:xL,y2:340,stroke:ORANGE,'stroke-dasharray':'3 4','stroke-opacity':.45}));
      rightSvg.append(svgNode('circle',{cx:xF,cy:243,r:6,fill:TEAL}),svgNode('circle',{cx:xL,cy:301,r:6,fill:ORANGE}));
      text(rightSvg,xF,229,`${fmt(t,6)} s`,{'text-anchor':'middle',fill:TEAL});text(rightSvg,xL,327,`${fmt(m.livoxRecordTime,6)} s`,{'text-anchor':'middle',fill:ORANGE});
      if(gap>1e-9)arrow(rightSvg,xF,272,xL,272,INK);
      text(rightSvg,285,263,`t_L − t_F = ${signed(-tau,2)} ms`,{'text-anchor':'middle','font-weight':600});
      text(rightSvg,260,375,'Bag-record time →',{'text-anchor':'middle',fill:MUTED});
      text(rightSvg,260,402,m.leader==='Neither'?'No time separation in this illustration':`${m.leader} content leads by ${fmt(Math.abs(tau),2)} ms`,{'text-anchor':'middle','font-size':15,'font-weight':600});
      leftNote.textContent=`At one recorded timestamp, ${m.leader==='Neither'?'both streams represent the same instant':`${m.leader} represents the later scene in the model`}. The signed angular gap also depends on rotation direction.${effectiveGain<gain?' Expansion is limited to 135° to keep the direction readable.':''}${gain===1 && Math.abs(displayDelta)>=360?' At real scale, orientations repeat every 360°; the printed gap includes full turns.':''}`;
      rightNote.textContent=`To see one matching flywheel scene, compare Camera at ${fmt(t,6)} s with Livox at ${fmt(m.livoxRecordTime,6)} s. Timeline spacing is expanded for readability; it does not show the sensors’ sampling intervals.`;
      stamp.textContent=`Reference bag time ${fmt(t,3)} s`;
      formulas.replaceChildren(node('span',`Angular gap: 6 × (${signed(rpm,4)} RPM) × (${signed(tau,3)} ms ÷ 1000) = ${signed(m.deltaDeg,3)}°`),node('span',`Matching scene: Livox time = Camera time − τ = ${fmt(m.livoxRecordTime,6)} s`));
      if(rpm===0)formulas.append(node('span','A stopped wheel gives no motion-based timing cue.'));
    }
    input.addEventListener('input',()=>{inputMessage.hidden=!!input.value.trim() && input.validity.valid;if(inputMessage.hidden){tau=Number(input.value);draw();}else inputMessage.textContent=`Enter an offset between −${tauBound} and +${tauBound} ms. The diagrams still show the last valid value.`;});
    speed.addEventListener('change',()=>{capture=Number(speed.value);draw();});magnify.addEventListener('change',()=>{gain=Number(magnify.value);draw();});slider.addEventListener('input',()=>{step=Number(slider.value);draw();});
    reset.addEventListener('click',()=>{tau=ctx.tau===null?30:ctx.tau;input.value=fmt(tau,3);inputMessage.hidden=true;draw();});
    download.addEventListener('click',()=>{
      const svg=svgNode('svg',{xmlns:NS,viewBox:'0 0 1120 700',width:1120,height:700,'font-family':'system-ui, sans-serif'});
      svg.append(svgNode('rect',{width:1120,height:700,fill:'#f4f5f1'}));
      text(svg,30,37,'Timing offset explained with a rotating flywheel',{'font-size':25,'font-weight':600});
      text(svg,30,67,badge.textContent,{'font-size':15,fill:MUTED});
      text(svg,30,98,'Same recorded timestamp',{'font-size':17,'font-weight':600});text(svg,585,98,'Same physical scene',{'font-size':17,'font-weight':600});
      for(const [original,x] of [[leftSvg,20],[rightSvg,575]]){const clone=original.cloneNode(true);clone.setAttribute('x',x);clone.setAttribute('y',110);clone.setAttribute('width',520);clone.setAttribute('height',430);svg.append(clone);}
      text(svg,30,568,formulas.children[0].textContent,{'font-size':14});text(svg,30,593,formulas.children[1].textContent,{'font-size':14});
      text(svg,30,627,'Schematic constant-speed motion; fixed phase removed. Only angular separation is visually magnified.',{fill:MUTED});
      text(svg,30,652,'Printed times are model values on bag-record time, not native sensor-header time.',{fill:MUTED});
      text(svg,30,677,'Timing remains physically uncalibrated. A conditional minimum or hypothetical example is not a measured offset.',{fill:MUTED});
      const blob=new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml;charset=utf-8'});const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download=`timing-explanation-${result.id.replace(/[^a-zA-Z0-9_.-]/g,'_')}.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    draw();return card;
  }
  return {mount,model,context};
})();
