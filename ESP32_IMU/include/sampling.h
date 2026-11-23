#pragma once
#include <stdint.h>

constexpr unsigned SENSOR_ODR=1125;
inline bool supportedLogRate(unsigned hz){return hz==50||hz==100||hz==200||hz==500;}
// Select actual FIFO samples at the independently requested logging rates.
struct SampleDeadline {
  uint64_t origin=0,next=0;
  uint32_t hz;
  bool started=false;
  explicit SampleDeadline(uint32_t rate):hz(rate){}
  bool due(uint64_t us, uint32_t& skipped) {
    if(!started){origin=us;started=true;}
    const uint64_t scaled=(us-origin)*hz;
    if(scaled<next)return false;
    skipped+=(scaled-next)/1000000;
    next=(scaled/1000000+1)*1000000;
    return true;
  }
};
constexpr unsigned FIFO_FRAME_BYTES=14; // accel XYZ, gyro XYZ, temperature
inline uint64_t fifoSampleTime(uint64_t observed, unsigned behind, uint64_t previous) {
  uint64_t age=uint64_t(behind)*1000000/SENSOR_ODR;
  uint64_t estimated=observed>age?observed-age:1;
  return estimated>previous?estimated:previous+1;
}
inline int16_t sensorBe16(const uint8_t* p){return int16_t((uint16_t(p[0])<<8)|p[1]);}
inline int16_t sensorLe16(const uint8_t* p){return int16_t((uint16_t(p[1])<<8)|p[0]);}
