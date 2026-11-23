'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const sensors=[{name:'Akcelerometr',unit:'g',short:'ACC'},{name:'Gyroskop',unit:'°/s',short:'GYR'},{name:'Magnetometr',unit:'µT',short:'MAG'}];
const colors=['#287bd4','#137653','#ae7412'];
const fmt=(v,n=2)=>v==null||!Number.isFinite(v)?'—':v.toLocaleString('cs-CZ',{minimumFractionDigits:n,maximumFractionDigits:n});
const bytes=v=>v>=1e9?`${fmt(v/1e9,2)} GB`:v>=1e6?`${fmt(v/1e6,1)} MB`:`${fmt(v/1e3,0)} kB`;
let state=null,tab='dashboard',config=null,pending=false,folder='/',toastTimer,historyBusy=false;
let source='live',buckets=[],data=null,reportBusy=false,view=[0,10],autoFit=true,follow=false,selected=null,historyFile='',lastHistory=0;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,6000);}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-IMU-Client':'1'}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);return d;}
function safe(fn){return async(...args)=>{try{await fn(...args);}catch(e){toast(e.message);}};}
function changeTab(name){tab=name;$$('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));$$('.panel').forEach(p=>p.classList.toggle('active',p.id===name));if(name==='charts'){refreshHistory();requestAnimationFrame(drawCharts);}if(name==='files')loadFiles();}
$$('[data-tab]').forEach(b=>b.onclick=()=>changeTab(b.dataset.tab));$$('[data-goto]').forEach(b=>b.onclick=()=>changeTab(b.dataset.goto));
$('.brand').onclick=e=>{e.preventDefault();changeTab('dashboard');};
for(let s=0;s<3;s++){
 const card=document.createElement('article');card.className='sensor-card';
 card.innerHTML=`<div class="sensor-header"><h3>${sensors[s].name}</h3><small>${sensors[s].unit}</small></div><table><thead><tr><th>Osa</th><th>Teď</th><th>Minimum</th><th>Maximum</th></tr></thead><tbody>${[0,1,2].map(a=>`<tr><td class="axis ${'xyz'[a]}">${'XYZ'[a]}</td>${['v','lo','hi'].map(k=>`<td id="${k}${s*3+a}">—</td>`).join('')}</tr>`).join('')}</tbody></table><div class="sensor-footer" id="sensorRange${s}"></div>`;$('#sensorCards').append(card);
 const chart=document.createElement('article');chart.className='chart-card';chart.innerHTML=`<div class="chart-title"><h3>${sensors[s].name}</h3><span>${sensors[s].unit}</span></div><canvas id="chart${s}" aria-label="Graf ${sensors[s].name}; použij časové ovládání pro přiblížení"></canvas>`;$('#chartCards').append(chart);
}
function updateState(s){
 state=s;const usb=s.storageOwner==='usb',logger=s.storageOwner==='logger'||s.mode==='recording'||Boolean(s.recovering);$('#demo').hidden=!s.demo;$('#connection').textContent='Deska připojena';$('#connection').className='connection online';
 $('#recoveryNotice').hidden=!s.recoveryMessage;$('#recoveryNotice').textContent=(s.recovering?'Obnova '+s.recoveryPercent+' % · ':'')+(s.recoveryMessage||'');
 $('#usbNotice').hidden=!usb;$('#releaseUsb').disabled=pending||s.usbBusy;
 $('#usbDetail').textContent=s.usbBusy?'Probíhá přenos přes USB. Přístup půjde vrátit webu po dokončení kopírování.':'Ve Windows je otevřené IMU-Test → Měřicí data. Vrácení přístupu webu zachová USB připojení; další požadavek Windows na soubory si kartu znovu převezme.';
 const stale=!s.imu||s.sampleAge>1500;
 $('#error').hidden=!s.error&&!stale;$('#error').textContent=s.error||(stale?'Měření není aktuální. Zkontroluj připojení senzoru.':'');
 const labels={idle:'PŘIPRAVENO',recording:'NAHRÁVÁNÍ',paused:'POZASTAVENO',error:'CHYBA ZÁZNAMU'};
 $('#recordBadge').textContent=s.recovering?'OBNOVA ZÁZNAMU':labels[s.mode]||s.mode;$('#recordBadge').className=`badge ${s.mode}`;
 const secs=Math.floor(s.elapsed||0);$('#duration').textContent=secs>=3600?`${Math.floor(secs/3600)}:${String(Math.floor(secs/60)%60).padStart(2,'0')}:${String(secs%60).padStart(2,'0')}`:`${String(Math.floor(secs/60)).padStart(2,'0')}:${String(secs%60).padStart(2,'0')}`;
 $('#recordFile').textContent=s.file||'Žádný záznam';$('#rate').textContent=(s.axisHz||[s.hz,s.hz,0]).map(v=>fmt(v,0)).join(' / ');
 $('#rateTarget').textContent=`Cíl ${s.accRate} / ${s.gyroRate} / ${s.magRate} Hz · ${stale?'IMU nedostupná':'IMU online'}`;
 $('#rows').textContent=fmt(s.rows,0);$('#queue').textContent=`Fronta ${s.queue} / ${s.queueCapacity}`;
 $('#loss').textContent=(s.fifoOverflows?'≥ ':'')+fmt(s.dropped+s.missed,0);$('#loss').classList.toggle('clip',s.dropped+s.missed>0||s.fifoOverflows>0);
 $('#lossDetail').textContent=`${s.missed} čas / ${s.dropped} fronta / ${s.ioErrors} I/O`+(s.acquisition==='FIFO'?` / ${s.fifoOverflows||0} přetečení FIFO`:'');
 $('#space').textContent=s.sd?bytes(s.sdTotal-s.sdUsed):'Bez karty';$('#sdState').textContent=usb?'Přístup přes USB · Měřicí data':s.sd?`Volné z ${bytes(s.sdTotal)} · FAT32`:'Vlož SD a restartuj desku';
 for(let i=0;i<9;i++){$(`#v${i}`).textContent=stale?'—':fmt(s.values[i]);$(`#v${i}`).classList.toggle('clip',Boolean(s.clip&(1<<i)));$(`#lo${i}`).textContent=fmt(s.min[i]);$(`#hi${i}`).textContent=fmt(s.max[i]);}
 $('#temperature').textContent=`Teplota ${stale?'—':fmt(s.temp,1)} °C`;
 $('#magStatus').textContent=s.magValid?`Magnetometr · stáří ${fmt(s.magAge/1000,0)} ms · přetečení dat ${s.magOverruns}`:'Magnetometr · neplatná / zastaralá data';
 $('#start').disabled=pending||s.transfer||usb||logger||s.mode==='paused'||!s.imu||!s.sd||!s.memory;
 $('#pause').disabled=pending||!['recording','paused'].includes(s.mode);$('#pause').textContent=s.mode==='paused'?'▶ Pokračovat':'Ⅱ Pozastavit';
 $('#stop').disabled=pending||!['recording','paused'].includes(s.mode);$('#reset').disabled=pending||s.mode==='recording';
 $('#saveSettings').disabled=pending||s.transfer||usb||logger||s.mode==='paused';
 $('#recordNote').textContent=s.mode==='recording'?'SD karta je vyhrazena záznamu. Živý přehled zůstává dostupný.':s.mode==='paused'?'Soubor je uzavřený a dostupný. Pokračovat naváže do stejného CSV.':'Nový záznam vytvoří samostatný CSV soubor.';
 $('#storageLocked').hidden=!usb&&!logger;$('#storageLocked').textContent=usb?'Soubory právě používá USB. Pro návrat klikni na Přestat používat USB.':s.recovering?'Probíhá kontrola záznamu po výpadku napájení.':'Zapisovač používá SD. Pozastav nebo ukonči záznam a počkej na dokončení zápisu.';$('#fileTools').hidden=usb||logger;
 if(typeof syncFileLocks==='function')syncFileLocks(s);
 if(typeof updateWifiState==='function')updateWifiState(s.wifi);
 if((usb||logger)&&tab==='files')$('#fileList').replaceChildren();
}
async function poll(){try{updateState(await api('/api/status'));if(tab==='charts'&&source==='live'&&Date.now()-lastHistory>1800)await refreshHistory();}catch(e){$('#connection').textContent='Spojení přerušeno';$('#connection').className='connection';$$('#start,#pause,#stop,#saveSettings').forEach(b=>b.disabled=true);$('#error').hidden=false;$('#error').textContent='Deska neodpovídá. Zobrazené hodnoty nejsou živé.';}finally{setTimeout(poll,600);}}
async function control(action){pending=true;if(state)updateState(state);try{updateState(await api('/api/control',{action}));if(action==='start'){historyFile='';buckets=[];autoFit=true;selected=null;}if(tab==='files')await loadFiles();}finally{pending=false;if(state)updateState(state);}}
$('#start').onclick=safe(()=>control('start'));$('#pause').onclick=safe(()=>control(state?.mode==='paused'?'resume':'pause'));$('#stop').onclick=safe(()=>control('stop'));$('#reset').onclick=safe(()=>control('reset'));

function pinout(){const spi=$('#bus').value==='true';$('#addressLabel').hidden=spi;const rows=spi?[['GPIO12','SCL / SCK'],['GPIO11','SDA / MOSI'],['GPIO13','SDO / MISO'],['GPIO10','CS']]:[['GPIO8','SDA'],['GPIO9','SCL'],['3V3 nebo ponechat pull-up','CS']];$('#pinout').innerHTML=`<table class="pin-table"><thead><tr><th>ESP32-S3</th><th>ADAFRUIT ICM-20948</th></tr></thead><tbody>${[['3V3','VIN'],['GND','GND'],...rows].map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')}</tbody></table>`;}
$('#bus').onchange=pinout;
async function loadConfig(){config=await api('/api/config');$('#displayRotation').value=String(config.displayRotation??0);const f=$('#settingsForm');for(const [k,v]of Object.entries(config)){if(!f.elements[k])continue;if(k==='autostart')f.elements[k].checked=v;else f.elements[k].value=String(v);}pinout();$('#sensorRange0').textContent=`±${config.accel} g · ${config.accRate} Hz · včetně gravitace`;$('#sensorRange1').textContent=`±${config.gyro} °/s · ${config.gyroRate} Hz`;$('#sensorRange2').textContent=`ROZSAH ±4 912 µT · ${config.magRate} Hz`;}
$('#displayForm').onsubmit=safe(async e=>{e.preventDefault();const button=$('#saveDisplay');button.disabled=true;try{const d=await api('/api/display',{displayRotation:Number($('#displayRotation').value)});if(config)config.displayRotation=d.displayRotation;toast(`Orientace ${d.displayRotation}° uložena bez restartu.`);}finally{button.disabled=false;}});
$('#settingsForm').onsubmit=safe(async e=>{e.preventDefault();const f=e.currentTarget,values={};for(const key of ['accRate','gyroRate','accel','gyro','magRate','filter','address'])values[key]=Number(f.elements[key].value);values.spi=f.elements.spi.value==='true';values.autostart=f.elements.autostart.checked;await api('/api/config',values);toast('Nastavení uloženo. Deska se restartuje; znovu se připoj k IMU-Test.');setTimeout(()=>loadConfig().catch(()=>{}),7000);});

function bounds(){if(source==='live')return buckets.length?[buckets[0][0],buckets.at(-1)[1]]:[0,10];return data?.length?[data.get(0)[0],data.get(data.length-1)[0]]:[0,10];}
function setView(a,b,manual=true){const [lo,hi]=bounds(),full=Math.max(.01,hi-lo),span=Math.max(.01,Math.min(b-a,full));a=Math.max(lo,Math.min(a,hi-span));view=[a,a+span];if(manual){autoFit=false;follow=false;$('#follow').setAttribute('aria-pressed','false');}$('#timeFrom').value=view[0].toFixed(2);$('#timeTo').value=view[1].toFixed(2);drawCharts();}
async function refreshHistory(){if(source!=='live'||historyBusy)return;historyBusy=true;try{const d=await api('/api/history');if(d.file!==historyFile){historyFile=d.file;autoFit=true;selected=null;}buckets=d.buckets;lastHistory=Date.now();$('#chartSource').textContent=`Živá historie · ${d.file||'čeká na záznam'} · obálka min/max po ${fmt(d.bucketUs/1e6,2)} s`;if(autoFit)setView(...bounds(),false);else if(follow){const b=bounds();setView(Math.max(b[0],b[1]-10),b[1],false);}else drawCharts();}catch(e){toast(e.message);}finally{historyBusy=false;}}
function zoom(factor,anchor=(view[0]+view[1])/2){setView(anchor+(view[0]-anchor)*factor,anchor+(view[1]-anchor)*factor);}
$('#zoomIn').onclick=()=>zoom(.5);$('#zoomOut').onclick=()=>zoom(2);$('#fit').onclick=()=>{autoFit=true;follow=false;selected=null;$('#follow').setAttribute('aria-pressed','false');setView(...bounds(),false);};$('#follow').onclick=()=>{follow=!follow;autoFit=false;$('#follow').setAttribute('aria-pressed',String(follow));if(follow){const b=bounds();setView(Math.max(b[0],b[1]-10),b[1],false);}};
$('#applyRange').onclick=()=>{const a=Number($('#timeFrom').value),b=Number($('#timeTo').value);if(!Number.isFinite(a+b)||b<=a){toast('Konec musí být větší než začátek.');return;}setView(a,b);};
$('#liveCharts').onclick=()=>{source='live';$('#pdfReport').disabled=true;data=null;autoFit=true;selected=null;refreshHistory();};
function lowerBound(t){let lo=0,hi=data.length;while(lo<hi){const mid=(lo+hi)>>1;if(data.get(mid)[0]<t)lo=mid+1;else hi=mid;}return lo;}
function getVisible(){if(source==='live')return buckets.filter(b=>b[1]>=view[0]&&b[0]<=view[1]);return null;}
function drawCharts(){if(tab!=='charts')return;const empty=source==='live'?!buckets.length:!data?.length;$('#chartEmpty').hidden=!empty;$('#chartCards').hidden=empty;if(empty)return;for(let s=0;s<3;s++)drawChart(s);}
function drawChart(s){
 const canvas=$(`#chart${s}`),rect=canvas.getBoundingClientRect();if(!rect.width)return;
 const dpr=Math.min(devicePixelRatio||1,2),w=rect.width,h=rect.height;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
 const left=53,right=w-10,top=12,bottom=h-28,pw=right-left,span=Math.max(.001,view[1]-view[0]);
 let lo=Infinity,hi=-Infinity;const bins=Array.from({length:Math.max(1,Math.ceil(pw))},()=>({lo:[Infinity,Infinity,Infinity],hi:[-Infinity,-Infinity,-Infinity],clip:0}));
 function include(t,valsLow,valsHigh,clip){const px=Math.max(0,Math.min(bins.length-1,Math.floor((t-view[0])/span*pw))),b=bins[px];b.clip|=clip;for(let a=0;a<3;a++){const l=valsLow[a],u=valsHigh[a];if(l!=null&&u!=null&&Number.isFinite(l+u)){b.lo[a]=Math.min(b.lo[a],l);b.hi[a]=Math.max(b.hi[a],u);lo=Math.min(lo,l);hi=Math.max(hi,u);}}}
 if(source==='live'){for(const b of getVisible())include((Math.max(view[0],b[0])+Math.min(view[1],b[1]))/2,[b[2+s*6],b[4+s*6],b[6+s*6]],[b[3+s*6],b[5+s*6],b[7+s*6]],b[20]);}
 else{const end=Math.min(data.length,lowerBound(view[1])+1);for(let i=Math.max(0,lowerBound(view[0])-1);i<end;i++){const r=data.get(i),v=[r[1+s*3],r[2+s*3],r[3+s*3]];include(r[0],v,v,r[10]);}}
 if(!Number.isFinite(lo+hi)){lo=-1;hi=1;}if(lo===hi){lo-=1;hi+=1;}const pad=(hi-lo)*.12;lo-=pad;hi+=pad;const y=v=>bottom-(v-lo)/(hi-lo)*(bottom-top),x=t=>left+(t-view[0])/span*pw;
 ctx.font='10px Segoe UI, sans-serif';ctx.textBaseline='middle';ctx.lineWidth=1;ctx.fillStyle='#64748b';
 for(let i=0;i<5;i++){const yy=top+(bottom-top)*i/4;ctx.strokeStyle='#e8edf2';ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();ctx.textAlign='right';const v=hi-(hi-lo)*i/4;ctx.fillText(Math.abs(v)>=1000?v.toFixed(0):v.toFixed(1),left-7,yy);}
 for(let i=0;i<5;i++){ctx.textAlign=i===0?'left':i===4?'right':'center';const xx=left+pw*i/4,t=view[0]+span*i/4;ctx.fillText(`${t.toFixed(span<5?2:1)}s`,xx,bottom+17);}
 ctx.save();ctx.beginPath();ctx.rect(left,top,pw,bottom-top);ctx.clip();
 for(let a=0;a<3;a++){let previous=null;for(let i=0;i<bins.length;i++){const b=bins[i];if(!Number.isFinite(b.lo[a]))continue;const xx=left+i,mid=(b.lo[a]+b.hi[a])/2,isClip=b.clip&(1<<(s*3+a));ctx.strokeStyle=isClip?'#d92d43':colors[a];ctx.lineWidth=isClip?2.4:1.3;ctx.beginPath();ctx.moveTo(xx,y(b.lo[a]));ctx.lineTo(xx,y(b.hi[a]));ctx.stroke();if(previous){const gap=(i-previous.i)/pw*span;const maxGap=source==='live'?Math.max(.5,(buckets[0]?.[1]-buckets[0]?.[0]||.1)*3):Math.max(.15,3/Math.min(config?.accRate||50,config?.gyroRate||50));if(gap<maxGap){ctx.strokeStyle=isClip||previous.clip?'#d92d43':colors[a];ctx.beginPath();ctx.moveTo(left+previous.i,y(previous.mid));ctx.lineTo(xx,y(mid));ctx.stroke();}}previous={i,mid,clip:isClip};}}
 if(selected!=null&&selected>=view[0]&&selected<=view[1]){ctx.strokeStyle='#142138';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x(selected),top);ctx.lineTo(x(selected),bottom);ctx.stroke();}ctx.restore();
}
function inspect(t){
 let lines=[],label;
 if(source==='live'){if(!buckets.length)return;let b=buckets.reduce((best,r)=>Math.abs((r[0]+r[1])/2-t)<Math.abs((best[0]+best[1])/2-t)?r:best,buckets[0]);selected=(b[0]+b[1])/2;label=`${fmt(b[0],3)}–${fmt(b[1],3)} s · obálka ${b[21]} vzorků`;for(let s=0;s<3;s++)lines.push(`${sensors[s].name} [${sensors[s].unit}]<br>${[0,1,2].map(a=>`${'XYZ'[a]} ${fmt(b[2+s*6+a*2],3)} … ${fmt(b[3+s*6+a*2],3)}`).join('<br>')}`);}
 else{if(!data?.length)return;let i=Math.min(data.length-1,lowerBound(t));if(i&&Math.abs(data.get(i-1)[0]-t)<Math.abs(data.get(i)[0]-t))i--;const r=data.get(i);selected=r[0];label=`${fmt(r[0],6)} s · vzorek ${i+1} · nové A/G/M: ${r[13]?1:0}/${r[14]?1:0}/${r[11]?1:0}${r[10]?' · LIMIT':''}`;for(let s=0;s<3;s++)lines.push(`${sensors[s].name} [${sensors[s].unit}]<br>${[0,1,2].map(a=>`${'XYZ'[a]} ${fmt(r[1+s*3+a],5)}`).join('<br>')}`);}
 $('#readout').innerHTML=`<strong>${label}</strong><div class="readout-grid">${lines.map(l=>`<div>${l}</div>`).join('')}</div>`;drawCharts();
}
for(let s=0;s<3;s++){
 const c=$(`#chart${s}`),points=new Map();let baseline=null,moved=false;
 const coord=e=>e.clientX-c.getBoundingClientRect().left, timeAt=x=>view[0]+(x-53)/Math.max(1,c.clientWidth-63)*(view[1]-view[0]);
 c.onwheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.2:.8,timeAt(coord(e)));};
 c.onpointerdown=e=>{c.setPointerCapture(e.pointerId);points.set(e.pointerId,coord(e));baseline={p:[...points.values()],view:[...view],x:coord(e)};moved=false;};
 c.onpointermove=e=>{if(!points.has(e.pointerId)||!baseline)return;points.set(e.pointerId,coord(e));const p=[...points.values()],width=Math.max(1,c.clientWidth-63),old=baseline.view,span=old[1]-old[0];if(p.length===2&&baseline.p.length===2){const oldDist=Math.abs(baseline.p[1]-baseline.p[0]),dist=Math.max(8,Math.abs(p[1]-p[0])),anchor=old[0]+((baseline.p[0]+baseline.p[1])/2-53)/width*span,newSpan=span*oldDist/dist;const a=anchor-((p[0]+p[1])/2-53)/width*newSpan;setView(a,a+newSpan);moved=true;}else if(p.length===1){const delta=(p[0]-baseline.p[0])/width*span;if(Math.abs(p[0]-baseline.p[0])>4)moved=true;if(moved)setView(old[0]-delta,old[1]-delta);}};
 const end=e=>{if(!moved&&points.size===1&&e.type!=='pointercancel')inspect(timeAt(coord(e)));points.delete(e.pointerId);baseline=null;};c.onpointerup=end;c.onpointercancel=end;
}
new ResizeObserver(()=>drawCharts()).observe($('#charts'));

