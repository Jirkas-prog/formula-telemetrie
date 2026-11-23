#include "../include/log_integrity.h"
#include <string>
#include <stdio.h>
#include <assert.h>

std::string row(int seq){
  std::string text=std::to_string(seq*2000)+","+std::to_string(seq)+",1,2,3,4,5,6,7,8,9,25,1,1,0,0,0,16,2000,500,500,100,3,1,1,0,0";
  char end[12];snprintf(end,sizeof(end),",%08x\n",csvCrc(text.data(),text.size()));return text+end;
}
CsvIntegrity scan(const std::string& data,size_t chunk=7){CsvIntegrity s;for(size_t i=0;i<data.size();i+=chunk)s.feed((const uint8_t*)data.data()+i,std::min(chunk,data.size()-i));s.finish();return s;}
int main(){
  assert(csvCrc("123456789",9)==0xcbf43926);
  std::string header=CSV_HEADER,a=row(0),b=row(1),c=row(2),all=header+a+b+c;
  auto complete=scan(all);assert(!complete.bad&&complete.rows==3&&complete.goodBytes==all.size());
  // Every possible power cut, including the header and exact row boundaries.
  for(size_t cut=0;cut<=all.size();cut++){
    auto s=scan(all.substr(0,cut));uint64_t good=0,rows=0;
    for(size_t i=0;i<cut;i++)if(all[i]=='\n'){good=i+1;rows++;}
    assert(s.goodBytes==good);assert(s.rows==(rows?rows-1:0));
    assert(s.bad==(cut<header.size()||cut!=good));
  }
  for(size_t i=header.size()+a.size();i<header.size()+a.size()+b.size();i++){
    auto broken=all;broken[i]^=1;auto s=scan(broken);assert(s.bad&&s.goodBytes==header.size()+a.size()&&s.rows==1);
  }
  auto duplicate=scan(header+a+a);assert(duplicate.bad&&duplicate.rows==1);
  auto reversed=scan(header+b+a);assert(reversed.bad&&reversed.rows==1);
  auto garbage=scan(header+a+std::string(1000,'x'));assert(garbage.bad&&garbage.rows==1);
  auto old=scan("time_us,seq\n0,0\n");assert(old.bad&&!old.headerOK&&old.goodBytes==0);
  puts("PASS: production CRC validator: every byte-boundary power cut, bit corruption, duplicates, reversed sequence, oversized row, and unknown header.");
}
