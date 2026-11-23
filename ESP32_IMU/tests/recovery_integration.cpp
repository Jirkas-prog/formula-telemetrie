// Run the production recovery transaction against files, with power cuts at its writes.
#include <atomic>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>
#include <stdexcept>
#include <cassert>
#include <cstdio>
#include "../include/log_integrity.h"
namespace fs=std::filesystem;
struct String:std::string {
  using std::string::string;String()=default;String(const std::string& s):std::string(s){}String(unsigned long n):std::string(std::to_string(n)){}
  bool isEmpty()const{return empty();}bool startsWith(const char* s)const{return rfind(s,0)==0;}bool endsWith(const char* s)const{return size()>=strlen(s)&&compare(size()-strlen(s),strlen(s),s)==0;}
};
int cut=-1,mutations=0;
bool fault(){return cut>=0&&mutations++==cut;}
void powerCut(){throw std::runtime_error("power cut");}
constexpr const char* FILE_READ="r";constexpr const char* FILE_WRITE="w";
struct File {
  std::shared_ptr<std::fstream> stream;fs::path path;bool writing=false;
  File()=default;File(fs::path p,bool write):path(p),writing(write){stream=std::make_shared<std::fstream>(p,write?(std::ios::binary|std::ios::out|std::ios::trunc):(std::ios::binary|std::ios::in));}
  explicit operator bool()const{return stream&&stream->is_open();}bool isDirectory()const{return fs::is_directory(path);}uint64_t size(){return fs::file_size(path);}
  bool available(){return stream&&stream->peek()!=EOF;}
  size_t read(uint8_t* dst,size_t n){stream->read((char*)dst,n);return stream->gcount();}
  size_t write(const uint8_t* data,size_t n){if(fault()){stream->write((const char*)data,n/2);stream->flush();powerCut();}stream->write((const char*)data,n);return *stream?n:0;}
  size_t print(const char* s){return write((const uint8_t*)s,strlen(s));}
  void flush(){stream->flush();if(fault())powerCut();}
  void close(){if(stream)stream->close();}
};
struct Card {
  fs::path root;
  fs::path local(const String& p){assert(p.size()&&p[0]=='/'&&p.find("..") == std::string::npos);return root/p.substr(1);}
  bool exists(const String& p){return fs::exists(local(p));}
  File open(const String& p,const char* mode){return File(local(p),mode==FILE_WRITE);}
  bool rename(const String& a,const String& b){if(exists(b))return false;fs::rename(local(a),local(b));if(fault())powerCut();return true;}
} SD_MMC;
struct Preferences {String marker;String getString(const char*,const char*){return marker;}bool remove(const char*){marker="";if(fault())powerCut();return true;}} prefs;
struct JsonDocument {struct Value {template<class T>Value& operator=(const T&){return *this;}};Value operator[](const char*){return {};}};
size_t serializeJson(JsonDocument&,File& f){return f.print("{\"recovery\":true}");}
bool sdOK=true;uint64_t sdTotal=1024ull*1024*1024,sdUsed=0;
void lock(){}void unlock(){}void refreshSpace(){}void vTaskDelay(int){}
bool safePath(const String& path){return path.startsWith("/")&&path.find("..") == std::string::npos;}
char csvBuffer[16384]; // Same shared workspace as the production SD writer.
#include "../src/log_recovery.h"

std::string row(int seq){auto text=std::to_string(seq*2000)+","+std::to_string(seq)+",1,2,3,4,5,6,7,8,9,25,1,1,0,0,0,16,2000,500,500,100,3,1,1,0,0";char end[12];snprintf(end,sizeof(end),",%08x\n",csvCrc(text.data(),text.size()));return text+end;}
std::string read(const fs::path& p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
void write(const fs::path& p,const std::string& text){std::ofstream f(p,std::ios::binary);f<<text;}
int main(){
  auto workspace=fs::current_path(),root=workspace/".cache"/"recovery-integration";
  assert(root.parent_path()==workspace/".cache");SD_MMC.root=root;
  const String path="/logs/boot_000042_run_001.csv";auto good=std::string(CSV_HEADER)+row(0)+row(1),broken=good+row(2).substr(0,21);
  // Interrupt every mutation of recovery, then boot again using the same NVS and card.
  for(int point=0;point<12;point++){
    fs::remove_all(root);fs::create_directories(root/"logs");write(SD_MMC.local(path),broken);prefs.marker=path;cut=point;mutations=0;
    try{recoverInterruptedLog();}catch(const std::runtime_error&){}
    cut=-1;assert(recoverInterruptedLog());
    assert(prefs.marker.empty());assert(read(SD_MMC.local(path))==good);
    assert(read(SD_MMC.local(path+".recovery-source"))==broken);
    assert(SD_MMC.exists(path+".recovery.json"));
  }
  // A partial header contains no committed rows; preserve it and create a valid empty CSV.
  fs::remove_all(root);fs::create_directories(root/"logs");write(SD_MMC.local(path),"time_us,se");prefs.marker=path;
  assert(recoverInterruptedLog());assert(read(SD_MMC.local(path))==CSV_HEADER);assert(read(SD_MMC.local(path+".recovery-source"))=="time_us,se");
  // A clean file after an unclean shutdown is validated without copying or changing it.
  fs::remove_all(root);fs::create_directories(root/"logs");write(SD_MMC.local(path),good);prefs.marker=path;
  assert(recoverInterruptedLog());assert(read(SD_MMC.local(path))==good);assert(!SD_MMC.exists(path+".recovery-source"));
  // Full card: keep the source and the pending NVS marker; recover once space is available.
  write(SD_MMC.local(path),broken);prefs.marker=path;sdUsed=sdTotal;
  assert(!recoverInterruptedLog());assert(prefs.marker==path);assert(read(SD_MMC.local(path+".recovery-source"))==broken);
  sdUsed=0;assert(recoverInterruptedLog());assert(read(SD_MMC.local(path))==good);
  // Reused scan/copy workspace must also preserve rows across many block boundaries.
  fs::remove_all(root);fs::create_directories(root/"logs");good=CSV_HEADER;
  for(int i=0;i<500;i++)good+=row(i);
  broken=good+row(500).substr(0,37);write(SD_MMC.local(path),broken);prefs.marker=path;
  assert(recoverInterruptedLog());assert(recoveredRows==500);
  assert(read(SD_MMC.local(path))==good);assert(read(SD_MMC.local(path+".recovery-source"))==broken);
  fs::remove_all(root);
  puts("PASS: production recovery transaction survives cuts during rename/copy/flush/report/NVS; preserves original; handles partial header, clean logs and full card.");
}
