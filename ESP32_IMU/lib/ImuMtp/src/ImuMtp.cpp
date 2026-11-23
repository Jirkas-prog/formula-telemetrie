#include "ImuMtp.h"
#include "USB.h"
#include "esp32-hal-tinyusb.h"
#include "mtp_compat.h"
#include "class/mtp/mtp_device.h"
#include "device/usbd_pvt.h"
#include "tinyusb_mtp.h"
#include "mtp/tinyusb_mtp_context.h"
#include "mtp/tinyusb_mtp_transfer.h"
#include "mtp/tinyusb_mtp_object_store.h"
#include "ff.h"
#include <atomic>

static SemaphoreHandle_t storageMutex;
static std::atomic<bool> owned{false}, connected{false};
static bool inFlight=false, installed=false, listingOnly=false;
static portMUX_TYPE capacityLock=portMUX_INITIALIZER_UNLOCKED;
static uint64_t capacityTotal=0,capacityFree=0;
void imuUsbCapacity(uint64_t total,uint64_t available){portENTER_CRITICAL(&capacityLock);capacityTotal=total;capacityFree=available;portEXIT_CRITICAL(&capacityLock);}
static QueueHandle_t changes;
static std::atomic<uint32_t> changedAt{0};
struct Change { uint16_t code;uint32_t handle; };
static void changed(uint16_t code,uint32_t handle){Change c{code,handle};xQueueSend(changes,&c,0);changedAt=millis();}
// Windows caches child IDs. Publish committed web/logger changes to invalidate them.
void imuUsbChanged(const String& path,bool removed){
    if(!installed||!connected||!changes||path=="/")return;
    imuStorageLock();mtp_lock();auto* storage=&mtp_context_get()->mux_protected.storages[0];
    if(!storage->used){mtp_unlock();imuStorageUnlock();return;}
    String full=String(storage->base_path)+path;
    if(removed){auto* object=mtp_find_object_by_path_locked(storage,full.c_str());if(object){changed(MTP_EVENT_OBJECT_REMOVED,object->handle);mtp_drop_objects_under_path_locked(storage,full.c_str());}}
    else {
        uint32_t parent=MTP_ROOT_PARENT;String prefix=storage->base_path;
        unsigned start=1;while(start<path.length()){
            int slash=path.indexOf('/',start);unsigned end=slash<0?path.length():slash;
            prefix+="/"+path.substring(start,end);struct stat st;if(stat(prefix.c_str(),&st))break;
            bool existed=mtp_find_object_by_path_locked(storage,prefix.c_str())!=nullptr;
            auto* object=mtp_get_or_create_object_locked(storage,parent,prefix.c_str(),&st);if(!object)break;
            parent=object->handle;if(!existed)changed(MTP_EVENT_OBJECT_ADDED,parent);else if(end==path.length())changed(MTP_EVENT_OBJECT_INFO_CHANGED,parent);
            start=end+1;
        }
    }
    mtp_unlock();imuStorageUnlock();
}
void imuUsbTick(){
    if(!installed||!connected||!changes||millis()-changedAt.load()<500)return;
    Change c;if(xQueuePeek(changes,&c,0)!=pdTRUE)return;
    mtp_event_t e={};e.code=c.code;e.transaction_id=UINT32_MAX;e.params[0]=c.handle;
    if(tud_mtp_event_send(&e))xQueueReceive(changes,&c,0);
}
static std::atomic<uint32_t> lastOperation{0};
static std::atomic<int32_t> lastResult{0};
uint32_t imuUsbOperation(){return lastOperation;}
int32_t imuUsbResult(){return lastResult;}
extern "C" void imu_mtp_trace(uint16_t op,int32_t result){lastOperation=op;lastResult=result;}
// Bounded RAM diagnostics survive a failed transfer; no SD or serial writes.
struct UsbTrace {uint32_t sequence,ms,transaction;uint16_t kind,code;int32_t value;};
static UsbTrace usbTrace[96];
static uint32_t traceSequence=0;
static portMUX_TYPE traceLock=portMUX_INITIALIZER_UNLOCKED;
extern "C" void imu_mtp_trace_detail(uint16_t kind,uint16_t code,uint32_t transaction,int32_t value){
    portENTER_CRITICAL(&traceLock);uint32_t seq=traceSequence++;usbTrace[seq%96]={seq,millis(),transaction,kind,code,value};portEXIT_CRITICAL(&traceLock);
}
void imuUsbTrace(JsonArray output){
    portENTER_CRITICAL(&traceLock);uint32_t end=traceSequence;portEXIT_CRITICAL(&traceLock);
    for(uint32_t seq=end>96?end-96:0;seq<end;seq++){
        portENTER_CRITICAL(&traceLock);UsbTrace entry=usbTrace[seq%96];portEXIT_CRITICAL(&traceLock);
        if(entry.sequence!=seq)continue;
        auto row=output.add<JsonArray>();row.add(entry.sequence);row.add(entry.ms);row.add(entry.kind);row.add(entry.code);row.add(entry.transaction);row.add(entry.value);
    }
}

