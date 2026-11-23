'use strict';
const cardPath='/scr?cmd=1.1.10.(3).(0)_1.20.20.0.(0,1,2,3,4,5,6,7,8,9)_1.20.40.0.0_10.60.40.0.0_2.60.20.0.0_10.60.20.0.0_10.50.40.0.0_10.60.25.0.0&fra0=logging.html';
let piLast=null,piRates={},piData=null,piDue=0,piPending=false,sdDue=0,sdPending=false;
function closeCardEditor(){
 $('sd-editor').replaceChildren();$('sd-editor').hidden=true;$('sd-open').setAttribute('aria-expanded','false');
 setText('sd-open','Nastavit obsah záznamu');
}
$('sd-open').onclick=()=>{
 if(!$('sd-editor').hidden){closeCardEditor();return}
 const frame=document.createElement('iframe');frame.title='Septentrio · nastavení záznamu na DSK1';
 const note=ovEl('p','settings-inner','Při výzvě „Authorization Required“ zadej účet přijímače Septentrio.');
 frame.src=$('sd-window').href;$('sd-editor').replaceChildren(note,frame);$('sd-editor').hidden=false;
 $('sd-open').setAttribute('aria-expanded','true');setText('sd-open','Zavřít nastavení karty');
};
function resetPiOverview(){
 piLast=piData=null;piRates={};piDue=sdDue=0;
 $('pi-overview').hidden=true;closeCardEditor();setText('sd-status','Čekání na stav DSK1.');
}
async function updateCardEditor(){
 const available=networkUp&&status?.receiver_url&&status.device?.connected;
 $('sd-open').disabled=!available;$('sd-window').hidden=!available;
 $('sd-window').href='https://'+location.hostname+':8444'+cardPath;
 if(!available){setText('sd-status','Přijímač není připojený.');return}
 if(sdPending||Date.now()<sdDue)return;
 sdDue=Date.now()+5000;sdPending=true;const gen=authGeneration;
 try{
  const data=await request('receiver/overview');
  if(gen!==authGeneration||!signed||currentPage!=='settings')return;
  const disk=data.frames.DiskStatus?.data,slot=ovParts(disk,'DiskID').find(s=>disk['DiskID'+s]===1);
  if(!slot){setText('sd-status','Přijímač dosud neohlásil stav karty DSK1.');return}
  const fields=[];
  if(disk['Mounted'+slot]===1){
   fields.push('Karta připojena',disk['Logging'+slot]===1?'záznam běží':'záznam vypnutý');
   const formats=data.frames.OutputLink?.data.find(l=>l.port===97)?.types||[];
   if(formats.length)fields.push(formats.map(t=>ovTypes[t]||String(t)).join(' + '));
   if(disk['DiskSize'+slot]>0)fields.push(decimal(disk['DiskSize'+slot],0)+' MiB');
   if(disk['Full'+slot]===1)fields.push('karta je plná');
  }else fields.push('Karta DSK1 není připojena');
  setText('sd-status',fields.join(' · '));
 }catch(e){if(signed&&gen===authGeneration)setText('sd-status',e.message)}
 finally{sdPending=false}
}
function rateBetween(a,b,key){
 if(!a||!b||!Number.isFinite(a[key])||!Number.isFinite(b[key]))return null;
 const dt=b.t-a.t;
 return dt>0&&dt<=15000&&b[key]>=a[key]?(b[key]-a[key])*1000/dt:null;
}
function drawPi(){
 const rows=piData?.samples||[],latest=rows.at(-1),end=piData?.end_ms;
 const cur=networkUp&&latest&&end-latest.t<=12000&&Date.now()-(piData?.received||0)<=15000?latest:null;
 const previous=rows.at(-2);
 const rate=v=>Number.isFinite(v)?decimal(v/1024,2)+' KiB/s':'—';
 const row=(label,a,b,color)=>({label,a,b:rate(b),color});
 const flows=[row('USB2 → Pi','GNSS · SBF',networkUp&&status?.device.connected?piRates.rx:null,'#72b1e9'),
  row('Wi-Fi → Pi','Příjem · wlan0',rateBetween(previous,cur,'wifi_rx_bytes'),'#69dec2'),
  row('Pi → Wi-Fi','Odesílání · wlan0',rateBetween(previous,cur,'wifi_tx_bytes'),'#69dec2'),
  row('NVMe → Pi','Čtení oddílu',rateBetween(previous,cur,'disk_read_bytes'),'#ffa181'),
  row('Pi → NVMe','Zápis na oddíl',rateBetween(previous,cur,'disk_write_bytes'),'#ffa181')];
 if(status?.rtk.source&&status.rtk.source!=='off'){
  const correction=(label,key)=>({label,a:'Korekce RTCM 3',b:networkUp&&Number.isFinite(piRates[key])?decimal(piRates[key],1)+' zpráv/s':'—',color:'#a6a2ef'});
  flows.push(correction('Základna → Pi','received'),correction('Pi → GNSS','sent'));
  if(status.rtk.relay)flows.push(correction('Pi → pit','relayed'));
 }
 ovFlow('pi-streams','chip','Raspberry Pi 5',flows);
 setText('pi-flow-stamp',cur?'Vzorek '+localTime(cur.t):'Čekání na měření');
 const target=$('pi-disk'),total=cur?.disk_total,used=cur?.disk_used,free=cur?.disk_free;
 if(total>0&&Number.isFinite(used)&&Number.isFinite(free)){
  const pct=100*used/total,reserved=Math.max(0,total-used-free);
  const ring=ovEl('div','ov-donut');ring.setAttribute('aria-hidden','true');
  ring.style.background='conic-gradient(var(--accent) 0 '+pct+'%, var(--teal) '+pct+'% '+(100*(1-reserved/total))+'%, var(--edge) 0)';
  ring.append(ovEl('b','',decimal(pct,0)+' %'));
  const txt=ovEl('div');txt.append(ovEl('strong','','NVMe · '+bytes(total)));
  for(const [label,v,c] of [['Obsazeno',used,'var(--accent)'],['Dostupné',free,'var(--teal)'],['Rezerva systému',reserved,'var(--edge)']]){
   if(label==='Rezerva systému'&&!reserved)continue;
   const legend=ovEl('div','ov-legend'),dot=ovEl('em');dot.style.background=c;legend.append(dot,label+' '+bytes(v));txt.append(legend);
  }
  txt.append(ovEl('small','',status?.recording.active?'Záznam jízdy běží':'Záznam jízdy vypnutý'));target.replaceChildren(ring,txt);
 }else target.replaceChildren(ovEl('p','ov-empty','Čekání na údaje o NVMe.'));
 const cpu=cur&&Number.isFinite(cur.cpu_pct)?cur.cpu_pct:null;
 const series=cur?rows.filter(r=>Number.isFinite(r.cpu_pct)).map(r=>({t:r.t,v:r.cpu_pct})):[];
 drawCpuMinute('pi-cpu',series,end,cpu,11000);
}
async function updatePiOverview(){
 const base=currentPage==='gps'&&!$('gps-technical').hidden?$('gps-technical'):['live','settings'].includes(currentPage)?$('page-'+currentPage):null;
 const panel=$('pi-overview');panel.hidden=!base||!signed;
 if(!base||!signed)return;
 if(panel.parentElement!==base)base.append(panel);
 if(currentPage==='settings')updateCardEditor();
 const sample={...status?.corrections,t:status?.now_ms,rx:status?.device.rx_bytes};
 if(!networkUp){piLast=null;piRates={}}
 else if(sample.t!==piLast?.t){
  for(const key of ['rx','received','sent','relayed'])piRates[key]=rateBetween(piLast,sample,key);
  piLast=sample;
 }
 drawPi();
 if(!networkUp||piPending||Date.now()<piDue||document.hidden)return;
 piPending=true;piDue=Date.now()+5000;const gen=authGeneration;
 try{
  const data=await request('hardware?minutes=1');if(!signed||gen!==authGeneration)return;
  piData={...data,received:Date.now()};drawPi();
 }catch{if(gen===authGeneration){piData=null;drawPi()}}
 finally{piPending=false}
}