// Chunked typed arrays retain exact CSV samples without one JS object per row.
class CsvData{
 constructor(){this.chunks=[];this.length=0;this.stride=15;this.chunkSize=8192;}
 add(row){if(this.length>=2000000)throw Error('CSV přesahuje limit 2 milionů vzorků. Rozděl jej v počítači.');const chunk=Math.floor(this.length/this.chunkSize),offset=(this.length%this.chunkSize)*this.stride;if(!this.chunks[chunk])this.chunks[chunk]=new Float64Array(this.chunkSize*this.stride);this.chunks[chunk].set(row,offset);this.length++;}
 get(i){const offset=(i%this.chunkSize)*this.stride;return this.chunks[Math.floor(i/this.chunkSize)].subarray(offset,offset+this.stride);}
}
function csvCrc32(text){let crc=0xffffffff;for(let i=0;i<text.length;i++){crc^=text.charCodeAt(i);for(let b=0;b<8;b++)crc=(crc>>>1)^(0xedb88320&-(crc&1));}return (crc^0xffffffff)>>>0;}
async function parseCsv(stream,name,total=0){
 const result=new CsvData(),reader=stream.getReader(),decoder=new TextDecoder();let tail='',header=null,freshIndexes=[],settingIndexes=[],crcIndex=-1,seqIndex=-1,previousSeq=null,loaded=0,last=-1,invalid=0;
 const settingNames=['accel_range_g','gyro_range_dps','accel_rate_hz','gyro_rate_hz','mag_rate_hz'];result.info={name,invalid:0,seqMissing:0,settings:{},crc:false};
 const required=['time_us','ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps','mx_uT','my_uT','mz_uT','clip_mask','mag_new','mag_valid'];
 function line(text){text=text.replace(/\r$/,'');if(!text)return;if(!header){const cols=text.replace(/^\uFEFF/,'').split(',');header=required.map(k=>cols.indexOf(k));freshIndexes=['accel_new','gyro_new'].map(k=>cols.indexOf(k));settingIndexes=settingNames.map(k=>cols.indexOf(k));crcIndex=cols.indexOf('crc32');seqIndex=cols.indexOf('seq');result.info.crc=crcIndex>=0;if(crcIndex>=0&&crcIndex!==cols.length-1)throw Error('CRC32 musí být poslední sloupec.');if(header.some(i=>i<0))throw Error('CSV nemá očekávanou hlavičku IMU Test.');return;}const cells=text.split(',');if(crcIndex>=0&&(!/^[0-9a-fA-F]{8}$/.test(cells[crcIndex]||'')||csvCrc32(text.slice(0,text.lastIndexOf(',')))!==parseInt(cells[crcIndex],16))){invalid++;return;}if(cells.length<=Math.max(...header)){invalid++;return;}const r=header.map(i=>cells[i].trim()===''?NaN:Number(cells[i]));r[0]/=1e6;if(!Number.isFinite(r[0])||r[0]<last||r.slice(1,7).some(v=>!Number.isFinite(v))||![r[10],r[11],r[12]].every(Number.isFinite)){invalid++;return;}last=r[0];if(seqIndex>=0){const seq=Number(cells[seqIndex]);if(Number.isFinite(seq)){if(previousSeq!==null)result.info.seqMissing+=Math.max(0,seq-previousSeq-1);previousSeq=seq;}}settingNames.forEach((key,i)=>{if(settingIndexes[i]<0)return;const value=cells[settingIndexes[i]];if(result.info.settings[key]!==undefined&&result.info.settings[key]!==value)result.info.settingsChanged=true;else result.info.settings[key]=value;});r.push(...freshIndexes.map(i=>i<0?1:Number(cells[i])));if(!r[12])r[7]=r[8]=r[9]=NaN;result.add(r);}
 $('#fileProgress').hidden=false;$('#fileProgress').value=0;
 try{for(;;){const {done,value}=await reader.read();if(done)break;loaded+=value.byteLength;tail+=decoder.decode(value,{stream:true});const lines=tail.split('\n');tail=lines.pop();for(const l of lines)line(l);if(tail.length>10000)throw Error('Neplatný nebo příliš dlouhý řádek CSV.');$('#fileProgress').value=total?loaded/total*100:0;$('#fileMessage').textContent=`Načítám ${name} · ${fmt(result.length,0)} vzorků`;await new Promise(r=>setTimeout(r,0));}tail+=decoder.decode();if(tail.trim())line(tail);if(!result.length)throw Error('CSV neobsahuje platné vzorky.');result.info.invalid=invalid;data=result;source='csv';$('#pdfReport').disabled=false;selected=null;autoFit=true;$('#chartSource').textContent=`${name} · ${fmt(data.length,0)} přesných vzorků${invalid?` · vynecháno poškozených řádků: ${invalid}`:''}`;$('#fileMessage').textContent=invalid?`Pozor: ${invalid} neúplných / poškozených řádků bylo vynecháno.`:'CSV načteno.';changeTab('charts');setView(...bounds(),false);if(invalid)toast(`Vynecháno ${invalid} neplatných řádků CSV.`);}catch(e){await reader.cancel();throw e;}finally{reader.releaseLock();$('#fileProgress').hidden=true;}
}
let remoteCsvLoading=false;
async function openRemoteCsv(path){
 if(remoteCsvLoading||state?.download?.active)throw Error('Načítání nebo stahování už probíhá. Počkej na dokončení.');
 if(state?.mode==='recording')throw Error('Nejdříve pozastav nebo ukonči záznam.');
 remoteCsvLoading=true;
 try{const r=await fetch('/api/download?path='+encodeURIComponent(path));if(!r.ok){const d=await r.json();throw Error(d.error);}await parseCsv(r.body,path,Number(r.headers.get('Content-Length')));}
 finally{remoteCsvLoading=false;}
}
$('#localCsv').onchange=safe(async e=>{const f=e.target.files[0];if(f)await parseCsv(f.stream(),f.name,f.size);e.target.value='';});
window.addEventListener('DOMContentLoaded',()=>{loadConfig().catch(e=>toast(e.message));poll();if(['charts','files','settings'].includes(location.hash.slice(1)))changeTab(location.hash.slice(1));});
// Exposed only for local deterministic parser/plot checks; no simulated values in production.
window.imuTest={CsvData,parseCsv,setView,inspect,changeTab,getState:()=>({state,source,view,dataLength:data?.length,buckets:buckets.length})};

