#pragma once
#include <ESPmDNS.h>
#include "network_config.h"

constexpr unsigned MAX_WIFI_NETWORKS=6;
struct SavedWifi { String ssid,password; } wifiNetworks[MAX_WIFI_NETWORKS];
unsigned wifiCount=0,wifiIndex=0;
uint32_t wifiAttemptAt=0,wifiRetryAt=0,wifiApplyAt=0;
bool wifiAttempting=false,wifiWasConnected=false;
bool mdnsStarted=false;
uint32_t mdnsStaAddress=0;
String wifiError;
struct NetworkConfig { String hostname="imu-test",apIp="192.168.4.1",ip="",gateway="",subnet="255.255.255.0",dns="";bool dhcp=true; } net;
void networkJson(JsonVariant d,const NetworkConfig& n){d["hostname"]=n.hostname;d["apIp"]=n.apIp;d["dhcp"]=n.dhcp;d["ip"]=n.ip;d["gateway"]=n.gateway;d["subnet"]=n.subnet;d["dns"]=n.dns;}
void readNetwork(JsonVariant d,NetworkConfig& n){n.hostname=d["hostname"]|"imu-test";n.apIp=d["apIp"]|"192.168.4.1";n.dhcp=d["dhcp"]|true;n.ip=d["ip"]|"";n.gateway=d["gateway"]|"";n.subnet=d["subnet"]|"255.255.255.0";n.dns=d["dns"]|"";}
bool validNetwork(const NetworkConfig& n){
  uint32_t ap,ip,mask,gateway,dns;
  if(!validHostname(n.hostname.c_str())||!parseIPv4(n.apIp.c_str(),ap)||!hostAddress(ap,0xffffff00))return false;
  if(n.dhcp)return true;
  if(!parseIPv4(n.ip.c_str(),ip)||!parseIPv4(n.subnet.c_str(),mask)||!validSubnet(mask)||!hostAddress(ip,mask)||!parseIPv4(n.gateway.c_str(),gateway)||!hostAddress(gateway,mask)||(ip&mask)!=(gateway&mask)||ip==gateway)return false;
  if(!parseIPv4(n.dns.c_str(),dns)||(dns>>24)==0||(dns>>24)>=224||(dns>>24)==127)return false;
  // The two interfaces must not share overlapping subnets.
  return (ap&mask)!=(ip&mask)&&(ap&0xffffff00)!=(ip&0xffffff00);
}
void restartMdns(){
  MDNS.end();mdnsStarted=MDNS.begin(net.hostname.c_str());
  if(mdnsStarted)mdnsStarted=MDNS.addService("http","tcp",80);
}
void applyNetwork(){
  wifiError="";
  WiFi.setHostname(net.hostname.c_str());
  // Arduino 2.x applies the DHCP hostname when the STA interface starts.
  WiFi.mode(WIFI_AP);WiFi.mode(WIFI_AP_STA);
  IPAddress ap,ip,gateway,mask,dnsAddress;ap.fromString(net.apIp);if(!WiFi.softAPConfig(ap,ap,IPAddress(255,255,255,0)))wifiError="Nelze nastavit IP hotspotu.";
  bool configured;
  if(net.dhcp)configured=WiFi.config(IPAddress(0U),IPAddress(0U),IPAddress(0U));
  else {ip.fromString(net.ip);gateway.fromString(net.gateway);mask.fromString(net.subnet);dnsAddress.fromString(net.dns);configured=WiFi.config(ip,gateway,mask,dnsAddress);}
  if(!configured)wifiError+=" Nelze nastavit IP Wi-Fi.";
  dns.stop();dns.start(53,"*",WiFi.softAPIP());mdnsStaAddress=0;restartMdns();
}