void imuStorageLock() { xSemaphoreTakeRecursive(storageMutex,portMAX_DELAY); }
bool imuStorageTryLock() { return xSemaphoreTakeRecursive(storageMutex,0)==pdTRUE; }
void imuStorageUnlock() { xSemaphoreGiveRecursive(storageMutex); }
extern "C" void imu_mtp_lock() { imuStorageLock(); }
extern "C" void imu_mtp_unlock() { imuStorageUnlock(); }
bool imuUsbOwned() { return owned; }
bool imuUsbConnected() { return connected; }

extern "C" esp_err_t imu_fat_info(const char* path,uint64_t* total,uint64_t* available) {
    if(strcmp(path,"/sdcard"))return ESP_ERR_INVALID_ARG;
    // Capacity discovery must work while the logger owns SD.
    portENTER_CRITICAL(&capacityLock);*total=capacityTotal;*available=capacityFree;portEXIT_CRITICAL(&capacityLock);
    return ESP_OK;
}

extern "C" bool imu_mtp_allow_command(uint16_t op,bool cached_properties) {
    // Device discovery and session keepalives do not claim the SD card.
    bool metadata=cached_properties||op==MTP_OP_GET_OBJECT_PROP_REFERENCES||op==MTP_OP_GET_DEVICE_INFO||op==MTP_OP_OPEN_SESSION||op==MTP_OP_CLOSE_SESSION||
        op==MTP_OP_GET_STORAGE_IDS||op==MTP_OP_GET_STORAGE_INFO||op==MTP_OP_GET_DEVICE_PROP_DESC||op==MTP_OP_GET_DEVICE_PROP_VALUE||
        op==MTP_OP_GET_OBJECT_PROPS_SUPPORTED||op==MTP_OP_GET_OBJECT_PROP_DESC||op==MTP_OP_GET_OBJECT_INFO||op==MTP_OP_GET_OBJECT_PROP_VALUE;
    // Once USB owns SD, HTTP status polling cannot interrupt its transaction.
    // The web's filesystem handlers already reject every access while owned.
    if(!metadata&&!owned&&!imuUsbStorageAllowed())return false;
    if(!metadata&&!owned){
        // Windows refreshes directories in the background after our change events.
        // Hold SD for that transaction, but do not leave the web locked afterward.
        listingOnly=op==MTP_OP_GET_OBJECT_HANDLES||op==MTP_OP_GET_NUM_OBJECTS||op==MTP_OP_GET_OBJECT_PROP_LIST;
        owned=true;
    }
    if(op==MTP_OP_CLOSE_SESSION)owned=false;
    inFlight=true;
    return true;
}
extern "C" void imu_mtp_response_done() { inFlight=false;if(listingOnly){owned=false;listingOnly=false;} }
// Listings have already copied their result into RAM; host ACKs need no SD lock.
extern "C" void imu_mtp_command_finished(){if(listingOnly){owned=false;listingOnly=false;}}
extern "C" int32_t tud_mtp_response_complete_cb(tud_mtp_cb_data_t*) {
    imuStorageLock();imu_mtp_response_done();imuStorageUnlock();return 0;
}

