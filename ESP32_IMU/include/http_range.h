#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// One byte range, including open-ended and suffix ranges. Overflow is rejected.
inline bool httpRange(const char* text, uint64_t size, uint64_t& first, uint64_t& last) {
  first=0;last=size?size-1:0;
  if(!text||!*text)return true;
  if(strncmp(text,"bytes=",6)||!size)return false;
  const char* p=text+6;
  auto number=[&](uint64_t& n){n=0;const char* start=p;while(*p>='0'&&*p<='9'){if(n>(UINT64_MAX-(*p-'0'))/10)return false;n=n*10+(*p++-'0');}return p!=start;};
  if(*p=='-'){++p;uint64_t n;if(!number(n)||*p||!n)return false;first=n>=size?0:size-n;return true;}
  if(!number(first)||*p++!='-'||first>=size)return false;
  if(*p&&(!number(last)||*p||last<first))return false;
  if(last>=size)last=size-1;
  return true;
}
