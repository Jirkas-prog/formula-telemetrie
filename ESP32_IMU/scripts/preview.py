"""Local-only UI simulator. Never communicates with the board or real SD card."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import math
import time
import mimetypes
import preview_storage

ROOT = Path(__file__).resolve().parents[1]
CONFIG = dict(displayRotation=0, spi=False, accRate=500, gyroRate=500, accel=16, gyro=2000, magRate=100, filter=3, address=105, autostart=True)
NETWORK = dict(hostname='imu-test',apIp='192.168.4.1',dhcp=True,ip='',gateway='',subnet='255.255.255.0',dns='')
NETWORKS = [dict(ssid='Ukázková Wi-Fi',password='demo-only')]
def wifi_status():
    return dict(connected=bool(NETWORKS),ssid=NETWORKS[0]['ssid'] if NETWORKS else '',ip='192.0.2.87' if NETWORKS else '',hostname=NETWORK['hostname'],url='http://'+NETWORK['hostname']+'.local/',state='connected' if NETWORKS else 'hotspot',rssi=-48,apIp=NETWORK['apIp'])
def wifi_config():
    return dict(settings=NETWORK,status=wifi_status(),networks=[dict(ssid=n['ssid'],hasPassword=bool(n['password'])) for n in NETWORKS])
MODE = 'idle' 
USB = False
START = time.monotonic() - 84

def values(t):
    return [3.8*math.sin(t*.8), 1.8*math.sin(t*.41), 1+.3*math.cos(t*2), 150*math.sin(t), 65*math.sin(t*.5), 240*math.cos(t*.6), 25+4*math.sin(t*.2), -14+2*math.cos(t*.3), 41+math.sin(t*.5)]

def csv_demo():
    lines = ['time_us,seq,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,mx_uT,my_uT,mz_uT,temp_C,mag_new,mag_valid,mag_age_us,mag_overflow,clip_mask,accel_range_g,gyro_range_dps,log_rate_hz,mag_rate_hz,dlpf']
    for i in range(5000):
        t=i/500
        v=values(t)
        clip=0
        if 2<t<2.3:
            v[0]=15.9
            clip=1
        lines.append(','.join(map(str,[i*2000,i,*v,32.6,int(i%5==0),1,(i%5)*2000,0,clip,16,2000,500,100,3])))
    return ('\n'.join(lines)+'\n').encode()

class Handler(BaseHTTPRequestHandler):
    def send(self, data, status=200, mime='application/json'):
        if not isinstance(data, bytes):
            data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        try: self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass

    def do_GET(self):
        path=urlparse(self.path).path
        t=time.monotonic()-START
        if preview_storage.handle(self,b'',USB or MODE=='recording'): return
        if path=='/api/status':
            v=values(t)
            return self.send(dict(demo=True,wifi=wifi_status(),download=preview_storage.download_state(),transfer=bool(preview_storage.UPLOAD) or preview_storage.download_state()["active"],uploadActive=bool(preview_storage.UPLOAD),storageOwner='usb' if USB else 'logger' if MODE=='recording' else 'web',usbConnected=True,usbBusy=False,mode=MODE,error='',imu=True,sd=True,memory=True,file='/logs/boot_000042_run_001.csv',rows=int(t*500),dropped=0,missed=0,ioErrors=0,magOverruns=0,hz=499.8,elapsed=t,sampleAge=3,clip=0,magAge=2000,magValid=True,temp=32.6,values=v,min=[-4,-2,.6,-180,-90,-300,20,-18,38],max=[4,2,1.4,180,90,300,30,-10,45],queue=14,queueCapacity=2048,sdTotal=31900000000,sdUsed=1240000000,ssid='IMU-Test',ip='192.168.4.1',rate=CONFIG['accRate'],accRate=CONFIG['accRate'],gyroRate=CONFIG['gyroRate'],magRate=CONFIG['magRate'],axisHz=[499.8,499.8,99.6],boot=42,clients=1))
        if path=='/api/wifi': return self.send(wifi_config())
        if path=='/api/config': return self.send(CONFIG)
        if path=='/api/history':
            result=[]
            for i in range(int(t*10)):
                tt=i/10
                v=values(tt)
                clip=0
                if 24<tt<25: v[0]=15.9; clip=1
                result.append([tt,tt+.098,*[x for a in v for x in (a-.08,a+.08)],clip,50])
            return self.send(dict(file='/logs/boot_000042_run_001.csv',bucketUs=100000,buckets=result))
        if path in ('/mobile','/qa'):
            query=parse_qs(urlparse(self.path).query)
            width=max(320,min(1600,int(query.get('width',['390'])[0])))
            panel=query.get('panel',['dashboard'])[0]
            if panel not in ('dashboard','charts','files','settings'): panel='dashboard'
            scale=min(1,500/width)
            html=f'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI QA {width}px</title><body style="margin:0;background:#dce3ea"><div style="width:{width*scale}px;margin:10px auto"><iframe title="UI {width} px" src="/#{panel}" style="display:block;width:{width}px;height:{max(700,800/scale)}px;border:0;transform:scale({scale});transform-origin:top left"></iframe></div>'
            return self.send(html.encode(),mime='text/html')
        file=ROOT/'web'/('index.html' if path=='/' else path.lstrip('/'))
        if not file.resolve().is_relative_to((ROOT/'web').resolve()) or not file.is_file(): return self.send({'error':'Not found'},404)
        self.send(file.read_bytes(),mime='text/javascript' if file.suffix=='.mjs' else mimetypes.guess_type(str(file))[0] or 'application/octet-stream')

    def do_POST(self):
        global MODE,START,USB,NETWORKS
        raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
        if len(raw)!=int(self.headers.get('Content-Length',0)): return self.send({'error':'Interrupted request'},400)
        if self.headers.get('X-IMU-Client')!='1': return self.send({'error':'Forbidden'},403)
        if preview_storage.handle(self,raw,USB or MODE=='recording'): return
        d=json.loads(raw)
        if self.path in ('/api/usb/release','/api/demo/usb'):
            USB = self.path=='/api/demo/usb' and bool(d.get('active'))
            if USB: MODE='idle'
            self.path='/api/status'
            return self.do_GET()
        if self.path=='/api/control':
            action=d.get('action')
            if action=='start': MODE='recording'; START=time.monotonic()
            elif action=='pause': MODE='paused'
            elif action=='resume': MODE='recording'
            elif action=='stop': MODE='idle'
            self.path='/api/status'
            return self.do_GET()
        if self.path=='/api/wifi':
            if preview_storage.download_state()['active'] or preview_storage.UPLOAD: return self.send({'error':'Nejdříve dokonči přenos.'},409)
            old={n['ssid']:n['password'] for n in NETWORKS}
            NETWORKS=[dict(ssid=n['ssid'],password=n.get('password',old.get(n['ssid'],''))) for n in d['networks']]
            NETWORK.update(d['settings'])
            return self.send(wifi_config())
        if self.path=='/api/display':
            rotation=d.get('displayRotation')
            if type(rotation) is not int or rotation not in (0,90,180,270): return self.send({'error':'Neplatná orientace.'},400)
            CONFIG['displayRotation']=rotation
            return self.send({'displayRotation':rotation})
        if self.path=='/api/config':
            if MODE in ('recording','paused'): return self.send({'error':'Nejdříve ukonči záznam.'},409)
            CONFIG.update(d)
            return self.send({'reboot':True})
        return self.send({'error':'Simulátor neprovádí změny souborů.'},400)

    def log_message(self,*args): pass

if __name__=='__main__':
    preview_storage.fixtures(csv_demo())
    print('SIMULATOR ONLY: http://127.0.0.1:18765 / mobile QA: /mobile',flush=True)
    ThreadingHTTPServer(('127.0.0.1',18765),Handler).serve_forever()