$('#otaFile').onchange=safe(async e=>{
 const file=e.target.files[0];if(!file)return;
 if(state?.transfer)throw Error('Nejdříve dokonči přenosy souborů.');
 if(state?.storageOwner==='usb')throw Error('Nejdříve vrať SD z USB webu.');
 if(state?.mode==='recording'||state?.mode==='paused')throw Error('Nejdříve ukonči záznam.');
 if(file.size<1024||file.size>0x700000)throw Error('Velikost firmwaru neodpovídá oddílu OTA (max. 7 MiB).');
 if(new Uint8Array(await file.slice(0,1).arrayBuffer())[0]!==0xe9)throw Error('Soubor nemá hlavičku ESP firmware.');
 if(!confirm(`Nahrát ${file.name} (${bytes(file.size)}) a restartovat desku?`)){e.target.value='';return;}
 const form=new FormData();form.append('firmware',file);$('#otaProgress').hidden=false;$('#otaMessage').textContent='Nahrávám firmware. Neodpojuj napájení…';
 try{await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/ota');xhr.setRequestHeader('X-IMU-Client','1');xhr.upload.onprogress=e=>{if(e.lengthComputable)$('#otaProgress').value=e.loaded/e.total*100;};xhr.onload=()=>xhr.status===200?resolve():reject(Error(JSON.parse(xhr.responseText).error||'Aktualizace selhala.'));xhr.onerror=()=>reject(Error('Spojení se přerušilo. Ověř stav desky po opětovném připojení.'));xhr.send(form);});$('#otaMessage').textContent='Firmware přijat. Deska se restartuje; připoj se znovu k IMU-Test.';toast('Aktualizace dokončena. Deska se restartuje.');}
 catch(err){$('#otaMessage').textContent=err.message;throw err;}
 finally{$('#otaProgress').hidden=true;e.target.value='';}
});

$('#releaseUsb').onclick=safe(async()=>{pending=true;try{updateState(await api('/api/usb/release',{}));if(tab==='files')await loadFiles();toast('SD karta je dostupná webu. Další požadavek na soubory přes USB ji může znovu převzít.');}finally{pending=false;if(state)updateState(state);}});
