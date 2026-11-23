let csvImportController=null;
async function openFile(f){
  if(!f||csvImportController||exportController)return;
  csvImportController=new AbortController();const signal=csvImportController.signal;
  ++loadToken;pause();clearTimeout(analysisTimer);
  $('file').disabled=$('file2').disabled=true;$('cancelImport').hidden=false;
  $('work').classList.add('loading');$('loadProgress').hidden=false;$('loadProgress').value=0;
  try{
    let nextArchive,nextManifest,nextTrajectory;
    if(/\.csv$/i.test(f.name)){
      status('Čtu CSV po blocích…');
      const imported=await loadCsvWorker(f,signal,p=>{
        $('loadProgress').value=p.total?p.loaded/p.total:0;
        status('CSV: '+fmt(p.loaded/p.total*100,0)+' % · '+p.rows.toLocaleString('cs-CZ')+' řádků · '+f.name);
      });
      const id='csv_'+f.name.replace(/\.csv$/i,''),source='csv-source';
      nextArchive={csvFile:f,csvData:imported.data,entries:new Map([[source,{size:f.size}]]),
        stream:async()=>f.stream(),member:async name=>name===source?f:new Blob([imported.data])};
      const item={id,file:f.name,sha256:imported.identity,derived_rows:imported.data.length/C,
        derived_member:'csv-derived',raw_member:source,start_s:imported.first_s,end_s:imported.end_s,
        duration_s:imported.duration_s,rows:imported.rows,bad_crc:null};
      const type=imported.schema.body?'CSV · vozidlové složky':'CSV · osy senzoru';
      const evidence='Samostatné CSV. Přehled po 10 ms; prázdné buňky zůstávají mezerami. '+
        (imported.schema.body?'Podélné a boční složky jsou převzaté z CSV. ':'Montáž vůči autu není známá. ')+
        (imported.schema.filtered?'Filtrované sloupce jsou převzaté ze souboru. ':'Další filtrace se neprovádí. ')+
        'CRC ani celková fyzikální správnost nebyly při importu ověřeny.';
      nextManifest={version:1,columns:imported.columns,runs:[item],csv:imported,
        results:{files:[{id,category:type,use_for_trajectory:false,digital_fault_fraction:imported.bad_fraction,evidence}],laps:[]}};
      nextTrajectory=new Float32Array();
    }else{
      status('Načítám adresář datového balíčku…');
      nextArchive=await new ZipReader(f).init();
      nextManifest=JSON.parse(await (await nextArchive.member('manifest.json')).text());
      if(nextManifest.version!==1||nextManifest.columns?.length!==C||!nextManifest.runs?.length||!nextManifest.results?.files)throw Error('Nepodporovaná nebo neúplná struktura FIMU.');
      nextTrajectory=new Float32Array(await (await nextArchive.member('derived/trajectory181.f32')).arrayBuffer());
    }
    signal.throwIfAborted();archive=nextArchive;manifest=nextManifest;trajectory=nextTrajectory;
    $('showbad').checked=false;
    $('filtered').disabled=!!manifest.csv&&!manifest.csv.schema.filtered;
    $('filtered').checked=!manifest.csv||manifest.csv.schema.filtered;
    $('filterLabel').textContent=manifest.csv?(manifest.csv.schema.filtered?'Filtrované sloupce CSV':'CSV bez dodatečné filtrace'):'Filtr 2 Hz';
    $('flagFormat').querySelector('option[value="overview"]').textContent=manifest.csv?'Přehled · 100 Hz':'Přehled · 100 Hz + filtr';
    $('speed').parentElement.hidden=!!manifest.csv;
    init();
    if(manifest.csv?.flags.length){const r=manifest.runs[0];if(!flagSets.get(r.sha256)?.length)flagSets.set(r.sha256,FlagData.validate(manifest.csv.flags,r.derived_rows))}
    await selectRun(manifest.csv?manifest.runs[0].id:manifest.runs.some(r=>r.id==='boot_000181_run_001')?'boot_000181_run_001':manifest.runs[0].id);
  }catch(e){status(e.name==='AbortError'?'Načítání bylo zrušeno. Předchozí data zůstávají otevřená.':e.message,e.name!=='AbortError')}
  finally{
    csvImportController=null;$('file').disabled=$('file2').disabled=false;
    $('file').value=$('file2').value='';$('cancelImport').hidden=true;$('loadProgress').hidden=true;
    $('work').classList.remove('loading');$('preset').disabled=!!manifest?.csv;
  }
}
