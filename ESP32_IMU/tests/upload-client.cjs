// Execute the production queue against a server that loses acknowledgements.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
const source=fs.readFileSync('web/files.js','utf8');
const elements=new Map(),payload=Buffer.alloc(150001,137),received=[];
let server=null,completed='',lostChunk=true,lostFinish=true;
const context={console,crypto:webcrypto,AbortController,Uint8Array,performance,Promise,Error,setTimeout:fn=>setTimeout(fn,0),
 $:key=>{if(!elements.has(key))elements.set(key,{});return elements.get(key);},
 joinPath:(p,n)=>p+'/'+n,validateName:()=>{},uploadProgress:()=>{},bytes:String,toast:()=>{},loadFiles:async()=>{},syncFileLocks:()=>{},state:null,orphanUpload:null,discardUpload:async()=>{},
 api:async(path,body)=>{
  if(path==='/api/upload/start'){server={id:body.id,path:body.path,size:body.size,offset:0,active:true,chunkSize:65536};return {...server};}
  if(path==='/api/upload/status')return server?{...server}:{active:false,completedId:completed};
  if(path.startsWith('/api/upload/finish')){assert.equal(server.offset,payload.length);completed=server.id;server=null;if(lostFinish){lostFinish=false;throw Error('response lost after successful rename');}return {done:true};}
  throw Error('Unexpected API '+path);
 },
 sendChunk:async(u,file)=>{assert.equal(u.offset,server.offset);const part=payload.subarray(u.offset,u.offset+u.chunkSize);received.push(part);server.offset+=part.length;if(lostChunk){lostChunk=false;throw Error('response lost after committed block');}return {...server};}
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('async function runUpload(){'),source.indexOf('async function enqueueFiles(')),context);
(async()=>{
 context.uploadJob={files:[{name:'big.bin',size:payload.length}],folder:'/test',index:0,total:payload.length,finishedBytes:0,session:null,running:false};
 await context.runUpload();assert.ok(context.uploadJob,'lost final response keeps a retryable job');
 assert.equal(elements.get('#retryUpload').hidden,false);
 await context.runUpload();assert.equal(context.uploadJob,null);
 assert.deepEqual(Buffer.concat(received),payload,'retry must neither skip nor duplicate bytes');
 assert.equal(elements.get('#uploadProgress').value,100);
 console.log('PASS: upload queue recovers lost chunk/final acknowledgements without duplicate data or restarting the file.');
})().catch(e=>{console.error(e);process.exitCode=1;});
