"""Small regression checks; no serial port or physical board is touched."""
from pathlib import Path
import importlib.util
import json
import re
import struct
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
subprocess.run(['node','--check',str(ROOT/'web/app.js')],check=True,cwd=ROOT)
subprocess.run(['node','--check',str(ROOT/'web/network.js')],check=True,cwd=ROOT)
subprocess.run(['node','--check',str(ROOT/'web/files.js')],check=True,cwd=ROOT)
subprocess.run(['node','--check',str(ROOT/'web/pdf-viewer.mjs')],check=True,cwd=ROOT)
subprocess.run(['node','--check',str(ROOT/'web/report.mjs')],check=True,cwd=ROOT)
subprocess.run(['node',str(ROOT/'tests/parser.cjs')],check=True,cwd=ROOT)
subprocess.run(['node',str(ROOT/'tests/usb-ui.cjs')],check=True,cwd=ROOT)
subprocess.run(['node',str(ROOT/'tests/upload-client.cjs')],check=True,cwd=ROOT)
subprocess.run(['node',str(ROOT/'tests/network-client.cjs')],check=True,cwd=ROOT)
subprocess.run(['node',str(ROOT/'tests/download-client.cjs')],check=True,cwd=ROOT)
subprocess.run(['node',str(ROOT/'tests/report.cjs')],check=True,cwd=ROOT)
subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/test_recovery.ps1')],check=True,cwd=ROOT)

spec=importlib.util.spec_from_file_location('flash',ROOT/'scripts/flash.py')
flash=importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash)
events=[]
with patch.object(sys,'argv',['flash.py','upload','--port','COM999']), patch.object(flash.subprocess,'run',side_effect=lambda *a,**kw:events.append(a[0])), patch.object(flash,'backup',side_effect=RuntimeError('backup failed')):
    try: flash.main()
    except RuntimeError: pass
    else: raise AssertionError('Failed backup must block upload')
assert len(events)==1 and '--target' not in events[0],events
events=[]
with patch.object(sys,'argv',['flash.py','upload','--port','COM999']), patch.object(flash.subprocess,'run',side_effect=lambda *a,**kw:events.append(a[0])), patch.object(flash,'backup',side_effect=lambda p:events.append('verified-backup')):
    flash.main()
assert events[1]=='verified-backup' and '--target' in events[2]
print('PASS: USB upload blocked on failed backup; verified backup precedes upload.')

partitions=[]
for line in (ROOT/'partitions.csv').read_text().splitlines():
    if line and not line.startswith('#'):
        name,kind,sub,offset,size,*_=line.split(',')
        partitions.append((name,int(offset,16),int(size,16)))
for a,b in zip(partitions,partitions[1:]): assert a[1]+a[2]<=b[1]
assert partitions[-1][1]+partitions[-1][2]==16*1024*1024
assert dict((n,z) for n,o,z in partitions)['app0']==dict((n,z) for n,o,z in partitions)['app1']==0x700000
firmware=ROOT/'.build/imu/firmware.bin'
if firmware.exists():
    b=firmware.read_bytes()
    assert b[0]==0xe9 and len(b)<0x700000
    assert struct.unpack_from('<H',b,12)[0]==9, 'Image must target ESP32-S3'
print('PASS: 16 MiB partition bounds, two 7 MiB OTA slots, firmware image target.')
objdump=ROOT/'.tools/platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-objdump.exe'
elf=ROOT/'.build/imu/firmware.elf'
if objdump.exists() and elf.exists():
    assembly=subprocess.check_output([str(objdump),'-d','-C',str(elf)],text=True,encoding='utf-8',errors='replace')
    frames={}
    for function in ('loggerTask','recoverInterruptedLog','scanLog'):
        match=re.search(r'<'+function+r'\([^\n]*\)>:\s*\n[^\n]*\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)',assembly)
        assert match, 'Missing stack frame for '+function
        frames[function]=int(match[1],0)
    # An 8 KiB task must leave room for FAT/VFS, String/JSON and RTOS call frames.
    assert sum(frames.values())<=3072, ('Recovery call chain exceeds stack budget',frames)
    print('PASS: compiled recovery stack frames fit budget:',frames)
print('Hardware timing, SD throughput, pinout and LCD require a physical board test.')
