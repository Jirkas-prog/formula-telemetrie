'use strict';
let entries=[],chosen=new Set(),folderTrail=[],listRequest=0,dialogAction=null,moveFolder='/',moving=[],uploadJob=null,orphanUpload=null,previewZoom=100,previewAbort=null,previewObjectUrl=null;
let downloadStarting=false;
const baseName=p=>p.split('/').at(-1),parentPath=p=>p.substring(0,p.lastIndexOf('/'))||'/',joinPath=(p,n)=>(p==='/'?'':p)+'/'+n;
const fileUrl=(path,preview=false)=>(preview?'/api/view':'/api/download')+'?path='+encodeURIComponent(path);
const imageFile=n=>/\.(png|jpe?g|gif|webp|bmp|avif)$/i.test(n),pdfFile=n=>/\.pdf$/i.test(n);
function validateName(name){if(!name||name==='.'||name.includes('..')||/[\\/:*?"<>|\x00-\x1f]/.test(name)||/[. ]$/.test(name))throw Error('Název obsahuje nepovolené znaky nebo končí tečkou či mezerou.');}
function fileButton(label,action,className=''){const b=document.createElement('button');b.type='button';b.textContent=label;b.className=className;b.onclick=safe(action);return b;}
function fileLocked(){return state?.storageOwner==='usb'||state?.storageOwner==='logger'||state?.mode==='recording'||state?.recovering;}
function syncFileLocks(s){
 const blocked=fileLocked(),busy=Boolean(s.transfer||uploadJob||orphanUpload);
 if(orphanUpload)showOrphan();
 $('#chooseUpload').disabled=blocked||busy;$('#newFolder').disabled=blocked||busy;
 $('#fileSpace').textContent=s.sd?`${bytes(s.sdTotal-s.sdUsed)} volných z ${bytes(s.sdTotal)}`:'SD není dostupná';
 syncDownloadUi(s.download);
 if(blocked){++listRequest;entries=[];chosen.clear();$('#selectionActions').hidden=true;$('#fileList').replaceChildren();if($('#previewDialog').open)$('#previewDialog').close();}
}
function crumbs(container,path,go){
 container.replaceChildren();const parts=path.split('/').filter(Boolean);let current='';
 const add=(label,to,last)=>{const b=fileButton(label,()=>go(to));if(last)b.setAttribute('aria-current','page');container.append(b);};
 add('SD karta','/',!parts.length);
 parts.forEach((part,i)=>{const sep=document.createElement('span');sep.textContent='/';sep.setAttribute('aria-hidden','true');container.append(sep);current+='/'+part;add(part,current,i===parts.length-1);});
}
async function goFolder(path,back=false){if(path===folder)return;if(!back)folderTrail.push(folder);folder=path;chosen.clear();$('#fileSearch').value='';await loadFiles();}
async function loadFiles(){
 if(fileLocked())return;
 const ticket=++listRequest,path=folder;$('#fileList').setAttribute('aria-busy','true');$('#fileMessage').textContent='';
 try{
  if(!uploadJob){const u=await api('/api/upload/status');orphanUpload=u.active?u:null;if(orphanUpload)showOrphan();}
  const list=await api('/api/files?path='+encodeURIComponent(path));if(ticket!==listRequest||path!==folder||fileLocked())return;
  entries=list.map(f=>({...f,name:baseName(f.name),path:joinPath(path,baseName(f.name))}));
  chosen=new Set([...chosen].filter(p=>entries.some(f=>f.path===p)));renderFiles();
 }catch(e){if(ticket===listRequest){entries=[];renderFiles();$('#fileMessage').textContent=e.message;}}
 finally{if(ticket===listRequest)$('#fileList').removeAttribute('aria-busy');}
}
function visibleFiles(){
 const query=$('#fileSearch').value.trim().toLocaleLowerCase('cs');const sort=$('#fileSort').value;
 return entries.filter(f=>f.name.toLocaleLowerCase('cs').includes(query)).sort((a,b)=>Number(b.dir)-Number(a.dir)||(sort==='size'?b.size-a.size:sort==='newest'?(b.modified||0)-(a.modified||0):0)||a.name.localeCompare(b.name,'cs',{numeric:true}));
}
function selectionState(){
 const list=visibleFiles();$('#selectAll').checked=!!list.length&&list.every(f=>chosen.has(f.path));$('#selectAll').indeterminate=list.some(f=>chosen.has(f.path))&&!$('#selectAll').checked;
 $('#fileCount').textContent=chosen.size?`Vybráno ${chosen.size} · ${list.length} položek`:`${list.length} ${list.length===1?'položka':list.length<5?'položky':'položek'}`;
 $('#selectionActions').hidden=!chosen.size;
}
function renderFiles(){
 crumbs($('#breadcrumbs'),folder,goFolder);$('#parentFolder').disabled=folder==='/';$('#fileBack').disabled=!folderTrail.length;
 const list=visibleFiles(),host=$('#fileList');host.replaceChildren();selectionState();
 $('#folderSummary').textContent=`${entries.filter(f=>f.dir).length} složek · ${entries.filter(f=>!f.dir).length} souborů · ${bytes(entries.reduce((n,f)=>n+(f.dir?0:f.size),0))}`;
 if(!list.length){const empty=document.createElement('div');empty.className='empty';empty.textContent=entries.length?'Žádné výsledky. Zkus jiný název.':'Tady je zatím prázdno. Vytvoř složku nebo nahraj první soubor.';host.append(empty);return;}
 let shown=0;
 function appendPage(){
  host.querySelector('.load-more')?.remove();
  for(const f of list.slice(shown,shown+100)){
   const row=document.createElement('div');row.className='file-row'+(chosen.has(f.path)?' selected':'');
   const check=document.createElement('input');check.type='checkbox';check.className='file-check';check.checked=chosen.has(f.path);check.setAttribute('aria-label','Vybrat '+f.name);
   check.onchange=()=>{check.checked?chosen.add(f.path):chosen.delete(f.path);row.classList.toggle('selected',check.checked);selectionState();};
   const open=fileButton('',()=>openFile(f),'file-open');if(!f.dir&&!imageFile(f.name)&&!pdfFile(f.name))open.dataset.fileTransfer='1';const icon=document.createElement('span');icon.className='file-icon '+(f.dir?'folder-icon':imageFile(f.name)?'image-icon':pdfFile(f.name)?'pdf-icon':'data-icon');
   icon.textContent=f.dir?'▰':imageFile(f.name)?'▧':pdfFile(f.name)?'PDF':/\.csv$/i.test(f.name)?'CSV':baseName(f.name).split('.').at(-1).slice(0,4).toUpperCase();icon.setAttribute('aria-hidden','true');
   const desc=document.createElement('span');desc.className='file-name';const title=document.createElement('strong');title.textContent=f.name;const detail=document.createElement('small');
   detail.textContent=f.dir?'Složka':bytes(f.size);if(f.modified>1577836800)detail.textContent+=' · '+new Date(f.modified*1000).toLocaleDateString('cs-CZ');if(f.name.endsWith('.upload-part'))detail.textContent+=' · nedokončený přenos';
   desc.append(title,detail);open.append(icon,desc);open.title=f.dir?'Otevřít složku':imageFile(f.name)||pdfFile(f.name)?'Zobrazit náhled':/\.csv$/i.test(f.name)?'Otevřít grafy':'Stáhnout soubor';
   const menu=document.createElement('details');menu.className='file-menu';const summary=document.createElement('summary');summary.textContent='•••';summary.setAttribute('aria-label','Možnosti: '+f.name);
   menu.ontoggle=()=>{if(menu.open)$$('.file-menu[open]').filter(x=>x!==menu).forEach(x=>x.open=false);};
   const actions=document.createElement('div');actions.className='file-menu-actions';
   const action=(label,fn,cls='')=>{const b=fileButton(label,()=>{menu.open=false;return fn();},cls);actions.append(b);return b;};
   action(f.dir?'Otevřít složku':/\.csv$/i.test(f.name)?'Otevřít grafy':'Otevřít',()=>openFile(f));
   if(!f.dir)action('Stáhnout',()=>downloadFile(f)).dataset.fileTransfer='1';
   if(/\.csv$/i.test(f.name))action('PDF report',async()=>{await openRemoteCsv(f.path);await createPdfReport();});
   action('Přejmenovat',()=>renameFile(f));action('Přesunout…',()=>moveFiles([f]));action('Smazat…',()=>deleteFiles([f]),'danger-text');
   menu.append(summary,actions);row.append(check,open,menu);host.append(row);
  }
  shown+=100;if(shown<list.length)host.append(fileButton(`Zobrazit dalších ${Math.min(100,list.length-shown)}`,appendPage,'load-more'));
 }
 appendPage();syncDownloadUi(state?.download);
}
function syncDownloadUi(d){
 const busy=downloadStarting||Boolean(d?.active);
 $$('[data-file-transfer]').forEach(b=>b.disabled=busy||fileLocked());
 const preview=$('#previewDownload');if(preview.dataset.remote==='1')preview.setAttribute('aria-disabled',String(busy||fileLocked()));
 $('#downloadPanel').hidden=!downloadStarting&&!d?.id;
 $('#cancelDownload').disabled=!d?.active||downloadStarting;
 if(!d?.id){if(downloadStarting){$('#downloadTitle').textContent='Připravuji stahování…';$('#downloadDetail').textContent='';$('#downloadProgress').value=0;}return;}
 const percent=d.size?Math.min(100,d.sent/d.size*100):d.state==='complete'?100:0;
 const labels={pending:'Čekám na prohlížeč',active:'Stahování probíhá',complete:'Data předána prohlížeči',cancelled:'Stahování zrušeno',error:'Stahování přerušeno'};
 $('#downloadTitle').textContent=labels[d.state]||'Stahování';$('#downloadProgress').value=percent;
 $('#downloadDetail').textContent=`${baseName(d.path)} · ${bytes(d.sent)} / ${bytes(d.size)} · ${Math.floor(percent)} %`;
 $('#downloadNote').textContent=d.active?'Další stažení můžeš spustit po dokončení nebo zrušení. SD zatím používá Wi-Fi.':d.state==='complete'?'Uložení do telefonu nebo počítače dokončí prohlížeč.':d.state==='error'?'Ověř spojení a spusť stažení znovu. Nedokončenou kopii spravuje prohlížeč.':'SD je znovu dostupná.';
}
async function downloadFile(f){
 if(downloadStarting||state?.download?.active){toast('Stahování už probíhá. Nejdříve ho dokonči nebo zruš.');return;}
 if(fileLocked())throw Error('SD právě používá USB nebo záznam.');
 downloadStarting=true;syncDownloadUi(state?.download);
 try{
  const job=await api('/api/download/start',{path:f.path});if(state)state.download=job;
  const a=document.createElement('a');a.href=fileUrl(f.path)+'&id='+encodeURIComponent(job.id);a.download=f.name;document.body.append(a);a.click();a.remove();
  toast('Stahování spuštěno. Průběh a zrušení najdeš nad seznamem souborů.');
 }finally{downloadStarting=false;syncDownloadUi(state?.download);}
}
$('#cancelDownload').onclick=safe(async()=>{const job=state?.download;if(!job?.active)return;$('#cancelDownload').disabled=true;try{const d=await api('/api/download/cancel?id='+encodeURIComponent(job.id),{});if(state)state.download=d;syncDownloadUi(d);}catch(e){syncDownloadUi(state?.download);throw e;}});
async function openFile(f){if(f.dir)return goFolder(f.path);if(/\.csv$/i.test(f.name))return openRemoteCsv(f.path);if(imageFile(f.name)||pdfFile(f.name))return previewFile(f);return downloadFile(f);}
function showFileDialog(title,description,confirm,action){
 $('#fileDialogTitle').textContent=title;$('#fileDialogDescription').textContent=description;$('#fileDialogError').textContent='';$('#confirmFileDialog').textContent=confirm;$('#confirmFileDialog').disabled=false;
 $('#fileNameLabel').hidden=true;$('#fileNameInput').required=false;$('#movePicker').hidden=true;dialogAction=action;$('#fileDialog').showModal();
}
function nameDialog(title,value,action){showFileDialog(title,'Pracuješ v aktuální složce. Existující soubory se nepřepisují.','Uložit',()=>{const name=$('#fileNameInput').value;validateName(name);return action(name);});$('#fileNameLabel').hidden=false;$('#fileNameInput').required=true;$('#fileNameInput').value=value;$('#fileNameInput').focus();const dot=value.lastIndexOf('.');$('#fileNameInput').setSelectionRange(0,dot>0?dot:value.length);}
function renameFile(f){nameDialog('Přejmenovat',f.name,async name=>{if(name!==f.name)await api('/api/file',{action:'rename',path:f.path,to:joinPath(parentPath(f.path),name)});await loadFiles();toast('Název uložen.');});}
async function applyFiles(list,action,to){
 const failed=[];let completed=0;
 for(const f of [...list]){try{await api('/api/file',{action,path:f.path,...(to?{to:joinPath(to,f.name)}:{})});chosen.delete(f.path);list.splice(list.indexOf(f),1);completed++;}catch(e){failed.push(f.name+': '+e.message);}}
 await loadFiles();if(failed.length)throw Error(`${completed?`Dokončeno: ${completed}. `:''}${failed.join(' · ')}`);toast(`Hotovo · ${completed} položek.`);
}
function deleteFiles(list){if(!list.length)return;showFileDialog(list.length===1?'Smazat položku?':`Smazat ${list.length} položek?`,list.map(f=>f.name).join(', ')+'. Smazání je trvalé. Složky musí být prázdné.','Smazat',()=>applyFiles(list,'delete'));}
async function moveFiles(list){if(!list.length)return;moving=[...list];moveFolder=folder;showFileDialog('Přesunout do složky',list.map(f=>f.name).join(', '),'Přesunout sem',()=>applyFiles(moving,'move',moveFolder));$('#movePicker').hidden=false;await showMoveFolder(moveFolder);}
async function showMoveFolder(path){
 moveFolder=path;$('#confirmFileDialog').disabled=true;$('#moveDestination').textContent='Načítám složky…';$('#moveFolders').replaceChildren();
 try{const list=await api('/api/files?path='+encodeURIComponent(path));if(path!==moveFolder)return;crumbs($('#moveBreadcrumbs'),path,showMoveFolder);
  if(path!=='/')$('#moveFolders').append(fileButton('↑ O úroveň výš',()=>showMoveFolder(parentPath(path))));
  const dirs=list.filter(f=>f.dir).sort((a,b)=>a.name.localeCompare(b.name,'cs'));
  for(const f of dirs){const name=baseName(f.name),dest=joinPath(path,name);const b=fileButton('▰ '+name,()=>showMoveFolder(dest));b.disabled=moving.some(x=>x.path===dest||dest.startsWith(x.path+'/'));$('#moveFolders').append(b);}
  $('#moveDestination').textContent='Cíl: '+path;$('#confirmFileDialog').disabled=moving.some(x=>parentPath(x.path)===path||x.path===path||path.startsWith(x.path+'/'));
 }catch(e){$('#fileDialogError').textContent=e.message;}
}
$('#fileForm').onsubmit=async e=>{e.preventDefault();$('#confirmFileDialog').disabled=true;$('#fileDialogError').textContent='';try{await dialogAction();$('#fileDialog').close();}catch(err){$('#fileDialogError').textContent=err.message;}finally{$('#confirmFileDialog').disabled=false;}};
$('#closeFileDialog').onclick=$('#cancelFileDialog').onclick=()=>$('#fileDialog').close();
$('#newFolder').onclick=()=>nameDialog('Nová složka','',async name=>{await api('/api/file',{action:'mkdir',path:joinPath(folder,name)});await loadFiles();toast('Složka vytvořena.');});
$('#refreshFiles').onclick=safe(loadFiles);$('#parentFolder').onclick=safe(()=>goFolder(parentPath(folder)));$('#fileBack').onclick=safe(()=>goFolder(folderTrail.pop()||'/',true));
$('#fileSearch').oninput=$('#fileSort').onchange=renderFiles;
$('#selectAll').onchange=e=>{visibleFiles().forEach(f=>e.target.checked?chosen.add(f.path):chosen.delete(f.path));renderFiles();};$('#clearSelection').onclick=()=>{chosen.clear();renderFiles();};
const selectedFiles=()=>entries.filter(f=>chosen.has(f.path));$('#moveSelected').onclick=safe(()=>moveFiles(selectedFiles()));$('#deleteSelected').onclick=()=>deleteFiles(selectedFiles());
document.addEventListener('click',e=>{$$('.file-menu[open]').forEach(m=>{if(!m.contains(e.target))m.open=false;});});

function previewFile(f){
 const dialog=$('#previewDialog'),body=$('#previewBody');body.replaceChildren();$('#previewTitle').textContent=f.name;$('#previewTitle').title=f.name;body.className=imageFile(f.name)?'preview-image':'';
 $('#previewDownload').href=fileUrl(f.path);$('#previewDownload').download=f.name;$('#previewDownload').dataset.remote='1';$('#previewDownload').onclick=safe(async e=>{e.preventDefault();await downloadFile(f);});syncDownloadUi(state?.download);$('#previewOpen').href=fileUrl(f.path,true);$('#imageZoom').hidden=pdfFile(f.name);previewZoom=100;$('#imageFit').textContent='Přizpůsobit';previewAbort?.abort();previewAbort=new AbortController();const signal=previewAbort.signal;
 if(imageFile(f.name)){const img=document.createElement('img');img.alt=f.name;img.src=fileUrl(f.path,true);img.onerror=()=>{const p=document.createElement('p');p.textContent='Obrázek nelze načíst. Ověř spojení, přístup k SD nebo soubor stáhni.';body.replaceChildren(p);};body.append(img);}
 else {body.textContent='Načítám PDF prohlížeč…';import('/pdf-viewer.mjs?v=3').then(m=>{if(!signal.aborted)return m.mountPdf(body,fileUrl(f.path,true),signal);}).catch(e=>{if(!signal.aborted)body.textContent='PDF nelze načíst: '+e.message;});}
 document.documentElement.classList.add('preview-open');dialog.showModal();
}
$('#closePreview').onclick=()=>$('#previewDialog').close();$('#previewDialog').onclose=()=>{previewAbort?.abort();$('#previewBody').replaceChildren();document.documentElement.classList.remove('preview-open');if(previewObjectUrl){URL.revokeObjectURL(previewObjectUrl);previewObjectUrl=null;}};
function imageScale(change){previewZoom=change===0?100:Math.max(50,Math.min(400,previewZoom+change));const img=$('#previewBody img');if(img){img.style.width=previewZoom+'%';img.style.height=previewZoom===100?'100%':'auto';}$('#imageFit').textContent=previewZoom===100?'Přizpůsobit':previewZoom+' %';}
$('#imageSmaller').onclick=()=>imageScale(-25);$('#imageLarger').onclick=()=>imageScale(25);$('#imageFit').onclick=()=>imageScale(0);

function showOrphan(){
 $('#transferPanel').hidden=false;$('#transferTitle').textContent='Nedokončený přenos';$('#transferDetail').textContent=`${orphanUpload.path} · ${bytes(orphanUpload.offset)} z ${bytes(orphanUpload.size)}. Zruš jej pro uvolnění SD. Pokračovat lze v původní kartě prohlížeče, kde byl soubor vybrán.`;
 $('#uploadProgress').value=orphanUpload.size?orphanUpload.offset/orphanUpload.size*100:0;$('#retryUpload').hidden=true;$('#cancelUpload').disabled=false;$('#chooseUpload').disabled=true;
}
function uploadProgress(extra=0){
 const j=uploadJob;if(!j)return;const sent=j.finishedBytes+(j.session?.offset||0)+extra,percent=j.total?Math.min(100,sent/j.total*100):0;
 $('#transferPanel').hidden=false;$('#transferTitle').textContent=`Nahrávání ${j.index+1} / ${j.files.length}`;$('#transferPercent').textContent=Math.floor(percent)+' %';$('#uploadProgress').value=percent;
 const speed=Math.max(0,sent-j.startedBytes)/Math.max(1,(performance.now()-j.startedAt)/1000);
 $('#transferDetail').textContent=`${j.files[j.index]?.name||''} · ${bytes(sent)} / ${bytes(j.total)}${speed>0?' · '+bytes(speed)+'/s · zbývá asi '+Math.ceil((j.total-sent)/speed)+' s':''}`;
}
function sendChunk(session,file,signal,onProgress){return new Promise((resolve,reject)=>{
 const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload/chunk?id='+encodeURIComponent(session.id)+'&offset='+session.offset);xhr.setRequestHeader('X-IMU-Client','1');xhr.timeout=0;
 let timer;const touch=()=>{clearTimeout(timer);timer=setTimeout(()=>{xhr.abort();reject(Error('Přenos 45 s nepokročil. Potvrzené bloky zůstaly uložené.'));},45000);};
 const abort=()=>xhr.abort();signal.addEventListener('abort',abort,{once:true});
 const clean=()=>{clearTimeout(timer);signal.removeEventListener('abort',abort);};
 xhr.upload.onprogress=e=>{touch();onProgress(Math.min(e.loaded,Math.min(session.chunkSize,file.size-session.offset)));};
 xhr.onload=()=>{clean();try{const d=JSON.parse(xhr.responseText);xhr.status===200?resolve(d):reject(Error(d.error||'Nahrání bloku selhalo.'));}catch(e){reject(e);}};
 xhr.onerror=()=>{clean();reject(Error('Spojení se přerušilo. Přenos lze obnovit.'));};xhr.onabort=()=>{clean();reject(Error('Přenos pozastaven.'));};
 const form=new FormData();form.append('file',file.slice(session.offset,session.offset+session.chunkSize),'chunk.bin');touch();xhr.send(form);
});}
async function runUpload(){
 const j=uploadJob;if(!j||j.running)return;j.running=true;j.cancel=false;j.controller=new AbortController();j.startedAt=performance.now();j.startedBytes=j.finishedBytes+(j.session?.offset||0);$('#retryUpload').hidden=true;$('#cancelUpload').disabled=false;
 try{
  while(j.index<j.files.length){
   const f=j.files[j.index],path=joinPath(j.folder,f.name);validateName(f.name);
   if(!j.session){j.token ||= [...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');j.session=await api('/api/upload/start',{path,size:f.size,id:j.token});}
   else {const current=await api('/api/upload/status');if(!current.active&&current.completedId===j.session.id){j.finishedBytes+=f.size;j.index++;j.session=null;j.token=null;continue;}if(!current.active||current.id!==j.session.id)throw Error('Deska už tento přenos nemá. Zruš frontu a vyber soubor znovu.');j.session=current;}
   uploadProgress();
   while(j.session.offset<f.size){
    if(j.cancel)throw Error('Přenos zrušen.');let last;
    for(let attempt=0;attempt<3;attempt++){
     try{j.session=await sendChunk(j.session,f,j.controller.signal,uploadProgress);last=null;break;}
     catch(e){last=e;if(j.cancel)throw e;await new Promise(r=>setTimeout(r,1000*(attempt+1)));const actual=await api('/api/upload/status');if(!actual.active||actual.id!==j.session.id)throw e;j.session=actual;if(actual.offset===f.size){last=null;break;}}
    }
    if(last)throw last;uploadProgress();
   }
   if(j.cancel)throw Error('Přenos zrušen.');await api('/api/upload/finish?id='+encodeURIComponent(j.session.id),{});j.finishedBytes+=f.size;j.index++;j.session=null;j.token=null;
  }
  $('#transferTitle').textContent='Všechny soubory jsou uložené';$('#transferDetail').textContent=`${j.files.length} souborů · ${bytes(j.total)}`;$('#uploadProgress').value=100;$('#transferPercent').textContent='100 %';$('#cancelUpload').disabled=true;uploadJob=null;orphanUpload=null;await loadFiles();toast('Nahrávání dokončeno.');
 }catch(e){$('#transferDetail').textContent=e.message;$('#transferTitle').textContent=j.cancel?'Ruším přenos…':'Přenos čeká na pokračování';$('#retryUpload').hidden=j.cancel;}
 finally{j.running=false;if(j.cancel)await discardUpload();if(state)syncFileLocks(state);}
}
async function enqueueFiles(files){
 if(uploadJob||orphanUpload)throw Error('Nejdříve dokonči nebo zruš současnou frontu.');if(fileLocked())throw Error('SD je právě zamčená.');
 const list=[...files];if(!list.length)return;list.forEach(f=>{validateName(f.name);if(f.size>0xffffffff)throw Error('FAT32: soubor nesmí přesáhnout 4 GiB − 1 B.');});
 uploadJob={files:list,folder,index:0,total:list.reduce((n,f)=>n+f.size,0),finishedBytes:0,session:null,running:false};await runUpload();
}
async function discardUpload(){
 try{const u=await api('/api/upload/status');if(u.active)await api('/api/upload/cancel?id='+encodeURIComponent(u.id),{});uploadJob=null;orphanUpload=null;$('#transferPanel').hidden=true;await loadFiles();toast('Nedokončený přenos byl zrušen. Hotové soubory zůstaly uložené.');}
 catch(e){$('#transferDetail').textContent='Zrušení zatím nebylo potvrzeno deskou. '+e.message;$('#cancelUpload').disabled=false;}
}
$('#chooseUpload').onclick=()=>$('#upload').click();$('#upload').onchange=safe(async e=>{const files=[...e.target.files];e.target.value='';await enqueueFiles(files);});
$('#retryUpload').onclick=safe(runUpload);$('#cancelUpload').onclick=safe(async()=>{if(uploadJob?.running){uploadJob.cancel=true;uploadJob.controller.abort();$('#cancelUpload').disabled=true;}else await discardUpload();});
let dragDepth=0;$('#fileTools').ondragenter=e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();dragDepth++;$('#fileTools').classList.add('dragover');}};$('#fileTools').ondragover=e=>e.preventDefault();$('#fileTools').ondragleave=()=>{if(--dragDepth<=0)$('#fileTools').classList.remove('dragover');};$('#fileTools').ondrop=safe(async e=>{e.preventDefault();dragDepth=0;$('#fileTools').classList.remove('dragover');await enqueueFiles(e.dataTransfer.files);});

async function createPdfReport(){
 if(reportBusy)return;if(source!=='csv'||!data?.length)throw Error('Nejdříve otevři CSV záznam.');
 const sourceData=data;reportBusy=true;$('#pdfReport').disabled=true;$('#pdfReport').textContent='Vytvářím PDF…';
 try{
  const {generateReport}=await import('/report.mjs'),blob=await generateReport(sourceData);
  if(previewObjectUrl)URL.revokeObjectURL(previewObjectUrl);previewObjectUrl=URL.createObjectURL(blob);
  const name=baseName(sourceData.info?.name||'Zaznam.csv').replace(/\.csv$/i,'')+'_report.pdf';
  const body=$('#previewBody');body.replaceChildren();body.className='';$('#previewTitle').textContent=name;$('#previewTitle').title=name;
  $('#previewDownload').href=previewObjectUrl;$('#previewDownload').download=name;$('#previewDownload').dataset.remote='0';$('#previewDownload').onclick=null;$('#previewDownload').removeAttribute('aria-disabled');$('#previewOpen').href=previewObjectUrl;$('#imageZoom').hidden=true;
  previewAbort?.abort();previewAbort=new AbortController();document.documentElement.classList.add('preview-open');$('#previewDialog').showModal();
  const {mountPdf}=await import('/pdf-viewer.mjs?v=3');await mountPdf(body,previewObjectUrl,previewAbort.signal);
 }finally{reportBusy=false;$('#pdfReport').disabled=source!=='csv';$('#pdfReport').textContent='PDF report';}
}
$('#pdfReport').onclick=safe(createPdfReport);
