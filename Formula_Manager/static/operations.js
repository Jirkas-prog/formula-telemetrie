'use strict';
let workSerial=0,workDue=0,mediaDue=0,workWriting=false,mediaTargets=[],exportItems=[],exportJob=null;
let usbTarget='',fileTarget='local',filePath='',filePage=0,selectedExports=new Set();
const workPages=['accuracy','export','files','hardware','ppk'];
function resetWorkPages(){
 if(typeof resetPpk==='function')resetPpk();
 workSerial++;workDue=0;mediaTargets=[];exportItems=[];exportJob=null;selectedExports.clear();
 usbTarget='';fileTarget='local';filePath='';filePage=0;
 $('hw-end').value='';$('hw-live').disabled=true;$('hw-charts').replaceChildren();setText('hw-stamp','');$('hw-error').hidden=true;
 accData=null;accMark=accRun=accPage=0;
}
async function workAction(fn){
 if(workWriting)return;
 workWriting=true;
 try{setBanner();await fn()}catch(e){showError(e);if($('acc-dialog').open)setText('acc-mark-error',e.message)}
 finally{workWriting=false;await refreshWorkPage(true)}
}
function targetLabel(t){return t.key==='local'?t.name:t.name+' · '+t.fs.toUpperCase()+' · '+bytes(t.size)}
function updateTargets(list,page){
 if(page==='files')list=[...list,{key:'data',name:'Data loggeru na NVMe',fs:'NVMe',mount:true},{key:'inbox',name:'PPK · příchozí soubory ze Samby',fs:'NVMe',mount:true}];
 mediaTargets=list;
 if(page==='export'){
   if(!list.some(t=>t.key===usbTarget))usbTarget=list.find(t=>t.key!=='local')?.key||'';
   setOptions($('usb-target'),[['','Vybrat cílovou jednotku'],...list.map(t=>[t.key,targetLabel(t)])],usbTarget);
   const t=list.find(t=>t.key===usbTarget),usb=t&&t.key!=='local';
   $('usb-mount').hidden=!usb||!!t.mount;$('usb-unmount').hidden=!usb||!t.mount;
   setText('usb-state',usb?(t.mount?'USB jednotka je připojená.':'Jednotka čeká na připojení.'):t?'Export se uloží do složky exports na NVMe.':list.length===1?'Vlož USB flash disk do Raspberry Pi. Pro místní export můžeš zvolit NVMe.':'Vyber připojenou flashku.');
 }else{
   setOptions($('files-target'),list.map(t=>[t.key,['data','inbox'].includes(t.key)?t.name:targetLabel(t)]),fileTarget);
   const t=list.find(t=>t.key===fileTarget);
   $('files-mount').hidden=!t?.key.startsWith('usb-');
   $('files-mount').textContent=t?.mount?'Odpojit':'Připojit';
 }
}
function drawSelection(){
 const scope=$('exp-scope').value;
 const rows=exportItems.filter(r=>r.kind==='ride'?$('exp-rides').checked:$('exp-tests').checked);
 const input=$('exp-amount'),amount=Number(input.value);
 $('exp-amount-row').hidden=!['latest','days'].includes(scope);
 setText('exp-amount-label',scope==='days'?'Počet dní':'Počet záznamů');
 const box=$('exp-items');box.hidden=scope!=='selected';
 if(!box.hidden){
   const frag=document.createDocumentFragment();
   for(const r of rows){
     const label=uiNode('label'),cb=uiNode('input');cb.type='checkbox';cb.checked=selectedExports.has(r.key);
     cb.onchange=()=>{if(cb.checked)selectedExports.add(r.key);else selectedExports.delete(r.key);updateCount()};
     label.append(cb,uiNode('span',(r.kind==='ride'?'Jízda':'Přesnost')+' · '+r.name),uiNode('small',localTime(r.t,true)));
     frag.append(label);
   }
   box.replaceChildren(frag);if(!rows.length)box.append(uiNode('p','Žádné ukončené záznamy.','tool-empty'));
 }
 function updateCount(){
   let count=rows.length;
   if(scope==='selected')count=rows.filter(r=>selectedExports.has(r.key)).length;
   if(scope==='latest')count=Math.min(count,amount);
   if(scope==='days')count=rows.filter(r=>r.t>=Date.now()-amount*86400000).length;
   setText('exp-count',scope==='new'?'Podle úspěšných exportů na vybranou jednotku.':'Položek ve výběru: '+(Number.isFinite(count)?nf.format(count):'—'));
   $('exp-go').disabled=!count||!mediaTargets.find(t=>t.key===usbTarget)?.mount||exportJob?.state==='running'||(['days','latest'].includes(scope)&&!input.checkValidity());
 }
 updateCount();
}
function drawJob(j){
 exportJob=j;
 const text=j.state==='running'?'Probíhá zápis · '+j.done+' / '+j.total:
   j.state==='done'?'Dokončeno · '+j.total+' položek · '+j.folder:j.state==='failed'?'Export selhal · '+j.error:'Zatím nebyl spuštěn žádný export.';
 setText('exp-job',text);$('exp-open').hidden=j.state!=='done';
 const p=$('exp-progress');p.hidden=j.state!=='running';if(!p.hidden){p.max=j.total;p.value=j.done}
 $('usb-unmount').disabled=j.state==='running'&&j.target===usbTarget;
}
function drawFiles(data){
 const parent=path=>filePath?filePath+'/'+path:path;
 const target=mediaTargets.find(t=>t.key===fileTarget);
 setText('files-path',(target?.name||'Jednotka')+' / '+filePath);$('files-up').disabled=!filePath;
 const rows=data.entries.map(r=>{
   let name;
   if(r.folder){name=uiButton(r.name,()=>{filePath=parent(r.name);filePage=0;refreshWorkPage(true)});name.classList.add('folder')}
   else{name=uiNode('a',r.name);name.href='/api/files/download?'+new URLSearchParams({target:fileTarget,path:parent(r.name)});name.download=r.name}
   const path=parent(r.name),target=fileTarget;
   const eligible=!r.folder&&target!=='data'&&/\.(?:obs|nav|rnx|[0-9]{2}[onghlpj]|sbf|ubx|rtcm3?)(?:\.gz)?$/i.test(r.name);
   return [name,r.folder?'Složka':'Soubor',r.folder?'—':bytes(r.size),localTime(r.t,true),
     eligible?uiButton('Importovat pro PPK',()=>workAction(async()=>{
       await request('ppk/import',{target,path});changePage('ppk');
     })):null];
 });
 uiTable($('files-list'),['Název','Typ','Velikost','Změněno','PPK'],rows,data.message||'Složka je prázdná.');
 filePage=data.page;$('files-prev').disabled=!filePage;$('files-next').disabled=(filePage+1)*100>=data.total;
 setText('files-count',nf.format(data.total)+' položek'+(data.total>100?' · strana '+(filePage+1):''));
}
const hwGroups=[
 ['Teploty',[['cpu_c','Čip CPU'],['ssd_c','NVMe'],['sink_c','Chladič']],'°C',1],
 ['Vytížení CPU',[['cpu_pct','Vytížení']],'%',1],
 ['Paměť RAM',[['ram_used','Použitá'],['ram_avail','Dostupná'],['ram_free','Zcela volná']],'GiB',1073741824],
 ['Úložiště NVMe',[['disk_used','Obsazeno'],['disk_free','Volno']],'GiB',1073741824],
 ['Ventilátor',[['rpm','Otáčky']],'ot/min',1]
];
function hardwareDraw(data){
 const rows=data.samples,end=data.end_ms,windowMs=Number($('hw-period').value)*60000;
 const last=rows.at(-1)||{},colors=['#69dec2','#ffa181','#92baff'],archive=!!$('hw-end').value;
 const errors=[data.storage_error,data.dropped?'Počet ztracených vzorků při výpadku zápisu: '+data.dropped:null].filter(Boolean);
 setText('hw-error',errors.join(' · '));$('hw-error').hidden=!errors.length;
 const frag=document.createDocumentFragment();
 for(const [name,series,unit,divisor] of hwGroups){
   const card=uiNode('article',null,'panel'),head=uiNode('div',null,'panel-head');head.append(uiNode('h2',name));card.append(head);
   const body=uiNode('div',null,'tool-body'),legend=uiNode('div',null,'hw-legend'),chart=svgEl('svg',{viewBox:'0 0 430 112',role:'img','aria-label':name+' za posledních '+$('hw-period').value+' minut'});
   let max=0;
   for(const [key] of series)for(const row of rows)if(Number.isFinite(row[key]))max=Math.max(max,row[key]/divisor);
   max=unit==='%'?100:Math.max(1,Math.ceil(max*(unit==='°C'?1.1:1.02)*10)/10);
   if(unit==='GiB')max=Math.max(max,(last[series[0][0]==='ram_used'?'ram_total':'disk_total']||0)/divisor);
   for(const [frac,y] of [[1,7],[.5,50],[0,93]]){
     chart.append(svgEl('line',{x1:38,x2:426,y1:y,y2:y,class:'axis'}));
     const txt=svgEl('text',{x:34,y:y+3,'text-anchor':'end'});txt.textContent=decimal(max*frac,max>10?0:1);chart.append(txt);
   }
   for(const [i,[key,label]] of series.entries()){
     const v=last[key],item=uiNode('span');const dot=uiNode('i');dot.style.background=colors[i];
     item.append(dot,label+' · '+(Number.isFinite(v)?decimal(v/divisor,unit==='GiB'?2:1)+' '+unit:key==='sink_c'?'bez čidla':'bez údajů'));legend.append(item);
     let path='',prev=0,dotPoint=null;
     for(const r of rows){if(!Number.isFinite(r[key])){prev=0;continue}
       const x=426-388*(end-r.t)/windowMs,y=93-86*r[key]/divisor/max;
       path+=(prev&&r.t-prev<12000?'L':'M')+x.toFixed(2)+' '+y.toFixed(2);prev=r.t;dotPoint=[x,y];
     }
     if(path){chart.append(svgEl('path',{d:path,fill:'none',stroke:colors[i],'stroke-width':1.8}));chart.append(svgEl('circle',{cx:dotPoint[0],cy:dotPoint[1],r:2.5,fill:colors[i]}))}
   }
   for(const [x,text,align] of [[38,'−'+$('hw-period').value+' min','start'],[426,archive?localTime(end):'Teď','end']]){
     const t=svgEl('text',{x,y:109,'text-anchor':align});t.textContent=text;chart.append(t);
   }
   body.append(legend,chart);if(name==='Paměť RAM')body.append(uiNode('small','Dostupná RAM zahrnuje také paměť, kterou Linux může uvolnit z mezipaměti.'));
   card.append(body);frag.append(card);
 }
 $('hw-charts').replaceChildren(frag);
 setText('hw-stamp',rows.length?'Poslední vzorek ve zvoleném období '+localTime(last.t,true):'Ve zvoleném období nejsou uložené žádné vzorky.');
}
async function refreshWorkPage(force){
 const page=currentPage;if(!signed||!workPages.includes(page)||(!force&&(document.hidden||Date.now()<workDue)))return;
 const serial=++workSerial,gen=authGeneration,valid=()=>signed&&currentPage===page&&serial===workSerial&&gen===authGeneration;
 workDue=Date.now()+(page==='files'?20000:page==='hardware'?5000:page==='accuracy'?Math.max(2000,Math.min(60000,(accData?.run?.n||0)/5)):2500);
 try{
   if(page==='accuracy'){
     const d=await request('accuracy?'+new URLSearchParams({mark:accMark,run:accRun,page:accPage}));if(valid())drawAccuracy(d);
   }else if(page==='ppk'){
     const d=await request('ppk?'+new URLSearchParams({job:ppkJob,page:ppkPage}));
     if(valid()){drawPpk(d);workDue=Date.now()+(d.jobs.some(j=>j.state==='running')?1500:15000)}
   }else if(page==='hardware'){
     const params=new URLSearchParams({minutes:$('hw-period').value});
     if($('hw-end').value){
       const end=new Date($('hw-end').value).getTime();
       if(!Number.isFinite(end))return;
       params.set('end_ms',end);
     }
     const d=await request('hardware?'+params);
     if(valid())hardwareDraw(d);
   }else if(page==='export'){
     if(force||Date.now()>=mediaDue||!mediaTargets.length||!exportJob){
       const [m,d]=await Promise.all([request('media'),request('transfers')]);
       if(valid()){mediaDue=Date.now()+8000;updateTargets(m.targets,page);exportItems=d.items;drawJob(d.job);drawSelection()}
     }else{const j=await request('transfers/job');if(valid()&&(j.state!==exportJob.state||j.folder!==exportJob.folder||j.done!==exportJob.done)){drawJob(j);drawSelection()}}
   }else{
     const m=await request('media?browse=1');if(!valid())return;updateTargets(m.targets,page);
     const t=mediaTargets.find(v=>v.key===fileTarget);
     if(!t?.mount){drawFiles({entries:[],total:0,page:0,message:t?'Nejdřív připoj jednotku.':'USB jednotka byla odebrána.'});return}
     const d=await request('files?'+new URLSearchParams({target:fileTarget,path:filePath,page:filePage}));if(valid())drawFiles(d);
   }
 }catch(e){if(valid()){showError(e);if(page==='files')drawFiles({entries:[],total:0,page:0,message:e.message})}}
}
$('usb-refresh').onclick=$('files-refresh').onclick=()=>refreshWorkPage(true);
$('usb-target').onchange=e=>{usbTarget=e.target.value;updateTargets(mediaTargets,'export');drawSelection()};
for(const [id,op] of [['usb-mount','mount'],['usb-unmount','unmount']]){
 $(id).onclick=()=>workAction(()=>request('media/'+op,{target:usbTarget}));
}
$('files-mount').onclick=()=>workAction(()=>{
 const mounted=mediaTargets.find(t=>t.key===fileTarget)?.mount;
 return request('media/'+(mounted?'unmount':'mount'),{target:fileTarget});
});
for(const id of ['exp-scope','exp-rides','exp-tests','exp-amount'])$(id).oninput=drawSelection;
$('exp-go').onclick=()=>workAction(async()=>{
 const kinds=[];if($('exp-rides').checked)kinds.push('ride');if($('exp-tests').checked)kinds.push('test');
 const items=exportItems.filter(r=>kinds.includes(r.kind)&&selectedExports.has(r.key)).map(r=>r.key);
 drawJob(await request('transfers/start',{target:usbTarget,scope:$('exp-scope').value,amount:Number($('exp-amount').value),kinds,items}));drawSelection();
});
$('exp-open').onclick=()=>{fileTarget=exportJob.target;filePath=exportJob.folder;filePage=0;changePage('files')};
$('files-target').onchange=e=>{fileTarget=e.target.value;filePath='';filePage=0;refreshWorkPage(true)};
$('files-up').onclick=()=>{filePath=filePath.split('/').slice(0,-1).join('/');filePage=0;refreshWorkPage(true)};
$('files-next').onclick=()=>{filePage++;refreshWorkPage(true)};$('files-prev').onclick=()=>{filePage--;refreshWorkPage(true)};
$('hw-period').onchange=()=>refreshWorkPage(true);
$('hw-end').onchange=()=>{$('hw-live').disabled=!$('hw-end').value;refreshWorkPage(true)};
$('hw-live').onclick=()=>{$('hw-end').value='';$('hw-live').disabled=true;refreshWorkPage(true)};

