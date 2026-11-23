#pragma once
// Only the NVS-marked, app-created log is repaired. The damaged original is retained.
std::atomic<bool> recovering{false};
bool recoveryHealthy=true;
String recoveryMessage,recoveryPath;
uint64_t recoveredRows=0;
std::atomic<uint32_t> recoveryPercent{0};
// Recovery runs only in sd-writer, before logging starts. Reuse its idle CSV
// buffer: nested 4 KiB scan/copy arrays overflowed this task's 8 KiB stack.
constexpr size_t recoveryBlockSize=4096;
static_assert(sizeof(csvBuffer)>=recoveryBlockSize,"Recovery workspace is too small");

void recoveryNote(const String& message){lock();recoveryMessage=message;unlock();}
bool scanLog(const String& path,CsvIntegrity& scan,uint64_t& size){
  File file=SD_MMC.open(path,FILE_READ);if(!file||file.isDirectory())return false;
  size=file.size();auto* buffer=reinterpret_cast<uint8_t*>(csvBuffer);uint64_t read=0;
  while(file.available()&&!scan.bad){size_t n=file.read(buffer,recoveryBlockSize);if(!n){file.close();return false;}scan.feed(buffer,n);read+=n;recoveryPercent=size?read*100/size:100;vTaskDelay(1);}
  file.close();scan.finish();return true;
}
bool recoverInterruptedLog(){
  String path=prefs.getString("openLog","");if(path.isEmpty())return true;
  lock();recoveryPath=path;unlock();
  if(!safePath(path)||!path.startsWith("/logs/boot_")||!path.endsWith(".csv")){
    recoveryNote("Neplatná cesta obnovy v NVS. Původní soubory zůstaly zachované.");return false;
  }
  if(!sdOK){recoveryNote("Obnova čeká na původní SD kartu. Vlož ji a restartuj desku.");return false;}
  recoveryNote("Kontroluji nedokončený záznam: "+path);
  const String raw=path+".recovery-source",part=path+".repair-part";
  String source=SD_MMC.exists(path)?path:raw;
  if(!SD_MMC.exists(source)){
    // Power may have failed after the NVS marker, before creating the file.
    prefs.remove("openLog");recoveryNote("Nedokončený záznam na této kartě nebyl nalezen. Žádná data nebyla změněna.");return true;
  }
  CsvIntegrity scan;uint64_t size=0;
  if(!scanLog(source,scan,size)){recoveryNote("SD odmítla čtení. Obnova se zopakuje po restartu.");return false;}
  lock();recoveredRows=scan.rows;unlock();
  bool repaired=scan.bad||source==raw;
  if(repaired){
    if(source==path){
      if(SD_MMC.exists(raw)||!SD_MMC.rename(path,raw)){recoveryNote("Nelze bezpečně zachovat původní soubor. Obnova nic nepřepsala.");return false;}
    }
    refreshSpace();uint64_t required=scan.headerOK?scan.goodBytes:strlen(CSV_HEADER);
    if(sdTotal-sdUsed<required+65536){recoveryNote("Pro obnovu chybí volné místo. Originál je zachován jako .recovery-source.");return false;}
    File input=SD_MMC.open(raw,FILE_READ),output=SD_MMC.open(part,FILE_WRITE);
    if(!input||!output){recoveryNote("Nelze otevřít pracovní soubor obnovy.");return false;}
    bool ok=true;auto* block=reinterpret_cast<uint8_t*>(csvBuffer);uint64_t remaining=scan.headerOK?scan.goodBytes:0;
    if(!scan.headerOK)ok=output.print(CSV_HEADER)==strlen(CSV_HEADER);
    while(remaining&&ok){size_t n=input.read(block,std::min<uint64_t>(recoveryBlockSize,remaining));ok=n&&output.write(block,n)==n;remaining-=n;vTaskDelay(1);}
    output.flush();output.close();input.close();
    CsvIntegrity check;uint64_t copySize=0;
    if(!ok||!scanLog(part,check,copySize)||check.bad||copySize!=required||check.rows!=scan.rows){recoveryNote("Kontrola opravené kopie selhala. Originál je zachovaný; obnova se zopakuje.");return false;}
    if(SD_MMC.exists(path)||!SD_MMC.rename(part,path)){recoveryNote("Nelze dokončit opravenou kopii. Originál zůstává zachovaný.");return false;}
  }
  JsonDocument report;report["file"]=path;report["reason"]="unclean_shutdown";report["repaired"]=repaired;
  report["valid_rows"]=scan.rows;report["original_bytes"]=size;report["valid_bytes"]=scan.goodBytes;report["removed_tail_bytes"]=size-scan.goodBytes;
  if(repaired)report["preserved_original"]=raw;
  File summary=SD_MMC.open(path+".recovery.json",FILE_WRITE);
  if(!summary||!serializeJson(report,summary)){recoveryNote("Záznam je ověřen, ale protokol obnovy nelze uložit.");return false;}
  summary.flush();summary.close();prefs.remove("openLog");refreshSpace();
  recoveryPercent=100;recoveryNote(String(repaired?"Obnoven":"Zkontrolován")+" záznam po výpadku: "+path+" · "+String((unsigned long)scan.rows)+" platných řádků."+(repaired?" Původní data jsou zachována v .recovery-source.":""));return true;
}
