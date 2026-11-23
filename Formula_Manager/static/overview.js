'use strict';
const ovSystems=['GPS','GLONASS','Galileo','SBAS','BeiDou','QZSS','NavIC'];
const ovQuality=[[0,'Celková kvalita','target'],[11,'RF výkon antény','antenna'],[1,'Signály GNSS','sat'],[21,'Rezerva CPU','chip'],[31,'RTK postprocessing','refresh']];
const ovTypes={1:'DaisyChain',32:'CMD',33:'SBF',34:'ASCII',35:'RINEX',36:'CGGTTS',40:'BINEX',64:'NMEA',96:'RTCM 2',97:'RTCM 3',98:'CMR',99:'RTCMV'};
const ovMissing='—';
let ovBusy=false,ovPreviousFlow=null,ovRates=new Map(),ovCpu=[];
function ovEl(tag,cls='',value=''){
 const el=document.createElement(tag);if(cls)el.className=cls;if(value!=='')el.textContent=value;return el;
}
function ovIcon(name){const el=ovEl('span','ov-icon');el.setAttribute('aria-hidden','true');putIcon(el,name);return el}
function resetOverview(){
 ovPreviousFlow=null;ovRates=new Map();ovCpu=[];
 renderOverview({},'Čekání na přijímač.');
}
function ovParts(f,field){
 return Object.keys(f||{}).filter(k=>k.startsWith(field+'_')).map(k=>k.slice(field.length));
}
function ovRows(id,rows){
 $(id).replaceChildren(...rows.map(([name,value,sub])=>{
   const row=reading(name,value??ovMissing);
   if(sub)row.lastChild.append(ovEl('small','',sub));return row;
 }));
}
function ovCoord(value,lat){
 if(!Number.isFinite(value))return ovMissing;
 const ticks=Math.round(Math.abs(value)*3600*10000), deg=Math.floor(ticks/36000000), min=Math.floor(ticks/600000)%60;
 const sec=((ticks%600000)/10000).toLocaleString('cs-CZ',{minimumFractionDigits:4,maximumFractionDigits:4});
 return (lat?(value<0?'S':'N'):(value<0?'W':'E'))+' '+deg+'° '+min+'′ '+sec+'″';
}
function ovUtc(t){
 if(!t||t.UTCYear<0||t.UTCMonth<1||t.UTCMonth>12||t.UTCDay<1||t.UTCDay>31||
    t.UTCHour<0||t.UTCHour>23||t.UTCMin<0||t.UTCMin>59||t.UTCSec<0||t.UTCSec>60)return null;
 const pad=n=>String(n).padStart(2,'0');
 return t.UTCDay+'. '+t.UTCMonth+'. '+(2000+t.UTCYear)+' '+[t.UTCHour,t.UTCMin,t.UTCSec].map(pad).join(':');
}
function ovFlag(text,tone){const el=ovEl('span');el.dataset.tone=tone;el.append(ovEl('em'),text);return el}
function ovScores(fields){
 const scores=new Map(ovParts(fields,'QualityType').map(s=>[fields['QualityType'+s],fields['QualityValue'+s]]));
 $('ov-quality').replaceChildren(...ovQuality.map(([code,label,icon])=>{
   const score=scores.get(code),valid=Number.isInteger(score)&&score>=0&&score<=10;
   const card=ovEl('div','ov-q'),value=ovEl('span','ov-value',valid?String(score):ovMissing),bar=ovEl('span','ov-scale'+(valid&&score<5?' low':''));
   value.append(ovEl('small','','/ 10'));bar.setAttribute('aria-hidden','true');
   for(let i=0;i<10;i++)bar.append(ovEl('i',valid&&i<score?'on':''));
   card.append(ovIcon(icon),ovEl('strong','',label),value,bar);return card;
 }));
 return scores.get(0);
}
function ovFlow(id,icon,title,rows,head){
 const target=$(id);target.replaceChildren();
 if(!rows.length){target.append(ovEl('p','ov-empty','Přijímač nehlásí žádný aktivní výstup.'));return}
 if(head){const labels=ovEl('div','ov-flowhead');labels.append(ovEl('span'),ovEl('span','',head[0]),ovEl('span','',head[1]));target.append(labels)}
 const grid=ovEl('div','ov-flow'),origin=ovEl('div','ov-origin');
 origin.append(ovIcon(icon),ovEl('span','',title));
 const lines=svgEl('svg',{viewBox:'0 0 100 100',preserveAspectRatio:'none','aria-hidden':'true',class:'ov-branches'});
 const list=ovEl('div','ov-flowrows');
 rows.forEach((r,i)=>{
   lines.append(svgEl('line',{x1:3,y1:50,x2:96,y2:100*(i+.5)/rows.length,stroke:r.color}));
   const row=ovEl('div','ov-flowrow'+(head?'':' stream')),dot=ovEl('i');dot.style.background=r.color;
   row.append(dot,ovEl('span','',r.label),ovEl(head?'b':'small','',r.a),ovEl('b','',r.b));list.append(row);
 });
 const wire=ovEl('div','ov-wire');wire.append(lines);
 grid.append(origin,wire,list);target.append(grid);
}
function ovLink(id,icon,label,detail,off){
 const pict=ovIcon(icon);pict.dataset.state=off?'off':'on';
 const text=ovEl('div');text.append(ovEl('strong','',label));if(detail)text.append(ovEl('small','',detail));
 $(id).replaceChildren(pict,text);
}
function ovNtrip(client,server){
 const names=['Vypnuto','Inicializace','Připojeno','Chyba','Obnovování','Duplicitní spojení'];
 const links=[];
 for(const [f,role] of [[client,'Klient'],[server,'Server']]){
   for(const s of ovParts(f,'CDIndex')){
     const state=f['Status'+s];
     if(state)links.push(role+' NTR'+f['CDIndex'+s]+' · '+(names[state]??state));
   }
 }
 const label=links.length?links.join(' / '):client&&server?'Vypnuto':ovMissing;
 ovLink('ov-ntrip','globe',label,'NTRIP klient a server přijímače',client&&server&&!links.length);
}
function ovPort(n){
 for(const [start,end,prefix,offset] of [[0,31,'COM',0],[32,47,'USB',32],[48,63,'OTG',48],[64,95,'IP',54],[96,127,'DSK',96],[128,159,'NTR',128],[160,191,'IPS',160],[200,205,'IPR',200]]){
   if(n>=start&&n<=end)return prefix+(n-offset);
 }
 return ({192:'BT01',193:'BT02',196:'UHF1',210:'DCL1',214:'CAN1',220:'SPI1'})[n]||('Port '+n);
}
function ovStreams(frame){
 if(!frame){ovPreviousFlow=null;ovRates.clear();$('ov-streams').replaceChildren(ovEl('p','ov-empty','Čekání na údaje o datových tocích.'));return}
 if(frame.t_ms!==ovPreviousFlow?.t_ms){
   ovRates.clear();
   const seconds=(frame.t_ms-(ovPreviousFlow?.t_ms??frame.t_ms))/1000;
   for(const link of frame.data){
     const prev=ovPreviousFlow?.data.find(x=>x.port===link.port);
     if(prev&&seconds>0&&seconds<=15&&link.sent>=prev.sent)ovRates.set(link.port,(link.sent-prev.sent)/seconds);
   }
   ovPreviousFlow=frame;
 }
 const rows=frame.data.filter(r=>r.types.length||ovRates.get(r.port)>0).map(link=>{
   const rate=ovRates.get(link.port);
   return {label:ovPort(link.port),a:link.types.map(t=>ovTypes[t]||('Typ '+t)).join(' + ')||ovMissing,
      b:rate==null?ovMissing:decimal(rate/1024,2)+' KiB/s',color:'#72b1e9'};
 });
 ovFlow('ov-streams','chip','mosaic-X5',rows);
}
function ovDisk(disk,streams){
 const index=ovParts(disk,'DiskID').find(s=>disk['DiskID'+s]===1);
 const field=name=>index?disk[name+index]:null, size=field('DiskSize'), hi=field('DiskUsageMSB'),lo=field('DiskUsageLSB');
 const mounted=field('Mounted'),known=mounted===1&&size>0&&Number.isInteger(hi)&&Number.isInteger(lo)&&!(hi===65535&&lo===4294967295);
 const used=known?(hi*4294967296+lo)/1048576:null,valid=known&&used<=size,pct=valid?100*used/size:null;
 const ring=ovEl('div','ov-donut'+(valid?'':' unknown'));ring.setAttribute('aria-hidden','true');
 if(valid)ring.style.setProperty('--used',pct+'%');
 ring.append(ovEl('b','',valid?decimal(pct,0)+' %':ovMissing));
 const txt=ovEl('div');
 txt.append(ovEl('strong','',size?'DSK1 · '+decimal(size,0)+' MiB':'Interní disk DSK1'));
 function legend(label,color){const row=ovEl('div','ov-legend'),dot=ovEl('em');dot.style.background=color;row.append(dot,label);txt.append(row)}
 legend('Obsazeno '+(valid?decimal(used,1)+' MiB · '+decimal(pct,0)+' %':ovMissing),'var(--accent)');
 legend('Volno '+(valid?decimal(size-used,1)+' MiB · '+decimal(100-pct,0)+' %':ovMissing),'var(--teal)');
 const logging=field('Logging'),link=streams?.find(x=>x.port===97),rate=ovRates.get(97);
 let caption=index==null?(disk?'Interní disk není hlášen':'Čekání na stav disku'):mounted===0?'Disk odpojen':logging===1?'Záznam aktivní':'Záznam vypnutý';
 if(logging&&link?.types.length)caption+=' · '+link.types.map(t=>ovTypes[t]||('Typ '+t)).join(' + ');
 if(logging&&rate!=null)caption+=' · odhad '+decimal(rate*86400/1048576,1)+' MiB/den';
 txt.append(ovEl('small','',caption));$('ov-disk').replaceChildren(ring,txt);
 return logging;
}
function ovCpuPlot(frame){
 const cpu=frame?.data.CPULoad,stamp=frame?.t_ms,valid=Number.isInteger(cpu)&&cpu>=0&&cpu<=100;
 if(!valid)ovCpu=[];
 else if(ovCpu.at(-1)?.t!==stamp){
   ovCpu=ovCpu.filter(p=>p.t>=stamp-60000&&p.t<stamp);ovCpu.push({t:stamp,v:cpu});
 }
 drawCpuMinute('ov-cpu',ovCpu,stamp,valid?cpu:null,5000);
}
function drawCpuMinute(target,points,stamp,cpu,gap){
 const valid=Number.isFinite(cpu);
 const chart=svgEl('svg',{viewBox:'0 0 240 78',preserveAspectRatio:'none',class:'ov-trace',role:'img','aria-label':'Vytížení CPU od 0 do 100 % za poslední minutu'});
 for(const y of [4,38,72])chart.append(svgEl('line',{x1:0,y1:y,x2:240,y2:y,stroke:'#3c484d'}));
 let line='',last=null;
 for(const p of points){
   const x=238-(stamp-p.t)*236/60000,y=72-p.v*.68;
   line+=(last===null||p.t-last>gap?'M':'L')+x.toFixed(1)+' '+y.toFixed(1)+' ';last=p.t;
 }
 if(line){const end=points.at(-1);chart.append(svgEl('path',{d:line,fill:'none',stroke:'#f1c075','stroke-width':2}));chart.append(svgEl('circle',{cx:238-(stamp-end.t)*236/60000,cy:72-end.v*.68,r:2.4,fill:'#f1c075'}))}
 const box=ovEl('div','ov-cpuvalue'),bar=ovEl('span','ov-meter'),fill=ovEl('i');
 fill.style.height=(valid?cpu:0)+'%';bar.append(fill);
 box.append(ovEl('strong','',valid?decimal(cpu,0)+' %':ovMissing),bar);
 const plot=ovEl('div','ov-plot'),axis=ovEl('div','ov-axis'),times=ovEl('div','ov-times');
 for(const tick of ['100 %','50 %','0 %'])axis.append(ovEl('span','',tick));
 times.append(ovEl('span','','−60 s'),ovEl('span','','Teď'));plot.append(axis,chart,times);
 $(target).replaceChildren(plot,box);
}
function renderOverview(frames,message=''){
 const get=name=>frames[name]?.data;
 const rx=get('ReceiverStatus'),setup=get('ReceiverSetup'),time=get('ReceiverTime'),ip=get('IPStatus'),sky=get('ChannelStatus'),cov=get('PosCovGeodetic');
 const online=gpsOnline(),p=online&&fresh()?status.latest:null, fix=p?.valid?(fixNames[p.mode]||'Platná poloha'):p?'Bez fixu':ovMissing;
 const tracked=sky?Object.values(sky).reduce((a,b)=>a+b.tracked,0):null;
 ovRows('ov-receiver',[['Model',setup?.ProductName,setup?.RxSerialNumber?'S/N '+setup.RxSerialNumber:null],['IPv4 Ethernetu',ip?.ipv4],['Doba od zapnutí',Number.isInteger(rx?.UpTime)?duration(rx.UpTime*1000):null]]);
 const sigma=key=>p?.valid&&cov?.Error===0&&cov.Type===p.mode&&Number.isFinite(cov[key])&&cov[key]>=0?'σ '+decimal(Math.sqrt(cov[key]),2)+' m':null;
 ovRows('ov-position',[['Šířka',ovCoord(p?.valid?p.lat:null,true),sigma('Cov_latlat')],['Délka',ovCoord(p?.valid?p.lon:null,false),sigma('Cov_lonlon')],['Výška',p?.valid?quantity(p.alt_m,'m',3):null,sigma('Cov_hgthgt')]]);
 ovRows('ov-status',[['Sledované družice',tracked],['Čas UTC',ovUtc(time)],['Teplota',rx?.Temperature>0&&rx.Temperature!==255?quantity(rx.Temperature-100,'°C',0):null]]);
 const overall=ovScores(get('QualityInd')),rf=get('RFStatus'),auth=get('GALAuthStatus');
 ovFlow('ov-sky','globe',fix,ovSystems.map(label=>{
   const pair=sky?.[label];
   return {label,a:pair?.used??ovMissing,b:pair?.tracked??ovMissing,color:pair?.used?'#69dec2':pair?.tracked?'#72b1e9':'#526066'};
 }),['Ve výpočtu','Sledováno']);
 ovNtrip(get('NTRIPClientStatus'),get('NTRIPServerStatus'));
 ovLink('ov-ethernet','network',ip?(ip.ipv4||'Bez adresy IPv4'):ovMissing,'Ethernet přijímače',ip&&!ip.ipv4);
 ovStreams(frames.OutputLink);
 const logging=ovDisk(get('DiskStatus'),get('OutputLink'));
 ovCpuPlot(frames.ReceiverStatus);
 const spectrum=rf?(rf.Misleading||rf.Inauthentic?'Varování RF':rf.N?'Aktivita ve spektru':'Spektrum čisté'):'Spektrum '+ovMissing;
 const osnma=['vypnuto','inicializace','čeká na čas','chyba času','chyba podpisu','chyba parametrů','ověřování'];
 $('ov-flags').replaceChildren(ovFlag('Poloha · '+fix,p?.valid?'good':''),
   ovFlag('Kvalita · '+(overall>=0&&overall<=10?overall+'/10':ovMissing),overall>=5&&overall<=10?'good':''),
   ovFlag('Korekce · '+(rx?(rx.DiffCorrIn?'příjem':'bez příjmu'):ovMissing),rx?.DiffCorrIn?'good':''),
   ovFlag('OSNMA · '+(osnma[auth?.Status]??ovMissing),auth?.Status===6?'good':''),
   ovFlag('Hodiny · '+(rx?(rx.ExtFreq?'externí':'interní'):ovMissing),''),
   ovFlag('Záznam GPS · '+(logging==null?ovMissing:logging?'zapnutý':'vypnutý'),logging?'good':''),
   ovFlag(spectrum,rf?(rf.N||rf.Misleading||rf.Inauthentic?'warn':'good'):''));
 $('ov-notice').hidden=!message;setText('ov-notice',message);
}
async function updateOverview(){
 if(!gpsOnline()){resetOverview();setText('ov-notice',networkUp?'GPS přijímač je odpojen.':'Spojení s Raspberry Pi je přerušené.');return}
 if(ovBusy||document.hidden)return;
 const version=gpsVersion;ovBusy=true;
 try{
   const res=await request('receiver/overview');
   if(version===gpsVersion&&currentPage==='gps'&&!$('gps-overview').hidden&&gpsOnline())
     renderOverview(res.frames,res.error||(Object.keys(res.frames).length?'':'Čekání na data z přijímače.'));
 }catch(e){
   if(version===gpsVersion&&currentPage==='gps'&&signed){resetOverview();setText('ov-notice',e.message)}
 }finally{ovBusy=false}
}
