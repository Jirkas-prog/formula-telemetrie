#pragma once
#include "http_range.h"
#include <sys/socket.h>
#include <errno.h>

bool storageAllowed();
struct Download {
  WiFiClient client; File file;
  String ticket;
  uint64_t remaining=0; uint32_t progress=0;
  uint8_t buffer[4096]; size_t used=0,sent=0;
};
// Bounded RAM; three streams let PDF viewers request separate byte ranges.
Download downloads[3];
struct DownloadJob { String id,path,state;uint32_t size=0,sent=0,activity=0; } downloadJob;
std::atomic<bool> downloadBusy{false};
bool downloadActive(){return downloadJob.state=="pending"||downloadJob.state=="active";}
bool hasDownloads(){return downloadBusy.load();}
void refreshDownloadBusy(){bool busy=downloadActive();for(auto& d:downloads)busy|=bool(d.file);downloadBusy=busy;}
void downloadJson(JsonVariant d){d["id"]=downloadJob.id;d["path"]=downloadJob.path;d["state"]=downloadJob.state;d["size"]=downloadJob.size;d["sent"]=downloadJob.sent;d["active"]=downloadActive();}
void downloadState(){JsonDocument d;downloadJson(d.to<JsonVariant>());jsonReply(d);}
void newDownloadJob(const String& path,uint32_t size){char id[25];snprintf(id,sizeof(id),"%08lx%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());downloadJob.id=id;downloadJob.path=path;downloadJob.state="pending";downloadJob.size=size;downloadJob.sent=0;downloadJob.activity=millis();refreshDownloadBusy();}
void closeDownload(Download& d,const char* outcome="error"){
  if(d.ticket.length()&&d.ticket==downloadJob.id)downloadJob.state=outcome;
  d.file.close();d.client.stop();d.client=WiFiClient();d.ticket="";d.remaining=0;d.used=d.sent=0;refreshDownloadBusy();
}
void startDownload(){
  if(!mutableRequest()||!storageAllowed())return;
  if(downloadActive()){problem(409,"Stahování už probíhá. Nejdříve ho dokonči nebo zruš.");return;}
  bool slot=false;for(auto& item:downloads)slot|=!item.file;if(!slot){problem(503,"Nejdříve zavři některý náhled souboru.");return;}
  JsonDocument d;if(deserializeJson(d,server.arg("plain"))){problem(400,"Neplatné JSON.");return;}
  String path=d["path"]|"";if(!safePath(path)){problem(400,"Neplatná cesta.");return;}
  File f=SD_MMC.open(path);if(!f||f.isDirectory()){problem(404,"Soubor neexistuje.");return;}
  newDownloadJob(path,f.size());downloadState();
}
void cancelDownload(){
  if(!mutableRequest())return;
  if(!downloadJob.id.length()||server.arg("id")!=downloadJob.id){problem(409,"Tento přenos už není aktuální.");return;}
  if(downloadActive()){for(auto& d:downloads)if(d.ticket==downloadJob.id&&d.file)closeDownload(d,"cancelled");downloadJob.state="cancelled";refreshDownloadBusy();}
  downloadState();
}
String fileMime(String name){
  name.toLowerCase();
  if(name.endsWith(".pdf"))return "application/pdf";
  if(name.endsWith(".jpg")||name.endsWith(".jpeg"))return "image/jpeg";
  if(name.endsWith(".png"))return "image/png";
  if(name.endsWith(".gif"))return "image/gif";
  if(name.endsWith(".webp"))return "image/webp";
  if(name.endsWith(".bmp"))return "image/bmp";
  if(name.endsWith(".avif"))return "image/avif";
  if(name.endsWith(".csv"))return "text/csv; charset=utf-8";
  return "application/octet-stream";
}
String quotedFilename(const String& name){
  String out;const char* hex="0123456789ABCDEF";
  for(unsigned i=0;i<name.length();i++){uint8_t c=name[i];if(isalnum(c)||c=='-'||c=='_'||c=='.')out+=char(c);else{out+='%';out+=hex[c>>4];out+=hex[c&15];}}
  return out;
}
void downloadRoute(){
  if(!storageAllowed())return;
  String path=server.arg("path");if(!safePath(path)){problem(400,"Neplatná cesta.");return;}
  File f=SD_MMC.open(path);if(!f||f.isDirectory()){problem(404,"Soubor neexistuje.");return;}
  String mime=fileMime(path),name=path.substring(path.lastIndexOf('/')+1);
  bool preview=server.uri()=="/api/view";
  const bool body=server.method()!=HTTP_HEAD;
  if(!preview&&body){
    String ticket=server.arg("id");
    if(ticket.length()&&(ticket!=downloadJob.id||!path.equalsIgnoreCase(downloadJob.path)||downloadJob.state=="cancelled")){problem(409,"Odkaz na stahování už není platný. Spusť přenos znovu z webu.");return;}
    if(downloadActive()&&!(downloadJob.state=="pending"&&ticket.length()&&ticket==downloadJob.id)){
      problem(409,"Soubor už se stahuje. Další přenos lze spustit po dokončení nebo zrušení.");return;
    }
  }
  if(preview&&!mime.startsWith("image/")&&mime!="application/pdf"){problem(415,"Tento typ souboru nemá náhled. Použij stažení.");return;}
  uint64_t size=f.size(),first,last;
  String range=server.header("Range");
  // No If-Range validator: safely send the full representation instead of mixing versions.
  if(server.hasHeader("If-Range")&&server.header("If-Range").length())range="";
  server.sendHeader("Accept-Ranges","bytes");server.sendHeader("Cache-Control","no-store");
  server.sendHeader("X-Content-Type-Options","nosniff");
  if(!httpRange(range.c_str(),size,first,last)){
    server.sendHeader("Content-Range","bytes */"+String((unsigned long)size));problem(416,"Rozsah je mimo soubor.");return;
  }
  Download* slot=nullptr;for(auto& d:downloads)if(!d.file){slot=&d;break;}
  if(!slot){server.sendHeader("Retry-After","1");problem(503,"Probíhají tři stahování. Zkus to po jejich dokončení.");return;}
  uint64_t length=size?last-first+1:0;
  if(first&&!f.seek(first)){problem(500,"Nelze nastavit pozici v souboru.");return;}
  if(!preview&&body){
    if(server.arg("id").isEmpty())newDownloadJob(path,size);
    downloadJob.state=length?"active":"complete";downloadJob.size=size;downloadJob.sent=first;downloadJob.activity=millis();refreshDownloadBusy();
  }
  server.sendHeader("Content-Disposition",String(preview?"inline":"attachment")+"; filename*=UTF-8''"+quotedFilename(name));
  if(range.length())server.sendHeader("Content-Range","bytes "+String((unsigned long)first)+"-"+String((unsigned long)last)+"/"+String((unsigned long)size));
  server.setContentLength(length);server.send(range.length()?206:200,mime,"");
  if(!body||!length)return;
  // WiFiClient copies share the socket. WebServer releases its own copy after this handler.
  slot->client=server.client();slot->file=f;slot->ticket=preview?"":downloadJob.id;slot->remaining=length;slot->progress=millis();slot->used=slot->sent=0;refreshDownloadBusy();
}
void pumpDownloads(){
  for(auto& d:downloads){
    if(!d.file)continue;
    if(!d.client.connected()||millis()-d.progress>30000){closeDownload(d);continue;}
    if(d.used==d.sent){
      d.used=d.file.read(d.buffer,std::min<uint64_t>(sizeof(d.buffer),d.remaining));d.sent=0;
      if(!d.used){closeDownload(d);continue;}
    }
    // Nonblocking send: stalled receivers cannot hold the web or USB task hostage.
    int n=send(d.client.fd(),d.buffer+d.sent,d.used-d.sent,MSG_DONTWAIT);
    if(n>0){d.sent+=n;d.remaining-=n;d.progress=millis();if(d.ticket.length()&&d.ticket==downloadJob.id){downloadJob.sent+=n;downloadJob.activity=millis();}if(!d.remaining)closeDownload(d,"complete");}
    else if(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)closeDownload(d);
  }
}

constexpr size_t UPLOAD_CHUNK=65536;
String chunkId,chunkPath,chunkTemp,chunkError,completedUpload;
uint32_t chunkSize=0,chunkOffset=0,chunkActivity=0,chunkRequestOffset=0;
uint8_t* chunkBuffer=nullptr;
size_t chunkUsed=0;
void uploadState(){JsonDocument d;d["active"]=chunkId.length()>0;d["id"]=chunkId;d["completedId"]=completedUpload;d["path"]=chunkPath;d["size"]=chunkSize;d["offset"]=chunkOffset;d["chunkSize"]=UPLOAD_CHUNK;jsonReply(d);}
bool uploadToken(){if(!chunkId.length()||server.arg("id")!=chunkId){problem(409,"Přenos už není aktivní. Vyber soubor znovu.");return false;}chunkActivity=millis();return true;}
void clearUpload(bool removePartial){
  if(removePartial&&chunkTemp.length())SD_MMC.remove(chunkTemp);
  free(chunkBuffer);chunkBuffer=nullptr;chunkId="";chunkPath="";chunkTemp="";chunkSize=chunkOffset=0;transfer=false;refreshSpace();
}
void startUpload(){
  if(!mutableRequest())return;
  JsonDocument d;if(deserializeJson(d,server.arg("plain"))){problem(400,"Neplatný požadavek.");return;}
  String id=d["id"]|"";bool validId=id.length()==32;for(unsigned i=0;i<id.length();i++)if(!isxdigit(id[i]))validId=false;
  if(!validId){problem(400,"Neplatné ID přenosu.");return;}
  if(chunkId==id){chunkActivity=millis();uploadState();return;}
  if(!storageAllowed())return;
  if(hasDownloads()){problem(409,"Nejdříve dokonči stahování nebo zavři náhled.");return;}
  String path=d["path"]|"";
  if(!d["size"].is<uint32_t>()||!safePath(path)||path=="/"||path.length()>165){problem(400,"Neplatná cesta nebo velikost. FAT32 podporuje soubory do 4 GiB − 1 B.");return;}
  if(SD_MMC.exists(path)||SD_MMC.exists(path+".upload-part")){problem(409,"Název už existuje. Nic se nepřepisuje; zvol jiný název nebo odstraň nedokončený .upload-part.");return;}
  String parent=path.substring(0,path.lastIndexOf('/'));if(!parent.length())parent="/";
  File dir=SD_MMC.open(parent);bool valid=dir&&dir.isDirectory();dir.close();
  if(!valid){problem(404,"Cílová složka neexistuje.");return;}
  refreshSpace();uint32_t total=d["size"];
  if(uint64_t(total)+65536>sdTotal-sdUsed){problem(507,"Na SD není dost místa.");return;}
  chunkBuffer=(uint8_t*)heap_caps_malloc(UPLOAD_CHUNK,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  if(!chunkBuffer){problem(503,"Nedostatek paměti pro přenos.");return;}
  chunkPath=path;chunkTemp=path+".upload-part";
  File f=SD_MMC.open(chunkTemp,FILE_WRITE);
  if(!f){free(chunkBuffer);chunkBuffer=nullptr;chunkPath=chunkTemp="";problem(500,"Soubor nelze vytvořit.");return;}f.close();
  chunkId=id;chunkSize=total;chunkOffset=0;chunkActivity=millis();transfer=true;uploadState();
}
void uploadChunk(){
  auto& u=server.upload();
  if(u.status==UPLOAD_FILE_START){
    chunkUsed=0;chunkError="";chunkRequestOffset=0;
    String origin=server.header("Origin");
    if(server.header("X-IMU-Client")!="1"||(origin.length()&&origin!="http://"+server.header("Host")))chunkError="Nepovolený původ požadavku.";
    else if(!chunkId.length()||server.arg("id")!=chunkId)chunkError="Přenos už není aktivní.";
    else {
      String offset=server.arg("offset");char* end;unsigned long long n=strtoull(offset.c_str(),&end,10);
      if(!offset.length()||*end||n>UINT32_MAX||n!=chunkOffset)chunkError="Pozice se změnila. Načti stav přenosu a pokračuj od potvrzeného bloku.";
      else {chunkRequestOffset=n;chunkActivity=millis();}
    }
  }else if(u.status==UPLOAD_FILE_WRITE&&chunkError.isEmpty()){
    if(u.currentSize>UPLOAD_CHUNK-chunkUsed)chunkError="Blok přesahuje 64 KiB.";
    else {memcpy(chunkBuffer+chunkUsed,u.buf,u.currentSize);chunkUsed+=u.currentSize;chunkActivity=millis();}
  }else if(u.status==UPLOAD_FILE_END&&chunkError.isEmpty()){
    if(!chunkUsed||uint64_t(chunkRequestOffset)+chunkUsed>chunkSize)chunkError="Blok přesahuje velikost souboru.";
    else {
      File f=SD_MMC.open(chunkTemp,"r+");
      if(!f||!f.seek(chunkOffset)||f.write(chunkBuffer,chunkUsed)!=chunkUsed)chunkError="SD odmítla zápis. Blok nebyl potvrzen; lze jej poslat znovu.";
      else {f.flush();chunkOffset+=chunkUsed;chunkActivity=millis();}
      f.close();
    }
  }else if(u.status==UPLOAD_FILE_ABORTED)chunkError="Blok byl přerušen. Potvrzená data zůstala zachovaná.";
}
void finishUpload(){
  if(!mutableRequest())return;
  if(server.arg("id")==completedUpload&&completedUpload.length()){server.send(200,"application/json","{\"done\":true}");return;}
  if(!uploadToken())return;
  if(chunkOffset!=chunkSize){problem(409,"Ještě nejsou přijaté všechny bloky.");return;}
  if(SD_MMC.exists(chunkPath)||!SD_MMC.rename(chunkTemp,chunkPath)){problem(409,"Dokončení souboru selhalo; cílový název musí být volný.");return;}
  imuUsbChanged(chunkPath);
  completedUpload=chunkId;clearUpload(false);server.send(200,"application/json","{\"done\":true}");
}
void storageTick(){
  pumpDownloads();
  // A browser save dialog may delay the GET; an abandoned reservation must expire.
  if(downloadJob.state=="pending"&&millis()-downloadJob.activity>120000){downloadJob.state="error";refreshDownloadBusy();}
  // Ten minutes without an upload request releases the card; partial data stays visible for cleanup.
  if(chunkId.length()&&millis()-chunkActivity>600000)clearUpload(false);
}
void storageRoutes(){
  server.on("/api/download/start",HTTP_POST,startDownload);
  server.on("/api/download/status",HTTP_GET,downloadState);
  server.on("/api/download/cancel",HTTP_POST,cancelDownload);
  server.on("/api/download",HTTP_GET,downloadRoute);server.on("/api/download",HTTP_HEAD,downloadRoute);
  server.on("/api/view",HTTP_GET,downloadRoute);server.on("/api/view",HTTP_HEAD,downloadRoute);
  server.on("/api/upload/start",HTTP_POST,startUpload);
  server.on("/api/upload/status",HTTP_GET,uploadState);
  server.on("/api/upload/chunk",HTTP_POST,[]{if(chunkError.length())problem(409,chunkError);else uploadState();},uploadChunk);
  server.on("/api/upload/finish",HTTP_POST,finishUpload);
  server.on("/api/upload/cancel",HTTP_POST,[]{if(!mutableRequest()||!uploadToken())return;clearUpload(true);server.send(200,"application/json","{}");});
}
