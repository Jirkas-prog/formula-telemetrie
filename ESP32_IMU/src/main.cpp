#include <Arduino.h>
#include <atomic>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <SD_MMC.h>
#include <SPI.h>
#include <Wire.h>
#include <ICM_20948.h>
#include <Adafruit_ST7789.h>
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <esp_heap_caps.h>
#include <Update.h>
#include "ImuMtp.h"
#include "model.h"
#include "log_integrity.h"
#include "sampling.h"
#include "web_assets.h"

Config cfg;
std::atomic<uint16_t> displayRotation{0},displayRotationApplied{0};
WebServer server(80);
DNSServer dns;
Preferences prefs;
SPIClass lcdBus(FSPI), imuBus(HSPI);
Adafruit_ST7789 lcd(&lcdBus,42,41,39);
ICM_20948_I2C imuI2c;
ICM_20948_SPI imuSpi;
ICM_20948* imu;
QueueHandle_t samples, commands, replies;
StaticQueue_t sampleQueueControl;
uint8_t* sampleQueueStorage=nullptr;
SemaphoreHandle_t gate, dataLock, historyLock;
TaskHandle_t samplerHandle;
esp_timer_handle_t sampleTimer;
Mode mode=Mode::Idle;
std::atomic<bool> loggerUsesSd{false};
std::atomic<bool> samplerReady{false};
std::atomic<bool> webActive{false};
bool sdOK=false, imuOK=false, memoryOK=false, transfer=false, rebootPending=false;
String errorText, logPath;
File logFile, uploadFile;
String uploadPath, uploadTemp, uploadError;
bool legacyUploadActive=false;
uint64_t startUs=0, endUs=0, lastMagUs=0, sdTotal=0, sdUsed=0;
uint32_t bootNumber=0, sessionNumber=0, sequence=0, written=0, dropped=0, missed=0, ioErrors=0, magOverruns=0;
std::atomic<uint32_t> fifoOverflows{0},fifoHighWater{0},queueHighWater{0},sampleReadMaxUs{0},sdWriteMaxUs{0};
std::atomic<uint32_t> timerGapMaxUs{0},samplerGapMaxUs{0};
float measuredHz=0,axisHz[3]={};
bool otaActive=false,otaOK=false;
String otaError;
Sample live={};
float minimums[9], maximums[9];
Bucket* history=nullptr;
size_t historyCount=0;
uint64_t bucketSpan=100000;
char csvBuffer[16384];
size_t csvUsed=0;
uint32_t lastFlush=0;
bool hasDownloads();
bool claimWebStorage(){if(!imuStorageTryLock())return false;bool ok=!imuUsbOwned();if(ok)webActive=true;imuStorageUnlock();return ok;}

enum Command { Start=1,Pause,Resume,Stop,ResetPeaks };

void lock() { xSemaphoreTake(dataLock,portMAX_DELAY); }
void unlock() { xSemaphoreGive(dataLock); }
void refreshSpace() { if(sdOK) { sdTotal=SD_MMC.totalBytes(); sdUsed=SD_MMC.usedBytes(); imuUsbCapacity(sdTotal,sdTotal-sdUsed); } }
void fail(const String& msg) { lock(); errorText=msg; mode=Mode::Error; if(startUs)endUs=esp_timer_get_time(); unlock(); }
#include "log_recovery.h"

