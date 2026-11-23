"""Flash is never written before a complete verified backup of this exact chip."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BACKUPS=ROOT/'backups'
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.stderr.reconfigure(encoding='utf-8',errors='replace')

def run(port,*args,after='no_reset'):
    cmd=[sys.executable,'-B','-m','esptool','--chip','esp32s3','--port',port,'--baud','460800','--after',after,*map(str,args)]
    result=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    print(re.sub(r'\d+ \(\d+ %\)\x08+','',result.stdout),flush=True)
    if result.returncode: raise RuntimeError('esptool selhal; flash nebyla tímto skriptem přepsána.')
    return result.stdout

def identity(port):
    output=run(port,'flash_id')
    mac=re.search(r'MAC:\s*([0-9a-fA-F:]{17})',output)
    size=re.search(r'Detected flash size:\s*(\d+)MB',output)
    if not mac or not size: raise RuntimeError('Nelze ověřit MAC a velikost flash.')
    if int(size[1])!=16: raise RuntimeError('Tento projekt je určen pro 16 MB flash. Identita desky vyžaduje kontrolu.')
    return mac[1].lower(),int(size[1])*1024*1024

def backup(port):
    mac,size=identity(port)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target=BACKUPS/f'original_{mac.replace(":", "")}_{stamp}.bin'
    if target.exists(): raise RuntimeError('Soubor zálohy již existuje.')
    run(port,'read_flash','0',hex(size),target)
    if target.stat().st_size!=size: raise RuntimeError('Záloha nemá očekávanou velikost.')
    run(port,'verify_flash','0',target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    meta=dict(mac=mac,size=size,sha256=digest,verified=True,created_utc=stamp,file=target.name)
    target.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(f'OVĚŘENÁ ZÁLOHA: {target}\nSHA256: {digest}',flush=True)
    return target,meta

def verify_backup(port,file,require_manifest=True):
    file=Path(file).resolve()
    mac,size=identity(port)
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    if file.stat().st_size!=size: raise RuntimeError('Nesprávná velikost zálohy.')
    if require_manifest:
        meta=json.loads(file.with_suffix('.json').read_text(encoding='utf-8'))
        if not meta.get('verified') or meta['mac']!=mac or meta['sha256']!=digest:
            raise RuntimeError('Nesouhlasí MAC / SHA-256 ověřené zálohy.')
    run(port,'verify_flash','0',file)
    meta=dict(mac=mac,size=size,sha256=digest,verified=True,verified_utc=datetime.now(timezone.utc).isoformat(),file=file.name)
    file.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(f'OVĚŘENÁ ZÁLOHA: {file}\nSHA256: {digest}',flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['backup','verify-backup','upload','restore'])
    parser.add_argument('--port',required=True)
    parser.add_argument('--backup')
    args=parser.parse_args()
    if not re.fullmatch(r'COM\d+',args.port,re.I): raise RuntimeError('Zadej sériový port desky, například COM11.')
    BACKUPS.mkdir(exist_ok=True)
    if args.action=='backup': backup(args.port)
    elif args.action=='verify-backup':
        if not args.backup: raise RuntimeError('Chybí --backup.')
        verify_backup(args.port,args.backup,require_manifest=False)
    elif args.action=='upload':
        subprocess.run([sys.executable,'-B','-m','platformio','run'],cwd=ROOT,check=True)
        if args.backup: verify_backup(args.port,args.backup)
        else: backup(args.port)
        # PlatformIO uses the compiled partition layout and includes boot_app0.
        subprocess.run([sys.executable,'-B','-m','platformio','run','--target','upload','--upload-port',args.port],cwd=ROOT,check=True)
    else:
        if not args.backup: raise RuntimeError('Obnova vyžaduje --backup s cestou k .bin.')
        file=Path(args.backup).resolve()
        meta=json.loads(file.with_suffix('.json').read_text(encoding='utf-8'))
        mac,size=identity(args.port)
        if not meta.get('verified') or meta['mac']!=mac or meta['size']!=size or file.stat().st_size!=size or hashlib.sha256(file.read_bytes()).hexdigest()!=meta['sha256']:
            raise RuntimeError('Záloha není ověřená, je poškozená nebo patří jiné desce.')
        backup(args.port) # Preserve the current firmware before the requested restore.
        run(args.port,'write_flash','0',file)
        run(args.port,'verify_flash','0',file,after='hard_reset')

if __name__=='__main__':
    try: main()
    except (RuntimeError,subprocess.CalledProcessError,OSError,KeyError) as exc:
        print(f'CHYBA: {exc}',file=sys.stderr)
        sys.exit(1)
