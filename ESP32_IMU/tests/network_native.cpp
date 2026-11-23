#include "../include/network_config.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
int main(){
  for(auto s:{"imu-test","a","formula-01"})assert(validHostname(s));
  for(auto s:{"","-imu","imu-","imu.local","IMU","a b","a/b","abcdefghijklmnopqrstuvwxyz1234567"})assert(!validHostname(s));
  uint32_t ip;
  assert(parseIPv4("192.168.4.1",ip)&&ip==0xc0a80401);
  assert(parseIPv4("0.0.0.0",ip)&&ip==0);
  for(auto s:{"","192.168.1","192.0.2.1.1","256.0.0.1","-1.2.3.4"," 1.2.3.4","1.2.3.4x","1..2.3","0000.1.2.3"})assert(!parseIPv4(s,ip));
  for(unsigned bits=1;bits<=30;bits++)assert(validSubnet(0xffffffffu<<(32-bits)));
  for(uint32_t mask:{0u,0xffffffffu,0xfffffffeu,0xffff00ffu,0x7fffffffu})assert(!validSubnet(mask));
  assert(hostAddress(0xc0a80401,0xffffff00));
  for(uint32_t address:{0xc0a80400u,0xc0a804ffu,0x7f000001u,0xe0000001u,0x00000001u})assert(!hostAddress(address,0xffffff00));
  puts("PASS: hostname, IPv4 octets, contiguous subnet masks, unicast host addresses.");
}
