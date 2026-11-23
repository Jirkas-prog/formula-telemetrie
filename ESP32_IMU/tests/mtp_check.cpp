// Hardware integration test using Windows Portable Devices, not Explorer automation.
#include <windows.h>
#include <PortableDeviceApi.h>
#include <PortableDevice.h>
#include <wrl/client.h>
#include <cstdio>
#include <string>
#include <vector>
#include <stdexcept>
using Microsoft::WRL::ComPtr;
void check(HRESULT hr,const char* step){if(FAILED(hr)){char s[160];sprintf_s(s,"%s: 0x%08lx",step,hr);throw std::runtime_error(s);}}
ComPtr<IPortableDeviceValues> values(){ComPtr<IPortableDeviceValues> v;check(CoCreateInstance(CLSID_PortableDeviceValues,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&v)),"Create values");return v;}
std::wstring name(IPortableDeviceProperties* p,const wchar_t* id){ComPtr<IPortableDeviceValues> v;check(p->GetValues(id,nullptr,&v),"Get object properties");PWSTR n=nullptr;HRESULT named=v->GetStringValue(WPD_OBJECT_ORIGINAL_FILE_NAME,&n);if(FAILED(named))named=v->GetStringValue(WPD_OBJECT_NAME,&n);check(named,"Get object name");std::wstring s(n);CoTaskMemFree(n);return s;}
std::vector<std::wstring> children(IPortableDeviceContent* c,const wchar_t* parent){ComPtr<IEnumPortableDeviceObjectIDs> e;check(c->EnumObjects(0,parent,nullptr,&e),"Enumerate objects");std::vector<std::wstring> ids;PWSTR id=nullptr;DWORD count;while(e->Next(1,&id,&count)==S_OK&&count){ids.emplace_back(id);CoTaskMemFree(id);}return ids;}
std::wstring find(IPortableDeviceContent* c,IPortableDeviceProperties* p,const wchar_t* parent,const wchar_t* wanted){for(unsigned attempt=0;attempt<20;attempt++){for(auto& id:children(c,parent))if(name(p,id.c_str())==wanted)return id;Sleep(250);}wprintf(L"Missing: %ls\n",wanted);throw std::runtime_error("Object not found after waiting for MTP change event");}
std::vector<unsigned char> read(IPortableDeviceResources* r,const wchar_t* id){ComPtr<IStream> stream;DWORD size=65536;check(r->GetStream(id,WPD_RESOURCE_DEFAULT,STGM_READ,&size,&stream),"Open USB read stream");std::vector<unsigned char> data;unsigned char buf[65536];ULONG n;do{check(stream->Read(buf,sizeof(buf),&n),"USB read");data.insert(data.end(),buf,buf+n);}while(n);return data;}
ComPtr<IPortableDevicePropVariantCollection> objectList(const wchar_t* id){ComPtr<IPortableDevicePropVariantCollection> list;check(CoCreateInstance(CLSID_PortableDevicePropVariantCollection,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&list)),"Create object list");PROPVARIANT v{};v.vt=VT_LPWSTR;v.pwszVal=const_cast<wchar_t*>(id);check(list->Add(&v),"Add object ID");return list;}
void resultOk(IPortableDevicePropVariantCollection* results){DWORD count=0;check(results->GetCount(&count),"Result count");if(count!=1)throw std::runtime_error("Expected one operation result");PROPVARIANT v{};check(results->GetAt(0,&v),"Operation result");HRESULT hr=v.vt==VT_ERROR?v.scode:E_UNEXPECTED;PropVariantClear(&v);check(hr,"Per-object result");}
int wmain(int argc,wchar_t** argv){
 if(argc<3||argc>5||wcsncmp(argv[1],L"USB_overeni_",11)!=0){puts("Usage: mtp-check USB_overeni_<id> <local-output> [expected-bytes] [extended|read-only]");return 2;}
 const size_t expected=argc>=4?_wcstoui64(argv[3],nullptr,10):256*1024;
 if(expected<65536||expected>64*1024*1024)return 2;
 setvbuf(stdout,nullptr,_IONBF,0);
 CoInitializeEx(nullptr,COINIT_MULTITHREADED);
 try{
  ComPtr<IPortableDeviceManager> manager;check(CoCreateInstance(CLSID_PortableDeviceManager,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&manager)),"Create manager");
  DWORD count=0;check(manager->GetDevices(nullptr,&count),"Device count");std::vector<PWSTR> ids(count);check(manager->GetDevices(ids.data(),&count),"Devices");std::wstring deviceId;
  for(auto id:ids){wchar_t friendly[256];DWORD len=256;if(SUCCEEDED(manager->GetDeviceFriendlyName(id,friendly,&len))&&wcscmp(friendly,L"IMU-Test")==0){if(!deviceId.empty())throw std::runtime_error("Ambiguous IMU devices");deviceId=id;}CoTaskMemFree(id);}if(deviceId.empty())throw std::runtime_error("IMU-Test not attached");
  ComPtr<IPortableDevice> device;check(CoCreateInstance(CLSID_PortableDeviceFTM,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&device)),"Create device");auto info=values();info->SetStringValue(WPD_CLIENT_NAME,L"IMU project USB test");info->SetUnsignedIntegerValue(WPD_CLIENT_DESIRED_ACCESS,GENERIC_READ|GENERIC_WRITE);check(device->Open(deviceId.c_str(),info.Get()),"Open IMU device");
  ComPtr<IPortableDeviceContent> content;check(device->Content(&content),"Content");ComPtr<IPortableDeviceProperties> props;check(content->Properties(&props),"Properties");ComPtr<IPortableDeviceResources> resources;check(content->Transfer(&resources),"Transfer");
  auto storage=children(content.Get(),WPD_DEVICE_OBJECT_ID);if(storage.size()!=1)throw std::runtime_error("Expected exactly one SD storage");
  auto root=children(content.Get(),storage[0].c_str());printf("Root entries: %zu\n",root.size());fflush(stdout);
  auto folder=find(content.Get(),props.Get(),storage[0].c_str(),argv[1]);auto file=find(content.Get(),props.Get(),folder.c_str(),L"overeni.bin");auto data=read(resources.Get(),file.c_str());
  if(data.size()!=expected)throw std::runtime_error("Wrong USB payload size");for(size_t i=0;i<data.size();i++)if(data[i]!=(i%256))throw std::runtime_error("USB data corruption");printf("PASS: USB read matches all %zu bytes\n",data.size());fflush(stdout);
  // Write a new test file only inside the freshly created test folder.
  if(argc<5||wcscmp(argv[4],L"read-only")!=0){
  auto created=values();created->SetStringValue(WPD_OBJECT_PARENT_ID,folder.c_str());created->SetStringValue(WPD_OBJECT_NAME,L"usb-return.bin");created->SetStringValue(WPD_OBJECT_ORIGINAL_FILE_NAME,L"usb-return.bin");created->SetGuidValue(WPD_OBJECT_CONTENT_TYPE,WPD_CONTENT_TYPE_GENERIC_FILE);created->SetGuidValue(WPD_OBJECT_FORMAT,WPD_OBJECT_FORMAT_UNSPECIFIED);created->SetUnsignedLargeIntegerValue(WPD_OBJECT_SIZE,data.size());
  ComPtr<IStream> out;DWORD block=65536;check(content->CreateObjectWithPropertiesAndData(created.Get(),&out,&block,nullptr),"Create USB test file");
  for(size_t pos=0;pos<data.size();){ULONG wrote=0,n=ULONG((data.size()-pos)>65536?65536:data.size()-pos);check(out->Write(data.data()+pos,n,&wrote),"Write USB test file");if(!wrote)throw std::runtime_error("Zero USB write");pos+=wrote;}check(out->Commit(STGC_DEFAULT),"Commit USB test file");out.Reset();
  auto newId=find(content.Get(),props.Get(),folder.c_str(),L"usb-return.bin");auto rename=values();rename->SetStringValue(WPD_OBJECT_ORIGINAL_FILE_NAME,L"usb-renamed.bin");ComPtr<IPortableDeviceValues> results;check(props->SetValues(newId.c_str(),rename.Get(),&results),"Rename USB test file");HRESULT renameResult;check(results->GetErrorValue(WPD_OBJECT_ORIGINAL_FILE_NAME,&renameResult),"Rename result");check(renameResult,"Rename property");
  if(read(resources.Get(),newId.c_str())!=data)throw std::runtime_error("USB write/read roundtrip differs");puts("PASS: USB write, rename and readback match");fflush(stdout);
  if(argc==5){
   auto folderProps=values();folderProps->SetStringValue(WPD_OBJECT_PARENT_ID,folder.c_str());folderProps->SetStringValue(WPD_OBJECT_NAME,L"USB_podslozka");folderProps->SetStringValue(WPD_OBJECT_ORIGINAL_FILE_NAME,L"USB_podslozka");folderProps->SetGuidValue(WPD_OBJECT_CONTENT_TYPE,WPD_CONTENT_TYPE_FOLDER);folderProps->SetGuidValue(WPD_OBJECT_FORMAT,WPD_OBJECT_FORMAT_PROPERTIES_ONLY);
   PWSTR childId=nullptr;check(content->CreateObjectWithPropertiesOnly(folderProps.Get(),&childId),"Create USB subfolder");std::wstring child(childId);CoTaskMemFree(childId);
   for(auto& destination:std::vector<std::wstring>{child,folder}){auto idsToMove=objectList(newId.c_str());ComPtr<IPortableDevicePropVariantCollection> moved;check(content->Move(idsToMove.Get(),destination.c_str(),&moved),"Move USB file");resultOk(moved.Get());newId=find(content.Get(),props.Get(),destination.c_str(),L"usb-renamed.bin");}
   if(read(resources.Get(),newId.c_str())!=data)throw std::runtime_error("Data changed after USB moves");puts("PASS: USB creates subfolder and moves file there and back without changing bytes");
   auto idsToDelete=objectList(child.c_str());ComPtr<IPortableDevicePropVariantCollection> deleted;check(content->Delete(PORTABLE_DEVICE_DELETE_NO_RECURSION,idsToDelete.Get(),&deleted),"Delete USB subfolder");resultOk(deleted.Get());for(auto& id:children(content.Get(),folder.c_str()))if(name(props.Get(),id.c_str())==L"USB_podslozka")throw std::runtime_error("Deleted folder remains");puts("PASS: USB deletion and refreshed directory listing");
   puts("CHECK: close USB read after 64 KiB");ComPtr<IStream> interrupted;DWORD chunkSize=65536;check(resources->GetStream(file.c_str(),WPD_RESOURCE_DEFAULT,STGM_READ,&chunkSize,&interrupted),"Open interrupted read");unsigned char first[65536];ULONG got=0;check(interrupted->Read(first,sizeof(first),&got),"Partial USB read");if(got!=sizeof(first))throw std::runtime_error("Short partial read");interrupted.Reset();
   if(read(resources.Get(),file.c_str())!=data)throw std::runtime_error("Read after interruption differs");puts("PASS: Interrupted USB read followed by complete byte-exact read");
   for(unsigned trial=0;trial<12;trial++){
    const size_t partialSizes[]={1,63,64,511,512,4096,65535,65536,65537,131072,262144,1048576};
    size_t partial=partialSizes[trial];
    created->SetStringValue(WPD_OBJECT_NAME,L"usb-cancelled.bin");created->SetStringValue(WPD_OBJECT_ORIGINAL_FILE_NAME,L"usb-cancelled.bin");created->SetUnsignedLargeIntegerValue(WPD_OBJECT_SIZE,16*1024*1024);ComPtr<IStream> cancelled;check(content->CreateObjectWithPropertiesAndData(created.Get(),&cancelled,&chunkSize,nullptr),"Create cancelled USB file");
    for(size_t pos=0;pos<partial;){ULONG wrote=0,n=ULONG((partial-pos)>65536?65536:partial-pos);check(cancelled->Write(data.data(),n,&wrote),"Partial USB write");if(wrote!=n)throw std::runtime_error("Short partial write");pos+=wrote;}
    printf("CHECK: cancel %u/12 after %zu bytes; immediately read and write in the same session\n",trial+1,partial);check(cancelled->Revert(),"Cancel USB write");cancelled.Reset();
    // No pause, retry, session reopen, or device reset may hide a stuck transaction.
    if(trial%2==0&&read(resources.Get(),newId.c_str())!=data)throw std::runtime_error("Read after cancelled write differs");
    created->SetStringValue(WPD_OBJECT_NAME,L"usb-after-cancel.bin");created->SetStringValue(WPD_OBJECT_ORIGINAL_FILE_NAME,L"usb-after-cancel.bin");created->SetUnsignedLargeIntegerValue(WPD_OBJECT_SIZE,65536);ComPtr<IStream> next;check(content->CreateObjectWithPropertiesAndData(created.Get(),&next,&chunkSize,nullptr),"Create immediately after cancel");ULONG wrote=0;check(next->Write(data.data(),65536,&wrote),"Write immediately after cancel");if(wrote!=65536)throw std::runtime_error("Short post-cancel write");check(next->Commit(STGC_DEFAULT),"Commit immediately after cancel");next.Reset();
    auto nextId=find(content.Get(),props.Get(),folder.c_str(),L"usb-after-cancel.bin");if(read(resources.Get(),nextId.c_str())!=std::vector<unsigned char>(data.begin(),data.begin()+65536))throw std::runtime_error("Post-cancel roundtrip differs");auto removeNext=objectList(nextId.c_str());ComPtr<IPortableDevicePropVariantCollection> removed;check(content->Delete(PORTABLE_DEVICE_DELETE_NO_RECURSION,removeNext.Get(),&removed),"Delete post-cancel fixture");resultOk(removed.Get());
    if(trial%2!=0&&read(resources.Get(),newId.c_str())!=data)throw std::runtime_error("Read after post-cancel write differs");
    for(auto& id:children(content.Get(),folder.c_str()))if(name(props.Get(),id.c_str())==L"usb-cancelled.bin")throw std::runtime_error("Cancelled USB upload remains visible");
    printf("PASS: cancellation %u/12, immediate read + write + readback, no partial file\n",trial+1);
   }
  }
  }
  device->Close();
  HANDLE dest=CreateFileW(argv[2],GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(dest==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot create local evidence");DWORD written=0;bool ok=WriteFile(dest,data.data(),DWORD(data.size()),&written,nullptr)&&written==data.size();CloseHandle(dest);if(!ok)throw std::runtime_error("Local evidence write failed");return 0;
 }catch(const std::exception& e){fprintf(stderr,"FAIL: %s\n",e.what());return 1;}
}
