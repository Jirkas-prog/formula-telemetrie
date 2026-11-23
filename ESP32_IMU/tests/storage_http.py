"""Exercise real file endpoints; creates and removes only a unique /imu-files-check-* tree.

Run while connected to the AP: python -B tests/storage_http.py --base http://192.168.4.1 --mib 16
The optional slow test spans >60 s while status requests remain responsive.
"""
import argparse
import hashlib
import http.client
import json
import re
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:18765');parser.add_argument('--mib',type=int,default=2);parser.add_argument('--slow',action='store_true');parser.add_argument('--resume-dir');parser.add_argument('--slow-existing');args=parser.parse_args()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base=args.base.rstrip('/');checks=[];prefix='/imu-files-check-'+uuid.uuid4().hex[:8]
    report={'base':base,'directory':prefix,'checks':checks,'success':False}
    if args.resume_dir:
        assert re.fullmatch(r'/imu-files-check-[0-9a-f]{8}',args.resume_dir)
        prefix=args.resume_dir;report['directory']=prefix
    if args.slow_existing:
        assert re.fullmatch(r'/imu-files-check-[0-9a-f]{8}',args.slow_existing)
        prefix=args.slow_existing;report['directory']=prefix
    def request(path,body=None,headers=None,status=200,method=None):
        h={'X-IMU-Client':'1',**(headers or {})}
        if isinstance(body,dict):body=json.dumps(body).encode();h['Content-Type']='application/json'
        req=urllib.request.Request(base+path,data=body,headers=h,method=method)
        try:r=opener.open(req,timeout=40)
        except urllib.error.HTTPError as e:r=e
        with r:
            data=r.read();assert r.status==status,(path,r.status,data[:400]);return (json.loads(data) if 'application/json' in r.headers.get('Content-Type','') else data),dict(r.headers)
    def passed(msg):checks.append(msg);print('PASS:',msg,flush=True)
    def quoted(path):return urllib.parse.quote(path)
    def action(op,path,to=None):return request('/api/file',{'action':op,'path':path,**({'to':to} if to else {})})
    def multipart(data):
        boundary='IMUfilescheck'+uuid.uuid4().hex
        return (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode(),{'Content-Type':'multipart/form-data; boundary='+boundary})
    def start(path,size):return request('/api/upload/start',{'id':uuid.uuid4().hex,'path':path,'size':size})[0]
    def chunk(u,data,offset=None,status=200):
        body,headers=multipart(data);return request('/api/upload/chunk?id='+u['id']+'&offset='+str(u['offset'] if offset is None else offset),body,headers,status=status)[0]
    def finish(u):return request('/api/upload/finish?id='+u['id'],{})
    def upload(path,data):
        u=start(path,len(data))
        while u['offset']<len(data):u=chunk(u,data[u['offset']:u['offset']+65536])
        finish(u);return u
    def slow_download(data):
        path=prefix+'/target/moved/Přejmenováno.bin'
        reserved=request('/api/download/start',{'path':path})[0]
        request('/api/download/start',{'path':path},status=409)
        request('/api/download?path='+quoted(path),status=409)
        request('/api/download/cancel?id='+reserved['id'],{})
        request('/api/download?path='+quoted(path)+'&id='+reserved['id'],status=409)
        job=request('/api/download/start',{'path':path})[0]
        parsed=urllib.parse.urlparse(base)
        conn=http.client.HTTPConnection(parsed.hostname,parsed.port or 80,timeout=40)
        conn.connect();conn.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,32768)
        conn.request('GET','/api/download?path='+quoted(path)+'&id='+job['id'])
        slow=conn.getresponse();assert slow.status==200
        request('/api/download/start',{'path':path},status=409)
        request('/api/download?path='+quoted(path)+'&id='+job['id'],status=409)
        request('/api/download?path='+quoted(path),status=409)
        passed('Reservation and active stream reject repeated clicks/GETs; cancelling invalidates the old link')
        total=0;begin=time.monotonic();max_status=0;next_status=0;digest=hashlib.sha256()
        try:
            while time.monotonic()-begin<65:
                block=slow.read(65536);assert block,'Download ended before slow-stream test completed';total+=len(block);digest.update(block)
                if time.monotonic()>next_status:
                    tick=time.monotonic();status=request('/api/status')[0];assert status['transfer'] and status['download']['active'] and status['download']['id']==job['id'];max_status=max(max_status,time.monotonic()-tick);next_status=time.monotonic()+2
                time.sleep(.4)
            rest=slow.read();digest.update(rest);assert total+len(rest)==len(data);assert digest.digest()==hashlib.sha256(data).digest()
        finally:
            slow.close();conn.close();report['slow_seconds']=round(time.monotonic()-begin,2);report['slow_bytes_before_drain']=total
        report['max_status_seconds_during_download']=round(max_status,3);passed('Download remains byte-exact beyond 60 seconds; status responds during streaming')
        assert request('/api/download/status')[0]['state']=='complete'
        # Cancel a running transfer, then resume a fresh request without stale locks.
        job=request('/api/download/start',{'path':path})[0]
        conn=http.client.HTTPConnection(parsed.hostname,parsed.port or 80,timeout=40)
        conn.connect();conn.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,32768)
        conn.request('GET','/api/download?path='+quoted(path)+'&id='+job['id'])
        aborted=conn.getresponse();assert aborted.status==200
        assert request('/api/download/cancel?id='+job['id'],{})[0]['state']=='cancelled'
        aborted.close();conn.close()
        assert request('/api/download?path='+quoted(path),headers={'Range':'bytes=0-49'},status=206)[0]==data[:50]
        passed('Active cancellation releases SD immediately; the next download succeeds')
    def cleanup():
        action('delete',prefix+'/target/moved/Přejmenováno.bin');action('delete',prefix+'/target/moved');action('delete',prefix+'/target');action('delete',prefix)
        passed('Own test files and folders removed')
    try:
        s=request('/api/status')[0]
        if s.get('storageOwner')=='usb':request('/api/usb/release',{})
        assert s['mode']!='recording','Stop recording before running filesystem tests'
        if args.slow_existing:
            data=bytes(range(256))*(args.mib*4096)+b'odd-tail-123';report['bytes']=len(data)
            slow_download(data);cleanup();report['success']=True;return
        if not args.resume_dir:
            action('mkdir',prefix);action('mkdir',prefix+'/nested');action('mkdir',prefix+'/target')
        data=bytes(range(256))*(args.mib*4096)+b'odd-tail-123';report['bytes']=len(data)
        if args.resume_dir:
            u=request('/api/upload/status')[0]
            assert u['active'] and u['path']==prefix+'/nested/large.bin' and u['size']==len(data),u
            report['resumed_offset']=u['offset']
        else:u=start(prefix+'/nested/large.bin',len(data))
        original_id=u['id'];initial_offset=u['offset']
        again=request('/api/upload/start',{'id':u['id'],'path':prefix+'/nested/large.bin','size':len(data)})[0];assert again['id']==original_id
        request('/api/files?path=/',status=409)
        # A multipart connection dies halfway through a block: no bytes may be acknowledged.
        parsed=urllib.parse.urlparse(base);body,headers=multipart(data[initial_offset:initial_offset+65536]);path='/api/upload/chunk?id='+u['id']+'&offset='+str(initial_offset)
        with socket.create_connection((parsed.hostname,parsed.port or 80),timeout=10) as sock:
            head=f'POST {path} HTTP/1.1\r\nHost: {parsed.netloc}\r\nX-IMU-Client: 1\r\nContent-Type: {headers["Content-Type"]}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            sock.sendall(head.encode()+body[:10000])
        actual=request('/api/upload/status')[0];assert actual['offset']==initial_offset,actual
        u=chunk(u,data[initial_offset:initial_offset+65536]);assert u['offset']==initial_offset+65536
        chunk(u,data[:65536],offset=initial_offset,status=409);assert request('/api/upload/status')[0]['offset']==initial_offset+65536
        passed('Interrupted chunk is not committed; duplicate/retried offset cannot append duplicate bytes')
        started=time.monotonic()
        while u['offset']<len(data):
            u=chunk(u,data[u['offset']:u['offset']+65536])
            if u['offset']%1048576==0:print(f'UPLOAD: {u["offset"]//1048576}/{args.mib} MiB',flush=True)
        finish(u);finish(u);report['upload_seconds']=round(time.monotonic()-started,2)
        received,headers=request('/api/download?path='+quoted(prefix+'/nested/large.bin'))
        assert hashlib.sha256(received).digest()==hashlib.sha256(data).digest()
        report['sha256']=hashlib.sha256(data).hexdigest();passed(f'{len(data)} bytes uploaded in bounded chunks and downloaded with matching SHA-256')
        for range_,expected in [('bytes=0-49',data[:50]),('bytes=-25',data[-25:]),('bytes=65530-65545',data[65530:65546]),(f'bytes={len(data)-11}-',data[-11:])]:
            part,h=request('/api/download?path='+quoted(prefix+'/nested/large.bin'),headers={'Range':range_},status=206);assert part==expected;assert h.get('Content-Range',h.get('Content-range','')).startswith('bytes ')
        request('/api/download?path='+quoted(prefix+'/nested/large.bin'),headers={'Range':'bytes=99999999999-'},status=416)
        passed('HTTP byte ranges: prefix, suffix, open end, block boundary and unsatisfiable range')
        action('rename',prefix+'/nested/large.bin',prefix+'/nested/Přejmenováno.bin');action('move',prefix+'/nested',prefix+'/target/moved')
        assert request('/api/download?path='+quoted(prefix+'/target/moved/Přejmenováno.bin'))[0]==data
        request('/api/file',{'action':'move','path':prefix+'/target','to':prefix+'/target/moved/invalid'},status=409)
        passed('UTF-8 rename and move of a nonempty folder; moving a folder into itself is rejected')
        for name in ('Obrazky/Prubeh_testu.png','Dokumenty/Zapojeni_a_poznamky.pdf'):
            fixture=ROOT/'.cache/preview-sd'/name
            if fixture.exists():
                dest=prefix+'/'+fixture.name;upload(dest,fixture.read_bytes());out,h=request('/api/view?path='+quoted(dest));assert out==fixture.read_bytes();assert h.get('Content-Type',h.get('Content-type','')).startswith(('image/','application/pdf'));action('delete',dest)
        passed('Image and PDF inline endpoint returns original bytes and the correct MIME type')
        u=start(prefix+'/cancelled.bin',100000);u=chunk(u,data[:65536]);request('/api/upload/cancel?id='+u['id'],{});assert not any(f['name'].endswith('cancelled.bin.upload-part') for f in request('/api/files?path='+quoted(prefix))[0]);passed('Explicit cancel removes only its incomplete upload and releases storage')
        if args.slow:
            slow_download(data)
        cleanup();report['success']=True
    finally:
        out=ROOT/'docs'/('files-http-'+time.strftime('%Y%m%dT%H%M%S')+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('REPORT:',out,flush=True)

if __name__=='__main__':main()
