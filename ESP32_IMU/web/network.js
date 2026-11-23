'use strict';
let wifiDraft=[],wifiLoaded=false,wifiSaving=false;
const networkForm=$('#networkForm');
function wifiRequestNetworks(rows){
 const result=rows.map(n=>{const row={ssid:n.ssid};if(n.open)row.password='';else if(n.password)row.password=n.password;else if(!n.hasPassword)row.password='';return row;});
 const seen=new Set();for(const n of result){if(!n.ssid||new TextEncoder().encode(n.ssid).length>32)throw Error('Název sítě musí mít 1 až 32 bajtů.');if(seen.has(n.ssid))throw Error('Stejná síť je v seznamu dvakrát.');seen.add(n.ssid);if(n.password&&!(n.password.length>=8&&n.password.length<=63)&&!/^[a-f0-9]{64}$/i.test(n.password))throw Error('Heslo musí mít 8 až 63 znaků nebo 64 hexadecimálních znaků.');}return result;
}
function renderWifi(){
 const list=$('#wifiNetworks');list.replaceChildren();
 wifiDraft.forEach((n,i)=>{
  const row=document.createElement('li');row.className='wifi-row';
  row.innerHTML='<div class="wifi-row-head"><strong></strong><div class="buttons"><button type="button" data-up aria-label="Vyšší priorita">↑</button><button type="button" data-down aria-label="Nižší priorita">↓</button><button type="button" data-remove>Odebrat</button></div></div><div class="form-grid"><label>Název sítě (SSID)<input data-ssid required maxlength="32" autocomplete="off" spellcheck="false"></label><label>Heslo<input data-password type="password" maxlength="64" autocomplete="new-password"></label></div><label class="check"><input data-open type="checkbox">Otevřená síť bez hesla</label>';
  row.querySelector('strong').textContent=`${i+1}. ${i===0?'Nejvyšší priorita':'Záložní síť'}`;
  const ssid=row.querySelector('[data-ssid]'),password=row.querySelector('[data-password]'),open=row.querySelector('[data-open]');
  ssid.value=n.ssid;password.value=n.password||'';open.checked=Boolean(n.open);password.disabled=open.checked;password.required=!n.hasPassword&&!n.open;password.placeholder=n.hasPassword?'Uloženo · prázdné ponechá heslo':'Alespoň 8 znaků';
  ssid.oninput=()=>{if(n.ssid!==ssid.value)n.hasPassword=false;n.ssid=ssid.value;password.required=!n.hasPassword&&!n.open;password.placeholder='Heslo pro tuto síť';};
  password.oninput=()=>n.password=password.value;open.onchange=()=>{n.open=open.checked;password.disabled=n.open;password.required=!n.hasPassword&&!n.open;};
  const up=row.querySelector('[data-up]'),down=row.querySelector('[data-down]');up.disabled=i===0;down.disabled=i===wifiDraft.length-1;
  up.onclick=()=>{[wifiDraft[i-1],wifiDraft[i]]=[n,wifiDraft[i-1]];renderWifi();$('#wifiNetworks').children[i-1].querySelector('[data-down]').focus();};
  down.onclick=()=>{[wifiDraft[i+1],wifiDraft[i]]=[n,wifiDraft[i+1]];renderWifi();$('#wifiNetworks').children[i+1].querySelector('[data-up]').focus();};
  row.querySelector('[data-remove]').onclick=()=>{wifiDraft.splice(i,1);renderWifi();};list.append(row);
 });
 $('#addWifi').disabled=wifiDraft.length>=6;
}
function updateStaticIp(){const on=!networkForm.elements.dhcp.checked;$('#staticIpFields').hidden=!on;for(const key of ['ip','subnet','gateway','dns']){networkForm.elements[key].disabled=!on;networkForm.elements[key].required=on;}}
function updateWifiState(w){
 if(!w)return;
 $('#wifiState').textContent=w.error|| (w.connected?`Připojeno k ${w.ssid} · ${w.rssi} dBm`:w.state==='connecting'?`Připojování k ${w.ssid}…`:w.state==='waiting'?'Čekání na uloženou síť':'Hotspot IMU-Test');
 const links=$('#wifiLinks');links.replaceChildren();for(const [label,url] of [[w.hostname+'.local',w.url],...(w.connected?[[w.ip,'http://'+w.ip+'/']]:[]),['Hotspot '+w.apIp,'http://'+w.apIp+'/']]){const a=document.createElement('a');a.textContent=label;a.href=url;links.append(a);}
 $('#saveWifi').disabled=!wifiLoaded||wifiSaving||Boolean(state?.transfer);
}
function applyWifiForm(d){
 wifiDraft=d.networks.map(n=>({...n,password:'',open:!n.hasPassword}));for(const [k,v]of Object.entries(d.settings)){const e=networkForm.elements[k];if(e){if(k==='dhcp')e.checked=v;else e.value=v;}}
 wifiLoaded=true;$('#networkFields').disabled=false;renderWifi();updateStaticIp();updateWifiState(d.status);
}
async function loadWifi(){
 if(wifiSaving)return;$('#reloadWifi').disabled=true;
 try{applyWifiForm(await api('/api/wifi'));$('#wifiMessage').textContent='Nastavení načteno. Hesla uložených sítí se neposílají zpět do prohlížeče.';}catch(e){$('#wifiMessage').textContent=e.message;throw e;}finally{$('#reloadWifi').disabled=false;}
}
$('#addWifi').onclick=()=>{if(wifiDraft.length>=6)return;wifiDraft.push({ssid:'',password:'',hasPassword:false,open:false});renderWifi();$('#wifiNetworks').lastElementChild.querySelector('input').focus();};
$('#reloadWifi').onclick=safe(loadWifi);networkForm.elements.dhcp.onchange=updateStaticIp;
networkForm.onsubmit=safe(async e=>{
 e.preventDefault();if(!wifiLoaded||wifiSaving)return;
 const networks=wifiRequestNetworks(wifiDraft),settings={dhcp:networkForm.elements.dhcp.checked};for(const key of ['hostname','apIp','ip','subnet','gateway','dns'])settings[key]=networkForm.elements[key].value.trim();
 wifiSaving=true;$('#networkFields').disabled=true;$('#reloadWifi').disabled=true;
 try{const d=await api('/api/wifi',{networks,settings});applyWifiForm(d);$('#wifiMessage').textContent=`Uloženo. Nová adresa: http://${d.settings.hostname}.local/ · hotspot http://${d.settings.apIp}/. Při změně adresy otevři nový odkaz.`;toast('Síťová nastavení uložena. Wi-Fi se znovu připojuje.');}
 finally{wifiSaving=false;$('#networkFields').disabled=false;$('#reloadWifi').disabled=false;$('#saveWifi').disabled=Boolean(state?.transfer);}
});
window.addEventListener('DOMContentLoaded',()=>loadWifi().catch(()=>{}));
