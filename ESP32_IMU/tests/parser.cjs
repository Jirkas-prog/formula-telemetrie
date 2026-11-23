// Run the production CSV parser under Node with tiny DOM stubs.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8');
const part=source.slice(source.indexOf('class CsvData{'),source.indexOf('async function openRemoteCsv('));
const elements=new Map();
const context={TextDecoder,Float64Array,Number,Math,Error,Promise,setTimeout,fmt:String,
 $:key=>{if(!elements.has(key))elements.set(key,{});return elements.get(key);},toast:()=>{},changeTab:()=>{},setView:()=>{},bounds:()=>[0,10],data:null};
vm.createContext(context);vm.runInContext(part+'\nthis.parse=parseCsv;this.Store=CsvData;',context);
const header='time_us,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,mx_uT,my_uT,mz_uT,clip_mask,mag_new,mag_valid,accel_new,gyro_new';
function stream(text,chunk=19){const b=new TextEncoder().encode(text);let pos=0;return new ReadableStream({pull(c){if(pos>=b.length)return c.close();c.enqueue(b.slice(pos,pos+chunk));pos+=chunk;}});}
(async()=>{
 await context.parse(stream('\uFEFF'+header+'\r\n0,1,2,3,4,5,6,nan,nan,nan,0,0,0,1,1\r\n2000,1,2,3,4,5,6,10,11,12,1,1,1,0,1\n4000,1,2,3,4,5,6,10,11,12,0,0,1,1,0\nBROKEN'), 'test.csv');
 assert.equal(context.data.length,3);assert.equal(context.data.get(1)[0],.002);
 assert.equal(context.data.get(1)[10],1);assert.equal(context.data.get(1)[13],0);assert.equal(context.data.get(1)[14],1);
 assert.ok(Number.isNaN(context.data.get(0)[7]));assert.match(elements.get('#fileMessage').textContent,/1/);
 await assert.rejects(()=>context.parse(stream('wrong,header\n1,2'),'bad.csv'),/hlavičku/);
 await assert.rejects(()=>context.parse(stream(header+'\n'),'empty.csv'),/platné vzorky/);
 const store=new context.Store();for(let i=0;i<8200;i++)store.add(Array(15).fill(i));assert.equal(store.get(8192)[0],8192);assert.equal(store.chunks.length,2);
 store.length=2000000;assert.throws(()=>store.add(Array(15).fill(0)),/2 milionů/);
 const crc=vm.runInContext('csvCrc32',context),checked='0,1,2,3,4,5,6,10,11,12,0,1,1,1,1';
 await context.parse(stream(header+',crc32\n'+checked+','+crc(checked).toString(16).padStart(8,'0')+'\n'+checked.replace(',1,2,',',9,2,')+','+crc(checked).toString(16).padStart(8,'0')+'\n'),'crc.csv');
 assert.equal(context.data.length,1);assert.equal(context.data.info.invalid,1);assert.equal(context.data.info.crc,true);
 console.log('PASS: CRC32 excludes a corrupted row from charts and PDF statistics.');
 console.log('PASS: CSV chunk boundaries, BOM/CRLF, stale mag, fresh flags, clipping, corrupt rows, invalid header, empty file, sample limit.');
})().catch(e=>{console.error(e);process.exitCode=1;});
