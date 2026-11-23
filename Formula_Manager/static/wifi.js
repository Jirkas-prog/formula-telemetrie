'use strict';
let wifiRows=[],wifiBusy=false,wifiGeneration=0,wifiDrag=null;
let eduroamTest=null,wifiTimer=null;
const wifiForm=$('wifi-form'),wf=wifiForm.elements;
function closeWifiForm(){wifiForm.reset();wifiForm.hidden=true;wf.kind.disabled=false}
function resetWifi(){
 clearTimeout(wifiTimer);eduroamTest=null;$('eduroam-test-result').hidden=true;
 delete $('wifi-note').dataset.loadError;
 wifiGeneration++;wifiBusy=false;wifiRows=[];wifiDrag=null;closeWifiForm();
 $('wifi-list').replaceChildren();setText('wifi-note','');
}
function wifiFields(){
 const kind=wf.kind.value,edu=kind==='eduroam',needsSsid=['personal','sae','open'].includes(kind);
 $('wifi-ssid-row').hidden=!needsSsid;wf.ssid.required=needsSsid;
 $('wifi-identity-row').hidden=!edu;wf.identity.required=edu;
 $('wifi-password-row').hidden=kind==='open';wf.password.required=kind!=='open';
 $('wifi-eduroam-help').hidden=!edu;setText('wifi-password-label',edu?'Heslo pro vzdálený přístup':'Heslo sítě');
}
function openWifiForm(editEdu=false){
 closeWifiForm();wf.kind.value=editEdu?'eduroam':wifiRows.some(r=>r.eduroam)?'personal':'eduroam';
 wf.kind.disabled=editEdu;wifiForm.hidden=false;wifiFields();
 (editEdu?wf.identity:wf.kind).focus();
}
function drawWifi(){
 const list=$('wifi-list');list.replaceChildren();
 const testing=eduroamTest?.state==='running';
 $('wifi-add').disabled=wifiBusy||testing;$('wifi-refresh').disabled=wifiBusy;
 const result=$('eduroam-test-result');result.hidden=!eduroamTest;
 if(eduroamTest){
  const t=eduroamTest,parts=[localTime(t.finished||t.started,true),t.message];
  if(t.ip)parts.push('IP na eduroamu '+t.ip);
  if(t.restored===true)parts.push('Zpět na '+t.previous);
  if(t.restored===false)parts.push('Návrat na '+t.previous+' se nepodařilo potvrdit.');
  result.textContent=parts.join(' · ');
 }
 for(const [i,r] of wifiRows.entries()){
  const li=document.createElement('li');li.draggable=!wifiBusy&&!testing;li.dataset.id=r.id;
  const order=document.createElement('b');order.textContent=String(i+1);
  const label=document.createElement('span'),ssid=document.createElement('strong'),detail=document.createElement('small');
  ssid.textContent=r.ssid||r.name;
  detail.textContent=[r.ap?'Vlastní hotspot':'Wi-Fi',r.active?'Aktivní':r.eduroam&&!r.enabled?'Čeká na školní účet a heslo':!r.enabled?'Automatické připojení vypnuto':'Uloženo'].join(' · ');
  label.append(ssid,detail);li.append(order,label);
  const controls=document.createElement('div');controls.className='wifi-actions';
  function button(text,desc,fn,disabled=false){
   const b=document.createElement('button');b.type='button';b.className='quiet';b.textContent=text;
   b.title=desc;b.setAttribute('aria-label',desc);b.disabled=wifiBusy||testing||disabled;b.onclick=fn;controls.append(b);
  }
  button('↑','Posunout '+r.ssid+' nahoru',()=>moveWifi(i,i-1),i===0);
  button('↓','Posunout '+r.ssid+' dolů',()=>moveWifi(i,i+1),i===wifiRows.length-1);
  if(r.eduroam)button(r.enabled?'Upravit účet':'Doplnit účet','Nastavit účet eduroam',()=>openWifiForm(true));
  if(r.eduroam&&r.enabled)button('Ověřit přihlášení','Ověřit přihlášení k eduroamu',()=>{
   if(confirm('Ověřit uložený účet připojením k eduroamu? Web může být krátce nedostupný. Pi se potom vrátí na původní síť.'))
    wifiChange('test-eduroam',{},'');
  });
  button('Odebrat','Odebrat '+r.ssid,()=>{
   const warning=r.active?' Tím se může přerušit spojení s Pi.':r.ap?' Pi přestane tento hotspot nabízet.':'';
   if(confirm('Odebrat profil '+r.ssid+'?'+warning))wifiChange('remove',{id:r.id},'Profil byl odebrán.');
  });
  li.append(controls);list.append(li);
  li.ondragstart=e=>{wifiDrag=r.id;e.dataTransfer.setData('text/plain',r.id);e.dataTransfer.effectAllowed='move'};
  li.ondragover=e=>{if(wifiDrag&&!wifiBusy)e.preventDefault()};
  li.ondrop=e=>{e.preventDefault();const from=wifiRows.findIndex(row=>row.id===wifiDrag);wifiDrag=null;if(from>=0)moveWifi(from,i)};
  li.ondragend=()=>{wifiDrag=null};
 }
 wifiForm.querySelector('[type=submit]').disabled=wifiBusy||testing;
}
function scheduleWifiCheck(){
 clearTimeout(wifiTimer);
 if(signed&&currentPage==='settings')wifiTimer=setTimeout(loadWifi,3000);
}
async function loadWifi(){
 if(wifiBusy)return;
 const generation=++wifiGeneration;
 try{
  const data=await request('wifi');
  if(generation!==wifiGeneration||!signed||currentPage!=='settings')return;
  if($('wifi-note').dataset.loadError){setText('wifi-note','');delete $('wifi-note').dataset.loadError}
  wifiRows=data.profiles;eduroamTest=data.eduroam_test;drawWifi();
  if(eduroamTest?.state==='running')scheduleWifiCheck();
 }catch(e){if(generation===wifiGeneration){$('wifi-note').dataset.loadError='1';setText('wifi-note',e.message);if(eduroamTest?.state==='running')scheduleWifiCheck()}}
}
async function wifiChange(op,data,done){
 if(wifiBusy)return;
 const generation=++wifiGeneration;
 if(op==='test-eduroam')eduroamTest={state:'running',started:Date.now(),message:'Čekám na výsledek z Pi.'};
 wifiBusy=true;drawWifi();setText('wifi-note',op==='test-eduroam'?'':'Ukládání…');
 try{
  const result=await request('wifi/'+op,{...data,before:wifiRows.map(r=>r.id)});
  if(generation!==wifiGeneration)return;
  wifiRows=result.profiles;eduroamTest=result.eduroam_test;if(op==='save')closeWifiForm();setText('wifi-note',done);
  if(eduroamTest?.state==='running')scheduleWifiCheck();
 }catch(e){
  if(generation===wifiGeneration){setText('wifi-note',e.message);wifiBusy=false;drawWifi();await loadWifi()}
 }finally{if(generation===wifiGeneration){wifiBusy=false;drawWifi()}}
}
function moveWifi(from,to){
 if(wifiBusy||from===to||to<0||to>=wifiRows.length)return;
 const ids=wifiRows.map(r=>r.id);ids.splice(to,0,ids.splice(from,1)[0]);
 wifiChange('order',{order:ids},'Pořadí bylo uloženo.');
}
$('wifi-refresh').onclick=loadWifi;$('wifi-add').onclick=()=>openWifiForm();$('wifi-cancel').onclick=closeWifiForm;
wf.kind.onchange=()=>{wf.password.value='';wifiFields()};
wifiForm.onsubmit=e=>{
 e.preventDefault();const kind=wf.kind.value,data={kind};
 if(kind==='eduroam')data.identity=wf.identity.value.trim();
 if(['personal','sae','open'].includes(kind))data.ssid=wf.ssid.value;
 if(kind!=='open')data.password=wf.password.value;
 wifiChange('save',data,'Profil byl uložen. Pi ho může použít při příštím připojování.');
};

