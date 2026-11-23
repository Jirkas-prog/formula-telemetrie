let bodyData=new Float64Array(),brakeEvents=[],analysisTimer=0,shownEvents=[],eventKey='',filterBeforeDiagnostics=true;
function qualityNotice(){
  $('qualityMode').textContent=$('showbad').checked?
    'Diagnostický pohled: všechny zapsané 100Hz průměry bez filtru, včetně poruch. Červené úseky nejsou použitelným měřením pohybu; do statistik se nezahrnují.':
    meta?.digital_fault_fraction>0?'Část zapsaných hodnot má opakovaný digitální vzor. Pro kontrolu jejich skutečného obsahu zapněte „Zobrazit i neplatná data“; tím se automaticky vypne filtr.':'';
}
function toggleDiagnosticView(){
  const show=$('showbad').checked,available=!manifest?.csv||manifest.csv.schema.filtered;
  if(show){filterBeforeDiagnostics=$('filtered').checked;$('filtered').checked=false}
  else $('filtered').checked=filterBeforeDiagnostics&&available;
  $('filtered').disabled=show||!available;
  qualityNotice();viewCache.clear();draw();scheduleAnalysis();
}
function prepareAnalysis(){
  bodyData=manifest.csv?manifest.csv.body:run.id==='boot_000181_run_001'&&meta.use_for_trajectory?DriveAnalysis.body(data,manifest.results.vehicle):new Float64Array();
  $('analysisCards').hidden=!!manifest.csv&&!bodyData.length;
  $('brakePanel').hidden=!!manifest.csv&&!bodyData.length;
  $('axesPanel').open=!!manifest.csv;
  $('trajectoryPanel').hidden=!!manifest.csv||!meta.use_for_trajectory;
  document.querySelector('.layout').classList.toggle('csv-layout',$('trajectoryPanel').hidden);
  for(const [i,id] of ['accChart','gyrChart','magChart'].entries())$(id).hidden=!!manifest.csv&&!manifest.csv.schema.groups[i];
  $('bodyChart').hidden=!bodyData.length;
  qualityNotice();
  eventKey='';scheduleAnalysis();
}
function analysisInterval(){return manifest.csv?[run.start_s,run.end_s]:DriveAnalysis.interval}
function scheduleAnalysis(){clearTimeout(analysisTimer);analysisTimer=setTimeout(renderAnalysis,120)}
function jumpAnalysis(time,window=null){
  pause();if(window)setWindow(...window);cursor=time;
  if(cursor<start||cursor>end)setWindow(Math.max(0,cursor-5),Math.min(run.end_s,cursor+5));
  draw();clearTimeout(analysisTimer);renderAnalysis();
  const charts=document.querySelector('.layout');charts.style.scrollMarginTop=(document.querySelector('.player').offsetHeight+12)+'px';charts.scrollIntoView({block:'start',behavior:'smooth'});
}
function markAnalysis(points){
  try{
    const flags=currentFlags().map(f=>({...f})),selected=[];
    for(const point of points){
      const index=FlagData.index(point.time,run.derived_rows);let f=flags.find(f=>f.index===index);
      if(!f){let number=1;while(flags.some(f=>f.number===number))number++;f={number,index,label:point.label.slice(0,160)};flags.push(f)}selected.push(f.number);
    }
    persistFlags(run,FlagData.validate(flags,run.derived_rows));renderFlags();draw();$('flagPanel').open=true;
    if(selected.length===2){$('flagFrom').value=selected[0];$('flagTo').value=selected[1];updateFlagRange()}
    flagMessage(selected.length===2?'Hranice události jsou označené. Můžete exportovat úsek mezi těmito vlaječkami.':'Maximum je označené vlaječkou.');
    $('analysisMessage').textContent='Uloženo: ⚑ '+selected.join(' → ⚑ ')+'.';
  }catch(e){$('analysisMessage').textContent=e.message}
}
function peakCard(title,value,time,label){
  const card=document.createElement('div');card.className='card';
  const small=document.createElement('small');small.textContent=title;const strong=document.createElement('strong');strong.textContent=value;card.append(small,strong);
  if(time!==null&&Number.isFinite(time)){
    const controls=document.createElement('div');controls.className='peakActions';
    controls.append(flagButton(fmt(time,3)+' s',()=>jumpAnalysis(time,[Math.max(0,time-5),Math.min(run.end_s,time+5)]),'Zobrazit '+title),flagButton('⚑',()=>markAnalysis([{time,label}]),'Označit '+title+' vlaječkou'));card.append(controls);
  }
  return card;
}
function renderAnalysis(){
  if(!data||!run)return false;
  const threshold=+$('brakeThreshold').value,minDuration=+$('brakeDuration').value;
  $('analysisScope').textContent=run.file+' · '+fmt(start,3)+'–'+fmt(end,3)+' s';
  $('analysisMessage').textContent='';
  try{
    const key=run.sha256+':'+threshold+':'+minDuration;
    if(key!==eventKey){brakeEvents=DriveAnalysis.events(bodyData,{threshold,minDuration,interval:analysisInterval()});eventKey=key}
  }catch(e){shownEvents=[];$('eventList').replaceChildren();$('exportEvents').disabled=true;$('analysisMessage').textContent=e.message;return false}
  const stats=DriveAnalysis.summarize(bodyData,start,end,brakeEvents,analysisInterval()),long=stats.long,lat=stats.lat,has=long.n>0;
  const brake=has&&long.min<0?-long.min:null,accel=has&&long.max>0?long.max:null;
  const side=has?Math.max(Math.abs(lat.min),Math.abs(lat.max)):null,sideTime=has?(Math.abs(lat.min)>Math.abs(lat.max)?lat.minTime:lat.maxTime):null;
  $('analysisCards').replaceChildren(
    peakCard('Max. brzdění · '+(manifest.csv?'CSV':'filtr 2 Hz'),brake===null?'—':fmt(brake,2)+' g',brake===null?null:long.minTime,'Max. brzdění '+fmt(brake,2)+' g'),
    peakCard('Max. akcelerace · '+(manifest.csv?'CSV':'filtr 2 Hz'),accel===null?'—':fmt(accel,2)+' g',accel===null?null:long.maxTime,'Max. akcelerace '+fmt(accel,2)+' g'),
    peakCard('Max. boční |a| · '+(manifest.csv?'CSV':'filtr 2 Hz'),side===null?'—':fmt(side,2)+' g',sideTime,'Max. boční zrychlení '+fmt(side,2)+' g'),
    peakCard(manifest.csv?'Dostupné vozidlové vzorky v okně':'Použitelný jízdní úsek v okně',fmt(stats.valid_s,2)+' s',null,''));
  $('analysisNote').textContent=has?'Vozidlové statistiky: 100 Hz, filtr 2 Hz, odhad montáže. Jízdní interval 677–1007 s. Jde o odhad z IMU; krátké rázy, brzdový pedál ani GPS rychlost zde neměříme.':'V tomto okně není použitelný jízdní úsek s odhadnutou orientací auta. Níže lze hodnotit osy senzoru; brzdění auta zde nevyvozujeme.';
  if(manifest.csv)$('analysisNote').textContent=has?'Podélné a boční složky jsou převzaté ze sloupců CSV v m/s². Bez další filtrace, ověření montáže nebo rekonstrukce trasy. Kandidáti zpomalení nejsou měřením brzdového pedálu.':'Samostatné CSV: statistiky dostupných os senzoru. Orientace vůči autu není doložena, proto z těchto os automaticky nevyvozujeme brzdění ani polohu.';
  $('analysisExposure').textContent=has?'Podélné a ≤ −0,30 g: '+fmt(stats.braking_s,2)+' s ('+fmt(stats.braking_fraction*100,1)+' %). Z toho současně |boční a| ≥ 0,30 g: '+fmt(stats.combined_braking_s,2)+' s.':'';
  const filtered=$('filtered').checked,channels=[];
  for(const [group,[name,unit,cols]] of [['Akcelerometr','g',filtered?[12,13,14]:[1,2,3]],['Gyroskop','°/s',filtered?[15,16,17]:[4,5,6]],['Magnetometr','µT',[7,8,9]]].entries())if(!manifest.csv||manifest.csv.schema.groups[group])for(let j=0;j<3;j++)channels.push({name:name+' '+'XYZ'[j],unit,stats:DriveAnalysis.stats(data,C,cols[j],start,end,11)});
  if(manifest.csv&&bodyData.length)for(const [i,name,unit] of [[1,'Podélné a','m/s²'],[2,'Boční a','m/s²'],[3,'Yaw','°/s']])channels.push({name,unit,stats:DriveAnalysis.stats(bodyData,5,i,start,end)});
  $('axesMode').textContent='Osy A/G: '+(filtered?'filtr 2 Hz':'průměry 100 Hz bez filtru')+'. Magnetometr bez filtru. Neplatné nebo chybějící hodnoty se vylučují i při zapnutém zobrazení chybných dat.';
  if(manifest.csv)$('axesMode').textContent='CSV: 10ms přehled, časy původního souboru. '+(filtered?'Použity dodané filtrované sloupce.':'Bez dodatečné filtrace.')+' Prázdné hodnoty jsou mezery, nikoli nuly. Detekované neplatné hodnoty se do statistik nezahrnují.';
  $('axisStats').replaceChildren();
  for(const c of channels){
    const tr=document.createElement('tr');const name=document.createElement('td');name.textContent=c.name+' ['+c.unit+']';tr.append(name);
    for(const type of ['min','max']){
      const td=document.createElement('td');td.dataset.label=type==='min'?'Minimum':'Maximum';
      if(c.stats.n){const time=c.stats[type+'Time'];td.append(flagButton(fmt(c.stats[type],3),()=>jumpAnalysis(time),c.name+' '+td.dataset.label+' v '+fmt(time,3)+' s'),flagButton('⚑',()=>markAnalysis([{time,label:c.name+' '+td.dataset.label+' '+fmt(c.stats[type],3)+' '+c.unit}]),'Vlaječka: '+c.name+' '+td.dataset.label));const at=document.createElement('small');at.textContent=fmt(time,3)+' s';td.append(at)}else td.textContent='—';tr.append(td);
    }
    for(const [label,value] of [['Průměr / σ',c.stats.n?fmt(c.stats.mean,3)+' / '+fmt(c.stats.std,3):'—'],['Platné vzorky',c.stats.n.toLocaleString('cs-CZ')+' / '+c.stats.total.toLocaleString('cs-CZ')]]){const td=document.createElement('td');td.dataset.label=label;td.textContent=value;tr.append(td)}$('axisStats').append(tr);
  }
  shownEvents=brakeEvents.filter(e=>e.end_s>=start&&e.start_s<=end);
  const sorted=[...shownEvents].sort($('brakeSort').value==='time'?(a,b)=>a.start_s-b.start_s:(a,b)=>b.peak_g-a.peak_g);
  const countLabel=n=>n+' '+(n===1?'událost':n>=2&&n<=4?'události':'událostí');
  $('eventCount').textContent=countLabel(sorted.length)+' v okně · '+brakeEvents.length+' v celé jízdě';
  $('eventRule').textContent='Začátek při a ≤ −'+fmt(threshold,2)+' g, konec po poklesu zpomalení pod '+fmt(threshold/2,2)+' g; délka alespoň '+fmt(minDuration,2)+' s. Zobrazeny jsou události zasahující do okna, hodnoty vždy za celou událost. Délka zahrnuje 10ms intervaly vzorků. ID událostí se při změně prahů přepočítají.';
  $('eventList').replaceChildren();$('exportEvents').disabled=!sorted.length;
  if(!sorted.length){const p=document.createElement('p');p.className='muted';p.textContent=has?'Pro tyto prahy v okně nebyla nalezena brzdná událost.':'Brzdné události jsou dostupné pouze v použitelném jízdním úseku záznamu 181.';$('eventList').append(p)}
  for(const e of sorted){
    const card=document.createElement('article');card.className='brakeEvent';const header=document.createElement('div');header.className='eventHeading';
    const strong=document.createElement('strong');strong.textContent=e.id+' · '+fmt(e.peak_g,2)+' g';const duration=document.createElement('span');duration.textContent=fmt(e.duration_s,2)+' s';header.append(strong,duration);card.append(header);
    const p=document.createElement('p');p.textContent=fmt(e.start_s,3)+'–'+fmt(e.end_s,3)+' s · průměr '+fmt(e.mean_g,2)+' g · max. |boční a| '+fmt(e.max_abs_lat_g,2)+' g';card.append(p);
    if(e.partial||e.start_s<start||e.end_s>end){const note=document.createElement('p');note.className='muted';note.textContent=e.partial?'Událost se dotýká hranice dostupných dat; její úplnost nelze potvrdit.':'Událost přesahuje zobrazené časové okno.';card.append(note)}
    const actions=document.createElement('div');actions.className='eventActions';actions.append(
      flagButton('Zobrazit',()=>jumpAnalysis(e.peak_time_s,[Math.max(0,e.start_s-1),Math.min(run.end_s,e.end_s+1)]),'Zobrazit událost '+e.id),
      flagButton('⚑ Maximum',()=>markAnalysis([{time:e.peak_time_s,label:e.id+' · brzdění '+fmt(e.peak_g,2)+' g · práh '+fmt(threshold,2)+' g / '+fmt(minDuration,2)+' s'}]),'Označit maximum '+e.id),
      flagButton('⚑ Hranice',()=>markAnalysis([{time:e.start_s,label:e.id+' · začátek · práh '+fmt(threshold,2)+' g / '+fmt(minDuration,2)+' s'},{time:e.end_s,label:e.id+' · konec · práh '+fmt(threshold,2)+' g / '+fmt(minDuration,2)+' s'}]),'Označit hranice '+e.id));card.append(actions);$('eventList').append(card);
  }
  return true;
}
for(const id of ['brakeThreshold','brakeDuration','brakeSort'])$(id).onchange=scheduleAnalysis;
$('refreshAnalysis').onclick=renderAnalysis;
$('exportEvents').onclick=()=>{
  if(!renderAnalysis())return;
  const columns=['event','start_s','end_s','duration_s','peak_time_s','peak_deceleration_g','mean_deceleration_g','max_abs_lateral_g','partial','threshold_g','release_g','minimum_duration_s'];
  const rows=shownEvents.map(e=>[e.id,e.start_s,e.end_s,e.duration_s,e.peak_time_s,e.peak_g,e.mean_g,e.max_abs_lat_g,e.partial?1:0,+$('brakeThreshold').value,+$('brakeThreshold').value/2,+$('brakeDuration').value].join(','));
  download(new Blob([columns.join(',')+'\r\n'+rows.join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'}),run.id+'_brzdne_udalosti.csv');
};
function renderAudit(){
  const audit=JSON.parse($('deceleration-audit').textContent);$('auditRows').replaceChildren();
  const matched=audit.filter(a=>manifest.runs.some(r=>r.id===a.id&&r.sha256===a.sha256));
  $('auditScope').closest('details').hidden=!matched.length;
  $('auditScope').textContent='Audit '+matched.length+' původních CSV se shodným SHA-256. Maxima jsou z celých souvislých platných úseků. U testů je projekce do osy auta pouze srovnávací číslo, nikoli brzdění vozidla.';
  for(const a of matched.sort((x,y)=>(y.filtered?.g??-Infinity)-(x.filtered?.g??-Infinity))){
    const row=document.createElement('tr');
    const name=document.createElement('td');name.textContent=a.id.replace('boot_','');const cls=document.createElement('td');cls.textContent=a.category;row.append(name,cls);
    for(const kind of ['filtered','raw']){const td=document.createElement('td');if(a[kind])td.append(flagButton(fmt(a[kind].g,2)+' g',async()=>{await selectRun(a.id);jumpAnalysis(a[kind].time,[Math.max(0,a[kind].time-5),Math.min(run.end_s,a[kind].time+5)])},'Zobrazit '+a.id+' '+kind));else td.textContent='—';row.append(td)}$('auditRows').append(row);
  }
}