bool imuUsbBusy() {
    if(!installed)return false;
    if(xSemaphoreTake(mtp_context_get()->constant.lock,0)!=pdTRUE)return true;
    auto& s=mtp_context_get()->mux_protected;
    bool busy=inFlight||s.active_read.active||s.active_edit.active||s.partial_write.active||
        s.active_buffer.active||(s.pending_write.state!=MTP_WRITE_IDLE&&s.pending_write.state!=MTP_WRITE_ZERO_SIZE_COMPLETE);
    mtp_unlock();return busy;
}
bool imuUsbRelease() {
    if(!owned)return true; // A buffered metadata reply does not own SD.
    if(imuUsbBusy())return false;
    owned=false;return true;
}
static void resetBackend() {
    imuStorageLock();
    if(installed) {
        mtp_lock();mtp_context_reset_transfers_locked(MTP_RESP_TRANSACTION_CANCELLED);
        mtp_context_get()->mux_protected.session_open=false;mtp_unlock();
    }
    owned=false;inFlight=false;listingOnly=false;imuStorageUnlock();
}
static void driverReset(uint8_t port) { resetBackend();mtpd_reset(port); }
static void usbEvent(void*,esp_event_base_t,int32_t event,void*) {
    if(event==ARDUINO_USB_STARTED_EVENT){imuStorageLock();connected=true;imuStorageUnlock();}
    else if(event==ARDUINO_USB_STOPPED_EVENT){resetBackend();imuStorageLock();connected=false;imuStorageUnlock();}
    // Suspend can be selective power saving, so it must never release ownership.
}
static uint16_t descriptor(uint8_t* dst,uint8_t* itf) {
    uint8_t bulk=tinyusb_get_free_duplex_endpoint(),event=tinyusb_get_free_in_endpoint();
    uint8_t str=tinyusb_add_string_descriptor("MTP");
    // Still Image / PIMA 15740, interrupt IN first, then bulk OUT/IN.
    uint8_t d[]={9,4,*itf,0,3,6,1,1,str, 7,5,uint8_t(event|0x80),3,32,0,6,
        7,5,bulk,2,64,0,0, 7,5,uint8_t(bulk|0x80),2,64,0,0};
    if(!bulk||!event)return 0;
    memcpy(dst,d,sizeof(d));++*itf;return sizeof(d);
}
extern "C" const usbd_class_driver_t* usbd_app_driver_get_cb(uint8_t* count) {
    static const usbd_class_driver_t driver={
#if CFG_TUSB_DEBUG >= CFG_TUD_LOG_LEVEL
        "MTP",
#endif
        mtpd_init,driverReset,mtpd_open,mtpd_control_xfer_cb,mtpd_xfer_cb,nullptr};
    *count=1;return &driver;
}
bool imuUsbBegin(bool sdAvailable) {
    storageMutex=xSemaphoreCreateRecursiveMutex();if(!storageMutex)return false;
    changes=xQueueCreate(32,sizeof(Change));if(!changes)return false;
    char serial[20];snprintf(serial,sizeof(serial),"%012llX",(unsigned long long)ESP.getEfuseMac());
    tinyusb_mtp_driver_config_t config={"IMU Test","IMU-Test","2.0",serial,"IMU-Test"};
    if(tinyusb_mtp_install_driver(&config)!=ESP_OK)return false;
    installed=true;
    if(sdAvailable) {
        tinyusb_mtp_storage_config_t sd={"/sdcard","Měřicí data",true};
        if(tinyusb_mtp_register_storage(&sd,nullptr)!=ESP_OK)return false;
    }
    USB.productName("IMU-Test");USB.manufacturerName("IMU Test");USB.serialNumber(serial);
    USB.PID(0x0002);USB.onEvent(usbEvent);
    if(tinyusb_enable_interface(USB_INTERFACE_CUSTOM,30,descriptor)!=ESP_OK)return false;
    return USB.begin();
}
