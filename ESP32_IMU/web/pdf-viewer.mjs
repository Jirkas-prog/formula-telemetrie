import {getDocument,GlobalWorkerOptions} from './pdfjs/pdf.mjs';
GlobalWorkerOptions.workerSrc='/pdfjs/pdf.worker.mjs';

export async function mountPdf(host,url,signal){
 let pageNumber=1,zoom=1,renderTask=null,pdfDoc=null,generation=0;
 host.replaceChildren();const tools=document.createElement('div');tools.className='pdf-tools';
 const button=(label,fn)=>{const b=document.createElement('button');b.textContent=label;b.onclick=()=>Promise.resolve(fn()).catch(showError);tools.append(b);return b;};
 const previous=button('←',()=>showPage(pageNumber-1));previous.setAttribute('aria-label','Předchozí stránka');
 const input=document.createElement('input');input.type='number';input.min=1;input.value=1;input.setAttribute('aria-label','Číslo stránky');tools.append(input);
 const count=document.createElement('span');count.textContent='/ …';tools.append(count);
 const next=button('→',()=>showPage(pageNumber+1));next.setAttribute('aria-label','Další stránka');
 button('−',()=>{zoom=Math.max(.5,zoom-.25);return showPage(pageNumber);}).setAttribute('aria-label','Zmenšit PDF');
 button('＋',()=>{zoom=Math.min(3,zoom+.25);return showPage(pageNumber);}).setAttribute('aria-label','Zvětšit PDF');
 const message=document.createElement('p');message.className='pdf-message';message.textContent='Načítám PDF…';
 const scroll=document.createElement('div');scroll.className='pdf-page';const canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Stránka PDF');scroll.append(canvas);host.append(tools,message,scroll);
 function showError(error){if(!signal.aborted&&error?.name!=='RenderingCancelledException'){message.hidden=false;message.textContent='PDF nelze zobrazit: '+error.message+'. Soubor můžeš stáhnout.';}}
 const task=getDocument({url,cMapUrl:'/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/pdfjs/standard_fonts/',wasmUrl:'/pdfjs/wasm/',rangeChunkSize:65536,disableStream:true,disableAutoFetch:true,isEvalSupported:false});
 let observedWidth=scroll.clientWidth;const resize=new ResizeObserver(()=>{if(Math.abs(scroll.clientWidth-observedWidth)<1)return;observedWidth=scroll.clientWidth;showPage(pageNumber).catch(showError);});resize.observe(scroll);
 signal.addEventListener('abort',()=>{++generation;resize.disconnect();renderTask?.cancel();task.destroy().catch(()=>{});},{once:true});
 task.onPassword=(update)=>{message.hidden=false;message.textContent='PDF je chráněné heslem.';const form=document.createElement('form'),password=document.createElement('input'),submit=document.createElement('button');password.type='password';password.autocomplete='off';password.placeholder='Heslo k PDF';password.setAttribute('aria-label','Heslo k PDF');submit.textContent='Odemknout';form.append(password,submit);message.append(form);form.onsubmit=e=>{e.preventDefault();update(password.value);password.value='';form.remove();message.textContent='Odemykám PDF…';};};
 async function showPage(number){
  if(!pdfDoc||signal.aborted)return;const ticket=++generation;pageNumber=Math.max(1,Math.min(pdfDoc.numPages,Number(number)||1));input.value=pageNumber;previous.disabled=pageNumber<=1;next.disabled=pageNumber>=pdfDoc.numPages;
  renderTask?.cancel();try{if(renderTask)await renderTask.promise;}catch{}if(ticket!==generation)return;
  message.hidden=false;message.textContent='Načítám stránku '+pageNumber+'…';const page=await pdfDoc.getPage(pageNumber);if(ticket!==generation||signal.aborted)return;
  const natural=page.getViewport({scale:1}),width=Math.max(180,scroll.clientWidth)*zoom,scale=width/natural.width;
  const viewport=page.getViewport({scale}),ratio=Math.min(devicePixelRatio||1,2,Math.sqrt(4000000/(viewport.width*viewport.height)));
  canvas.width=Math.floor(viewport.width*ratio);canvas.height=Math.floor(viewport.height*ratio);canvas.style.width=viewport.width+'px';canvas.style.height=viewport.height+'px';
  renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:[ratio,0,0,ratio,0,0]});await renderTask.promise;if(ticket===generation)message.hidden=true;
 }
 input.onchange=()=>showPage(input.value).catch(showError);
 try{pdfDoc=await task.promise;if(signal.aborted)return;count.textContent='/ '+pdfDoc.numPages;input.max=pdfDoc.numPages;await showPage(1);}catch(error){showError(error);}
}
