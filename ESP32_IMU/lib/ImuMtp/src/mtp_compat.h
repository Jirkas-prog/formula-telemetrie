#pragma once
#include "sdkconfig.h"
#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>
#define CONFIG_TINYUSB_MTP_ENABLED 1
#define CONFIG_TINYUSB_MTP_MAX_STORAGES 1
#define CONFIG_TINYUSB_MTP_MAX_OBJECTS 1024
#define CFG_TUD_MTP 1
#define CONFIG_TINYUSB_DESC_MANUFACTURER_STRING "IMU Test"
#define CONFIG_TINYUSB_DESC_PRODUCT_STRING "IMU-Test"
#define TUD_EPBUF_DEF(name, size) uint8_t name[size] __attribute__((aligned(4)))
#define TUD_EPBUF_TYPE_DEF(type, name) type name __attribute__((aligned(4)))
#include "mtp_capabilities.h"
#ifdef __cplusplus
extern "C" {
#endif
esp_err_t imu_fat_info(const char *path, uint64_t *total, uint64_t *free_bytes);
void imu_mtp_lock(void);
void imu_mtp_unlock(void);
bool imu_mtp_allow_command(uint16_t op, bool cached_properties);
void imu_mtp_response_done(void);
void imu_mtp_command_finished(void);
void imu_mtp_trace(uint16_t op,int32_t result);
void imu_mtp_trace_detail(uint16_t kind,uint16_t code,uint32_t transaction,int32_t value);
#ifdef __cplusplus
}
#endif
#define esp_vfs_fat_info imu_fat_info
