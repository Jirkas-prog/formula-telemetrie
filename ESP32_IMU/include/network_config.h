#pragma once
#include <stdint.h>
#include <string.h>
inline bool validHostname(const char* s){
  size_t n=strlen(s);if(!n||n>31||s[0]=='-'||s[n-1]=='-')return false;
  for(size_t i=0;i<n;i++)if(!((s[i]>='a'&&s[i]<='z')||(s[i]>='0'&&s[i]<='9')||s[i]=='-'))return false;
  return true;
}
inline bool parseIPv4(const char* s,uint32_t& ip){
  ip=0;for(int part=0;part<4;part++){
    unsigned n=0,digits=0;while(*s>='0'&&*s<='9'){n=n*10+(*s++-'0');if(++digits>3||n>255)return false;}
    if(!digits)return false;ip=(ip<<8)|n;
    if(part<3){if(*s++!='.')return false;}else if(*s)return false;
  }return true;
}
inline bool validSubnet(uint32_t mask){uint32_t host=~mask;return mask&&host>=3&&(host&(host+1))==0;}
inline bool hostAddress(uint32_t ip,uint32_t mask){unsigned first=ip>>24;return first>0&&first<224&&first!=127&&(ip&~mask)!=0&&(ip&~mask)!=~mask;}
