"""Embed the offline UI in firmware flash; no SD or CDN needed."""
from pathlib import Path
import gzip

try:
    Import('env')
    root = Path(env.subst('$PROJECT_DIR'))
except NameError:
    root = Path(__file__).resolve().parents[1]
items = []
for name, mime in [('index.html', 'text/html; charset=utf-8'), ('app.css', 'text/css'), ('app.js', 'text/javascript'), ('files.js', 'text/javascript')]:
    data = gzip.compress((root / 'web' / name).read_bytes(), mtime=0)
    symbol = name.replace('.', '_')
    items.append(f'const uint8_t {symbol}[] PROGMEM = {{' + ','.join(map(str, data)) + '};\n')
extra=[]
for i,path in enumerate([root/'web/network.js',root/'web/pdf-viewer.mjs',root/'web/report.mjs', *sorted((root/'web/pdfjs').rglob('*')), *sorted((root/'web/vendor').rglob('*'))]):
    if not path.is_file() or not (path.name.startswith('LICENSE') or path.suffix in ('.js','.mjs','.wasm','.bcmap','.pfb','.ttf','.woff','.woff2')):continue
    data=gzip.compress(path.read_bytes(),mtime=0)
    symbol=f'extra_asset_{i}'
    items.append(f'const uint8_t {symbol}[] PROGMEM = {{'+','.join(map(str,data))+'};\n')
    url='/'+path.relative_to(root/'web').as_posix()
    mime='text/javascript' if path.suffix in ('.js','.mjs') else 'application/wasm' if path.suffix=='.wasm' else 'application/octet-stream'
    extra.append(f'{{"{url}","{mime}",{symbol},sizeof({symbol})}}')
items.append('struct WebAsset {const char* path;const char* mime;const uint8_t* data;size_t size;};\nconst WebAsset extraAssets[]={'+','.join(extra)+'};\n')
content = '#pragma once\n#include <Arduino.h>\n' + ''.join(items)
dest = root / 'include' / 'web_assets.h'
if not dest.exists() or dest.read_text() != content:
    dest.write_text(content)