void resetStats() {
  xSemaphoreTake(historyLock,portMAX_DELAY);
  historyCount=0; bucketSpan=100000; written=dropped=missed=ioErrors=magOverruns=0;
  xSemaphoreGive(historyLock);
  fifoOverflows=0;fifoHighWater=0;queueHighWater=0;sampleReadMaxUs=0;sdWriteMaxUs=0;
  timerGapMaxUs=0;samplerGapMaxUs=0;
  for(int i=0;i<9;i++) { minimums[i]=INFINITY; maximums[i]=-INFINITY; }
}
void addHistory(const Sample& s) {
  if(!history) return;
  const uint64_t t=s.us-startUs;
  if(historyCount==HISTORY_SIZE && t-history[historyCount-1].first>=bucketSpan) {
    for(size_t j=0;j<historyCount/2;j++) {
      Bucket a=history[2*j],b=history[2*j+1]; a.last=b.last; a.clip|=b.clip; a.count+=b.count;
      for(int k=0;k<9;k++) { a.lo[k]=fminf(a.lo[k],b.lo[k]); a.hi[k]=fmaxf(a.hi[k],b.hi[k]); }
      history[j]=a;
    }
    historyCount/=2; bucketSpan*=2;
  }
  if(!historyCount || t-history[historyCount-1].first>=bucketSpan) {
    Bucket& b=history[historyCount++]; b.first=b.last=t; b.clip=0; b.count=0;
    for(int i=0;i<9;i++) { b.lo[i]=INFINITY; b.hi[i]=-INFINITY; }
  }
  Bucket& b=history[historyCount-1]; b.last=t; b.clip|=s.clip; b.count++;
  for(int i=0;i<9;i++) if(isfinite(s.v[i])) { b.lo[i]=fminf(b.lo[i],s.v[i]); b.hi[i]=fmaxf(b.hi[i],s.v[i]); }
}
bool flushBytes() {
  if(!csvUsed) return true;
  uint64_t began=esp_timer_get_time();
  size_t expected=csvUsed,actual=logFile.write(reinterpret_cast<uint8_t*>(csvBuffer),expected);
  sdWriteMaxUs=max(sdWriteMaxUs.load(),uint32_t(esp_timer_get_time()-began));
  csvUsed=0;
  return actual==expected;
}
bool appendSample(const Sample& s) {
  char line[512];
  int n=snprintf(line,sizeof(line),"%llu,%lu,%.5f,%.5f,%.5f,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.2f,%u,%u,%lu,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%lu,%lu",
    (unsigned long long)(s.us-startUs),(unsigned long)s.seq,s.v[0],s.v[1],s.v[2],s.v[3],s.v[4],s.v[5],s.v[6],s.v[7],s.v[8],s.temp,
    s.magNew,s.magValid,(unsigned long)s.magAge,s.magOverflow,s.clip,cfg.accel,cfg.gyro,cfg.accRate,cfg.gyroRate,cfg.magRate,cfg.filter,s.accNew,s.gyroNew,(unsigned long)s.accAge,(unsigned long)s.gyroAge);
  if(n<0 || n+10>=int(sizeof(line))) return false;
  n+=snprintf(line+n,sizeof(line)-n,",%08lx\n",(unsigned long)csvCrc(line,n));
  if(csvUsed+n>sizeof(csvBuffer) && !flushBytes()) return false;
  memcpy(csvBuffer+csvUsed,line,n); csvUsed+=n;
  xSemaphoreTake(historyLock,portMAX_DELAY);addHistory(s);xSemaphoreGive(historyLock);
  lock(); written++; unlock(); return true;
}
void metadata() {
  JsonDocument d;
  d["schema"]=3; d["row_integrity"]="CRC-32/ISO-HDLC"; d["file"]=logPath; d["state"]=modeName(mode); d["rows"]=written;
  d["queue_dropped"]=dropped; d["timer_missed"]=missed; d["sensor_errors"]=ioErrors; d["mag_overruns"]=magOverruns;
  d["acquisition"]="hardware FIFO";d["fifo_overflows"]=fifoOverflows.load();d["fifo_high_water_bytes"]=fifoHighWater.load();d["queue_high_water"]=queueHighWater.load();
  d["accel_rate_hz"]=cfg.accRate; d["gyro_rate_hz"]=cfg.gyroRate; d["sensor_odr_hz"]=1125; d["mag_hz"]=cfg.magRate;
  d["accel_g"]=cfg.accel; d["gyro_dps"]=cfg.gyro; d["mag_uT"]=4912; d["filter"]=cfg.filter;
  d["transport"]=cfg.spi?"SPI":"I2C"; d["clip_threshold"]=0.98; d["error"]=errorText;
  File f=SD_MMC.open(logPath+".json",FILE_WRITE); if(f) { serializeJson(d,f); f.close(); }
}
bool closeLog() {
  bool ok=flushBytes();
  if(logFile) { logFile.flush(); logFile.close(); }
  if(!ok) fail("Chyba zápisu SD: část záznamu nebyla uložena.");
  if(logPath.length()) metadata();
  if(logPath.length()){imuUsbChanged(logPath);imuUsbChanged(logPath+".json");}
  refreshSpace(); loggerUsesSd=false; return ok;
}
bool beginLog() {
  if(!sdOK || !imuOK || !memoryOK || transfer || recovering || !recoveryHealthy || imuUsbOwned()) return false;
  if(prefs.getString("openLog","").length()){fail("Nedokončený záznam čeká na obnovu. Restartuj desku.");return false;}
  if(!SD_MMC.exists("/logs") && !SD_MMC.mkdir("/logs")) { fail("Nelze vytvořit /logs."); return false; }
  refreshSpace();
  if(sdTotal-sdUsed<1024*1024) { fail("Na SD zbývá méně než 1 MB."); return false; }
  char name[80];
  do { snprintf(name,sizeof(name),"/logs/boot_%06lu_run_%03lu.csv",(unsigned long)bootNumber,(unsigned long)++sessionNumber); } while(SD_MMC.exists(name));
  loggerUsesSd=true;
  if(prefs.putString("openLog",name)!=strlen(name)){loggerUsesSd=false;fail("Nelze uložit značku obnovy do NVS.");return false;}
  logFile=SD_MMC.open(name,FILE_WRITE);
  if(!logFile) { loggerUsesSd=false; fail("Nelze otevřít nový CSV soubor."); return false; }
  if(logFile.print(CSV_HEADER)!=strlen(CSV_HEADER)) { logFile.close(); loggerUsesSd=false; fail("Nelze zapsat hlavičku CSV."); return false; }
  logFile.flush();
  xSemaphoreTake(gate,portMAX_DELAY); lock();
  resetStats(); startUs=esp_timer_get_time(); endUs=0; sequence=0; logPath=name; csvUsed=0; errorText=""; mode=Mode::Recording;
  unlock(); xSemaphoreGive(gate); lastFlush=millis(); return true;
}
void loggerTask(void*) {
  recoveryHealthy=recoverInterruptedLog();recovering=false;
  for(unsigned warmup=0;imuOK&&!samplerReady&&warmup<500;warmup++)vTaskDelay(pdMS_TO_TICKS(1));
  if(cfg.autostart&&recoveryHealthy&&imuOK&&sdOK)beginLog();
  if(mode!=Mode::Recording)loggerUsesSd=false;
  for(;;) {
    int cmd; bool ok=true;
    if(xQueueReceive(commands,&cmd,0)==pdTRUE) {
      if(cmd==Start) ok=(mode!=Mode::Recording && mode!=Mode::Paused) && beginLog();
      else if(cmd==ResetPeaks) { lock(); for(int i=0;i<9;i++) {minimums[i]=INFINITY;maximums[i]=-INFINITY;} unlock(); }
      else if(cmd==Resume) {
        ok=mode==Mode::Paused && imuOK && sdOK && !transfer;
        if(ok)ok=prefs.putString("openLog",logPath)==logPath.length();
        if(ok) { logFile=SD_MMC.open(logPath,FILE_APPEND); ok=bool(logFile); if(ok) {loggerUsesSd=true;lock();mode=Mode::Recording;endUs=0;unlock();} else fail("Obnovení souboru selhalo."); }
      } else if(cmd==Pause || cmd==Stop) {
        if(mode==Mode::Recording || mode==Mode::Paused) {
          xSemaphoreTake(gate,portMAX_DELAY); lock();mode=cmd==Pause?Mode::Paused:Mode::Idle;endUs=esp_timer_get_time();unlock();xSemaphoreGive(gate);
          Sample s; while(xQueueReceive(samples,&s,0)==pdTRUE) if(!appendSample(s)) {ok=false;break;}
          ok=closeLog() && ok; if(ok)prefs.remove("openLog");else fail("Zápis SD selhal při ukončení záznamu.");
        }
      }
      xQueueSend(replies,&ok,portMAX_DELAY);
    }
    Sample s;
    for(unsigned batch=0;batch<32;batch++) {
      if(xQueueReceive(samples,&s,batch?0:pdMS_TO_TICKS(4))!=pdTRUE)break;
      if(!appendSample(s)) {
        xSemaphoreTake(gate,portMAX_DELAY);fail("Zápis SD selhal (plná nebo odpojená karta).");xSemaphoreGive(gate);
        xQueueReset(samples); logFile.close(); csvUsed=0; metadata(); loggerUsesSd=false;break;
      }
    }
    if(mode==Mode::Recording && millis()-lastFlush>=250) {
      if(!flushBytes()) {xSemaphoreTake(gate,portMAX_DELAY);fail("SD: neúplný zápis.");xSemaphoreGive(gate);xQueueReset(samples);logFile.close();metadata();loggerUsesSd=false;}
      else {uint64_t began=esp_timer_get_time();logFile.flush();sdWriteMaxUs=max(sdWriteMaxUs.load(),uint32_t(esp_timer_get_time()-began));}
      lastFlush=millis();
    }
    // Yield once per batch, not once per CSV row. A row can contain mag-only data.
    if(uxQueueMessagesWaiting(samples))vTaskDelay(1);
  }
}
bool command(int c) {
  if(recovering || transfer || hasDownloads() || otaActive || !memoryOK || ((c==Start||c==Resume)&&imuUsbOwned())) return false;
  if((c==Start||c==Resume)&&!claimWebStorage())return false;
  bool ok=false;
  if(xQueueSend(commands,&c,0)!=pdTRUE) return false;
  // The owner acknowledges only after the queue is drained and the file closed.
  xQueueReceive(replies,&ok,portMAX_DELAY); return ok;
}
bool initSensor() {
  if(cfg.spi) { imuBus.begin(SCK_PIN,MISO_PIN,MOSI_PIN,CS_PIN); imu=&imuSpi; imuSpi.begin(CS_PIN,imuBus,4000000); }
  else { Wire.begin(SDA_PIN,SCL_PIN,400000); Wire.setTimeOut(4); imu=&imuI2c; imuI2c.begin(Wire,cfg.address==0x69); }
  if(imu->status!=ICM_20948_Stat_Ok) return false;
  ICM_20948_fss_t ranges={}; ranges.a=cfg.accel==2?0:cfg.accel==4?1:cfg.accel==8?2:3; ranges.g=cfg.gyro==250?0:cfg.gyro==500?1:cfg.gyro==1000?2:3;
  if(imu->setFullScale(ICM_20948_Internal_Acc|ICM_20948_Internal_Gyr,ranges)!=ICM_20948_Stat_Ok) return false;
  ICM_20948_dlpcfg_t filter={cfg.filter,cfg.filter};
  if(imu->setDLPFcfg(ICM_20948_Internal_Acc|ICM_20948_Internal_Gyr,filter)!=ICM_20948_Stat_Ok) return false;
  if(imu->enableDLPF(ICM_20948_Internal_Acc|ICM_20948_Internal_Gyr,true)!=ICM_20948_Stat_Ok) return false;
  ICM_20948_smplrt_t rate={0,0};
  if(imu->setSampleRate(ICM_20948_Internal_Acc|ICM_20948_Internal_Gyr,rate)!=ICM_20948_Stat_Ok) return false;
  uint8_t mr=0; if(imu->writeMag(AK09916_REG_CNTL2,&mr)!=ICM_20948_Stat_Ok) return false; delay(2);
  mr=cfg.magRate==10?2:cfg.magRate==20?4:cfg.magRate==50?6:8;
  if(imu->writeMag(AK09916_REG_CNTL2,&mr)!=ICM_20948_Stat_Ok) return false;
  // AK09916 locks its output while HXL..ST2 are being read. Poll only ST1
  // until DRDY, so a read cannot discard a conversion which finishes meanwhile.
  if(imu->i2cMasterConfigureSlave(0,0x0c,0x10,1)!=ICM_20948_Stat_Ok) return false;
  uint8_t shadow=0x80,zero=0,axes=0x1f;
  if(imu->setBank(3)!=ICM_20948_Stat_Ok||imu->write(0x02,&shadow,1)!=ICM_20948_Stat_Ok)return false;
  return imu->enableFIFO(false)==ICM_20948_Stat_Ok&&imu->setBank(0)==ICM_20948_Stat_Ok&&
    imu->write(0x76,&zero,1)==ICM_20948_Stat_Ok&&imu->write(0x66,&zero,1)==ICM_20948_Stat_Ok&&
    imu->write(0x67,&axes,1)==ICM_20948_Stat_Ok&&imu->setFIFOmode(true)==ICM_20948_Stat_Ok&&
    imu->resetFIFO()==ICM_20948_Stat_Ok&&imu->enableFIFO()==ICM_20948_Stat_Ok;

}
bool magTransferLength(uint8_t length) {
  uint8_t ctrl=length?uint8_t(0x80|length):0;
  return imu->setBank(3)==ICM_20948_Stat_Ok&&imu->write(AGB3_REG_I2C_PERIPH0_CTRL,&ctrl,1)==ICM_20948_Stat_Ok;
}
void sampleTask(void*) {
  Sample held={};for(float& v:held.v)v=NAN;
  uint64_t lastA=0,lastG=0,lastFrame=0,hzTime=esp_timer_get_time();
  uint32_t hzCount=0,counts[3]={};bool magPending=false,magFresh=false,magOverflow=false;
  uint64_t pendingAt=0,magTime=0,lastWake=esp_timer_get_time();float magValues[3]={};
  SampleDeadline accel(cfg.accRate),gyro(cfg.gyroRate);
  imu->resetFIFO(); // Discard setup-time data before establishing timestamps.
  for(;;) {
    // esp_timer callbacks run on core 0, where Wi-Fi association can delay them.
    // The sampler on core 1 must drain the hardware FIFO even without a callback.
    ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(2));
    if(!imuOK||otaActive) continue;
    uint64_t tick=esp_timer_get_time();
    samplerGapMaxUs=max(samplerGapMaxUs.load(),uint32_t(tick-lastWake));lastWake=tick;
    if(magPending&&tick-pendingAt>=1200){
      uint8_t mb[9]={},status=0;
      bool ok=magTransferLength(0)&&imu->setBank(0)==ICM_20948_Stat_Ok&&
        imu->read(AGB0_REG_I2C_MST_STATUS,&status,1)==ICM_20948_Stat_Ok&&imu->read(AGB0_REG_EXT_PERIPH_SENS_DATA_00,mb,9)==ICM_20948_Stat_Ok;
      ok=magTransferLength(1)&&ok&&!(status&1);magPending=false;magOverflow=mb[8]&8;
      if(ok&&!magOverflow){for(int i=0;i<3;i++)magValues[i]=sensorLe16(mb+1+2*i)*0.15f;magFresh=true;magTime=pendingAt;}
      else {lastMagUs=0;if(!ok){lock();ioErrors++;unlock();}}
    }else if(!magPending){
      uint8_t st1=0;
      bool ok=imu->setBank(0)==ICM_20948_Stat_Ok&&imu->read(AGB0_REG_EXT_PERIPH_SENS_DATA_00,&st1,1)==ICM_20948_Stat_Ok;
      if(ok&&(st1&1)){
        if(st1&2){lock();if(mode==Mode::Recording)magOverruns++;unlock();}
        if(magTransferLength(9)){magPending=true;pendingAt=tick;}else{lock();ioErrors++;unlock();}
      }else if(!ok){lock();ioErrors++;unlock();}
    }
    uint64_t began=esp_timer_get_time();uint8_t countBytes[2],interrupts[5];
    if(imu->setBank(0)!=ICM_20948_Stat_Ok||imu->read(AGB0_REG_I2C_MST_STATUS,interrupts,sizeof(interrupts))!=ICM_20948_Stat_Ok||
       imu->read(AGB0_REG_FIFO_COUNT_H,countBytes,2)!=ICM_20948_Stat_Ok){lock();ioErrors++;unlock();continue;}
    unsigned count=((countBytes[0]&0x1f)<<8)|countBytes[1];fifoHighWater=max(fifoHighWater.load(),uint32_t(count));
    // FIFO_CFG=0 selects one combined FIFO; other FIFO flags are irrelevant.
    if(interrupts[AGB0_REG_INT_STATUS_2-AGB0_REG_I2C_MST_STATUS]&1){if(mode==Mode::Recording)fifoOverflows++;imu->resetFIFO();continue;}
    const uint64_t observed=esp_timer_get_time();unsigned remaining=count/FIFO_FRAME_BYTES;
    while(remaining) {
      // Fits Arduino Wire's 128-byte buffer on both supported transports.
      uint8_t batch[FIFO_FRAME_BYTES*4];unsigned frames=min(remaining,4u);
      if(imu->readFIFO(batch,frames*FIFO_FRAME_BYTES)!=ICM_20948_Stat_Ok){lock();ioErrors++;unlock();imu->resetFIFO();break;}
      for(unsigned frame=0;frame<frames;frame++,remaining--) {
        const uint8_t* b=batch+frame*FIFO_FRAME_BYTES;
        uint64_t now=fifoSampleTime(observed,remaining-1,lastFrame);lastFrame=now;
        Sample s=held;s.us=now;s.accNew=s.gyroNew=s.magNew=s.magOverflow=false;uint32_t skipped=0;
        s.accNew=accel.due(now,skipped);s.gyroNew=gyro.due(now,skipped);
        if(s.accNew){for(int i=0;i<3;i++)s.v[i]=sensorBe16(b+2*i)*(cfg.accel/32768.0f);lastA=now;counts[0]++;}
        if(s.gyroNew){for(int i=0;i<3;i++)s.v[i+3]=sensorBe16(b+6+2*i)*(cfg.gyro/32768.0f);lastG=now;counts[1]++;}
        s.temp=sensorBe16(b+12)/333.87f+21;
        if(remaining==1){
          s.magOverflow=magOverflow;magOverflow=false;
          if(magFresh){for(int i=0;i<3;i++)s.v[i+6]=magValues[i];lastMagUs=magTime;s.magNew=true;counts[2]++;magFresh=false;}
        }
        // Idle/paused time and buffered frames preceding this run are not lost log samples.
        if(skipped){lock();if(mode==Mode::Recording&&now>=startUs)missed+=skipped;unlock();}
    s.magValid=lastMagUs&&now-lastMagUs<max(uint32_t(200000),uint32_t(3000000/cfg.magRate));
    s.magAge=lastMagUs?uint32_t(min(uint64_t(UINT32_MAX),now-lastMagUs)):UINT32_MAX;
    s.accAge=lastA?uint32_t(min(uint64_t(UINT32_MAX),now-lastA)):UINT32_MAX;
    s.gyroAge=lastG?uint32_t(min(uint64_t(UINT32_MAX),now-lastG)):UINT32_MAX;
    if(!s.magValid)for(int i=6;i<9;i++)s.v[i]=NAN;
    if(!s.accNew&&!s.gyroNew&&!s.magNew&&!s.magOverflow)continue;
    s.clip=clipping(s.v,cfg.accel,cfg.gyro,s.magOverflow);held=s;hzCount++;
    xSemaphoreTake(gate,portMAX_DELAY);lock();
    if(now-hzTime>=1000000){measuredHz=hzCount*1e6/(now-hzTime);for(int i=0;i<3;i++){axisHz[i]=counts[i]*1e6/(now-hzTime);counts[i]=0;}hzTime=now;hzCount=0;}
    live=s;
    if(s.magValid)samplerReady=true;
    for(int i=0;i<9;i++)if(isfinite(s.v[i])){minimums[i]=fminf(minimums[i],s.v[i]);maximums[i]=fmaxf(maximums[i],s.v[i]);}
    if(mode==Mode::Recording&&s.us>=startUs){s.seq=sequence++;if(xQueueSend(samples,&s,0)!=pdTRUE)dropped++;queueHighWater=max(queueHighWater.load(),uint32_t(uxQueueMessagesWaiting(samples)));}
    unlock();xSemaphoreGive(gate);
      }
    }
    sampleReadMaxUs=max(sampleReadMaxUs.load(),uint32_t(esp_timer_get_time()-began));
  }
}
void timerTick(void*) { static uint64_t previous=0;uint64_t now=esp_timer_get_time();if(previous)timerGapMaxUs=max(timerGapMaxUs.load(),uint32_t(now-previous));previous=now;if(samplerHandle)xTaskNotifyGive(samplerHandle); }
void jsonReply(JsonDocument& d,int status=200) {String body;serializeJson(d,body);server.send(status,"application/json; charset=utf-8",body);}
void problem(int code,const String& msg) {JsonDocument d;d["error"]=msg;jsonReply(d,code);}
bool mutableRequest() {
  String origin=server.header("Origin"), host=server.header("Host");
  if(server.header("X-IMU-Client")!="1" || (origin.length() && origin!="http://"+host)) {problem(403,"Nepovolený původ požadavku.");return false;}
  return true;
}
#include "storage_http.h"
#include "wifi_settings.h"

