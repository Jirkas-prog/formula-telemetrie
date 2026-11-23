'use strict';
const $ = id => document.getElementById(id);
const paths = {
  pulse:'M2 12h5l3-8 4 16 3-8h5',archive:'M3 4h18v5H3zM5 9v11h14V9M9 13h6',
  sliders:'M4 6h8m5 0h3M4 12h2m5 0h9M4 18h11m4 0h1M12 3v6M7 9v6m9 0v6',
  board:'M6 5h12v14H6zM9 2v3m5-3v3M9 19v3m5-3v3M3 9h3m-3 5h3m12-5h3m-3 5h3',
  logout:'M10 4H5v16h5M9 12h12m-5-5 5 5-5 5',arrow:'M4 12h15m-6-6 6 6-6 6',
  record:'M12 5a7 7 0 1 1 0 14 7 7 0 1 1 0-14',stop:'M6 6h12v12H6z',
  power:'M12 2v10M7 5a8 8 0 1 0 10 0',
  globe:'M22 12a10 10 0 1 1-20 0 10 10 0 1 1 20 0M2 12h20M12 2c6 5 6 15 0 20-6-5-6-15 0-20',
  network:'M9 3h6v5H9zm3 5v5M5 17v-4h14v4M2 17h6v4H2zm14 0h6v4h-6z',
  usb:'M12 21V4m-3 3 3-4 3 4m-3 8 6-5V8m-6 10-6-5v-3',
  chip:'M6 6h12v12H6zM9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4',
  antenna:'M12 13v8m-4 0h8M6 5a8 8 0 0 0 0 12m12-12a8 8 0 0 1 0 12M9 8a4 4 0 0 0 0 6m6-6a4 4 0 0 1 0 6M12 10v2',
  target:'M12 4a8 8 0 1 1 0 16 8 8 0 1 1 0-16m0-3v5m0 12v5M1 12h5m12 0h5m-11-2a2 2 0 1 1 0 4 2 2 0 1 1 0-4',
  sat:'m9 7 8 8-4 4-8-8zM7 4l3-3 4 4-3 3zm9 10 3-3 4 4-3 3zM4 15a5 5 0 0 1 5 5m-7-1a3 3 0 0 1 3 3',
  speed:'M4 19a10 10 0 1 1 16 0zM12 14l5-6M6 12h2M12 5v2m6 6h2',
  drive:'m5 5 14 0 3 10v4H2v-4zm-3 10h20m-5 2h2',refresh:'M20 8a8 8 0 1 0 0 8m0-13v5h-5',
  download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',external:'M14 3h7v7m0-7L10 14m0-9H4v15h15v-6',
};
const svgNS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs) {
  const el = document.createElementNS(svgNS, tag);
  for (const [k,v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}
function putIcon(el,name) {
  const s = svgEl('svg',{viewBox:'0 0 24 24','aria-hidden':'true'});
  s.append(svgEl('path',{d:paths[name]})); el.replaceChildren(s);
}
document.querySelectorAll('[data-icon]').forEach(el=>putIcon(el,el.dataset.icon));
const nf = new Intl.NumberFormat('cs-CZ');
const decimal = (n,d=1)=>Number.isFinite(n) ? n.toLocaleString('cs-CZ',{maximumFractionDigits:d}) : '—';
const localTime = (t, date=false)=>Number.isFinite(t) ? new Intl.DateTimeFormat('cs-CZ',date?{dateStyle:'short',timeStyle:'medium'}:{timeStyle:'medium'}).format(t) : '—';
const bytes = n=>Number.isFinite(n)? n >= 1073741824 ? decimal(n/1073741824)+' GiB' : n >= 1048576 ? decimal(n/1048576)+' MiB' : n >= 1024 ? decimal(n/1024)+' KiB' : n+' B':'—';
const duration = ms=>{ if (!Number.isFinite(ms)||ms<0) return '—'; const s=Math.floor(ms/1000);return [Math.floor(s/3600),Math.floor(s/60)%60,s%60].map(v=>String(v).padStart(2,'0')).join(':') };
const channels={speed_kmh:['Rychlost','km/h'],alt_m:['Výška','m'],sats:['Počet satelitů','']};
for(const id of ['live-channel','history-channel']) for(const [key,[label,unit]] of Object.entries(channels)) $(id).add(new Option(label+(unit?' ('+unit+')':''),key));
for(const id of ['settings-form','startup-form']){
 const fields=$(id).elements;
 for(const hz of [1,5,10,20,50])fields.rate_hz.add(new Option(hz+' Hz',hz));
 for(const ms of [20,50,100,200,500,1000])fields.commit_ms.add(new Option(ms+' ms',ms));
}
let csrf='', status=null, currentPage='live', sessions=[], selected=null, selectedPoints=[], livePoints=[], activePoints=[];
const pageNames={live:'PŘEHLED',history:'ZÁZNAMY JÍZD',startup:'ZÁZNAM PO SPUŠTĚNÍ',gps:'GPS DIAGNOSTIKA',accuracy:'PŘESNOST',export:'EXPORT NA USB',files:'SOUBORY',drive:'SÍŤOVÝ DISK',ppk:'VÝPOČET PPK',hardware:'HARDWARE',settings:'NASTAVENÍ'};
if(Object.hasOwn(pageNames,location.hash.slice(1)))currentPage=location.hash.slice(1);
let currentSession=null, lastSavedFetch=0, historyVersion=0, pointsVersion=0, authGeneration=0, signed=false, settingsDirty=false, pendingAction=false;
let mapTiles=false; const maps={}; let timer=null, networkUp=false, pollVersion=0;
let rtkDirty=false, startupDirty=false;
let lastCookieRenewal=0;
function resumeSession(){lastCookieRenewal=0;poll()}
window.addEventListener('online',resumeSession);
window.addEventListener('pageshow',e=>{if(e.persisted)resumeSession()});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)resumeSession()});
const setText=(id,value)=>{$(id).textContent=value};
function setBanner(message=''){setText('banner',message);$('banner').hidden=!message}
function authView(show){signed=!show;$('auth').hidden=!show;$('app').hidden=show}
function clearPrivate(){
 if(typeof resetWifi==='function')resetWifi();
 if(typeof resetDriveGuide==='function')resetDriveGuide();
 if(typeof resetPiOverview==='function')resetPiOverview();
 if(typeof resetWorkPages==='function')resetWorkPages();
 if(typeof resetGps==='function')resetGps();
 authGeneration++; pointsVersion++; historyVersion++; clearTimeout(timer); csrf='';status=null;sessions=[];selected=null;selectedPoints=[];livePoints=[];activePoints=[];
 currentSession=null;lastSavedFetch=0;settingsDirty=false;setText('login-error','');setBanner();authView(true);
 rtkDirty=false;$('rtk-form').reset();setText('rtk-note','');
 startupDirty=false;$('startup-form').reset();setText('startup-note','');
 $('session-detail').hidden=true;$('sessions').replaceChildren();$('settings-note').textContent='';
 for(const m of Object.values(maps)){m.line.setLatLngs([]);if(m.marker){m.marker.remove();m.marker=null}m.centered=false}
 document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
}
async function request(path,data) {
 const options={credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000)};
 if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data)}
 let r;
 try {r=await fetch('/api/'+path,options)} catch {throw Error('Spojení s Raspberry Pi se nezdařilo.')}
 let payload;try {payload=await r.json()}catch{payload={}}
 if(!r.ok){if(r.status===401 && path!=='login')clearPrivate();throw Error(payload.error || ('Požadavek selhal (HTTP '+r.status+').'))}
 return payload;
}
const fixed=p=>!!p?.valid && Number.isFinite(p.lat)&&Number.isFinite(p.lon)&&Math.abs(p.lat)<=90&&Math.abs(p.lon)<=180;
function segments(points){let result=[],part=[];for(const p of points){if(fixed(p)){part.push([p.lat,p.lon])}else if(part.length){result.push(part);part=[]}}if(part.length)result.push(part);return result}
const TrackScale=L.Control.Scale.extend({
 _updateMetric(metres){
   if(metres>=1)return L.Control.Scale.prototype._updateMetric.call(this,metres);
   if(!(metres>0))return;
   const centimetres=metres>=.01, available=metres*(centimetres?100:1000);
   const magnitude=10**Math.floor(Math.log10(available));
   const step=[5,2,1].find(value=>value*magnitude<=available)??1;
   const length=step*magnitude;
   this._updateScale(this._mScale,length.toLocaleString('cs-CZ')+(centimetres?' cm':' mm'),length/available);
 }
});
function ensureMap(key){
 if(maps[key])return maps[key];
 const m=L.map(key+'-map',{zoomControl:true,zoomAnimation:false,scrollWheelZoom:false,attributionControl:true,maxZoom:34,minZoom:2,preferCanvas:true}).setView([50.7671,15.0562],15);
 m.attributionControl.setPrefix(false);new TrackScale({imperial:false,position:'bottomleft'}).addTo(m);
 const obj={m,line:L.polyline([],{color:'#5de1bd',weight:4,opacity:.95}).addTo(m),tiles:null,marker:null,centered:false,follow:true};
 m.on('dragstart',()=>{obj.follow=false});maps[key]=obj;applyTiles(obj);return obj;
}
function applyTiles(o){
 if(mapTiles&&!o.tiles){o.tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxNativeZoom:19,maxZoom:22,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'}).addTo(o.m)}
 if(!mapTiles&&o.tiles){o.tiles.remove();o.tiles=null}
}
for(const el of document.querySelectorAll('.tiles-switch'))el.addEventListener('change',()=>{mapTiles=el.checked; document.querySelectorAll('.tiles-switch').forEach(x=>{x.checked=mapTiles});Object.values(maps).forEach(applyTiles)});
function drawMap(key,points,position,stale,fit=false){
 const o=ensureMap(key), line=segments(points), coords=fixed(position)?[position.lat,position.lon]:null;
 o.line.setLatLngs(line);
 if(coords){if(!o.marker)o.marker=L.circleMarker(coords,{radius:7,weight:3,color:'#143129',fillColor:'#6bf5cd',fillOpacity:1}).addTo(o.m);else o.marker.setLatLng(coords)}
 else if(o.marker){o.marker.remove();o.marker=null}
 if(fit&&line.length){const bounds=L.latLngBounds(line.flat());o.m.fitBounds(bounds,{maxZoom:17,padding:[25,25],animate:false});o.centered=true}
 else if(coords&&(!o.centered||o.follow)){if(!o.centered)o.m.setView(coords,Math.max(17,o.m.getZoom()),{animate:false});else o.m.panInside(coords,{padding:[40,40],animate:false});o.centered=true}
 const msg=$(key+'-map-message');const isEmpty=!coords&&!line.length; const text=key==='history'?'Záznam neobsahuje platnou polohu':stale?'Živá poloha není dostupná':'Čekání na platnou polohu GNSS';
 msg.hidden=!isEmpty;if(isEmpty&&msg.textContent!==text){const icon=document.createElement('i');icon.dataset.icon='target';putIcon(icon,'target');msg.replaceChildren(icon,document.createTextNode(text))}
}
$('center').addEventListener('click',()=>{const o=maps.live,p=status?.latest;if(o&&fixed(p)&&networkUp&&fresh()){o.m.setView([p.lat,p.lon],o.m.getZoom(),{animate:false});o.follow=true}else if(o&&o.line.getBounds().isValid())o.m.fitBounds(o.line.getBounds(),{maxZoom:17,padding:[25,25]})});
function drawChart(key,points){
 const node=$(key+'-chart'),channel=$(key+'-channel').value,[label,unit]=channels[channel];
 const xval=p=>p.t_ms, yval=p=>(channel==='sats'||p.valid)&&Number.isFinite(p[channel])?p[channel]:null;
 const series=points.filter(p=>Number.isFinite(xval(p))), values=series.filter(p=>yval(p)!==null);
 const width=Math.max(285,node.clientWidth-26),height=Math.max(130,node.clientHeight-18),left=44,end=width-14,top=14,bottom=height-23;
 const s=svgEl('svg',{viewBox:'0 0 '+width+' '+height,role:'img','aria-label':label+(unit?' v '+unit:'')});node.replaceChildren(s);
 function txt(x,y,t,anchor='start'){const el=svgEl('text',{x,y,fill:'#a4b0b5','font-family':'Consolas,monospace','font-size':10,'text-anchor':anchor});el.textContent=t;s.append(el)}
 let low=Infinity,high=-Infinity;for(const p of values){low=Math.min(low,yval(p));high=Math.max(high,yval(p))}
 if(low===high){if(channel==='alt_m'){low-=1;high+=1}else{low=Math.max(0,low-1);high+=1}}
 for(let i=0;i<=3;i++){const y=top+(bottom-top)*i/3;s.append(svgEl('line',{x1:left,y1:y,x2:end,y2:y,stroke:'#344046','stroke-dasharray':'3 4'}));if(values.length)txt(left-6,y+3,decimal(high-(high-low)*i/3,1),'end')}
 if(!values.length){const message=document.createElement('div');message.className='chart-empty';message.textContent='Pro tuto veličinu zatím nejsou data.';node.append(message);return}
 let first=series[0].t_ms,last=series[series.length-1].t_ms;const x=t=>left+(end-left)*(last===first?.5:Math.max(0,Math.min(1,(t-first)/(last-first))));
 const y=v=>bottom-(v-low)/(high-low)*(bottom-top);let d='',pen=false,only=null;
 for(const p of series){const value=yval(p);if(value===null){pen=false;continue}only=[x(xval(p)),y(value)];d+=(pen?'L':'M')+only[0].toFixed(2)+' '+only[1].toFixed(2)+' ';pen=true}
 s.append(svgEl('path',{d,fill:'none',stroke:'#65dbbd','stroke-width':2,'stroke-linejoin':'round'}));
 if(only)s.append(svgEl('circle',{cx:only[0],cy:only[1],r:2.7,fill:'#91f4da'}));
 txt(left,height-4,localTime(first));if(last!==first)txt(end,height-4,localTime(last),'end');
}
function fresh(){const d=status?.device;if(!d?.connected||!status.latest)return false;return Number.isFinite(d.age_s)&&d.age_s<=Math.max(3,3/(status.settings?.rate_hz||1))}
function changePage(name){
 if(!Object.hasOwn(pageNames,name))return;
 if(currentPage==='settings'&&name!=='settings')resetWifi();
 if(currentPage==='drive'&&name!=='drive')resetDriveGuide();
 currentPage=name;
 for(const n of Object.keys(pageNames))$('page-'+n).hidden=n!==name;
 for(const b of document.querySelectorAll('[data-page]')){b.classList.toggle('active',b.dataset.page===name);if(b.dataset.page===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')}
 setText('breadcrumb',pageNames[name]);
 window.history.replaceState(null,'',location.pathname+location.search+(name==='live'?'':'#'+name));
 if(!signed)return;
 if(name==='drive')loadDriveGuide();
 if(name==='live'&&status){ensureMap('live').m.invalidateSize();renderLive()}
 if(name==='history'){refreshHistory().catch(showError);if(selected){ensureMap('history').m.invalidateSize();renderDetail(true)}}
 if(name==='settings'){if(status)renderSettings();loadWifi()}
 if(name==='startup'&&status)renderStartup();
 if(name==='gps'&&status&&typeof updateGps==='function')updateGps();
 if(typeof refreshWorkPage==='function')refreshWorkPage(true);
 if(typeof updatePiOverview==='function')updatePiOverview();
}
document.querySelectorAll('[data-page],[data-goto]').forEach(b=>b.addEventListener('click',()=>changePage(b.dataset.page||b.dataset.goto)));
window.addEventListener('hashchange',()=>changePage(location.hash.slice(1)||'live'));
function showError(e){if(signed)setBanner(e.message)}
function renderLive(){
 const d=status.device||{},p=status.latest,rec=status.recording||{},recent=networkUp&&fresh(),row=sessions.find(s=>s.id===rec.id);
 const rstate=$('receiver-state'),fstate=$('fix-state');
 rstate.className=!networkUp?'bad':!d.connected?'bad':recent?'ok':'warn';
 rstate.textContent=!networkUp?'Neznámý':!d.connected?'Odpojen':recent?'Připojen':'Čeká na data';
 setText('receiver-detail',d.connected&&networkUp?('Přijato '+bytes(d.rx_bytes)):'USB spojení');
 const modeNames={1:'Samostatná',2:'Diferenciální',3:'Pevná poloha',4:'RTK fix',5:'RTK float',6:'SBAS',7:'RTK fix',8:'RTK float',10:'PPP'};
 fstate.className=!recent?'':fixed(p)?'ok':'warn';fstate.textContent=!recent?'—':fixed(p)?(modeNames[p.mode]||'Platná poloha'):'Bez fixu';
 setText('fix-detail',recent&&fixed(p)?decimal(p.lat,6)+'°, '+decimal(p.lon,6)+'°':recent?'Pozice není určena':'Čekání na čerstvý vzorek');
 setText('satellites',recent?decimal(p.sats,0):'—');setText('speed',recent&&fixed(p)?decimal(p.speed_kmh):'—');
 const state=$('record-state');state.classList.toggle('running',networkUp&&!!rec.active);state.lastChild.textContent=!networkUp?' Aktuální stav neznámý':rec.active?' Záznam běží':' Záznam vypnutý';
 setText('session-name',rec.active?row?.name||('Jízda '+rec.id):'Připraveno k měření');
 setText('duration',rec.active&&row?duration((status.now_ms??p?.t_ms)-row.started_ms):'—');
 setText('samples',rec.active&&row?nf.format(row.samples):'—');setText('commit',decimal(status.settings?.commit_ms,0)+' ms');setText('free',bytes(status.database?.free_bytes));
 const btn=$('record');btn.disabled=pendingAction||!networkUp;putIcon(btn.firstElementChild,rec.active?'stop':'record');btn.lastElementChild.textContent=rec.active?'Zastavit záznam':'Spustit záznam';
 setText('track-label',rec.active?'Trasa zaznamenávané jízdy':'Poloha při otevřeném přehledu');
 const source=rec.active?activePoints:livePoints;
 drawMap('live',source,recent?p:null,!recent);
 setText('last-sample',p?'Poslední vzorek '+localTime(p.t_ms):'Dosud bez vzorků');
 setText('live-chart-caption','Poslední živé vzorky · obnova přibližně 1× za sekundu');drawChart('live',livePoints);
}
function fillProfile(form,profile){
 form.elements.rate_hz.value=profile.rate_hz;
 form.elements.commit_ms.value=profile.commit_ms;
 form.elements.raw_observations.checked=profile.raw_observations;
}
function renderStartup(){
 const form=$('startup-form'),profile=status.startup_settings;
 if(!startupDirty){
   fillProfile(form,profile);
   form.elements.autostart.checked=profile.autostart;
 }
 const state=$('startup-state');
 state.textContent=networkUp?(profile.autostart?'Zapnutý':'Vypnutý'):'Bez spojení';
 state.className='chip'+(networkUp&&profile.autostart?' ok':'');
 for(const el of form.elements)el.disabled=pendingAction||!networkUp;
}
function renderSettings(){
 const form=$('settings-form'),d=status.device||{};
 if(!settingsDirty)fillProfile(form,status.manual_settings);
 renderRtk();
 for(const el of form.elements)el.disabled=pendingAction||!networkUp||!!status.recording?.active;
 if(status.recording?.active)setText('settings-note','Pro změnu nastavení ukonči záznam.');
 else if($('settings-note').textContent==='Pro změnu nastavení ukonči záznam.')setText('settings-note','');
 setText('device-name',d.name||'—');setText('rx',bytes(d.rx_bytes));setText('crc',decimal(d.crc_errors,0));setText('device-error',d.error||'');
 $('receiver-link-row').hidden=!status.receiver_url;$('receiver-link').href='https://'+location.hostname+':8444/';
}
function renderSessions(){
 const node=$('sessions');node.replaceChildren();setText('db-size','SQLite · '+bytes(status?.database?.size_bytes));
 if(!sessions.length){const wrap=document.createElement('div');wrap.className='empty';const title=document.createElement('strong');title.textContent='Zatím žádné jízdy';wrap.append(title,'První jízdu spustíš v živém přehledu.');node.append(wrap);return}
 for(const s of sessions){const b=document.createElement('button');b.className='session-row';b.classList.toggle('selected',s.id===selected);const name=document.createElement('strong');name.textContent=s.name||('Jízda '+s.id);
 const date=document.createElement('span');date.className='session-date';date.textContent=localTime(s.started_ms,true);
 const count=document.createElement('span');count.className='session-count';count.textContent=(s.state==='interrupted'?'Přerušeno · ':!s.stopped_ms?'Probíhá · ':'')+nf.format(s.samples)+' vz.';
 const arrow=document.createElement('i');arrow.dataset.icon='arrow';putIcon(arrow,'arrow');b.append(name,date,count,arrow);b.addEventListener('click',()=>openSession(s.id).catch(showError));node.append(b)}
}
async function refreshHistory(){
 const generation=authGeneration,version=++historyVersion;const result=await request('sessions');if(generation!==authGeneration||version!==historyVersion)return;
 sessions=result.sessions;if(currentPage==='history'){renderSessions();if(selected)renderDetail(false)}
}
async function openSession(id){
 selected=id; selectedPoints=[];const version=++pointsVersion;renderSessions();renderDetail(false);const result=await request('sessions/'+id+'/points?limit=1200');
 if(version!==pointsVersion)return;selectedPoints=result.points;renderDetail(true);
}
function renderDetail(fit){
 const row=sessions.find(s=>s.id===selected);$('session-detail').hidden=!row;if(!row||currentPage!=='history')return;
 setText('detail-name',row.name||('Jízda '+row.id));setText('detail-meta',localTime(row.started_ms,true)+' · '+nf.format(row.samples)+' vzorků · '+bytes(row.raw_bytes)+' surových dat');
 if(row.obs_epochs!=null){
   const profile=JSON.parse(row.settings_json);
   $('detail-meta').append(profile.raw_observations
      ? ' · PPK: '+nf.format(row.obs_epochs)+' epoch s družicemi, '+nf.format(row.nav_blocks)+' navigačních bloků'
      : ' · RAW pro PPK vypnuto');
 }
 $('csv').href='/api/sessions/'+row.id+'/export.csv';$('raw').href='/api/sessions/'+row.id+'/raw.bin';$('raw').hidden=!row.raw_bytes;
 for(const id of ['rename-session','delete-session'])$(id).hidden=row.state==='recording'||status?.recording?.id===row.id;
 $('delete-session').disabled=!!status?.recording?.active;
 $('delete-session').title=status?.recording?.active?'Smazání je dostupné po ukončení probíhajícího záznamu.':'';
 const o=ensureMap('history');o.m.invalidateSize();drawMap('history',selectedPoints,null,false,fit);drawChart('history',selectedPoints);setText('point-count','Zobrazený výběr z databáze: '+nf.format(selectedPoints.length)+' vzorků');
}
function setConnection(ok){networkUp=ok;const el=$('connection');el.className='chip '+(ok?'ok':'bad');el.lastChild.textContent=ok?' Raspberry Pi online':' Bez spojení s Raspberry Pi'}
function renderControls(){
 if(currentPage==='live')renderLive();
 if(currentPage==='settings')renderSettings();
 if(currentPage==='startup')renderStartup();
 if(typeof updatePiOverview==='function')updatePiOverview();
}
async function poll(){
 clearTimeout(timer); const generation=authGeneration,version=++pollVersion;
 try{
 const renew=!signed||!networkUp||Date.now()-lastCookieRenewal>=86400000;
 const s=await request(renew?'status?renew=1':'status');if(generation!==authGeneration||version!==pollVersion)return;
 if(renew)lastCookieRenewal=Date.now();
 status=s;csrf=s.csrf;const wasIn=signed;authView(false);setConnection(true);if(!wasIn)changePage(currentPage);
 if($('banner').dataset.network==='1'){setBanner();delete $('banner').dataset.network}
 const p=s.latest;if(p&&fresh()&&(!livePoints.length||livePoints.at(-1).seq!==p.seq||livePoints.at(-1).t_ms!==p.t_ms)){livePoints.push(p);if(livePoints.length>180)livePoints.shift()}
 else if((!p||!fresh())&&livePoints.at(-1)?.valid){livePoints.push({valid:false,t_ms:s.now_ms??Date.now()})}
 const rec=s.recording?.active?s.recording.id:null;if(currentSession!==rec){currentSession=rec;activePoints=[];lastSavedFetch=0}
 renderControls();
 if(currentPage==='gps'&&typeof updateGps==='function')updateGps();
 if(typeof refreshWorkPage==='function')refreshWorkPage(false);
 if(rec&&currentPage==='live'&&Date.now()-lastSavedFetch>=4000){
 lastSavedFetch=Date.now();const result=await Promise.all([request('sessions/'+rec+'/points?limit=1200'),refreshHistory()]);
 if(generation===authGeneration&&version===pollVersion&&rec===currentSession&&currentPage==='live'){activePoints=result[0].points;renderLive()}
 }
 }catch(e){if(generation===authGeneration&&version===pollVersion){if(signed){setConnection(false);setBanner(e.message);$('banner').dataset.network='1';if(status)renderControls();if(currentPage==='gps')updateGps()}else{setText('login-error',e.message)}}}
 finally{if(generation===authGeneration&&version===pollVersion&&signed)timer=setTimeout(poll,document.hidden?3500:950)}
}
async function action(fn){
 if(pendingAction)return;pendingAction=true;setBanner();if(status)renderControls();
 try{await fn()}catch(e){showError(e)}finally{pendingAction=false;if(signed&&status)renderControls()}
}
$('login-form').addEventListener('submit',async e=>{
 e.preventDefault();const f=e.currentTarget,b=f.querySelector('button');b.disabled=true;setText('login-error','');
 try{const result=await request('login',{username:f.username.value.trim(),password:f.password.value});csrf=result.csrf;f.password.value='';await poll()}
 catch(err){setText('login-error',err.message)}finally{b.disabled=false}
});
$('logout').addEventListener('click',()=>action(async()=>{await request('logout',{});clearPrivate()}));
$('record').addEventListener('click',()=>{
 if(status?.recording?.active){action(async()=>{await request('stop',{});await poll();await refreshHistory()});return}
 const f=$('start-form');f.elements.name.value='Jízda '+new Intl.DateTimeFormat('cs-CZ',{dateStyle:'short',timeStyle:'short'}).format(new Date());$('start-dialog').showModal();f.elements.name.select();
});
$('cancel').addEventListener('click',()=>$('start-dialog').close());
let editedSessionId=null;
function editSession(dialogId){
 const row=sessions.find(item=>item.id===selected);
 if(!row||row.state==='recording'||pendingAction)return;
 editedSessionId=row.id;
 if(dialogId==='rename-dialog')$('rename-form').elements.name.value=row.name;
 else setText('delete-warning','Jízda „'+row.name+'“ bude trvale odstraněna včetně vzorků, trasy a surových dat. Tuto akci nelze vrátit.');
 $(dialogId).showModal();
 if(dialogId==='rename-dialog')$('rename-form').elements.name.select();
}
$('rename-session').addEventListener('click',()=>editSession('rename-dialog'));
$('delete-session').addEventListener('click',()=>editSession('delete-dialog'));
document.querySelectorAll('[data-close]').forEach(btn=>btn.addEventListener('click',()=>$(btn.dataset.close).close()));
$('rename-form').addEventListener('submit',e=>{
 e.preventDefault();const id=editedSessionId,name=e.currentTarget.elements.name.value.trim();
 if(!name)return;
 $('rename-dialog').close();
 action(async()=>{await request('sessions/'+id+'/rename',{name});await refreshHistory()});
});
$('confirm-delete').addEventListener('click',()=>{
 const id=editedSessionId;$('delete-dialog').close();
 action(async()=>{
   await request('sessions/'+id+'/delete',{confirm_id:id});
   if(selected===id){pointsVersion++;selected=null;selectedPoints=[];$('session-detail').hidden=true}
   await refreshHistory();
 });
});
$('start-form').addEventListener('submit',e=>{e.preventDefault();const name=e.currentTarget.elements.name.value.trim();if(!name)return;$('start-dialog').close();action(async()=>{await request('start',{name});await poll()})});
for(const page of ['settings','startup']){
 const form=$(page+'-form'), note=page+'-note';
 function markDirty(value){if(page==='startup')startupDirty=value;else settingsDirty=value}
 form.addEventListener('input',()=>{markDirty(true);setText(note,'Změny čekají na uložení.')});
 form.addEventListener('submit',e=>{
   e.preventDefault();
   const f=form.elements, data={rate_hz:Number(f.rate_hz.value),commit_ms:Number(f.commit_ms.value),raw_observations:f.raw_observations.checked};
   if(page==='startup')data.autostart=f.autostart.checked;
   action(async()=>{
     await request(page,data);
     markDirty(false);
     setText(note,page==='startup'?'Profil pro příští spuštění uložen.':'Nastavení uloženo.');
     await poll();
   });
 });
}

function showRtkFields() {
 const f=$('rtk-form').elements;
 for(const row of document.querySelectorAll('[data-rtk]')){
   const condition=row.dataset.rtk;
   row.hidden=!(condition===f.source.value || (f.source.value!=='off' &&
     (condition==='on' || (condition==='relay' && f.relay.checked))));
 }
}
function renderRtk(){
 const f=$('rtk-form').elements, cfg=status.rtk, c=status.corrections;
 if(!cfg||!c)return;
 const radio=rtkDirty?f.radio.value:cfg.radio;
 const radios=[...new Set(['',...(status.radios||[]),radio])];
 if(JSON.stringify(radios)!==f.radio.dataset.list){
   f.radio.replaceChildren(...radios.map(v=>new Option(v||'Vybrat rádio',v)));
   f.radio.dataset.list=JSON.stringify(radios);
 }
 f.radio.value=radio;
 if(!rtkDirty){
   for(const k of ['source','host','port','baud','relay_host','relay_port'])f[k].value=cfg[k];
   f.relay.checked=cfg.relay;
 }
 showRtkFields();
 for(const el of f)el.disabled=pendingAction||!networkUp||!!status.recording?.active||!!el.closest('[hidden].setting');
 setText('rtk-state',!networkUp?'Bez spojení':cfg.source==='off'?'Vypnuto':c.connected?'Připojen':'Čeká na zdroj');
 setText('rtk-age',c.age_s==null?'—':'RTCM '+c.message+' · před '+decimal(c.age_s)+' s');
 setText('rtk-count',[c.received,c.sent,c.relayed].map(n=>nf.format(n)).join(' / '));
 setText('rtk-crc',nf.format(c.bad));
 setText('rtk-error',[c.error,c.relay_error].filter(Boolean).join(' · '));
}
$('rtk-form').addEventListener('input',()=>{rtkDirty=true;renderRtk();setText('rtk-note','Změny čekají na uložení.')});
$('rtk-form').addEventListener('submit',e=>{
 e.preventDefault();
 const f=e.currentTarget.elements;
 const cfg={...status.rtk,source:f.source.value,relay:f.source.value!=='off'&&f.relay.checked};
 if(cfg.source==='tcp')Object.assign(cfg,{host:f.host.value.trim(),port:Number(f.port.value)});
 if(cfg.source==='serial')Object.assign(cfg,{radio:f.radio.value,baud:Number(f.baud.value)});
 if(cfg.relay)Object.assign(cfg,{relay_host:f.relay_host.value.trim(),relay_port:Number(f.relay_port.value)});
 action(async()=>{await request('rtk',cfg);rtkDirty=false;setText('rtk-note','Nastavení RTK uloženo.');await poll()});
});
$('refresh-history').addEventListener('click',()=>action(async()=>{await refreshHistory();if(selected)await openSession(selected)}));
$('live-channel').addEventListener('change',()=>drawChart('live',livePoints));$('history-channel').addEventListener('change',()=>drawChart('history',selectedPoints));
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!signed)return;if(currentPage==='live'&&maps.live){maps.live.m.invalidateSize();drawChart('live',livePoints)}else if(currentPage==='history'&&selected&&maps.history){maps.history.m.invalidateSize();drawChart('history',selectedPoints)}},150)});
window.addEventListener('DOMContentLoaded',poll,{once:true});