void wifiStatus(JsonVariant d){
  bool connected=WiFi.status()==WL_CONNECTED;
  d["connected"]=connected;d["ssid"]=connected?WiFi.SSID():wifiAttempting&&wifiIndex<wifiCount?wifiNetworks[wifiIndex].ssid:"";
  d["ip"]=connected?WiFi.localIP().toString():"";d["hostname"]=net.hostname;d["url"]="http://"+net.hostname+".local/";
  d["state"]=connected?"connected":wifiAttempting?"connecting":wifiCount?"waiting":"hotspot";
  d["rssi"]=connected?WiFi.RSSI():0;d["apIp"]=WiFi.softAPIP().toString();d["mdnsStarted"]=mdnsStarted;d["error"]=wifiError+(mdnsStarted?"":" Alias .local není dostupný.");
}
void wifiConfigRoute(){
  JsonDocument d;networkJson(d["settings"].to<JsonObject>(),net);wifiStatus(d["status"].to<JsonObject>());auto a=d["networks"].to<JsonArray>();
  for(unsigned i=0;i<wifiCount;i++){auto n=a.add<JsonObject>();n["ssid"]=wifiNetworks[i].ssid;n["hasPassword"]=wifiNetworks[i].password.length()>0;}
  jsonReply(d);
}
void saveWifi(){
  if(!mutableRequest())return;
  if(transfer||hasDownloads()||otaActive){problem(409,"Nejdříve dokonči přenos souborů. Přepnutí Wi-Fi by ho přerušilo.");return;}
  JsonDocument d;if(deserializeJson(d,server.arg("plain"))||!d["networks"].is<JsonArray>()||d["networks"].size()>MAX_WIFI_NETWORKS){problem(400,"Lze uložit nejvýše šest sítí.");return;}
  NetworkConfig nextNet=net;
  if(d["settings"].is<JsonObject>()){if(!d["settings"]["dhcp"].is<bool>()){problem(400,"Neplatná volba DHCP.");return;}readNetwork(d["settings"],nextNet);}
  if(!validNetwork(nextNet)){problem(400,"Neplatný alias nebo IP konfigurace. Alias: malá písmena, čísla a pomlčky; IP hotspotu a pevná IP musí být v různých podsítích.");return;}
  SavedWifi next[MAX_WIFI_NETWORKS];unsigned count=0;
  for(JsonVariant n:d["networks"].as<JsonArray>()){
    if(!n["ssid"].is<String>()||(n["password"].isNull()==false&&!n["password"].is<String>())){problem(400,"Neplatný název sítě nebo heslo.");return;}
    auto& target=next[count];target.ssid=n["ssid"].as<String>();
    if(!target.ssid.length()||target.ssid.length()>32){problem(400,"Název sítě musí mít 1 až 32 bajtů.");return;}
    for(unsigned j=0;j<count;j++)if(next[j].ssid==target.ssid){problem(400,"Síť je v seznamu dvakrát.");return;}
    if(n["password"].is<String>())target.password=n["password"].as<String>();
    else for(unsigned j=0;j<wifiCount;j++)if(wifiNetworks[j].ssid==target.ssid)target.password=wifiNetworks[j].password;
    size_t len=target.password.length();bool hex=len==64;for(unsigned j=0;hex&&j<len;j++)hex=isxdigit(target.password[j]);
    if(len&&((len<8||len>63)&&!hex)){problem(400,"Heslo musí mít 8 až 63 znaků, nebo 64 hexadecimálních znaků. Prázdné heslo je pro otevřenou síť.");return;}
    ++count;
  }
  JsonDocument saved;networkJson(saved["settings"].to<JsonObject>(),nextNet);auto a=saved["networks"].to<JsonArray>();for(unsigned i=0;i<count;i++){auto n=a.add<JsonObject>();n["ssid"]=next[i].ssid;n["password"]=next[i].password;}
  String text;serializeJson(saved,text);
  if(prefs.putString("networkConfig",text)!=text.length()){problem(500,"Uložení Wi-Fi selhalo.");return;}
  for(unsigned i=0;i<MAX_WIFI_NETWORKS;i++)wifiNetworks[i]=next[i];wifiCount=count;net=nextNet;
  wifiApplyAt=millis()+700;wifiConfigRoute();
}
void wifiTick();
void wifiBegin(){
  JsonDocument d;if(!deserializeJson(d,prefs.getString("networkConfig","{}"))){
    NetworkConfig loaded;readNetwork(d["settings"],loaded);if(validNetwork(loaded))net=loaded;
    for(JsonVariant n:d["networks"].as<JsonArray>()){
      if(wifiCount>=MAX_WIFI_NETWORKS)break;
      String ssid=n["ssid"]|"";if(!ssid.length()||ssid.length()>32)continue;
      wifiNetworks[wifiCount].ssid=ssid;wifiNetworks[wifiCount++].password=n["password"]|"";
    }
  }
  WiFi.persistent(false);WiFi.setHostname(net.hostname.c_str());WiFi.mode(WIFI_AP_STA);WiFi.setAutoReconnect(false);WiFi.setSleep(false);
  WiFi.softAP(AP_NAME,AP_PASS,6,false,4);applyNetwork();
  // Prepare the first station association before starting the sampling tasks.
  wifiTick();
}
void wifiTick(){
  uint32_t now=millis();
  if(wifiApplyAt){if(int32_t(now-wifiApplyAt)<0)return;wifiApplyAt=0;WiFi.disconnect(false,false);applyNetwork();wifiIndex=0;wifiAttempting=wifiWasConnected=false;wifiRetryAt=now+500;return;}
  if(WiFi.status()==WL_CONNECTED){
    const uint32_t address=uint32_t(WiFi.localIP());
    // Rejoin/announce on the live STA interface, after DHCP rather than only
    // during AP setup. Also refresh when a connected station receives a new IP.
    if(address&&(!wifiWasConnected||address!=mdnsStaAddress)){restartMdns();mdnsStaAddress=address;}
    wifiWasConnected=true;wifiAttempting=false;return;
  }
  if(wifiWasConnected){wifiWasConnected=false;wifiIndex=0;wifiRetryAt=now;}
  if(!wifiCount)return;
  if(wifiAttempting){
    if(now-wifiAttemptAt<15000)return;
    WiFi.disconnect(false,false);wifiAttempting=false;wifiIndex++;
    if(wifiIndex>=wifiCount){wifiIndex=0;wifiRetryAt=now+15000;}else wifiRetryAt=now+500;
    return;
  }
  if(int32_t(now-wifiRetryAt)<0)return;
  WiFi.setMinSecurity(wifiNetworks[wifiIndex].password.isEmpty()?WIFI_AUTH_OPEN:WIFI_AUTH_WPA2_PSK);
  WiFi.begin(wifiNetworks[wifiIndex].ssid.c_str(),wifiNetworks[wifiIndex].password.c_str());wifiAttemptAt=now;wifiAttempting=true;
}
