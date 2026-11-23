const groups=[['Akcelerometr','g'],['Gyroskop','°/s'],['Magnetometr','µT']];
const axisColors=[[40,123,212],[19,118,83],[174,116,18]],red=[217,45,67],ink=[20,33,56],muted=[97,114,134];
const number=v=>Number.isFinite(v)?Math.abs(v)>=1e7?v.toExponential(3):v.toLocaleString('cs-CZ',{maximumFractionDigits:5}):'—';

export function summarize(data){
 if(!data?.length)throw Error('CSV neobsahuje žádné vzorky.');
 const from=data.get(0)[0],to=data.get(data.length-1)[0],span=Math.max(.000001,to-from),binCount=900;
 const axes=Array.from({length:9},()=>({min:Infinity,max:-Infinity,minTime:0,maxTime:0,count:0,clipped:0,bins:Array.from({length:binCount},()=>({lo:Infinity,hi:-Infinity,clip:false}))}));
 for(let i=0;i<data.length;i++){
  const row=data.get(i),bin=Math.min(binCount-1,Math.max(0,Math.floor((row[0]-from)/span*binCount)));
  for(let axis=0;axis<9;axis++){
   const fresh=axis<3?row[13]:axis<6?row[14]:row[11],value=row[axis+1];
   if(!fresh||!Number.isFinite(value)||(axis>=6&&!row[12]))continue;
   const s=axes[axis];s.count++;
   if(value<s.min){s.min=value;s.minTime=row[0];}if(value>s.max){s.max=value;s.maxTime=row[0];}
   const clipped=Boolean(row[10]&(1<<axis));s.clipped+=clipped;
   const b=s.bins[bin];b.lo=Math.min(b.lo,value);b.hi=Math.max(b.hi,value);b.clip||=clipped;
  }
 }
 return {from,to,span,rows:data.length,axes};
}
function binary(bytes){let s='';for(let i=0;i<bytes.length;i+=16384)s+=String.fromCharCode(...bytes.subarray(i,i+16384));return s;}

