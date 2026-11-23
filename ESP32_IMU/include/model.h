#pragma once
#include <Arduino.h>

constexpr char AP_NAME[] = "IMU-Test";
#include "local_wifi.h"
constexpr char AP_PASS[] = IMU_AP_PASSWORD;
constexpr int SDA_PIN=8, SCL_PIN=9, MOSI_PIN=11, MISO_PIN=13, SCK_PIN=12, CS_PIN=10;
constexpr int HISTORY_SIZE=4096, QUEUE_SIZE=2048;
struct Config { uint16_t accRate=500, gyroRate=500, gyro=2000; uint8_t accel=16, magRate=100, filter=3, address=0x69; bool spi=false, autostart=true; };
struct Sample { uint64_t us; float v[9]; float temp; uint32_t seq, magAge, accAge, gyroAge; uint16_t clip; bool accNew, gyroNew, magNew, magValid, magOverflow; };
struct Bucket { uint64_t first,last; float lo[9],hi[9]; uint16_t clip; uint32_t count; };
enum class Mode { Idle, Recording, Paused, Error };
inline const char* modeName(Mode m) { return m==Mode::Recording?"recording":m==Mode::Paused?"paused":m==Mode::Error?"error":"idle"; }
inline bool safePath(const String& p) {
  if (!p.startsWith("/") || p.length()>180 || p.indexOf("..")>=0 || p.indexOf("//")>=0) return false;
  for (unsigned i=0;i<p.length();i++) if (uint8_t(p[i])<32 || String("\\:*?\"<>|").indexOf(p[i])>=0) return false;
  return !p.endsWith(".") && !p.endsWith(" ");
}
inline uint16_t clipping(const float* v, int accel, int gyro, bool overflow) {
  uint16_t mask=0;
  for (int i=0;i<9;i++) if (isfinite(v[i]) && fabsf(v[i])>=(i<3?accel:i<6?gyro:4912)*0.98f) mask|=1<<i;
  return mask | (overflow?0x1c0:0);
}
