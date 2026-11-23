"""Disposable local SD fixture. Every path is confined to this project's .cache."""
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from email.parser import BytesParser
from email.policy import default
import json
import mimetypes
import struct
import zlib
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1] / '.cache' / 'preview-sd'
UPLOAD = None
COMPLETED = ''
DOWNLOAD = None
DOWNLOAD_LOCK = threading.RLock()

def download_state():
    with DOWNLOAD_LOCK:
        if DOWNLOAD and DOWNLOAD['state']=='pending' and time.monotonic()-DOWNLOAD['activity']>120: DOWNLOAD['state']='error'
        return {**{k:v for k,v in (DOWNLOAD or {}).items() if k!='activity'},'active':bool(DOWNLOAD and DOWNLOAD['state'] in ('pending','active'))}

def new_download(path,size):
    global DOWNLOAD
    DOWNLOAD=dict(id=uuid.uuid4().hex,path=path,size=size,sent=0,state='pending',activity=time.monotonic())

def local(path):
    p=(ROOT / path.lstrip('/')).resolve()
    if not p.is_relative_to(ROOT.resolve()): raise ValueError('Neplatná cesta.')
    return p

def fixtures(csv):
    if ROOT.exists(): return
    for folder in ('logs/2026-10-21', 'Dokumenty', 'Obrazky', 'Archiv'):
        local(folder).mkdir(parents=True,exist_ok=True)
    local('logs/2026-10-21/Jizda_01.csv').write_bytes(csv)
    local('logs/2026-10-21/Jizda_02_dlouhy_nazev_mereni_predni_napravy.csv').write_bytes(csv)
    local('logs/README.txt').write_text('Demo uloziste. Zadna skutecna mereni.\n',encoding='utf-8')
    width,height=640,360
    pixels=b''.join(b'\0'+bytes(c for x in range(width) for c in ((40,123,212) if abs(y-(180+int(75*__import__('math').sin(x/48))))<3 else (19,118,83) if abs(y-(180+int(42*__import__('math').sin(x/34))))<3 else (235,240,245) if x%64==0 or y%45==0 else (250,252,254))) for y in range(height))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
    local('Obrazky/Prubeh_testu.png').write_bytes(png)
    stream=b'BT /F1 24 Tf 60 760 Td (IMU TEST - ukazkovy dokument) Tj 0 -42 Td /F1 12 Tf (Nahled PDF funguje primo z SD karty.) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    pdf=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(pdf));pdf+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(pdf);pdf+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{p:010d} 00000 n \n'.encode() for p in offsets[1:])+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    local('Dokumenty/Zapojeni_a_poznamky.pdf').write_bytes(pdf)

def upload_state():
    return dict(active=bool(UPLOAD),completedId=COMPLETED,chunkSize=65536,**(UPLOAD or dict(id='',path='',size=0,offset=0)))

