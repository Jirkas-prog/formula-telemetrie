'use strict';
let accData=null,accMark=0,accRun=0,accPage=0,accEditing=null;
function uiNode(tag,text,cls){
 const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;
}
function uiButton(text,fn,cls='quiet'){
 const btn=uiNode('button',text,cls);btn.type='button';btn.addEventListener('click',fn);return btn;
}
function setOptions(select,items,value){
 const sig=JSON.stringify(items);
 if(select.dataset.options!==sig){
   select.replaceChildren(...items.map(([key,name])=>new Option(name,String(key))));select.dataset.options=sig;
 }
 select.value=String(value);
}
function uiTable(container,headers,rows,empty){
 if(!rows.length){container.replaceChildren(uiNode('p',empty,'tool-empty'));return}
 const table=uiNode('table'),head=table.createTHead().insertRow();
 headers.forEach(h=>head.append(uiNode('th',h)));
 const body=table.createTBody();
 for(const cells of rows){const tr=body.insertRow();for(const val of cells){
   const td=tr.insertCell();if(val instanceof Node)td.append(val);else td.textContent=val??'—';
 }}
 container.replaceChildren(table);
}
const metres=v=>Number.isFinite(v)?decimal(v,3)+' m':'—';
function polarPlot(detail){
 const box=$('acc-plot');box.replaceChildren();
 if(!detail?.plot?.length){box.append(uiNode('p','Čekání na platné polohové vzorky.','tool-empty'));return}
 const svg=svgEl('svg',{viewBox:'0 0 400 330',role:'img','aria-label':'Polární graf vodorovných odchylek od těžiště testu'});
 const cx=200,cy=163,R=126;
 const raw=Math.max(0.01,detail.maximum||0);
 const unit=10**Math.floor(Math.log10(raw)),scale=([1,2,5,10].find(k=>k*unit>=raw)||10)*unit;
 function label(x,y,t,anchor='middle'){const el=svgEl('text',{x,y,'text-anchor':anchor});el.textContent=t;svg.append(el)}
 for(const k of [.25,.5,.75,1])svg.append(svgEl('circle',{cx,cy,r:k*R,class:'ring'}));
 for(const [x1,y1,x2,y2] of [[cx-R,cy,cx+R,cy],[cx,cy-R,cx,cy+R]])svg.append(svgEl('line',{x1,y1,x2,y2,class:'axis'}));
 for(const [x,y,t] of [[cx,18,'S'],[cx,318,'J'],[42,cy+4,'Z'],[358,cy+4,'V']])label(x,y,t);
 label(cx+5,cy-R+13,decimal(scale,3)+' m','start');
 const far=detail.farthest;
 function dot(p,big){
   const [e,n,t,m]=p,rad=Math.hypot(e,n),az=(Math.atan2(e,n)*180/Math.PI+360)%360;
   const el=svgEl('circle',{cx:cx+e/scale*R,cy:cy-n/scale*R,r:big?4.6:2.7,fill:big?'#ff895e':'#69dec2',opacity:big?1:.68});
   const title=svgEl('title',{});title.textContent=localTime(t,true)+' · '+metres(rad)+(rad?' · '+decimal(az,1)+'°':'')+' · '+(fixNames[m]||'Režim '+m);
   el.append(title);svg.append(el);
 }
 for(const p of detail.plot)dot(p,false);
 if(far)dot(far,true);
 svg.append(svgEl('path',{d:'M194 163h12m-6-6v12',stroke:'#fff','stroke-width':1.5}));
 box.append(svg);
}
function drawAccuracy(data){
 accData=data;accMark=data.mark?.id||0;accPage=data.page;
 const active=data.active,mark=data.mark,run=data.run,d=data.detail,ref=data.reference;
 setOptions($('acc-mark'),data.marks.map(m=>[m.id,m.name]),accMark);
 $('acc-edit').disabled=!mark;$('acc-start').disabled=!mark||!!active;
 const here=active&&active.mark_id===accMark;
 $('acc-stop').hidden=$('acc-reset').hidden=!here;$('acc-step').disabled=!!here;
 if(here)$('acc-step').value=active.step_s;
 setText('acc-place-note',mark?mark.note:'Přidej místo a popiš, kam položíš střed antény.');
 const coords=(lat,lon)=>decimal(lat,8)+'°, '+decimal(lon,8)+'°';
 setText('acc-coords',mark?[
   mark.anchor_lat!=null?'První změřená poloha '+coords(mark.anchor_lat,mark.anchor_lon):'První platný vzorek uloží polohu značky.',
   mark.known_lat!=null?'Známá poloha '+coords(mark.known_lat,mark.known_lon):''
 ].filter(Boolean).join(' · '):'');
 let msg='Polož anténu na značku a po dobu testu s ní nehýbej.';
 if(active){
   const waiting=!status?.device?.connected?'Čeká na přijímač.':!fresh()||!status?.latest?.valid?'Čeká na platný fix.':status.latest.mode===3?'Přijímač má vynucenou pevnou polohu.':'';
   msg='Běží test #'+active.id+' · '+(data.marks.find(m=>m.id===active.mark_id)?.name||'')+' · '+nf.format(active.n)+' vzorků. '+waiting+(here?' Při vynulování se dosavadní test uloží.':'');
 }
 setText('acc-status',data.error||msg);
 setText('acc-plot-id',run?'Test #'+run.id:'');
 polarPlot(d);setText('acc-plot-note',d?.plot.length?'Křížek · těžiště　 Oranžový bod · maximum　 Zobrazeno '+nf.format(d.plot.length)+' z '+nf.format(run.n):'');
 const stats=[['Začátek',run?localTime(run.started_ms,true):'—'],['Vzorky / interval',run?nf.format(run.n)+' / '+run.step_s+' s':'—'],
   ['Maximální odskok',metres(d?.maximum)],['Průměrný odskok',metres(d?.mean)]];
 if(run&&run.n){
   if(run.coordinates)stats.push(['Souřadnice těžiště',coords(...run.coordinates)]);
   if(d.maximum>0){const [e,n,t]=d.farthest;stats.push(['Největší odskok · azimut / čas',decimal((Math.atan2(e,n)*180/Math.PI+360)%360,1)+'° · '+localTime(t)])}
   stats.push(['Těžiště od první polohy místa','V '+metres(run.east)+' · S '+metres(run.north)]);
   if(data.known_en)stats.push(['Odchylka od známé značky',metres(Math.hypot(run.east-data.known_en[0],run.north-data.known_en[1]))]);
   stats.push(['Režimy řešení',Object.entries(d.modes).map(([k,v])=>(fixNames[k]||k)+' × '+nf.format(v)).join(' · ')]);
 }
 $('acc-stats').replaceChildren(...stats.map(([k,v])=>reading(k,v)));
 setText('acc-baseline',ref?'Referenční těžiště · test #'+ref.id+' · '+localTime(ref.started_ms,true):'První ukončený test s body určí referenci');
 const rows=data.history.map(r=>{
   const dx=r.n&&ref?r.east-ref.east:null,dy=r.n&&ref?r.north-ref.north:null;
   const open=uiButton('#'+r.id+' · '+localTime(r.started_ms,true),()=>{accRun=r.id;refreshWorkPage(true)});
   if(run?.id===r.id)open.classList.add('current');
   const choose=r.id===ref?.id?'Reference':r.n&&r.state!=='running'?uiButton('Jako referenci',()=>workAction(async()=>{await request('accuracy/reference',{mark:accMark,run:r.id})})):'—';
   return [open,({done:'Ukončen',running:'Probíhá',interrupted:'Přerušen'})[r.state],nf.format(r.n),metres(dx),metres(dy),dx==null?'—':metres(Math.hypot(dx,dy)),choose];
 });
 uiTable($('acc-history'),['Test / začátek','Stav','Body','Δ východ','Δ sever','Posun těžiště','Reference'],rows,'Na tomto místě zatím není uložený test.');
 $('acc-prev').disabled=!data.page;$('acc-next').disabled=(data.page+1)*data.per_page>=data.total;
 setText('acc-page',data.total?'Strana '+(data.page+1)+' z '+Math.ceil(data.total/data.per_page)+' · '+nf.format(data.total)+' testů':'');
}
function openMark(edit){
 const mark=edit?accData?.mark:null,f=$('acc-mark-form').elements;
 accEditing=mark?.id??null;
 if(!$('acc-mark-error')){const err=uiNode('p');err.id='acc-mark-error';err.setAttribute('role','alert');$('acc-mark-form').append(err)}
 setText('acc-mark-error','');
 f.namedItem('name').value=mark?.name||'';f.note.value=mark?.note||'';
 f.lat.value=mark?.known_lat??'';f.lon.value=mark?.known_lon??'';
 setText('acc-mark-title',mark?'Upravit měřicí místo':'Nové měřicí místo');$('acc-dialog').showModal();
}
$('acc-new').onclick=()=>openMark(false);$('acc-edit').onclick=()=>openMark(true);
$('acc-mark-form').onsubmit=e=>{
 e.preventDefault();const f=e.currentTarget.elements;
 if((f.lat.value==='')!==(f.lon.value==='')){const field=f.lat.value===''?f.lat:f.lon;field.setCustomValidity('Doplň druhou souřadnici.');field.reportValidity();field.setCustomValidity('');return}
 const data={id:accEditing,name:f.namedItem('name').value,note:f.note.value,known_lat:f.lat.value===''?null:Number(f.lat.value),known_lon:f.lon.value===''?null:Number(f.lon.value)};
 workAction(async()=>{const r=await request('accuracy/mark',data);accMark=r.id;accRun=0;accPage=0;$('acc-dialog').close()});
};
$('acc-mark').onchange=e=>{accMark=Number(e.target.value);accRun=0;accPage=0;refreshWorkPage(true)};
$('acc-start').onclick=()=>workAction(async()=>{const r=await request('accuracy/start',{mark:accMark,step_s:Number($('acc-step').value)});accRun=r.id;accPage=0});
for(const op of ['stop','reset'])$('acc-'+op).onclick=()=>workAction(async()=>{const r=await request('accuracy/'+op,{run:accData.active.id});accRun=r.id;accPage=0});
for(const [id,delta] of [['acc-next',1],['acc-prev',-1]])$(id).onclick=()=>{accPage+=delta;accRun=0;refreshWorkPage(true)};

