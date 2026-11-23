'use strict';
let ppkJob=0,ppkPage=0,ppkAssets=[];
const ppkLabels={obs:'Observace RINEX',nav:'Navigace RINEX',sbf:'Septentrio SBF',ubx:'u-blox UBX',rtcm3:'RTCM 3'};
function resetPpk(){
 ppkJob=ppkPage=0;ppkAssets=[];$('ppk-form').reset();
 for(const id of ['ppk-table','ppk-jobs','ppk-rover','ppk-base','ppk-result','ppk-nav']){
   $(id).replaceChildren();delete $(id).dataset.options;
 }
 setText('ppk-summary','');$('ppk-csv').hidden=true;
}
function ppkFields(){
 const manual=$('ppk-ref').value==='manual';$('ppk-llh').hidden=!manual;
 for(const id of ['ppk-lat','ppk-lon','ppk-height'])$(id).required=manual;
 setText('ppk-ref-note',manual?'Zadej souřadnice referenčního bodu antény základny v systému WGS 84.':'Přesnost celé trasy závisí na souřadnicích uložených v hlavičce základny.');
 const ids=[$('ppk-base').value,$('ppk-rover').value.replace(/^file-/,'')];
 const rtc=ppkAssets.some(a=>ids.includes(String(a.id))&&a.format==='rtcm3');
 $('ppk-date-row').hidden=!rtc;$('ppk-date').required=rtc;
}
function drawPpk(d){
 ppkAssets=d.assets;
 const empty=[['','Vyber měření']],obs=d.assets.filter(a=>a.format!=='nav');
 const name=a=>'#'+a.id+' · '+a.name+' · '+ppkLabels[a.format];
 setOptions($('ppk-rover'),[...empty,...d.rides.map(r=>['ride-'+r.id,'Jízda #'+r.id+' · '+r.name+(r.obs_epochs===0?' · bez RAW epoch':'')]),...obs.map(a=>['file-'+a.id,name(a)])],$('ppk-rover').value);
 setOptions($('ppk-base'),[...empty,...obs.map(a=>[a.id,name(a)])],$('ppk-base').value);
 const nav=$('ppk-nav'),opts=d.assets.filter(a=>a.format==='nav'),signature=opts.map(a=>a.id).join(',');
 if(nav.dataset.options!==signature){
   const selected=new Set(Array.from(nav.selectedOptions,o=>o.value));
   nav.replaceChildren(...opts.map(a=>new Option(name(a),String(a.id),false,selected.has(String(a.id)))));
   nav.dataset.options=signature;
 }
 ppkFields();
 $('ppk-start').disabled=d.jobs.some(j=>j.state==='running')||!obs.length;
 const states={running:'Probíhá',done:'Hotovo',failed:'Chyba'};
 uiTable($('ppk-jobs'),['Začátek','Úloha','Stav','Výsledek'],d.jobs.map(j=>{
   const p=JSON.parse(j.params);
   return [localTime(j.started,true),j.kind==='import'?'Import · '+p.path:'PPK #'+j.id,states[j.state],j.note];
 }),'Zatím žádné úlohy.');
 setOptions($('ppk-result'),d.solutions.map(j=>[j.id,'#'+j.id+' · '+localTime(j.started,true)+' · '+j.note]),d.job);
 const result=d.detail;
 if(result){
   const p=JSON.parse(result.params),ref=JSON.parse(result.reference);
   const file=id=>d.assets.find(a=>a.id===id)?.name||'#'+id;
   const source=p.ride?'jízda #'+p.ride:file(p.rover);
   const program=result.solver?JSON.parse(result.solver).program:'';
   setText('ppk-summary',[source,'základna '+file(p.base),(ref[0]==='-r'?'XYZ z hlavičky (m)':'WGS 84 (°, °, m)')+' '+ref.slice(1).join(' / '),result.note,program].filter(Boolean).join(' · '));
 }else setText('ppk-summary','');
 $('ppk-csv').hidden=!d.count;$('ppk-csv').href='/api/ppk/result.csv?job='+d.job;
 const quality={1:'RTK Fix',2:'RTK Float',3:'SBAS',4:'DGPS',5:'Samostatná',6:'PPP'};
 uiTable($('ppk-table'),['GPS týden','TOW (s)','Šířka (°)','Délka (°)','Výška (m)','Řešení','Družice','σ N/E/U (m)','Ratio'],
   d.epochs.map(r=>[r.gps_week,(r.tow_ms/1000).toFixed(3),r.lat.toFixed(9),r.lon.toFixed(9),r.height_m.toFixed(3),quality[r.quality]||r.quality,r.satellites,[r.sd_n_m,r.sd_e_m,r.sd_u_m].map(v=>v.toFixed(3)).join(' / '),r.ratio]),
   'Po dokončení výpočtu se zde zobrazí výsledné souřadnice.');
 ppkPage=d.page;setText('ppk-page',d.count?(d.page+1)+' / '+Math.ceil(d.count/50):'');
 $('ppk-prev').disabled=!d.page;$('ppk-next').disabled=(d.page+1)*50>=d.count;
}
for(const id of ['ppk-ref','ppk-base','ppk-rover'])$(id).onchange=ppkFields;
$('ppk-files').onclick=()=>{fileTarget='inbox';filePath='';filePage=0;changePage('files')};
$('ppk-result').onchange=()=>{ppkJob=Number($('ppk-result').value);ppkPage=0;refreshWorkPage(true)};
$('ppk-prev').onclick=()=>{ppkPage=Math.max(0,ppkPage-1);refreshWorkPage(true)};
$('ppk-next').onclick=()=>{ppkPage++;refreshWorkPage(true)};
$('ppk-form').onsubmit=e=>{
 e.preventDefault();
 const [source,id]=$('ppk-rover').value.split('-'),manual=$('ppk-ref').value==='manual';
 const params={base:Number($('ppk-base').value),[source==='ride'?'ride':'rover']:Number(id),
   reference:manual?'manual':'header',nav:Array.from($('ppk-nav').selectedOptions,o=>Number(o.value)),
   date:$('ppk-date').value};
 if(manual)params.llh=['ppk-lat','ppk-lon','ppk-height'].map(id=>$(id).valueAsNumber);
 workAction(async()=>{await request('ppk/solve',params);ppkJob=ppkPage=0});
};
