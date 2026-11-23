// Run the actual click handler with delayed network acknowledgements.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/files.js','utf8'),nodes=new Map();
const element=k=>{if(!nodes.has(k))nodes.set(k,{dataset:{},setAttribute(n,v){this[n]=v;}});return nodes.get(k);};
let requests=0,clicks=0,reply,reject;
const ctx={downloadStarting:false,state:{storageOwner:'web'},$:element,$$:()=>[element('file button')],bytes:String,baseName:s=>s.split('/').at(-1),fileLocked:()=>false,safe:f=>f,toast:()=>{},fileUrl:p=>'/api/download?path='+encodeURIComponent(p),encodeURIComponent,
 api:()=>{requests++;return new Promise((ok,no)=>{reply=ok;reject=no;});},document:{body:{append(){}},createElement(){return {click(){clicks++;},remove(){}};}}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function syncDownloadUi('),source.indexOf('async function openFile(')),ctx);
(async()=>{
 const file={path:'/logs/test.csv',name:'test.csv'},job={id:'ticket',path:file.path,state:'pending',active:true,size:900000,sent:0};
 const first=ctx.downloadFile(file);await ctx.downloadFile(file);await ctx.downloadFile(file);
 assert.equal(requests,1,'triple click must reserve only one transfer before the first response');
 reply(job);await first;assert.equal(clicks,1);assert.equal(element('file button').disabled,true);
 await ctx.downloadFile(file);assert.equal(requests,1,'active transfer must stay locked');
 ctx.state.download={...job,active:false,state:'complete',sent:job.size};ctx.syncDownloadUi(ctx.state.download);
 assert.equal(element('file button').disabled,false);assert.equal(element('#downloadProgress').value,100);
 const failed=ctx.downloadFile(file);reject(Error('offline'));await assert.rejects(failed,/offline/);assert.equal(ctx.downloadStarting,false);
 const again=ctx.downloadFile(file);reply({...job,id:'new'});await again;assert.equal(clicks,2,'a new download is allowed after completion');
 element('#previewDownload').dataset.remote='1';ctx.syncDownloadUi(ctx.state.download);assert.equal(element('#previewDownload')['aria-disabled'],'true');
 console.log('PASS: rapid triple click starts one download; active job locks all entry points; completion and errors unlock retry.');
})().catch(e=>{console.error(e);process.exitCode=1;});