export function buildReport(jsPDF,data,fontRegular,fontBold,created=new Date()){
 const summary=summarize(data),info=data.info||{},name=info.name||'Záznam CSV';
 const doc=new jsPDF({unit:'mm',format:'a4',compress:true,putOnlyUsedFonts:true});
 doc.addFileToVFS('ImuRegular.ttf',binary(fontRegular));doc.addFont('ImuRegular.ttf','IMU','normal');
 doc.addFileToVFS('ImuBold.ttf',binary(fontBold));doc.addFont('ImuBold.ttf','IMU','bold');
 doc.setProperties({title:'IMU Test · '+name,subject:'Naměřená minima, maxima a průběhy všech os',author:'IMU Test'});
 function text(value,x,y,size=10,color=ink,bold=false,options={}){doc.setFont('IMU',bold?'bold':'normal');doc.setFontSize(size);doc.setTextColor(...color);doc.text(Array.isArray(value)?value:String(value),x,y,options);}
 function wrapped(value,x,y,width,size=9,color=muted){doc.setFont('IMU','normal');doc.setFontSize(size);const lines=doc.splitTextToSize(value,width);text(lines,x,y,size,color);return y+lines.length*size*.42;}
 function header(title,page){
  text('IMU / TEST',16,17,10,muted,true);text(title,16,29,23,ink,true);
  doc.setDrawColor(220,228,236);doc.line(16,35,194,35);
  text('ICM-20948 · ESP32-S3-LCD-1.47',16,286,8,muted);text(page+' / 4',194,286,8,muted,false,{align:'right'});
 }
 header('Report měření',1);
 let y=wrapped(name,16,44,178,11,ink)+5;
 text('Vygenerováno: '+created.toLocaleString('cs-CZ'),16,y,9,muted);y+=8;
 text('Čas záznamu',16,y,9,muted);text('Řádků CSV',104,y,9,muted);y+=7;
 text(number(summary.from)+'–'+number(summary.to)+' s',16,y,15,ink,true);text(number(summary.rows),104,y,15,ink,true);y+=10;
 text('Délka: '+number(summary.to-summary.from)+' s',16,y,9,muted);y+=7;
 const cfg=info.settings||{};
 y=wrapped('Rozsahy: A ±'+(cfg.accel_range_g??'neuvedeno')+' g · G ±'+(cfg.gyro_range_dps??'neuvedeno')+' °/s · M ±4912 µT',16,y,178)+3;
 y=wrapped('Frekvence A / G / M: '+[cfg.accel_rate_hz,cfg.gyro_rate_hz,cfg.mag_rate_hz].map(v=>v??'—').join(' / ')+' Hz'+(info.settingsChanged?' · nastavení se v souboru mění':''),16,y,178)+5;
 text('Naměřené extrémy',16,y,13,ink,true);y+=8;
 const xs=[18,53,88,124,158,191];
 doc.setFillColor(238,243,247);doc.rect(16,y-5,178,9,'F');
 ['Osa','Minimum','Maximum','Max. |v|','Vzorků','Limit'].forEach((v,i)=>text(v,xs[i],y,8,muted,true,{align:i?'right':'left'}));y+=9;
 summary.axes.forEach((s,i)=>{
  text(['A','G','M'][Math.floor(i/3)]+' '+ 'XYZ'[i%3],xs[0],y,9,axisColors[i%3],true);
  [number(s.min),number(s.max),s.count?number(Math.max(Math.abs(s.min),Math.abs(s.max))):'—',number(s.count),number(s.clipped)].forEach((v,j)=>text(v,xs[j+1],y,8,j===4&&s.clipped?red:ink,false,{align:'right'}));
  doc.setDrawColor(234,239,244);doc.line(16,y+3,194,y+3);y+=9;
 });
 y+=5;y=wrapped('Jednotky: A [g], G [°/s], M [µT]. Extrémy a počty vycházejí pouze z nových platných odečtů dané skupiny. Opakované hodnoty pomalejšího senzoru se do počtu nezahrnují.',16,y,178)+4;
 y=wrapped('Kontrola importu: '+(info.invalid||0)+' vynechaných řádků · '+(info.seqMissing||0)+' chybějících sekvenčních čísel. '+(info.crc?'Kontrolní součty CRC32 ověřeny.':'Starší CSV bez kontrolních součtů CRC32.'),16,y,178,9,(info.invalid||info.seqMissing)?red:muted)+4;
 wrapped('Červená označuje ≥98 % rozsahu nebo overflow. Za saturací nelze určit skutečnou špičku. Grafy zachovávají minima a maxima v časových úsecích; přesná data zůstávají v CSV. Čas je relativní, nejde o čas dne.',16,y,178,8);
 for(let group=0;group<3;group++){
  doc.addPage();header(groups[group][0],group+2);
  text('Celý záznam · '+number(summary.from)+' až '+number(summary.to)+' s · '+groups[group][1],16,44,10,muted);
  for(let a=0;a<3;a++){
   const s=summary.axes[group*3+a],top=65+a*72,left=31,right=194,bottom=top+47;
   text('XYZ'[a]+' ['+groups[group][1]+']',16,top-9,12,axisColors[a],true);
   text('min '+number(s.min)+' · max '+number(s.max)+' · limit '+s.clipped,194,top-9,8,muted,false,{align:'right'});
   if(!s.count){text('Žádná platná nová data této osy.',31,top+22,11,muted);continue;}
   let lo=s.min,hi=s.max;if(lo===hi){const pad=Math.max(1,Math.abs(lo)*.05);lo-=pad;hi+=pad;}else{const pad=(hi-lo)*.08;lo-=pad;hi+=pad;}
   const py=v=>bottom-(v-lo)/(hi-lo)*(bottom-top),px=i=>left+i/(s.bins.length-1)*(right-left);
   for(let tick=0;tick<5;tick++){
    const yy=top+(bottom-top)*tick/4;doc.setDrawColor(229,235,241);doc.setLineWidth(.15);doc.line(left,yy,right,yy);
    text(number(Number((hi-(hi-lo)*tick/4).toPrecision(4))),left-3,yy+1,6.5,muted,false,{align:'right'});
    text(number(Number((summary.from+(summary.to-summary.from)*tick/4).toFixed(3)))+' s',left+(right-left)*tick/4,bottom+5,6.5,muted,false,{align:tick===0?'left':tick===4?'right':'center'});
   }
   let previous=null;doc.setLineWidth(.22);
   s.bins.forEach((b,i)=>{if(!Number.isFinite(b.lo)){previous=null;return;}const x=px(i),mid=(b.lo+b.hi)/2;doc.setDrawColor(...(b.clip?red:axisColors[a]));doc.line(x,py(b.lo),x,py(b.hi));if(b.lo===b.hi){doc.setFillColor(...(b.clip?red:axisColors[a]));doc.circle(x,py(mid),.2,'F');}if(previous){doc.setDrawColor(...(b.clip||previous.clip?red:axisColors[a]));doc.line(previous.x,py(previous.mid),x,py(mid));}previous={x,mid,clip:b.clip};});
   text('Minimum v '+number(s.minTime)+' s · maximum v '+number(s.maxTime)+' s',left,bottom+11,7,muted);
  }
 }
 return {doc,summary};
}

export async function generateReport(data){
 await import('/vendor/jspdf.umd.min.js');
 const read=async name=>{const r=await fetch('/pdfjs/standard_fonts/'+name);if(!r.ok)throw Error('Nelze načíst písmo reportu.');return new Uint8Array(await r.arrayBuffer());};
 const fonts=await Promise.all([read('LiberationSans-Regular.ttf'),read('LiberationSans-Bold.ttf')]);
 await new Promise(resolve=>setTimeout(resolve,0));
 return buildReport(window.jspdf.jsPDF,data,...fonts).doc.output('blob');
}
