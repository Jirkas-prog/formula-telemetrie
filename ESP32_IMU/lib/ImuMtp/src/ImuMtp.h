#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
void imuUsbTrace(JsonArray output);
bool imuUsbBegin(bool sdAvailable);
void imuStorageLock();
bool imuStorageTryLock();
void imuStorageUnlock();
bool imuUsbOwned();
bool imuUsbConnected();
bool imuUsbBusy();
bool imuUsbRelease();
uint32_t imuUsbOperation();
int32_t imuUsbResult();
void imuUsbChanged(const String& path,bool removed=false);
void imuUsbTick();
void imuUsbCapacity(uint64_t total,uint64_t free);
// Called with the storage mutex held, before any filesystem operation from USB.
bool imuUsbStorageAllowed();
