'use strict';
let driveInfo=null,driveRevision=0,secretRevision=0,hideDriveTimer;
function hideDrivePassword(){
 secretRevision++;clearTimeout(hideDriveTimer);
 $('drive-password').value='';$('drive-copy').hidden=true;
 setText('drive-reveal','Zobrazit heslo');
}
function resetDriveGuide(){
 driveRevision++;driveInfo=null;hideDrivePassword();
 $('drive-user').value='';$('drive-reveal').disabled=true;
 for(const id of ['drive-unc','drive-uri','drive-win-cmd','drive-linux-cmd','drive-note'])setText(id,'');
}
function drawDriveGuide(){
 if(!driveInfo)return;
 const remote=$('drive-network').value==='tailscale';
 const host=driveInfo[$('drive-network').value];
 const unc='\\\\'+host+'\\'+driveInfo.share,share='//'+host+'/'+driveInfo.share;
 setText('drive-unc',unc);setText('drive-uri','smb:'+share);
 setText('drive-win-cmd','net use P: '+unc+' /user:'+driveInfo.username+' * /persistent:yes');
 setText('drive-linux-cmd','sudo apt install cifs-utils\nsudo mkdir -p /mnt/formula-ppk\nsudo mount -t cifs '+share+' /mnt/formula-ppk -o username='+driveInfo.username+',uid=$(id -u),gid=$(id -g),vers=3.1.1');
 const hint=remote?'Připoj počítač ke stejné síti Tailscale jako Raspberry Pi.':'Připoj počítač ke stejné Wi-Fi nebo hotspotu jako Raspberry Pi. Pokud se jméno .local nepřeloží, vyber nahoře IP adresu.';
 setText('drive-note',hint+(driveInfo.tailscale?'':' Vzdálená adresa zatím není dostupná.')+(driveInfo.has_password?'':' Správce zatím nezpřístupnil heslo.'));
}
async function loadDriveGuide(){
 const revision=++driveRevision;
 try{
  const data=await request('network-drive');
  if(revision!==driveRevision||!signed||currentPage!=='drive')return;
  driveInfo=data;$('drive-user').value=data.username;
  const menu=$('drive-network');
  for(const option of menu.options)option.disabled=!data[option.value];
  if(!data[menu.value])menu.value='local';
  $('drive-reveal').disabled=!data.has_password;drawDriveGuide();
 }catch(e){if(revision===driveRevision)showError(e)}
}
$('drive-refresh').onclick=loadDriveGuide;$('drive-network').onchange=drawDriveGuide;
$('drive-reveal').onclick=async()=>{
 if($('drive-password').value){hideDrivePassword();return}
 const revision=++secretRevision;
 try{
  const {password}=await request('network-drive/password',{});
  if(revision!==secretRevision||!signed||currentPage!=='drive'||document.hidden)return;
  $('drive-password').value=password;$('drive-copy').hidden=false;
  setText('drive-reveal','Skrýt heslo');hideDriveTimer=setTimeout(hideDrivePassword,60000);
 }catch(e){if(revision===secretRevision)showError(e)}
};
$('drive-copy').onclick=async()=>{
 try{await navigator.clipboard.writeText($('drive-password').value);setText('drive-note','Heslo bylo zkopírováno.')}
 catch{$('drive-password').select();setText('drive-note','Heslo je vybrané. Použij příkaz Kopírovat.')}
};
document.addEventListener('visibilitychange',()=>{if(document.hidden)hideDrivePassword()});
window.addEventListener('pagehide',hideDrivePassword);
