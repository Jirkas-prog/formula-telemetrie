'use strict';
// Shared by the background importer and streaming range export. No network dependencies.
function createCsvData(){
  const columns=['t_s','ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps','mx_uT','my_uT','mz_uT','temp_C','bad_fraction','fax_g','fay_g','faz_g','fgx_dps','fgy_dps','fgz_dps'];
  const limit=2000000,chunkBytes=4*1024*1024;
  function fields(text,delimiter){
    if(!text.includes('"'))return text.split(delimiter);
    const out=[];let cell='',quoted=false,closed=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++}else{quoted=false;closed=true}}else cell+=c}
      else if(c===delimiter){out.push(cell);cell='';closed=false}
      else if(c==='"'&&!cell&&!closed)quoted=true;
      else if(closed){if(!/\s/.test(c))throw Error('Neplatné uvozovky v CSV.')}
      else if(c==='"')throw Error('Neplatné uvozovky v CSV.');else cell+=c;
    }
    if(quoted)throw Error('Neuzavřené uvozovky v CSV.');out.push(cell);return out;
  }
  async function* records(file,{signal,chunk=()=>{}}={}){
    const decoder=new TextDecoder('utf-8',{fatal:true});let pending='',record='',quoted=false,lineNumber=0;
    for(let offset=0;offset<file.size;offset+=chunkBytes){
      signal?.throwIfAborted();const bytes=await file.slice(offset,offset+chunkBytes).arrayBuffer();
      pending+=decoder.decode(bytes,{stream:offset+bytes.byteLength<file.size});let at=0,end;
      while((end=pending.indexOf('\n',at))>=0){
        const line=pending.slice(at,end).replace(/\r$/,'');at=end+1;lineNumber++;
        record+=(record?'\n':'')+line;
        if(line.includes('"'))for(const c of line)if(c==='"')quoted=!quoted;
        if(record.length>1048576)throw Error('Řádek CSV je delší než 1 MB.');
        if(!quoted){if(record.trim())yield {text:record,line:lineNumber};record=''}
      }
      pending=pending.slice(at);if(pending.length>1048576)throw Error('Řádek CSV je delší než 1 MB.');
      await chunk(bytes,Math.min(file.size,offset+bytes.byteLength));signal?.throwIfAborted();
    }
    if(pending){record+=(record?'\n':'')+pending.replace(/\r$/,'');if(pending.includes('"'))for(const c of pending)if(c==='"')quoted=!quoted}
    if(quoted)throw Error('CSV končí uvnitř neuzavřené buňky.');
    if(record.trim())yield {text:record,line:lineNumber+1};
  }
  function schema(text,delimiter){
    text=text.replace(/^\uFEFF/,'');delimiter=delimiter||(text.includes(';')?';':',');
    const header=fields(text,delimiter).map(s=>s.trim().toLowerCase());
    if(new Set(header).size!==header.length)throw Error('CSV má duplicitní názvy sloupců.');
    const index=Object.fromEntries(header.map((name,i)=>[name,i]));
    const times=['time_us','t_s','time_s'].filter(k=>k in index);
    if(times.length!==1)throw Error('CSV musí mít jeden časový sloupec time_us, t_s nebo time_s.');
    const sensor=columns.slice(1,10).some(c=>c.toLowerCase() in index);
    const body=['ax_m_s2','ay_m_s2'].every(c=>c in index);
    if(!sensor&&!body)throw Error('CSV neobsahuje měřené osy. Očekávám ax_g…gz_dps / mx_uT…mz_uT nebo ax_m_s2 a ay_m_s2. Souhrnné tabulky událostí nejsou časový záznam.');
    return {header,index,delimiter,time:times[0],scale:times[0]==='time_us'?1e-6:1,sensor,body,
      quality:'bad_fraction' in index||['ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps','accel_range_g','gyro_range_dps'].every(k=>k in index),
      filtered:columns.slice(12,18).some(c=>c in index),groups:[['ax_g','ay_g','az_g'],['gx_dps','gy_dps','gz_dps'],['mx_ut','my_ut','mz_ut']].map(g=>g.some(c=>c in index))};
  }
  function number(value,delimiter){
    let s=(value??'').trim();if(!s||/^(nan|[-+]?inf(?:inity)?)$/i.test(s))return NaN;
    if(delimiter===';')s=s.replace(',','.');
    if(!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(s))throw Error('Neplatné číslo: '+s.slice(0,30));
    return Number(s);
  }
  function row(record,s){
    const cells=fields(record.text,s.delimiter);if(cells.length!==s.header.length)throw Error('Řádek '+record.line+': jiný počet sloupců než v hlavičce.');
    const get=name=>number(cells[s.index[name]],s.delimiter);
    const time=get(s.time)*s.scale;
    if(!Number.isFinite(time)||time<0)throw Error('Řádek '+record.line+': neplatný čas.');
    return {cells,get,time};
  }
  const hex=bytes=>Array.from(new Uint8Array(bytes),n=>n.toString(16).padStart(2,'0')).join('');
  async function read(file,{signal,progress=()=>{}}={}){
    let s,delimiter,rows=0,first=NaN,last=-Infinity,badRows=0,invalidRows=0,active=-1,flags=[];
    let sums=new Float64Array(21),counts=new Uint32Array(21),binRows=0,binBad=0;
    const chunks=[],bodyChunks=[],blockRows=32768,hashes=[],usedNumbers=new Set(),usedBins=new Set();
    let length=0,seenFiltered=false;const seenGroups=[false,false,false];
    function push(values,body){
      if(length>=limit)throw Error('CSV přesahuje čas 20 000 s nebo limit 2 milionů 100Hz bodů. Vyberte kratší záznam s relativním časem.');
      const b=Math.floor(length/blockRows),p=length%blockRows;
      if(!chunks[b]){chunks[b]=new Float32Array(blockRows*18);chunks[b].fill(NaN);if(s.body){bodyChunks[b]=new Float64Array(blockRows*5);bodyChunks[b].fill(NaN)}}
      chunks[b].set(values,p*18);if(s.body)bodyChunks[b].set(body,p*5);length++;
    }
    function flush(){
      if(active<0)return;
      if(active>=limit)throw Error('CSV má příliš velké časové značky. Podporován je relativní čas do 20 000 s.');
      while(length<active)push([length*.01+.005,...Array(17).fill(NaN)],[length*.01+.005,NaN,NaN,NaN,NaN]);
      const vals=Array.from(sums,(sum,i)=>counts[i]?sum/counts[i]:NaN),time=active*.01+.005;
      const out=[time,...vals.slice(0,10),binRows?binBad/binRows:NaN,...vals.slice(10,16)];
      const body=[time,...vals.slice(16,20)];if(binBad>0)body.fill(NaN,1);
      push(out,body);sums.fill(0);counts.fill(0);binRows=binBad=0;
    }
    const chunk=async(bytes,loaded)=>{hashes.push(hex(await crypto.subtle.digest('SHA-256',bytes)));progress({loaded,total:file.size,rows});await new Promise(r=>setTimeout(r,0))};
    for await(const record of records(file,{signal,chunk})){
      if(!s){const sep=record.text.replace(/^\uFEFF/,'').match(/^sep=([;,])$/i);if(sep){delimiter=sep[1];continue}s=schema(record.text,delimiter);continue}
      const r=row(record,s),{get,cells,time}=r;
      if(time<last)throw Error('Řádek '+record.line+': čas se vrací zpět. Záznamy s restartem nejprve rozdělte.');
      if(!rows)first=time;last=time;rows++;
      const bin=Math.floor(time*100+1e-5);if(bin!==active){flush();active=bin}
      let bad=0;
      if('bad_fraction' in s.index){const b=get('bad_fraction');if(Number.isFinite(b))bad=Math.max(0,Math.min(1,b))}
      else if(['ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps','accel_range_g','gyro_range_dps'].every(k=>k in s.index)){
        const av=get('accel_range_g'),gv=get('gyro_range_dps');
        if(av>0&&gv>0){const words=columns.slice(1,7).map((k,i)=>Math.round(get(k)*32768/(i<3?av:gv)));if(words.every(Number.isFinite)&&words.every(v=>v===words[0]))bad=1}
      }
      binRows++;binBad+=bad;if(bad>0)badRows++;
      const vals=columns.slice(1,11).map(k=>get(k.toLowerCase())).concat(columns.slice(12,18).map(get));
      if(s.body)vals.push(get('ax_m_s2'),get('ay_m_s2'),get('yaw_deg_s'),get('az_dynamic_m_s2'));
      const fresh=[!('accel_new' in s.index)||get('accel_new')===1,!('gyro_new' in s.index)||get('gyro_new')===1,
        (!('mag_new' in s.index)||get('mag_new')===1)&&(!('mag_valid' in s.index)||get('mag_valid')===1)&&(!('mag_overflow' in s.index)||get('mag_overflow')!==1)];
      if(!vals.some(Number.isFinite))invalidRows++;
      vals.forEach((v,i)=>{const eligible=i<9?fresh[Math.floor(i/3)]:true;if(Number.isFinite(v)&&eligible){sums[i]+=v;counts[i]++;if(i<9)seenGroups[Math.floor(i/3)]=true;if(i>=10&&i<16)seenFiltered=true}});
      const marker=cells[s.index.flag_number]?.trim();
      if(marker){
        if(!/^\d+$/.test(marker)||+marker<1||+marker>999999)throw Error('Řádek '+record.line+': vlaječka musí mít jedno číslo 1–999999.');
        if(usedNumbers.has(+marker)||usedBins.has(bin))throw Error('Řádek '+record.line+': duplicitní vlaječka nebo více bodů ve stejném 10ms intervalu.');
        const label=cells[s.index.flag_label]||'';if(label.length>160)throw Error('Popis vlaječky je delší než 160 znaků.');
        flags.push({number:+marker,index:bin,label});usedNumbers.add(+marker);usedBins.add(bin);
      }
    }
    if(!s||!rows)throw Error('CSV neobsahuje žádné vzorky.');
    if(invalidRows===rows)throw Error('CSV neobsahuje žádnou konečnou měřenou hodnotu.');
    flush();s.groups=seenGroups;s.filtered=seenFiltered;progress({loaded:file.size,total:file.size,rows});
    const data=new Float32Array(length*18),body=s.body?new Float64Array(length*5):new Float64Array();
    chunks.forEach((v,i)=>data.set(v.subarray(0,Math.min(blockRows,length-i*blockRows)*18),i*blockRows*18));
    bodyChunks.forEach((v,i)=>body.set(v.subarray(0,Math.min(blockRows,length-i*blockRows)*5),i*blockRows*5));
    // Namespaced block digest: stable bounded-memory identity, deliberately not a raw-file SHA-256.
    const identity='csv-block-sha256-v1:'+hex(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(hashes.join(''))));
    return {data,body,flags,columns,schema:s,rows,first_s:Math.floor(first*100+1e-5)*.01,
      end_s:Math.max(last,(length-.5)*.01),duration_s:last-first,bad_fraction:s.quality?badRows/rows:null,identity,invalidRows};
  }
  function cell(value,delimiter){const s=String(value??'');return s.includes(delimiter)||/["\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s}
  async function* rawChunks(file,flags,first,last,signal,progress=()=>{}){
    const ordered=[...flags].sort((a,b)=>a.index-b.index),limits=[first,last].sort((a,b)=>a.index-b.index);
    let s,delimiter,previous,pointer=0,active=false,finished=false,scanned=0,emitted=0,block='';
    const markTime=f=>f.index*.01+.005;
    function accept(previous,midpoint){
      const marks=[];while(pointer<ordered.length&&markTime(ordered[pointer])<=midpoint)marks.push(ordered[pointer++]);
      if(marks.some(f=>f.number===limits[0].number))active=true;
      if(active){const values=previous.cells.filter((_,i)=>!['flag_number','flag_label'].includes(s.header[i]));
        const label=marks.map(f=>f.label).join(' | ');values.push(marks.map(f=>f.number).join('|'),/^[\s]*[=+@-]/.test(label)?"'"+label:label);
        block+=values.map(v=>cell(v,s.delimiter)).join(s.delimiter)+'\r\n';emitted++}
      if(marks.some(f=>f.number===limits[1].number))finished=true;
    }
    for await(const record of records(file,{signal})){
      if(!s){const sep=record.text.replace(/^\uFEFF/,'').match(/^sep=([;,])$/i);if(sep){delimiter=sep[1];continue}s=schema(record.text,delimiter);
        yield s.header.filter(k=>!['flag_number','flag_label'].includes(k)).map(k=>k==='crc32'?'source_crc32':k).concat(['flag_number','flag_label']).join(s.delimiter)+'\r\n';continue}
      const current=row(record,s);if(previous&&current.time<previous.time)throw Error('Neplatná časová osa CSV.');
      if(previous)accept(previous,(previous.time+current.time)/2);previous=current;scanned++;
      if(scanned%5000===0||finished){if(block){yield block;block=''}progress({scanned,emitted,time:current.time});await new Promise(r=>setTimeout(r,0));signal?.throwIfAborted()}
      if(finished)break;
    }
    if(!finished&&previous)accept(previous,Infinity);
    if(!finished||!emitted)throw Error('Ve zvoleném úseku nejsou řádky CSV.');if(block)yield block;
  }
  return {read,records,fields,schema,rawChunks};
}
const CsvData=createCsvData();
function loadCsvWorker(file,signal,progress){
  return new Promise((resolve,reject)=>{
    const code='const csv=('+createCsvData.toString()+')();onmessage=async e=>{try{const r=await csv.read(e.data,{progress:p=>postMessage({progress:p})});postMessage({result:r},[r.data.buffer,r.body.buffer])}catch(e){postMessage({error:e.message})}}';
    const url=URL.createObjectURL(new Blob([code],{type:'text/javascript'})),worker=new Worker(url);
    const stop=()=>{worker.terminate();URL.revokeObjectURL(url);signal.removeEventListener('abort',cancel)};
    const cancel=()=>{stop();reject(new DOMException('Načítání bylo zrušeno.','AbortError'))};
    signal.addEventListener('abort',cancel,{once:true});
    worker.onmessage=e=>{if(e.data.progress)progress(e.data.progress);else{stop();e.data.error?reject(Error(e.data.error)):resolve(e.data.result)}};
    worker.onerror=e=>{stop();reject(Error(e.message||'CSV se nepodařilo načíst.'))};
    if(signal.aborted)cancel();else worker.postMessage(file);
  });
}
