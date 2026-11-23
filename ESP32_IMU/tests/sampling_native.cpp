#include "../include/sampling.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

int main(){
  const uint8_t bytes[]={0x80,0x01};
  assert(sensorBe16(bytes)==-32767&&sensorLe16(bytes)==384);
  for(unsigned hz:{50u,100u,200u,500u}){
    assert(supportedLogRate(hz));
    SampleDeadline rate(hz);uint32_t missed=0,count=0;uint64_t previous=0;
    // FIFO preserves every conversion despite a varying host wake-up interval.
    for(unsigned frame=1;frame<=1125*60;frame++){
      uint64_t us=1000000+uint64_t(frame)*1000000/1125;
      if(rate.due(us,missed))count++;
      assert(us>previous);previous=us;
    }
    assert(missed==0&&count==hz*60);
  }
  for(unsigned hz:{0u,501u,750u,1000u,1125u,1200u,1500u})assert(!supportedLogRate(hz));
  uint32_t missed=0;SampleDeadline rate(500);
  assert(rate.due(1000,missed));assert(!rate.due(2000,missed));
  assert(rate.due(9000,missed)&&missed==3); // A real gap stays visible.
  assert(fifoSampleTime(10000,3,7000)==7334);
  assert(fifoSampleTime(10000,3,8000)==8001); // Monotonic after host clock jitter.
  assert(fifoSampleTime(10,30,0)==1); // No unsigned underflow at startup.
  puts("PASS: FIFO timestamp bounds, byte order, independent rates and real-gap detection.");
}
