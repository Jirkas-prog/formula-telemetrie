#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

constexpr char CSV_HEADER[]="time_us,seq,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,mx_uT,my_uT,mz_uT,temp_C,mag_new,mag_valid,mag_age_us,mag_overflow,clip_mask,accel_range_g,gyro_range_dps,accel_rate_hz,gyro_rate_hz,mag_rate_hz,dlpf,accel_new,gyro_new,accel_age_us,gyro_age_us,crc32\n";
inline uint32_t csvCrc(const char* data,size_t size){
  uint32_t crc=0xffffffff;
  for(size_t i=0;i<size;i++){crc^=(uint8_t)data[i];for(int bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&uint32_t(-int32_t(crc&1)));}
  return crc^0xffffffff;
}
// Stream validation uses bounded RAM, also when the file is several GiB long.
struct CsvIntegrity {
  char line[512];size_t used=0;uint64_t goodBytes=0,rows=0,lastTime=0,lastSeq=0;
  bool bad=false,headerOK=false;
  bool number(const char*& p,uint64_t& value){
    value=0;if(*p<'0'||*p>'9')return false;
    while(*p>='0'&&*p<='9'){unsigned digit=*p++-'0';if(value>(UINT64_MAX-digit)/10)return false;value=value*10+digit;}
    return *p++==',';
  }
  bool rowOK(){
    char* end=strrchr(line,',');if(!end||strlen(end+1)!=8)return false;
    uint32_t expected=0;for(char* p=end+1;*p;p++){int n=*p>='0'&&*p<='9'?*p-'0':*p>='a'&&*p<='f'?*p-'a'+10:*p>='A'&&*p<='F'?*p-'A'+10:-1;if(n<0)return false;expected=(expected<<4)|n;}
    if(csvCrc(line,end-line)!=expected)return false;
    int commas=0;for(char* p=line;*p;p++)commas+=*p==',';if(commas!=27)return false;
    const char* p=line;uint64_t time,seq;if(!number(p,time)||!number(p,seq)||(rows&&(time<lastTime||seq<=lastSeq)))return false;
    lastTime=time;lastSeq=seq;return true;
  }
  void feed(const uint8_t* bytes,size_t size){
    for(size_t i=0;i<size&&!bad;i++){
      char c=bytes[i];if(c!='\n'){if(used>=sizeof(line)-1||c=='\0'){bad=true;break;}line[used++]=c;continue;}
      line[used]=0;
      if(!headerOK){if(used!=strlen(CSV_HEADER)-1||memcmp(line,CSV_HEADER,used)){bad=true;break;}headerOK=true;}
      else {if(!rowOK()){bad=true;break;}rows++;}
      goodBytes+=used+1;used=0;
    }
  }
  void finish(){if(used||!headerOK)bad=true;}
};
