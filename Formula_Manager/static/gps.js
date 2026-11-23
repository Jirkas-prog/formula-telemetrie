'use strict';
let gpsParams=[], gpsDevice='', gpsBlockKey='', gpsCatalogDue=0;
let gpsLiveBusy=false, gpsCatalogBusy=false, gpsQueryBusy=false, gpsSnapshotBusy=false;
let gpsVersion=0;
let displayedFrame=null;
const gpsLabels={PVTGeodetic:'Poloha a rychlost',ReceiverStatus:'Stav přijímače',ReceiverSetup:'Identita a firmware',MeasEpoch:'Družicová měření',MeasExtra:'Doplňková měření',DOP:'Geometrie družic',SatVisibility:'Viditelnost družic',ChannelStatus:'Sledovací kanály',ReceiverTime:'Čas přijímače',InputLink:'Vstupní spojení',QualityInd:'Indikátory kvality',RFStatus:'Rádiový signál'};
const fixNames={1:'Samostatná',2:'Diferenciální',3:'Pevná poloha',4:'RTK fix',5:'RTK float',6:'SBAS',7:'RTK fix',8:'RTK float',10:'PPP'};

function clearGpsFrame(){
 gpsBlockKey='';displayedFrame=null;$('gps-report').hidden=true;
 $('gps-fields').replaceChildren();setText('gps-hex','');setText('gps-block-state','');
 setText('frame-field-count','');$('frame-filter').value='';
 for(const id of ['frame-technical','frame-binary']){$(id).open=false;$(id).hidden=true}
}
function resetGps(){
 gpsVersion++;gpsDevice='';gpsParams=[];gpsCatalogDue=0;
 if(typeof resetOverview==='function')resetOverview();
 $('gps-block').replaceChildren();$('gps-param').replaceChildren();
 $('gps-inventory').replaceChildren();
 for(const id of ['gps-answer','gps-param-note','gps-snapshot-state'])setText(id,'');
 $('gps-args').value='';$('gps-search').value='';$('gps-freeze').checked=false;
 clearGpsFrame();
}
function gpsOnline(){return signed&&networkUp&&!!status?.device?.connected}
function selectedParam(){return gpsParams.find(p=>p.name===$('gps-param').value)}
function gpsControls(){
 const p=selectedParam(),online=gpsOnline();
 $('gps-param').disabled=!online||!gpsParams.length||gpsQueryBusy;
 $('gps-search').disabled=!online||!gpsParams.length||gpsQueryBusy;
 $('gps-read').disabled=$('gps-help').disabled=!online||!p?.readable||gpsQueryBusy;
 $('gps-write').hidden=!p?.editable;
 for(const e of $('gps-write').elements)e.disabled=!online||gpsQueryBusy||!!status?.recording.active;
 $('gps-snapshot').disabled=!online||gpsSnapshotBusy;
 $('gps-block').disabled=!online||!$('gps-block').length;
 $('gps-freeze').disabled=!online;
 if(p)setText('gps-param-note',!p.readable?'Tento parametr otevři v úplné správě přijímače.':
   p.editable?(status?.recording.active?'Před změnou ukonči záznam.':'Změna platí pro aktuální konfiguraci. Pro uložení do profilu Boot použij web GPS.'):
   'Hodnotu čteš přímo z přijímače. Další volby najdeš v jeho webu.');
}
function gpsFilter(){
 const search=$('gps-search').value.trim().toLocaleLowerCase('cs');
 const list=$('gps-param'),before=list.value;list.replaceChildren();
 const groups=new Map();
 for(const p of gpsParams){
   if(!(p.name+' '+p.group).toLocaleLowerCase('cs').includes(search))continue;
   if(!groups.has(p.group)){const g=document.createElement('optgroup');g.label=p.group;groups.set(p.group,g);list.append(g)}
   groups.get(p.group).append(new Option(p.name,p.name));
 }
 if(Array.from(list.options).some(o=>o.value===before))list.value=before;
 else if(Array.from(list.options).some(o=>o.value==='ElevationMask'))list.value='ElevationMask';
 gpsSelection();
}
function gpsSelection(){
 setText('gps-answer','');$('gps-args').value='';
 $('gps-args').placeholder=$('gps-param').value==='ElevationMask'?'PVT, 10':'Argumenty podle syntaxe';
 if(!selectedParam())setText('gps-param-note','Žádný odpovídající parametr.');
 gpsControls();
}
async function gpsCatalog(){
 if(gpsCatalogBusy||Date.now()<gpsCatalogDue)return;
 gpsCatalogBusy=true;gpsCatalogDue=Date.now()+6000;
 const version=gpsVersion;
 try{
   const r=await request('receiver/parameters');
   if(version!==gpsVersion)return;
   gpsParams=r.parameters;gpsFilter();
 }catch(e){if(version===gpsVersion)setText('gps-param-note',e.message)}
 finally{gpsCatalogBusy=false}
}
async function gpsCommand(action){
 const p=selectedParam();if(!p||gpsQueryBusy||!gpsOnline())return;
 gpsQueryBusy=true;gpsControls();
 const version=gpsVersion;
 try{
   const r=await request('receiver',{action,name:p.name,arguments:$('gps-args').value});
   if(version!==gpsVersion)return;
   setText('gps-answer',(action==='write'?'Přečteno po změně\n':'')+(r.reply||'Přijímač nevrátil žádnou hodnotu.'));
   if(action==='write')$('gps-args').value='';
 }catch(e){if(version===gpsVersion)setText('gps-answer',e.message)}
 finally{gpsQueryBusy=false;gpsControls()}
}
async function gpsSnapshot(){
 if(!gpsOnline()||gpsSnapshotBusy)return;
 const version=gpsVersion;
 gpsSnapshotBusy=true;gpsControls();
 try{
   await request('receiver',{action:'snapshot'});
   if(version===gpsVersion)setText('gps-snapshot-state','Vyžádáno v '+localTime(Date.now())+'. Přijaté bloky najdeš v seznamu.');
 }catch(e){if(version===gpsVersion)setText('gps-snapshot-state',e.message)}
 finally{gpsSnapshotBusy=false;gpsControls()}
}
const pvtErrors={
  1:'Pro výpočet polohy zatím chybí družicová měření.',
  2:'Chybí údaje o drahách družic (efemeridy).',
  3:'Geometrie družic nestačí pro spolehlivý výpočet.',
  4:'Odchylky měření jsou příliš velké.',5:'Výpočet polohy se neustálil.',
  6:'Po vyřazení odlehlých hodnot zbývá málo měření.',
  7:'Přijímač omezil výstup polohy.',8:'Chybí diferenciální korekce.',
  9:'Souřadnice základny nejsou k dispozici.',10:'Přijímač čeká na pevné řešení RTK.'
};
const measured=v=>Number.isFinite(v)&&v!==-2e10;
function quantity(v,unit='',places=1){
 return measured(v)?decimal(v,places)+(unit?' '+unit:''):null;
}
function reading(label,value){
 const cell=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');
 dt.textContent=label;dd.textContent=value;cell.append(dt,dd);return cell;
}
function describeFrame(b){
 const f=b.fields, metrics=[];
 let title=gpsLabels[b.name]||b.name,description='',tone='neutral',icon='pulse';
 const add=(label,value)=>{if(value!=null&&value!=='')metrics.push([label,value])};
 const gpsWeek=()=>add('GPS týden',f.WNc===65535||!Number.isInteger(f.WNc)?'Neurčen':String(f.WNc));
 if(!Object.keys(f).length){
   description=b.error?'Tento rámec nelze dekódovat. Původní bajty jsou dostupné v HEX.':'Rámec je dostupný v původním formátu HEX.';
 }else if(b.name==='PVTGeodetic'){
   icon='target';
   const fix=f.Type>0&&f.Error===0&&measured(f.Latitude)&&Math.abs(f.Latitude)<=Math.PI/2&&measured(f.Longitude)&&Math.abs(f.Longitude)<=Math.PI;
   if(fix){
     title=fixNames[f.Type]||'Platná poloha';tone='good';
     description='Zeměpisná poloha a pohyb v okamžiku měření.';
     add('Zeměpisná šířka',decimal(f.Latitude*180/Math.PI,7)+'°');
     add('Zeměpisná délka',decimal(f.Longitude*180/Math.PI,7)+'°');
     add('Výška nad elipsoidem',quantity(f.Height,'m',2));
     if(measured(f.Vn)&&measured(f.Ve))add('Vodorovná rychlost',quantity(Math.hypot(f.Vn,f.Ve)*3.6,'km/h'));
     if(f.HAccuracy<655.35)add('Vodorovná přesnost · 2DRMS',quantity(f.HAccuracy,'m',2));
     if(f.VAccuracy<655.35)add('Svislá přesnost · 2σ',quantity(f.VAccuracy,'m',2));
   }else{
     title='Čeká na polohu';tone='waiting';
     description=pvtErrors[f.Error]||(f.Error?'Přijímač hlásí chybu výpočtu č. '+f.Error+'.':'Přijímač zatím neurčil platné souřadnice.');
     gpsWeek();
   }
   add('Použité družice',f.NrSV===255?'Neuvedeno':quantity(f.NrSV,'',0));
 }else if(b.name==='ReceiverStatus'){
   icon='board';
   const faults=Object.entries(f).filter(([k,v])=>k.endsWith('Error')&&v===1).map(([k])=>k);
   description=faults.length?'Aktivní chyby: '+faults.join(', '):'Přijímač v tomto rámci nehlásí chybu.';
   tone=faults.length?'waiting':'good';
   if(f.Temperature>0)add('Teplota přijímače',quantity(f.Temperature-100,'°C',0));
   if(f.CPULoad<=100)add('Vytížení procesoru',quantity(f.CPULoad,'%',0));
   if(measured(f.UpTime))add('Doba od zapnutí',Math.floor(f.UpTime/3600)+' h '+Math.floor(f.UpTime%3600/60)+' min');
 }else if(b.name==='ReceiverSetup'){
   title=f.ProductName||title;icon='board';
   add('Sériové číslo',f.RxSerialNumber);add('Firmware přijímače',f.RxVersion);
   add('GNSS firmware',f.GNSSFWVersion);add('Anténa',f.AntType==='Unknown'?'Neuvedena':f.AntType);
 }else if(b.name==='DOP'){
   icon='sat';
   for(const [key,label] of [['HDOP','Vodorovná geometrie'],['VDOP','Svislá geometrie'],['PDOP','Prostorová geometrie'],['TDOP','Časová geometrie']]){
     if(f[key]>0&&f[key]<655.35)add(label+' · '+key,quantity(f[key],'',2));
   }
   if(!metrics.length)description='Pro tuto epochu není k dispozici výpočet geometrie družic.';
   add('Družice ve výpočtu',f.NrSV===255?null:quantity(f.NrSV,'',0));
 }else if(b.name==='ReceiverTime'){
   const parts=[f.UTCHour,f.UTCMin,f.UTCSec],max=[23,59,60];
   if(parts.every((v,i)=>Number.isInteger(v)&&v>=0&&v<=max[i]))add('Čas UTC',parts.map(v=>String(v).padStart(2,'0')).join(':'));
   else description='Čas UTC dosud není určen.';
   gpsWeek();if(f.DeltaLS!==-128)add('Rozdíl GPS a UTC',quantity(f.DeltaLS,'s',0));
 }else if(['MeasEpoch','MeasExtra','ChannelStatus','SatVisibility','InputLink','RFStatus','QualityInd'].includes(b.name)){
   const count=b.name==='MeasEpoch'?f.N1:f.N;
   const labels={MeasEpoch:'Primární měření',MeasExtra:'Doplňková měření',ChannelStatus:'Družicové záznamy',SatVisibility:'Družice v přehledu',InputLink:'Vstupní záznamy',RFStatus:'Záznamy RF',QualityInd:'Indikátory kvality'};
   icon=['MeasEpoch','MeasExtra','ChannelStatus','SatVisibility'].includes(b.name)?'sat':'pulse';
   add(labels[b.name],quantity(count,'',0));
   if(count===0)description='V této zprávě nejsou žádné položky.';
   const ids=[...new Set(Object.entries(f).filter(([k])=>/^SVID_\d+$/.test(k)).map(([,v])=>v))];
   if(ids.length)add('Identifikátory družic (SVID)',ids.join(', '));
   gpsWeek();
 }else{
   for(const [key,value] of Object.entries(f).filter(([k,v])=>!/^Reserved|Padding|^(TOW|WNc)$/.test(k)&&v!=null&&v!==-2e10).slice(0,4))add(key,String(value));
 }
 return {title,description,tone,icon,metrics};
}
function renderTechnicalFields(){
 if(!$('frame-technical').open||!displayedFrame)return;
 const filter=$('frame-filter').value.trim().toLowerCase(),fields=document.createDocumentFragment();
 for(const [k,v] of Object.entries(displayedFrame.fields)){
   if(k.toLowerCase().includes(filter))fields.append(reading(k,v==null?'—':String(v)));
 }
 $('gps-fields').replaceChildren(fields);
 if(!$('gps-fields').childElementCount)setText('gps-fields',filter?'Žádné odpovídající pole.':'Žádná dekódovaná pole.');
}
function gpsShowFrame(b){
 if(!b){clearGpsFrame();setText('gps-block-state','Čekání na první rámec vybraného typu.');return}
 const key=b.id+'-'+b.count+'-'+b.t_ms;
 if(key===gpsBlockKey)return;
 gpsBlockKey=key;displayedFrame=b;
 const report=describeFrame(b);
 $('gps-report').hidden=false;$('gps-report').dataset.tone=report.tone;
 putIcon($('frame-icon'),report.icon);
 setText('frame-title',report.title);setText('frame-description',report.description);
 $('frame-metrics').replaceChildren(...report.metrics.map(([label,value])=>reading(label,value)));
 const meta=document.createDocumentFragment();
 for(const [label,value] of [['Příjem',localTime(b.t_ms,true)],['Počet',nf.format(b.count)+'×'],['Rámec','#'+b.id+' · r'+b.revision+' · '+b.length+' B']]){
   const item=document.createElement('span'),name=document.createElement('b');
   name.textContent=label;item.append(name,' '+value);meta.append(item);
 }
 $('gps-block-state').replaceChildren(meta);
 $('frame-technical').hidden=false;$('frame-binary').hidden=false;
 setText('frame-field-count',String(Object.keys(b.fields).length));
 renderTechnicalFields();
 if($('frame-binary').open)setText('gps-hex',b.hex);
}
$('frame-technical').addEventListener('toggle',renderTechnicalFields);
$('frame-filter').addEventListener('input',renderTechnicalFields);
$('frame-binary').addEventListener('toggle',()=>{if(displayedFrame&&$('frame-binary').open)setText('gps-hex',displayedFrame.hex)});
async function gpsFrames(){
 if(gpsLiveBusy||$('gps-freeze').checked)return;
 const sel=$('gps-block'),id=sel.value||'4007',version=gpsVersion;
 gpsLiveBusy=true;
 try{
   const r=await request('diagnostics?block='+encodeURIComponent(id));
   if(version!==gpsVersion||currentPage!=='gps'||$('gps-freeze').checked||(sel.value&&sel.value!==id))return;
   const signature=r.blocks.map(b=>b.id).join(',');
   if(sel.dataset.list!==signature||sel.length!==r.blocks.length){
     sel.replaceChildren(...r.blocks.map(b=>new Option((gpsLabels[b.name]?gpsLabels[b.name]+' · ':'')+b.name,String(b.id))));
     sel.dataset.list=signature;
     if(r.blocks.some(b=>String(b.id)===id))sel.value=id;
   }
   const rows=document.createDocumentFragment();
   for(const b of r.blocks){
     const row=document.createElement('tr');
     for(const value of [b.name,b.id,nf.format(b.count),localTime(b.t_ms)]){
       const cell=document.createElement('td');cell.textContent=value;row.append(cell);
     }
     rows.append(row);
   }
   $('gps-inventory').replaceChildren(rows);
   gpsShowFrame(r.detail);gpsControls();
 }catch(e){if(version===gpsVersion){clearGpsFrame();setText('gps-block-state',e.message)}}
 finally{gpsLiveBusy=false}
}
function updateGps(){
 const d=status?.device||{},p=status?.latest,c=status?.corrections||{},online=gpsOnline(),recent=online&&fresh();
 const device=online?d.name:'';
 if(device!==gpsDevice){resetGps();gpsDevice=device}
 for(const a of document.querySelectorAll('.gps-web')){
   a.hidden=!status?.receiver_url;a.href='https://'+location.hostname+':8444/';
 }
 setText('gps-connected',!networkUp?'Bez spojení':online?'Připojen':'Odpojen');
 setText('gps-bytes',online?bytes(d.rx_bytes)+' · CRC chyby '+nf.format(d.crc_errors):d.error||'');
 setText('gps-fix',recent?(p.valid?(fixNames[p.mode]||'Platná poloha'):'Bez fixu'):'—');
 setText('gps-age',recent?'Stáří vzorku '+decimal(d.age_s,2)+' s':'Čekání na aktuální polohovou zprávu');
 setText('gps-sats',recent?decimal(p.sats,0):'—');
 setText('gps-time',recent&&p.gps_week!=null?'GPS týden '+p.gps_week+' · TOW '+decimal(p.tow_ms,0)+' ms':'');
 setText('gps-rtcm',networkUp?nf.format(c.sent||0):'—');
 setText('gps-rtcm-age',networkUp&&c.usb_age_s!=null?'Poslední zápis před '+decimal(c.usb_age_s)+' s':status?.rtk?.source==='off'?'Příjem korekcí vypnutý':'Čekání na korekce');
 gpsControls();
 if(!$('gps-overview').hidden){
   if(typeof updateOverview==='function')updateOverview();
 }else if(online){if(!gpsParams.length)gpsCatalog();gpsFrames()}
}
for(const [button,overview] of [['show-overview',true],['show-technical',false]]){
 $(button).addEventListener('click',()=>{
   $('gps-overview').hidden=!overview;$('gps-technical').hidden=overview;
   $('show-overview').setAttribute('aria-pressed',String(overview));
   $('show-technical').setAttribute('aria-pressed',String(!overview));
   updateGps();
 });
}
$('gps-search').addEventListener('input',gpsFilter);
$('gps-param').addEventListener('change',gpsSelection);
$('gps-block').addEventListener('change',()=>{$('gps-freeze').checked=false;clearGpsFrame();gpsFrames()});
$('gps-freeze').addEventListener('change',()=>{if(!$('gps-freeze').checked)gpsFrames()});
$('gps-read').addEventListener('click',()=>gpsCommand('read'));
$('gps-help').addEventListener('click',()=>gpsCommand('help'));
$('gps-write').addEventListener('submit',e=>{e.preventDefault();gpsCommand('write')});
$('gps-snapshot').addEventListener('click',gpsSnapshot);