bool storageAllowed() {if(recovering){problem(409,"Probíhá kontrola a obnova záznamu po výpadku.");return false;}if(transfer){problem(409,"Probíhá nahrávání souboru. Dokonči nebo zruš přenos.");return false;}if(!sdOK){problem(503,"SD karta není dostupná.");return false;}if(!claimWebStorage()){problem(409,"SD kartu používá USB. Nejdříve vrať přístup webu.");return false;}if(mode==Mode::Recording||loggerUsesSd){problem(409,"Nejdříve pozastav nebo zastav záznam a počkej na dokončení zápisu.");return false;}return true;}
void configJson(JsonDocument& d) {d["spi"]=cfg.spi;d["accRate"]=cfg.accRate;d["gyroRate"]=cfg.gyroRate;d["accel"]=cfg.accel;d["gyro"]=cfg.gyro;d["magRate"]=cfg.magRate;d["filter"]=cfg.filter;d["address"]=cfg.address;d["autostart"]=cfg.autostart;d["displayRotation"]=displayRotation.load();}
void saveDisplay() {
  if(!mutableRequest())return;
  JsonDocument d;if(deserializeJson(d,server.arg("plain"))){problem(400,"Neplatné JSON.");return;}
  if(!d["displayRotation"].is<int>()){problem(400,"Zvol otočení 0, 90, 180 nebo 270 stupňů.");return;}
  int rotation=d["displayRotation"];
  if(rotation<0||rotation>270||rotation%90){problem(400,"Zvol otočení 0, 90, 180 nebo 270 stupňů.");return;}
  // Separate NVS key keeps existing sensor settings compatible across OTA.
  if(rotation!=displayRotation&&prefs.putUShort("lcdRotation",rotation)!=sizeof(uint16_t)){problem(500,"Uložení orientace selhalo.");return;}
  displayRotation=rotation;d.clear();d["displayRotation"]=rotation;jsonReply(d);
}
void statusRoute() {
  JsonDocument d;lock();
  d["storageOwner"]=imuUsbOwned()?"usb":(mode==Mode::Recording||loggerUsesSd)?"logger":"web";
  d["recovering"]=bool(recovering);d["recoveryMessage"]=recoveryMessage;d["recoveryPercent"]=recoveryPercent.load();d["recoveredRows"]=recoveredRows;
  d["transfer"]=transfer||hasDownloads();d["uploadActive"]=chunkId.length()>0;
  downloadJson(d["download"].to<JsonObject>());
  d["usbConnected"]=imuUsbConnected();d["usbBusy"]=imuUsbBusy();
  d["usbOperation"]=imuUsbOperation();d["usbResult"]=imuUsbResult();
  d["mode"]=modeName(mode);d["error"]=errorText;d["imu"]=imuOK;d["sd"]=sdOK;d["memory"]=memoryOK;
  d["file"]=logPath;d["rows"]=written;d["dropped"]=dropped;d["missed"]=missed;d["ioErrors"]=ioErrors;d["magOverruns"]=magOverruns;d["hz"]=measuredHz;for(int i=0;i<3;i++)d["axisHz"][i]=axisHz[i];d["accRate"]=cfg.accRate;d["gyroRate"]=cfg.gyroRate;d["magRate"]=cfg.magRate;
  d["fifoOverflows"]=fifoOverflows.load();d["fifoHighWater"]=fifoHighWater.load();d["queueHighWater"]=queueHighWater.load();d["sampleReadMaxUs"]=sampleReadMaxUs.load();d["sdWriteMaxUs"]=sdWriteMaxUs.load();d["acquisition"]="FIFO";
  d["timerGapMaxUs"]=timerGapMaxUs.load();d["samplerGapMaxUs"]=samplerGapMaxUs.load();
  d["displayRotation"]=displayRotationApplied.load();
  wifiStatus(d["wifi"].to<JsonObject>());
  d["elapsed"]=startUs?((endUs?endUs:esp_timer_get_time())-startUs)/1e6:0;d["sampleAge"]=live.us?(esp_timer_get_time()-live.us)/1000:UINT32_MAX;
  d["clip"]=live.clip;d["magAge"]=live.magAge;d["magValid"]=live.magValid;d["temp"]=imuOK?live.temp:NAN;
  for(int i=0;i<9;i++) {d["values"][i]=imuOK?live.v[i]:NAN;d["min"][i]=minimums[i];d["max"][i]=maximums[i];}
  unlock();d["queue"]=samples?uxQueueMessagesWaiting(samples):0;d["queueCapacity"]=QUEUE_SIZE;d["sdTotal"]=sdTotal;d["sdUsed"]=sdUsed;d["ssid"]=AP_NAME;d["ip"]=WiFi.softAPIP().toString();d["rate"]=cfg.accRate;d["boot"]=bootNumber;d["clients"]=WiFi.softAPgetStationNum();jsonReply(d);
}
void historyRoute() {
  if(!history){problem(503,"Historie není dostupná.");return;}
  Bucket* copy=(Bucket*)heap_caps_malloc(HISTORY_SIZE*sizeof(Bucket),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  if(!copy) {problem(503,"Nedostatek RAM pro historii.");return;}
  lock();String file=logPath;unlock();
  xSemaphoreTake(historyLock,portMAX_DELAY);size_t count=historyCount;uint64_t span=bucketSpan;memcpy(copy,history,count*sizeof(Bucket));xSemaphoreGive(historyLock);
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);server.send(200,"application/json","");
  JsonDocument head;head["file"]=file;head["bucketUs"]=span;String text;serializeJson(head,text);text.remove(text.length()-1);server.sendContent(text+",\"buckets\":[");
  String chunk;chunk.reserve(8192);
  for(size_t j=0;j<count;j++) {
    JsonDocument d;auto a=d.to<JsonArray>();a.add(copy[j].first/1e6);a.add(copy[j].last/1e6);
    for(int i=0;i<9;i++){a.add(copy[j].lo[i]);a.add(copy[j].hi[i]);}a.add(copy[j].clip);a.add(copy[j].count);
    if(j)chunk+=',';serializeJson(d,chunk);if(chunk.length()>=4096){server.sendContent(chunk);chunk="";delay(1);}
  }
  if(chunk.length())server.sendContent(chunk);
  server.sendContent("]}");server.sendContent("");free(copy);
}
void saveConfig() {
  if(!claimWebStorage()){problem(409,"Před restartem vrať SD z USB webu.");return;}
  if(!mutableRequest())return;if(transfer||hasDownloads()||mode==Mode::Recording||mode==Mode::Paused||loggerUsesSd){problem(409,"Nejdříve ukonči záznam.");return;}
  JsonDocument d;if(deserializeJson(d,server.arg("plain"))){problem(400,"Neplatné JSON.");return;}
  int r=d["accRate"]|0,gr=d["gyroRate"]|0,a=d["accel"]|0,g=d["gyro"]|0,m=d["magRate"]|0,f=d["filter"]|-1,ad=d["address"]|0;
  if(!supportedLogRate(r)||!supportedLogRate(gr)||!(a==2||a==4||a==8||a==16)||!(g==250||g==500||g==1000||g==2000)||!(m==10||m==20||m==50||m==100)||f<0||f>6||!(ad==104||ad==105)||!d["spi"].is<bool>()||!d["autostart"].is<bool>()){problem(400,"Nastavení je mimo podporovaný rozsah.");return;}
  Config next;next.accRate=r;next.gyroRate=gr;next.accel=a;next.gyro=g;next.magRate=m;next.filter=f;next.address=ad;next.spi=d["spi"];next.autostart=d["autostart"];
  if(prefs.putBytes("config2",&next,sizeof(next))!=sizeof(next)){problem(500,"Uložení nastavení selhalo.");return;}
  server.send(200,"application/json","{\"reboot\":true}");rebootPending=true;
}
void filesRoute() {
  if(!storageAllowed())return;String path=server.arg("path");if(!path.length())path="/";
  if(!safePath(path)){problem(400,"Neplatná cesta.");return;}
  File dir=SD_MMC.open(path);if(!dir||!dir.isDirectory()){problem(404,"Složka neexistuje.");return;}
  refreshSpace();server.setContentLength(CONTENT_LENGTH_UNKNOWN);server.send(200,"application/json","");server.sendContent("[");bool first=true;
  for(File f=dir.openNextFile();f;f=dir.openNextFile()) {JsonDocument d;d["name"]=String(f.name());d["dir"]=f.isDirectory();d["size"]=f.size();d["modified"]=(uint32_t)f.getLastWrite();String s;serializeJson(d,s);server.sendContent((first?"":",")+s);first=false;f.close();delay(1);}
  dir.close();server.sendContent("]");server.sendContent("");
}
void fileAction() {
  if(!mutableRequest()||!storageAllowed())return;if(hasDownloads()){problem(409,"Nejdříve dokonči stahování nebo zavři náhled.");return;}JsonDocument d;if(deserializeJson(d,server.arg("plain"))){problem(400,"Neplatné JSON.");return;}
  String action=d["action"]|"",p=d["path"]|"",to=d["to"]|"";
  if(!safePath(p)||p=="/"||p=="/logs"||(mode==Mode::Paused&&(p==logPath||logPath.startsWith(p+"/")))){problem(400,"Cesta je neplatná nebo chráněná otevřeným záznamem.");return;}
  bool ok=false;
  if(action=="mkdir")ok=!SD_MMC.exists(p)&&SD_MMC.mkdir(p);
  else if(action=="rename"||action=="move") {
    if(!safePath(to)||to=="/"||to==p||to.startsWith(p+"/")||SD_MMC.exists(to)){problem(409,"Cíl je obsazený, neplatný nebo leží uvnitř přesouvané složky.");return;}
    String parent=to.substring(0,to.lastIndexOf('/'));if(!parent.length())parent="/";
    File dir=SD_MMC.open(parent);bool valid=dir&&dir.isDirectory();dir.close();
    if(!valid){problem(404,"Cílová složka neexistuje.");return;}ok=SD_MMC.rename(p,to);
  }
  else if(action=="delete") {File f=SD_MMC.open(p);if(f){bool dir=f.isDirectory();f.close();ok=dir?SD_MMC.rmdir(p):SD_MMC.remove(p);}}
  if(!ok){problem(400,"Operace selhala. Složku lze smazat pouze prázdnou.");return;}if(action=="delete")imuUsbChanged(p,true);else if(action=="rename"||action=="move"){imuUsbChanged(p,true);imuUsbChanged(to);}else imuUsbChanged(p);refreshSpace();server.send(200,"application/json","{}");
}
void uploadRoute() {
  HTTPUpload& u=server.upload();
  if(u.status==UPLOAD_FILE_START) {
    uploadError="";uploadPath="";uploadTemp="";legacyUploadActive=false;
    String origin=server.header("Origin");
    if(server.header("X-IMU-Client")!="1"||(origin.length()&&origin!="http://"+server.header("Host")))uploadError="Nepovolený původ požadavku.";
    else if(!sdOK||transfer||hasDownloads()||mode==Mode::Recording||loggerUsesSd||!claimWebStorage())uploadError="SD je nedostupná, probíhá záznam nebo kartu používá USB.";
    else {
      uploadPath=server.arg("path");uploadTemp=uploadPath+".upload-part";
      if(!safePath(uploadPath)||uploadPath=="/"||SD_MMC.exists(uploadPath)||SD_MMC.exists(uploadTemp))uploadError="Cesta je neplatná nebo soubor již existuje.";
      else {transfer=true;legacyUploadActive=true;uploadFile=SD_MMC.open(uploadTemp,FILE_WRITE);if(!uploadFile)uploadError="Soubor nelze otevřít.";}
    }
  } else if(u.status==UPLOAD_FILE_WRITE && uploadError.isEmpty()) {
    if(uploadFile.write(u.buf,u.currentSize)!=u.currentSize)uploadError="Neúplný zápis, zkontroluj volné místo na SD.";
  } else if(u.status==UPLOAD_FILE_END || u.status==UPLOAD_FILE_ABORTED) {
    if(uploadFile)uploadFile.close();
    if(u.status==UPLOAD_FILE_ABORTED)uploadError="Nahrávání bylo přerušeno.";
    if(uploadError.isEmpty()&&!SD_MMC.rename(uploadTemp,uploadPath))uploadError="Dokončení souboru selhalo.";
    if(!uploadError.isEmpty()&&legacyUploadActive&&uploadTemp.length())SD_MMC.remove(uploadTemp);
    if(legacyUploadActive){if(uploadError.isEmpty())imuUsbChanged(uploadPath);refreshSpace();transfer=false;legacyUploadActive=false;}
  }
}
void otaUpload() {
  HTTPUpload& u=server.upload();
  if(u.status==UPLOAD_FILE_START) {
    otaError="";otaOK=false;
    String origin=server.header("Origin");
    if(server.header("X-IMU-Client")!="1"||(origin.length()&&origin!="http://"+server.header("Host")))otaError="Nepovolený původ aktualizace.";
    else if(mode==Mode::Recording||mode==Mode::Paused||loggerUsesSd||transfer||hasDownloads()||!claimWebStorage())otaError="Nejdříve ukonči záznam a přenosy souborů a vrať SD z USB webu.";
    else if(!u.filename.endsWith(".bin"))otaError="Vyber firmware.bin pro tento projekt.";
    else {
      otaActive=true;
      if(sampleTimer)esp_timer_stop(sampleTimer);
      if(!Update.begin(UPDATE_SIZE_UNKNOWN,U_FLASH))otaError=Update.errorString();
    }
  } else if(u.status==UPLOAD_FILE_WRITE&&otaError.isEmpty()) {
    if(Update.write(u.buf,u.currentSize)!=u.currentSize)otaError=Update.errorString();
  } else if(u.status==UPLOAD_FILE_END||u.status==UPLOAD_FILE_ABORTED) {
    if(u.status==UPLOAD_FILE_ABORTED)otaError="Aktualizace byla přerušena.";
    if(otaError.isEmpty()) {otaOK=Update.end(true);if(!otaOK)otaError=Update.errorString();}
    if(!otaOK) {Update.abort();if(otaActive&&sampleTimer)esp_timer_start_periodic(sampleTimer,2000);otaActive=false;}
  }
}
void routes() {
  const char* headers[]={"Origin","X-IMU-Client","Host","Range","If-Range"};server.collectHeaders(headers,5);
  storageRoutes();
  server.on("/",[]{server.sendHeader("Content-Encoding","gzip");server.send_P(200,"text/html; charset=utf-8",(const char*)index_html,sizeof(index_html));});
  server.on("/app.css",[]{server.sendHeader("Content-Encoding","gzip");server.send_P(200,"text/css",(const char*)app_css,sizeof(app_css));});
  server.on("/app.js",[]{server.sendHeader("Content-Encoding","gzip");server.send_P(200,"text/javascript",(const char*)app_js,sizeof(app_js));});
  server.on("/files.js",[]{server.sendHeader("Content-Encoding","gzip");server.send_P(200,"text/javascript",(const char*)files_js,sizeof(files_js));});
  server.on("/api/status",HTTP_GET,statusRoute);server.on("/api/history",HTTP_GET,historyRoute);
  server.on("/api/usb/release",HTTP_POST,[]{if(!mutableRequest())return;if(!imuStorageTryLock()){problem(409,"USB právě přistupuje ke kartě.");return;}bool released=imuUsbRelease();if(released)webActive=true;imuStorageUnlock();if(!released){problem(409,"USB právě přenáší soubor. Počkej na dokončení kopírování a zkus to znovu.");return;}refreshSpace();statusRoute();});
  server.on("/api/usb/trace",HTTP_GET,[]{JsonDocument d;imuUsbTrace(d["events"].to<JsonArray>());jsonReply(d);});
  server.on("/api/config",HTTP_GET,[]{JsonDocument d;configJson(d);jsonReply(d);});server.on("/api/config",HTTP_POST,saveConfig);
  server.on("/api/display",HTTP_POST,saveDisplay);
  server.on("/api/wifi",HTTP_GET,wifiConfigRoute);server.on("/api/wifi",HTTP_POST,saveWifi);
  server.on("/api/control",HTTP_POST,[]{if(!mutableRequest())return;JsonDocument d;if(deserializeJson(d,server.arg("plain"))){problem(400,"Neplatné JSON.");return;}String a=d["action"]|"";int c=a=="start"?Start:a=="pause"?Pause:a=="resume"?Resume:a=="stop"?Stop:a=="reset"?ResetPeaks:0;if(!c||!command(c)){problem(409,"Příkaz nelze provést. Zkontroluj stav senzoru, SD a záznamu.");return;}statusRoute();});
  server.on("/api/files",HTTP_GET,filesRoute);server.on("/api/file",HTTP_POST,fileAction);
  server.on("/api/upload",HTTP_POST,[]{if(uploadError.isEmpty())server.send(200,"application/json","{}");else problem(400,uploadError);},uploadRoute);
  server.on("/api/ota",HTTP_POST,[]{if(otaOK){server.send(200,"application/json","{\"reboot\":true}");rebootPending=true;}else problem(400,otaError.length()?otaError:"Chybí firmware.");},otaUpload);
  server.onNotFound([]{for(const auto& asset:extraAssets){if(server.uri()==asset.path){server.sendHeader("Content-Encoding","gzip");server.sendHeader("Cache-Control","no-cache");server.send_P(200,asset.mime,(const char*)asset.data,asset.size);return;}}if(server.uri().startsWith("/api/"))problem(404,"Neznámé API.");else{server.sendHeader("Location","http://"+WiFi.softAPIP().toString()+"/");server.send(302,"text/plain","");}});
  server.begin();
}
void displayTask(void*) {
  constexpr uint16_t bg=0x0843,white=0xffff,muted=0x9cd3,green=0x3f57,red=0xfa69;
  for(;;) {
  const uint16_t rotation=displayRotation.load();
  const bool landscape=(rotation/90)%2;
  const int width=landscape?306:158,stripHeight=landscape?34:62;
  // Only this task touches the LCD. Rebuild strips once on orientation changes.
  GFXcanvas16 strip(width,stripHeight);
  if(!strip.getBuffer()){vTaskDelay(pdMS_TO_TICKS(1000));continue;}
  strip.setTextWrap(false);
  uint32_t cycle=UINT32_MAX;String previous[3],previousFooter,previousHeader;
  lcd.setRotation(rotation/90);displayRotationApplied=rotation;
  lcd.fillScreen(bg);lcd.setTextSize(1);lcd.setTextColor(white,bg);
  lcd.drawFastHLine(7,landscape?19:37,width,muted);
  while(displayRotation.load()==rotation) {
    bool connected=WiFi.status()==WL_CONNECTED;
    String headerLeft=connected?WiFi.SSID():"IMU-Test / IMU-DEMO-CHANGE-ME",headerRight="IP "+(connected?WiFi.localIP():WiFi.softAPIP()).toString();
    headerLeft=headerLeft.substring(0,landscape?30:26);
    String header=headerLeft+"|"+headerRight;
    if(header!=previousHeader){previousHeader=header;strip.fillScreen(bg);strip.setTextSize(1);strip.setTextColor(white);strip.setCursor(0,0);strip.print(headerLeft);strip.setCursor(landscape?198:0,landscape?0:15);strip.print(headerRight);lcd.drawRGBBitmap(7,5,strip.getBuffer(),width,landscape?12:29);}
    uint32_t page=(millis()/2000)%3;bool changed=page!=cycle;
    Sample s;float lo[9],hi[9];Mode m;uint32_t rows;float hz;
    lock();s=live;memcpy(lo,minimums,sizeof(lo));memcpy(hi,maximums,sizeof(hi));m=mode;rows=written;hz=measuredHz;unlock();
    if(changed){strip.fillScreen(bg);strip.setTextSize(1);strip.setTextColor(white);strip.setCursor(0,0);strip.print(page==0?"AKCELEROMETR [g]":page==1?"GYROSKOP [deg/s]":"MAGNETOMETR [uT]");lcd.drawRGBBitmap(7,landscape?27:49,strip.getBuffer(),width,20);cycle=page;}
    for(int axis=0;axis<3;axis++) {
      int i=page*3+axis;char value[24],low[32],high[32];
      if(!imuOK||!isfinite(s.v[i]))snprintf(value,sizeof(value),"%c       --","XYZ"[axis]);else snprintf(value,sizeof(value),"%c %+8.2f","XYZ"[axis],s.v[i]);
      if(isfinite(lo[i]))snprintf(low,sizeof(low),"min %+9.2f",lo[i]);else strcpy(low,"min        --");
      if(isfinite(hi[i]))snprintf(high,sizeof(high),"max %+9.2f",hi[i]);else strcpy(high,"max        --");
      bool clip=s.clip&(1<<i);String signature=String(value)+low+high+char(clip?'1':'0');
      if(!changed&&signature==previous[axis])continue;previous[axis]=signature;
      strip.fillScreen(bg);strip.setTextSize(2);strip.setTextColor(clip?red:green);strip.setCursor(0,0);strip.print(value);
      strip.setTextSize(1);strip.setTextColor(muted);strip.setCursor(landscape?128:0,landscape?4:26);strip.print(low);strip.setCursor(landscape?220:0,landscape?4:38);strip.print(high);
      lcd.drawRGBBitmap(7,(landscape?48:74)+axis*(landscape?28:62),strip.getBuffer(),width,landscape?28:62);
    }
    char line1[32],line2[32],line3[32];
    if(recovering)snprintf(line1,sizeof(line1),"OBNOVA CSV %lu%%",(unsigned long)recoveryPercent.load());else snprintf(line1,sizeof(line1),"%s %.0f Hz",modeName(m),hz);
    snprintf(line2,sizeof(line2),"SD %s  IMU %s",imuUsbOwned()?"USB":sdOK?"OK":"CHYBI",imuOK?"OK":"CHYBI");
    snprintf(line3,sizeof(line3),"%lu radku   %lu/3",(unsigned long)rows,(unsigned long)page+1);
    String footer=String(line1)+line2+line3;
    if(footer!=previousFooter){previousFooter=footer;strip.fillScreen(bg);strip.setTextSize(1);strip.setTextColor(white);strip.setCursor(0,3);strip.print(line1);strip.setCursor(landscape?160:0,landscape?3:19);strip.print(line2);strip.setCursor(0,landscape?20:36);strip.print(line3);lcd.drawRGBBitmap(7,landscape?136:263,strip.getBuffer(),width,landscape?34:55);}
    vTaskDelay(pdMS_TO_TICKS(200));
  }
  }
}
bool imuUsbStorageAllowed() { return sdOK && !webActive && !recovering && !loggerUsesSd && mode!=Mode::Recording && mode!=Mode::Paused && !transfer && !hasDownloads() && !otaActive && !rebootPending; }
void setup() {
  Serial.begin(115200);
  gate=xSemaphoreCreateMutex();dataLock=xSemaphoreCreateMutex();historyLock=xSemaphoreCreateMutex();
  prefs.begin("imu-test",false);if(prefs.getBytesLength("config2")==sizeof(cfg))prefs.getBytes("config2",&cfg,sizeof(cfg));
  // Also retire rates stored by the temporary high-rate diagnostic firmware.
  if(!supportedLogRate(cfg.accRate)||!supportedLogRate(cfg.gyroRate)){
    if(!supportedLogRate(cfg.accRate))cfg.accRate=500;
    if(!supportedLogRate(cfg.gyroRate))cfg.gyroRate=500;
    prefs.putBytes("config2",&cfg,sizeof(cfg));
  }
  uint16_t rotation=prefs.getUShort("lcdRotation",0);displayRotation=rotation<=270&&rotation%90==0?rotation:0;
  bootNumber=prefs.getUInt("boot",0)+1;prefs.putUInt("boot",bootNumber);
  history=(Bucket*)heap_caps_malloc(HISTORY_SIZE*sizeof(Bucket),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  sampleQueueStorage=(uint8_t*)heap_caps_malloc(QUEUE_SIZE*sizeof(Sample),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  if(sampleQueueStorage)samples=xQueueCreateStatic(QUEUE_SIZE,sizeof(Sample),sampleQueueStorage,&sampleQueueControl);
  commands=xQueueCreate(2,sizeof(int));replies=xQueueCreate(2,sizeof(bool));
  memoryOK=history&&samples&&commands&&replies;resetStats();for(float& v:live.v)v=NAN;
  lcdBus.begin(40,-1,45,42);lcd.init(172,320);lcd.setRotation(0);lcd.setTextWrap(false);lcd.fillScreen(ST77XX_BLACK);pinMode(48,OUTPUT);digitalWrite(48,HIGH);
  SD_MMC.setPins(14,15,16,18,17,21);sdOK=SD_MMC.begin("/sdcard",false,false,SDMMC_FREQ_DEFAULT);refreshSpace();
  imuOK=initSensor();
  if(!imuOK)errorText="ICM-20948 nebyl nalezen. Zkontroluj zapojení a nastavení sběrnice.";
  if(!sdOK)errorText+=" SD karta není dostupná (FAT32).";
  if(!memoryOK)errorText+=" Nedostatek RAM / PSRAM.";
  wifiBegin();
  Serial.printf("IMU-Test: http://192.168.4.1 | SD=%d IMU=%d PSRAM=%u\n",sdOK,imuOK,ESP.getPsramSize());
  if(memoryOK) {
    recovering=prefs.getString("openLog","").length()>0;loggerUsesSd=recovering.load()||cfg.autostart;
    xTaskCreatePinnedToCore(loggerTask,"sd-writer",8192,nullptr,4,nullptr,0);
    xTaskCreatePinnedToCore(sampleTask,"imu-sample",6144,nullptr,5,&samplerHandle,1);
    esp_timer_create_args_t args={};args.callback=timerTick;args.name="imu-clock";esp_timer_create(&args,&sampleTimer);esp_timer_start_periodic(sampleTimer,2000);
  }
  if(!imuUsbBegin(sdOK))errorText+=" USB MTP není dostupné.";
  xTaskCreatePinnedToCore(displayTask,"lcd",4096,nullptr,1,nullptr,0);routes();
}
void loop() {
  dns.processNextRequest();
  // Only SD operations claim storage. Status/graphs/assets must not make MTP busy.
  // Claims release the mutex immediately to avoid priority inheritance starvation.
  server.handleClient();
  if((hasDownloads()||transfer)&&claimWebStorage())storageTick();
  // No USB task can claim while webActive is true; releasing needs no blocking lock.
  webActive=false;
  imuUsbTick();wifiTick();
  if(rebootPending){delay(400);ESP.restart();}
  delay(2);
}
