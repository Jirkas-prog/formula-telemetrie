"""Local preview only. Production viewer works from a local HTML + FIMU file."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
import zipfile
ROOT=Path(__file__).resolve().parent
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  url=urlsplit(self.path);name=url.path.lstrip('/')
  if name=='qa':
   width=max(280,min(1600,int(parse_qs(url.query).get('width',['390'])[0])))
   data=f'<html><body style="margin:0;background:#31383c"><iframe src="/?demo" style="border:0;width:{width}px;height:100vh;display:block;margin:auto"></iframe></body></html>'.encode();typ='text/html'
  elif not name:
   data=(ROOT/'app/viewer.html').read_bytes();typ='text/html; charset=utf-8'
  elif name=='manifest.json' or name.startswith('derived/') or name.startswith('raw/'):
   try:
    with zipfile.ZipFile(ROOT/'output/Formule_IMU.fimu') as z:data=z.read(name)
    typ='application/json' if name.endswith('.json') else 'application/octet-stream'
   except KeyError:self.send_error(404);return
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
if __name__=='__main__':
 print('http://127.0.0.1:18766/?demo',flush=True);ThreadingHTTPServer(('127.0.0.1',18766),Handler).serve_forever()
