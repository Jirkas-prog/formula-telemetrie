import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const source=fs.readFileSync(path.join(root,'app/csv_import.js'),'utf8');
const csv=vm.runInNewContext(source+';CsvData',{TextDecoder,TextEncoder,crypto:webcrypto,setTimeout});
const read=s=>csv.read(new Blob([s]));
const collect=async gen=>{let s='';for await(const x of gen)s+=x;return s};
let result=await read('time_us,ax_g,ay_g,accel_new\n1000,1,,1\n3000,999,2,0\n9000,3,4,1\n21000,5,6,1');
assert.equal(result.rows,4);assert.equal(result.data.length,54);
assert.equal(result.data[1],2);assert.equal(result.data[2],4);
assert.ok(Number.isNaN(result.data[18+1]));assert.ok(Number.isNaN(result.data[4]));
assert.equal(result.data[36+1],5);assert.equal(result.body.length,0);
assert.equal(result.schema.filtered,false);
const semicolon='\uFEFFsep=;\r\ntime_s;ax_m_s2;ay_m_s2;flag_number;flag_label\r\n1,005;-9,8;2;1;"brzda; nájezd\nlevá"\r\n1,015;-8,1;3;;\r\n1,025;-7;4;2;konec';
result=await read(semicolon);assert.equal(result.first_s,1);assert.equal(result.body[100*5+1],-9.8);
assert.equal(result.flags[0].label,'brzda; nájezd\nlevá');assert.equal(result.schema.groups.some(Boolean),false);
const exported=await collect(csv.rawChunks(new Blob([semicolon]),result.flags,...result.flags));
const roundtrip=await read(exported);assert.equal(roundtrip.rows,3);assert.equal(roundtrip.body[100*5+1],-9.8);assert.equal(roundtrip.flags[0].label,result.flags[0].label);
result=await read('t_s,ax_g,fax_g,bad_fraction\n0.005,2,1,0\n0.015,nan,,1');
assert.equal(result.schema.filtered,true);assert.equal(result.data[12],1);assert.equal(result.data[29],1);
result=await read('t_s,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,accel_range_g,gyro_range_dps\n0.005,0.5,0.5,0.5,62.5,62.5,62.5,16,2000');
assert.equal(result.data[11],1);assert.equal(result.bad_fraction,1);
result=await read('t_s,mx_uT,mag_new,mag_valid,mag_overflow\n0.005,1,1,1,0\n0.006,999,1,1,1\n0.007,999,0,1,0');
assert.equal(result.data[7],1);
for(const [input,error] of [
 ['time_us,seq\n1,1',/měřené/],['time_us,t_s,ax_g\n0,0,1',/jeden časový/],
 ['t_s,ax_g\n1,1\n0,2',/vrací/],['t_s,ax_g\n0,wrong',/Neplatné číslo/],
 ['t_s,ax_g\n0,NaN',/konečnou/],['t_s,ax_g\n20001,1',/příliš/],
 ['t_s,ax_g,flag_number\n0.005,1,1\n0.015,2,1',/duplicitní/],
 ['t_s,ax_g,flag_label\n0,1,"broken',/neuzavřené/],
 ['t_s,ax_g\n0,1,2',/počet/],['t_s,ax_g,ax_g\n0,1,2',/duplicitní/],
]) await assert.rejects(()=>read(input),error);
const abort=new AbortController();abort.abort();await assert.rejects(()=>csv.read(new Blob(['t_s,ax_g\n0,1']),{signal:abort.signal}),{name:'AbortError'});
// Cross the 4 MiB decoder boundary inside a quoted cell containing a multibyte character.
const base='t_s,ax_g,note\n',line='0.005,1,plain\n';
let crossing=base+line.repeat(Math.floor((4*1024*1024-base.length-20)/line.length));
crossing+='0.005,1,"'+ 'x'.repeat(100)+'český\nřádek"\n0.015,2,end';
result=await read(crossing);assert.equal(result.data[19],2);
const raw=await csv.read(await fs.openAsBlob('./input/logs/boot_000144_run_001.csv'));
assert.ok(raw.rows>100);assert.ok(raw.schema.groups[0]);
const excerpt=await csv.read(await fs.openAsBlob(path.join(root,'output/QA_vlajecky_vyrez.csv')));
assert.equal(excerpt.rows,25051);assert.equal(excerpt.flags.length,3);assert.equal(excerpt.flags[0].number,11);
assert.ok(Math.abs(excerpt.first_s-781.3)<1e-9);assert.equal(excerpt.flags[2].index,83140);
const body=await csv.read(await fs.openAsBlob(path.join(root,'report_drivetrain/data/jizda_100Hz_2Hz.csv')));
assert.equal(body.rows,33000);assert.equal(body.first_s,677);assert.ok(body.schema.body);
let peak=0;for(let i=67700;i<body.body.length/5;i++)peak=Math.max(peak,-body.body[i*5+1]/9.80665);
assert.ok(Math.abs(peak-1.066903)<0.00001,peak);
const repeat=await csv.read(await fs.openAsBlob(path.join(root,'report_drivetrain/data/jizda_100Hz_2Hz.csv')));
assert.equal(body.identity,repeat.identity);assert.notEqual(raw.identity,body.identity);
// An exported overview must carry vehicle channels and flags back into a new CSV import.
const html=fs.readFileSync(path.join(root,'app/viewer.html'),'utf8');
const flagSource=[...html.matchAll(/<script(?:[^>]*)>([\s\S]*?)<\/script>/g)][0][1];
const flagData=vm.runInNewContext(flagSource+';FlagData',{TextDecoderStream,setTimeout});
const bodyFlags=[{number:1,index:94900,label:'brzdění'},{number:2,index:95200,label:'konec'}];
const bodyOverview=await collect(flagData.overviewChunks(body.data,18,[...body.columns,'ax_m_s2','ay_m_s2','yaw_deg_s','az_dynamic_m_s2'],bodyFlags,94900,95200,undefined,()=>{},
 i=>Array.from(body.body.slice(i*5+1,i*5+5))));
const bodyRestored=await read(bodyOverview);assert.equal(bodyRestored.rows,301);assert.equal(bodyRestored.flags.length,2);
assert.ok(Math.abs(bodyRestored.body[95003*5+1]-body.body[95003*5+1])<1e-5);
if(process.argv.includes('--large')){
 const started=Date.now();let lastProgress=0;
 const large=await csv.read(await fs.openAsBlob('./input/logs/boot_000181_run_001.csv'),{progress:p=>{if(Date.now()-lastProgress>10000){console.log('Large CSV',p.loaded,p.total,p.rows);lastProgress=Date.now()}}});
 console.log('Full original CSV:',large.rows,'rows,',(Date.now()-started)/1000,'s');
 assert.ok(large.rows>500000);assert.ok(large.data.length>100000*18);
}
console.log('PASS CSV: streaming parsing, units, freshness/quality, gaps, flags roundtrip, cancellation, malformed inputs, real logs and drivetrain peak.');