def handle(h,raw,blocked):
    global UPLOAD,COMPLETED
    parsed=urlparse(h.path);route=parsed.path;q=parse_qs(parsed.query)
    if route not in ('/api/files','/api/file','/api/download','/api/view') and not route.startswith(('/api/upload/','/api/download/')):return False
    def send(data,status=200):h.send(data,status);return True
    if route=='/api/upload/status':return send(upload_state())
    if route=='/api/download/status':return send(download_state())
    if route=='/api/download/cancel':
        with DOWNLOAD_LOCK:
            if not DOWNLOAD or q.get('id',[''])[0]!=DOWNLOAD['id']:return send({'error':'Přenos už není aktuální.'},409)
            if download_state()['active']:DOWNLOAD['state']='cancelled'
            return send(download_state())
    if blocked:return send({'error':'SD kartu používá USB nebo zapisovač.'},409)
    try:
        if route=='/api/download/start':
            with DOWNLOAD_LOCK:
                if download_state()['active']:return send({'error':'Stahování už probíhá.'},409)
                if UPLOAD:return send({'error':'Probíhá nahrávání.'},409)
                path=json.loads(raw)['path'];p=local(path)
                if not p.is_file():return send({'error':'Soubor neexistuje.'},404)
                new_download(path,p.stat().st_size());return send(download_state())
        if route.startswith('/api/upload/'):
            if route=='/api/upload/start':
                d=json.loads(raw);dest=local(d['path']);temp=local(d['path']+'.upload-part')
                if UPLOAD and UPLOAD['id']==d['id']:return send(upload_state())
                if UPLOAD:return send({'error':'Jiný přenos je aktivní.'},409)
                if dest.exists() or temp.exists():return send({'error':'Název už existuje. Nic se nepřepisuje.'},409)
                temp.write_bytes(b'');UPLOAD=dict(id=d['id'],path=d['path'],size=d['size'],offset=0)
                return send(upload_state())
            token=q.get('id',[''])[0]
            if route=='/api/upload/finish' and token==COMPLETED:return send({'done':True})
            if not UPLOAD or token!=UPLOAD['id']:return send({'error':'Přenos není aktivní.'},409)
            temp=local(UPLOAD['path']+'.upload-part')
            if route=='/api/upload/cancel':temp.unlink(missing_ok=True);UPLOAD=None;return send({})
            if route=='/api/upload/chunk':
                offset=int(q['offset'][0]);message=BytesParser(policy=default).parsebytes(('Content-Type: '+h.headers['Content-Type']+'\r\n\r\n').encode()+raw);data=next(message.iter_parts()).get_payload(decode=True)
                if offset!=UPLOAD['offset'] or not 0<len(data)<=65536 or offset+len(data)>UPLOAD['size']:return send({'error':'Neplatný blok nebo pozice.'},409)
                with temp.open('r+b') as f:f.seek(offset);f.write(data)
                UPLOAD['offset']+=len(data);return send(upload_state())
            if route=='/api/upload/finish':
                if UPLOAD['offset']!=UPLOAD['size']:return send({'error':'Chybí bloky.'},409)
                dest=local(UPLOAD['path'])
                if dest.exists():return send({'error':'Cíl už existuje.'},409)
                temp.rename(dest);COMPLETED=token;UPLOAD=None;return send({'done':True})
        if UPLOAD:return send({'error':'Probíhá nahrávání souboru.'},409)
        if route=='/api/files':
            p=local(q.get('path',['/'])[0]);return send([dict(name=f.name,dir=f.is_dir(),size=f.stat().st_size if f.is_file() else 0,modified=int(f.stat().st_mtime)) for f in p.iterdir()])
        if route=='/api/file':
            d=json.loads(raw);p=local(d['path'])
            if p==ROOT.resolve() or d['path']=='/logs':return send({'error':'Chráněná cesta.'},400)
            if d['action']=='mkdir':p.mkdir()
            elif d['action']=='delete':p.rmdir() if p.is_dir() else p.unlink()
            elif d['action'] in ('rename','move'):
                dest=local(d['to'])
                if dest.exists() or dest.is_relative_to(p):return send({'error':'Cíl je obsazený nebo uvnitř přesouvané složky.'},409)
                p.rename(dest)
            return send({})
        if route in ('/api/download','/api/view'):
            p=local(q['path'][0]);data=p.read_bytes();total=len(data);mime=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
            if route=='/api/view' and not (mime.startswith('image/') or mime=='application/pdf'):return send({'error':'Tento typ nemá náhled.'},415)
            status=200;range_=h.headers.get('Range');first,last=0,total-1
            if range_:
                start,end=range_.removeprefix('bytes=').split('-');first=int(start) if start else max(0,total-int(end));last=min(total-1,int(end)) if start and end else total-1
                if first>=total or first>last:return send({'error':'Rozsah je mimo soubor.'},416)
                data=data[first:last+1];status=206
            job=None
            if route=='/api/download':
                with DOWNLOAD_LOCK:
                    token=q.get('id',[''])[0]
                    if token and (not DOWNLOAD or token!=DOWNLOAD['id'] or DOWNLOAD['path']!=q['path'][0] or DOWNLOAD['state']=='cancelled'):return send({'error':'Neplatný přenos.'},409)
                    if download_state()['active'] and not (DOWNLOAD['state']=='pending' and token==DOWNLOAD['id']):return send({'error':'Stahování už probíhá.'},409)
                    if not token:new_download(q['path'][0],total)
                    job=DOWNLOAD;job['state']='active';job['sent']=first
            h.send_response(status);h.send_header('Content-Type',mime);h.send_header('Content-Length',str(len(data)));h.send_header('Accept-Ranges','bytes');h.send_header('Cache-Control','no-store');h.send_header('Content-Disposition',('inline' if route=='/api/view' else 'attachment')+"; filename*=UTF-8''"+quote(p.name))
            if status==206:h.send_header('Content-Range',f'bytes {first}-{last}/{total}')
            h.end_headers()
            try:
                for i in range(0,len(data),65536):
                    if job and job['state']=='cancelled':h.close_connection=True;return True
                    block=data[i:i+65536];h.wfile.write(block)
                    if job:job['sent']+=len(block)
                if job:job['state']='complete'
            except OSError:
                if job:job['state']='error'
            return True
    except (OSError,ValueError,KeyError,StopIteration) as e:return send({'error':str(e)},400)
    return send({'error':'Neznámá operace.'},404)
