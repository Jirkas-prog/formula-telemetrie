"""Bounded Windows AP check; temporary Wi-Fi profile, always restore prior network.

Usage: python -B scripts/hardware_check.py --interface GUID --restore-profile NAME [--ota]
Only writes its report inside this project. No persistent Wi-Fi profile is created.
"""
from xml.sax.saxutils import escape
import getpass
import argparse
import csv
import ctypes as c
from ctypes import wintypes as w
import gzip
import hashlib
import io
import os
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://192.168.4.1'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, body=None, content_type='application/json', expected=200, timeout=15):
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    headers = {'X-IMU-Client': '1', 'Content-Type': content_type}
    req = urllib.request.Request(BASE + path, data=body, headers=headers)
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        assert response.status == expected, (path, response.status, data[:500])
        if response.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(data)
        return json.loads(data) if 'application/json' in response.headers.get('Content-Type', '') else data


def multipart(name, filename, data):
    boundary = 'IMUcheck' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    return body, 'multipart/form-data; boundary=' + boundary


class Connection(c.Structure):
    _fields_ = [('mode', w.DWORD), ('profile', w.LPCWSTR), ('ssid', c.c_void_p),
                ('bssids', c.c_void_p), ('bssType', w.DWORD), ('flags', w.DWORD)]


def main():
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='LAN address; skips all changes to PC Wi-Fi')
    parser.add_argument('--interface', default='9f8f6cd2-3719-4696-8ed1-28d6492b91c5')
    parser.add_argument('--restore-profile', default='LAB-WIFI')
    parser.add_argument('--ota', action='store_true')
    parser.add_argument('--wifi-ssid')
    parser.add_argument('--wifi-password-env', default='IMU_WIFI_PASSWORD')
    parser.add_argument('--settings', action='store_true')
    parser.add_argument('--display', action='store_true', help='Verify live LCD rotation, validation and NVS persistence through reboot')
    parser.add_argument('--usb-api', action='store_true', help='Copy and write/rename/read back through Windows Portable Devices API')
    parser.add_argument('--usb-mib', type=int, choices=range(1,65), help='Larger USB payload; default remains 256 KiB')
    parser.add_argument('--usb-extended', action='store_true', help='Also exercise USB folder creation, move, delete and interrupted read/write')
    parser.add_argument('--usb-copy', action='store_true', help='Prepare a 256 KiB USB fixture, poll HTTP during an Explorer copy, verify SHA-256')
    parser.add_argument('--files', action='store_true', help='Run 16 MiB interrupted/range/slow transfer checks on real SD')
    parser.add_argument('--probe', action='store_true', help='Read status and upload state only')
    parser.add_argument('--sample-seconds', type=int, default=0, help='Observe actual sensor rates under repeated history requests')
    parser.add_argument('--sample-label', default='sampling')
    parser.add_argument('--capture', action='store_true', help='Stop, download and validate the observed CSV; then start a fresh recording')
    parser.add_argument('--stop-log', action='store_true', help='Flush and stop recording before OTA/storage checks')
    parser.add_argument('--resume-files', help='Resume only the named interrupted test directory')
    parser.add_argument('--slow-files', help='Finish slow download verification of an existing own test directory')
    args = parser.parse_args()
    if args.base: BASE=args.base.rstrip('/')
    dll = c.WinDLL('wlanapi')
    handle, version = w.HANDLE(), w.DWORD()
    assert dll.WlanOpenHandle(2, None, c.byref(version), c.byref(handle)) == 0
    guid = (c.c_ubyte * 16).from_buffer_copy(uuid.UUID(args.interface).bytes_le)
    ap_key = escape(os.environ.get('IMU_AP_PASSWORD') or getpass.getpass('Heslo hotspotu vlastní IMU: ')) if not args.base else ''
    xml = f'''<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>IMU-Test</name><SSIDConfig><SSID><name>IMU-Test</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType><connectionMode>manual</connectionMode><MSM><security>
    <authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
    <sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>{ap_key}</keyMaterial></sharedKey>
    </security></MSM></WLANProfile>'''
    connection = Connection(1, xml, None, None, 1, 0)
    report = {'time': time.strftime('%Y-%m-%dT%H:%M:%S'), 'ota_requested': args.ota, 'checks': []}
    stop_monitor = threading.Event()
    monitor = None
    usb_process = None
    usb_log = None

    def keep_ap():
        # A temporary network without Internet can lose to Windows auto-connect.
        # Inspect the current SSID; reconnect only when this test's AP is lost.
        missing = 0
        while not stop_monitor.wait(4):
            size, pointer, opcode = w.DWORD(), c.c_void_p(), w.DWORD()
            result = dll.WlanQueryInterface(handle, c.byref(guid), 7, None, c.byref(size), c.byref(pointer), c.byref(opcode))
            on_ap = False
            if result == 0:
                raw = c.string_at(pointer, size.value)
                dll.WlanFreeMemory(pointer)
                if len(raw) >= 560:
                    length = int.from_bytes(raw[520:524], 'little')
                    on_ap = int.from_bytes(raw[:4], 'little') == 1 and raw[524:524+length] == b'IMU-Test'
            missing = 0 if on_ap else missing + 1
            # Association/authentication may take several seconds after OTA.
            # Repeated Connect calls would cancel Windows' own pending connection.
            if missing >= 6:
                missing = 0
                report['ap_reconnections'] = report.get('ap_reconnections', 0) + 1
                print('AP connection changed; reconnecting temporary IMU-Test profile.', flush=True)
                dll.WlanConnect(handle, c.byref(guid), c.byref(connection), None)

    def connect():
        if not args.base: assert dll.WlanConnect(handle, c.byref(guid), c.byref(connection), None) == 0
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                # Short connection probe; normal requests have a longer transfer timeout.
                with opener.open(BASE + '/api/status', timeout=1) as response:
                    return json.load(response)
            except (OSError, ValueError):
                time.sleep(.5)
        raise RuntimeError('AP did not respond within 25 seconds')

    def passed(name):
        report['checks'].append(name)
        print('PASS:', name, flush=True)

    try:
        status = connect()
        report['status_before'] = status
        if not args.base and (args.files or args.resume_files or args.slow_files or args.usb_copy):
            monitor = threading.Thread(target=keep_ap, daemon=True)
            monitor.start()
        if args.probe:
            report['upload'] = request('/api/upload/status')
            print(json.dumps({'status': status, 'upload': report['upload']}, ensure_ascii=False), flush=True)
            report['success'] = True
            return
        if args.wifi_ssid:
            original=request('/api/wifi')
            networks=[dict(ssid=args.wifi_ssid,password=os.environ[args.wifi_password_env])]+[dict(ssid=n['ssid']) for n in original['networks'] if n['ssid']!=args.wifi_ssid]
            public=request('/api/wifi',dict(settings=original['settings'],networks=networks))
            assert 'password' not in json.dumps(public)
            time.sleep(3)
            for _ in range(12):
                try: public=request('/api/wifi',timeout=3)
                except OSError:
                    connect();continue
                if public['status']['connected'] and public['status']['ip'] not in ('','0.0.0.0','255.255.255.255'):break
                time.sleep(2)
            assert public['status']['ssid']==args.wifi_ssid and public['status']['connected'] and public['status']['ip'] not in ('','0.0.0.0','255.255.255.255'),public
            report['wifi']=public
            passed('Priority Wi-Fi connected; credentials retained only in device NVS')
            print(json.dumps(public,ensure_ascii=False),flush=True)
            report['success']=True
            return
        if args.usb_copy:
            if status['mode'] in ('recording','paused'):status=request('/api/control',{'action':'stop'},timeout=60)
            for _ in range(120):
                if not status['usbBusy']:break
                time.sleep(.25);status=request('/api/status')
            if status['storageOwner']=='usb':status=request('/api/usb/release',{})
            name='USB_overeni_'+uuid.uuid4().hex[:6]
            remote='/'+name
            dest=ROOT/'.cache'/name
            dest.mkdir()
            payload=bytes(range(256))*(args.usb_mib*4096 if args.usb_mib else 1024)
            (dest/'expected.bin').write_bytes(payload)
            request('/api/file',{'action':'mkdir','path':remote})
            upload=request('/api/upload/start',{'id':uuid.uuid4().hex,'path':remote+'/overeni.bin','size':len(payload)})
            while upload['offset']<len(payload):
                offset=upload['offset'];body,kind=multipart('file','chunk.bin',payload[offset:offset+65536])
                try:upload=request('/api/upload/chunk?id='+upload['id']+'&offset='+str(offset),body,kind,timeout=40)
                except OSError:
                    upload=request('/api/upload/status')
                    assert upload['active'] and upload['path']==remote+'/overeni.bin' and upload['offset'] in (offset,offset+65536),upload
                if upload['offset']%1048576==0:print('USB fixture upload: '+str(upload['offset'])+' bytes',flush=True)
            request('/api/upload/finish?id='+upload['id'],{})
            report['usb_bytes']=len(payload);report['usb_extended']=args.usb_extended
            report['usb_remote']=remote+'/overeni.bin';report['usb_local']=str(dest/'overeni.bin')
            print('USB COPY: '+report['usb_remote']+' -> '+report['usb_local'],flush=True)
            report['usb_status_polls']=0;report['usb_owned_polls']=0;report['usb_max_status_seconds']=0
            usb_process=None;usb_log=None
            if args.usb_api:
                usb_log=(dest/'wpd.log').open('w',encoding='utf-8')
                command=[str(ROOT/'.cache/mtp-check.exe'),name,str(dest/'overeni.bin'),str(len(payload))]
                if args.usb_extended:command.append('extended')
                usb_process=subprocess.Popen(command,stdout=usb_log,stderr=usb_log,cwd=ROOT)
            deadline=time.monotonic()+max(600 if args.usb_extended else 180,len(payload)/1048576*60)
            while time.monotonic()<deadline:
                poll_start=time.monotonic()
                try:status=request('/api/status',timeout=3)
                except OSError:status=connect()
                report['usb_max_status_seconds']=max(report['usb_max_status_seconds'],time.monotonic()-poll_start)
                if usb_process and usb_process.poll() not in (None,0):
                    usb_log.close()
                    try:report['usb_trace']=request('/api/usb/trace')
                    except Exception as error:report['usb_trace_error']=str(error)
                    raise AssertionError((dest/'wpd.log').read_text())
                report['usb_status_polls']+=1
                if status['storageOwner']=='usb':report['usb_owned_polls']+=1
                if (dest/'overeni.bin').exists() and (dest/'overeni.bin').stat().st_size==len(payload):break
                time.sleep(.15)
            if usb_process and usb_process.poll() is None and not (dest/'overeni.bin').exists():
                usb_process.kill();usb_process.wait(timeout=5);usb_log.close()
                raise TimeoutError('USB test exceeded its bounded deadline: '+(dest/'wpd.log').read_text())
            copied=(dest/'overeni.bin').read_bytes()
            assert copied==payload
            report['usb_sha256']=hashlib.sha256(copied).hexdigest()
            assert report['usb_owned_polls']>0
            if usb_process:
                assert usb_process.wait(timeout=5)==0;usb_log.close();report['usb_api_log']=(dest/'wpd.log').read_text()
            passed('Windows USB MTP copy is byte-exact while HTTP status is polled continuously')
            if status['storageOwner']=='usb':request('/api/files?path=/',expected=409)
            for _ in range(40):
                status=request('/api/status')
                if not status['usbBusy']:break
                time.sleep(.25)
            request('/api/usb/release',{})
            assert request('/api/download?path='+remote+'/overeni.bin')==payload
            passed('USB ownership blocks web files; explicit release restores byte-exact web access')
            if args.usb_api:
                assert request('/api/download?path='+remote+'/usb-renamed.bin')==payload
                request('/api/file',{'action':'delete','path':remote+'/usb-renamed.bin'})
                passed('USB write and rename produce byte-exact file visible over HTTP')
            request('/api/file',{'action':'delete','path':remote+'/overeni.bin'})
            request('/api/file',{'action':'delete','path':remote})
            passed('Only the temporary USB fixture was removed; copied local evidence retained')
            report['success']=True
            return
        if args.sample_seconds:
            assert status['imu'], 'IMU is not connected'
            assert status['mode'] == 'recording', 'Start a recording before sampling check'
            assert status['sampleAge']<1500 and all(v>0 for v in status['axisHz']), ('Sensor is not producing all three groups',status)
            report['samples'] = [status]
            report['config'] = request('/api/config')
            end = time.monotonic() + args.sample_seconds
            count = 0
            while time.monotonic() < end:
                time.sleep(1)
                try:current = request('/api/status')
                except OSError:
                    report['ap_reconnections']=report.get('ap_reconnections',0)+1
                    current=connect()
                assert current['boot'] == status['boot'] and current['mode'] == 'recording', current
                report['samples'].append(current)
                if count % 5 == 0:
                    try:
                        history = request('/api/history')
                        report['history_buckets'] = len(history['buckets'])
                    except OSError:
                        report['ap_reconnections']=report.get('ap_reconnections',0)+1
                        connect()
                if count % 10 == 0:
                    print(json.dumps({k: current.get(k) for k in ('elapsed','axisHz','missed','dropped','ioErrors','magOverruns','queue','fifoOverflows','fifoHighWater','sampleReadMaxUs','timerGapMaxUs','samplerGapMaxUs','sdWriteMaxUs')}, ensure_ascii=False), flush=True)
                count += 1
            report['delta'] = {k: current[k]-status[k] for k in ('rows','missed','dropped','ioErrors','magOverruns')}
            report['rate_min'] = [min(s['axisHz'][i] for s in report['samples']) for i in range(3)]
            report['rate_max'] = [max(s['axisHz'][i] for s in report['samples']) for i in range(3)]
            print(json.dumps({k: report[k] for k in ('delta','rate_min','rate_max')},ensure_ascii=False),flush=True)
            if args.capture:
                stopped=request('/api/control', {'action':'stop'}, timeout=60)
                payload=request('/api/download?path='+urllib.parse.quote(stopped['file']),timeout=60)
                target=ROOT/'docs'/('measurement-'+args.sample_label+'.csv')
                target.write_bytes(payload)
                lines=payload.splitlines();bad_crc=0;gaps=0;previous=None;axis_times=[[],[],[]]
                for line in lines[1:]:
                    data,crc=line.rsplit(b',',1)
                    bad_crc+=zlib.crc32(data)!=int(crc,16)
                for row in csv.DictReader(io.StringIO(payload.decode())):
                    seq=int(row['seq']);us=int(row['time_us'])
                    if previous is not None:gaps+=seq!=previous+1
                    previous=seq
                    for i,key in enumerate(('accel_new','gyro_new','mag_new')):
                        if int(row[key]):axis_times[i].append(us)
                report['csv']={'file':stopped['file'],'local':str(target.relative_to(ROOT)),'bytes':len(payload),'rows':len(lines)-1,'bad_crc':bad_crc,'sequence_gaps':gaps,'axis_counts':[len(t) for t in axis_times],'axis_hz':[(len(t)-1)*1e6/(t[-1]-t[0]) if len(t)>1 else 0 for t in axis_times],'max_axis_interval_us':[max((b-a for a,b in zip(t,t[1:])),default=0) for t in axis_times]}
                assert not bad_crc and not gaps,report['csv']
                print(json.dumps(report['csv'],ensure_ascii=False),flush=True)
                request('/api/control',{'action':'start'})
            report['success'] = True
            return
        if args.resume_files:
            subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'tests/storage_http.py'),'--base',BASE,'--mib','16','--slow','--resume-dir',args.resume_files],check=True,cwd=ROOT)
            passed('Resumed real SD transfer suite with SHA-256, ranges and slow download')
            report['success'] = True
            return
        for attempt in range(20):
            if status.get('storageOwner') != 'usb': break
            if not status.get('usbBusy'):
                status = request('/api/usb/release', {})
                break
            time.sleep(1)
            status = request('/api/status')
        assert status.get('storageOwner') != 'usb', 'USB has an outstanding transaction after 20 seconds; storage test was not started'
        if args.stop_log and status['mode'] in ('recording','paused'):
            status = request('/api/control', {'action':'stop'}, timeout=60)
            passed('Existing recording flushed and closed without deletion')
        assert status['ssid'] == 'IMU-Test' and status['memory']
        passed('Real ESP32 HTTP status and PSRAM allocation')
        report['config'] = request('/api/config')
        if args.display: report['config'].setdefault('displayRotation', 0)
        assert all(key in report['config'] for key in ('accRate', 'gyroRate', 'magRate'))
        passed('Independent accelerometer, gyroscope and magnetometer configuration')
        if args.settings:
            original = report['config']
            changed = dict(original, accRate=100, gyroRate=200, magRate=20)
            invalid = dict(original, magRate=500)
            request('/api/config', invalid, expected=400)
            try:
                assert request('/api/config', changed)['reboot']
                time.sleep(3)
                connect()
                assert request('/api/config') == changed
                passed('100 / 200 / 20 Hz persist independently through reboot; 500 Hz mag rejected')
            finally:
                assert request('/api/config', original)['reboot']
                time.sleep(3)
                status = connect()
                assert request('/api/config') == original
                passed('Original settings restored and verified after reboot')
        assert isinstance(request('/api/history')['buckets'], list)
        passed('Live history endpoint')
        if not status['imu']:
            request('/api/control', {'action': 'start'}, expected=409)
            passed('Missing sensor prevents false recording')
        if status['sd'] and not args.ota:
            testdir = '/imu-check-' + uuid.uuid4().hex[:8]
            request('/api/file', {'action': 'mkdir', 'path': testdir})
            payload = b'time_s,ax_g\n0.000,1.0\n0.002,1.1\n'
            body, kind = multipart('file', 'check.csv', payload)
            request('/api/upload?path=' + urllib.parse.quote(testdir + '/check.csv'), body, kind)
            assert request('/api/download?path=' + testdir + '/check.csv') == payload
            request('/api/file', {'action': 'rename', 'path': testdir + '/check.csv', 'to': testdir + '/renamed.csv'})
            entries = request('/api/files?path=' + testdir)
            assert len(entries) == 1 and entries[0]['name'].endswith('renamed.csv')
            request('/api/file', {'action': 'delete', 'path': testdir + '/renamed.csv'})
            request('/api/file', {'action': 'delete', 'path': testdir})
            passed('SD mkdir, upload, byte-exact download, rename, list and delete')
        elif not status['sd']:
            report['sd_note'] = 'SD unavailable; file operations could not be tested'
        if args.ota:
            if request('/api/status')['storageOwner']=='usb':
                request('/api/usb/release', {})
            firmware = (ROOT / '.build/imu/firmware.bin').read_bytes()
            report['firmware_sha256'] = hashlib.sha256(firmware).hexdigest()
            body, kind = multipart('firmware', 'firmware.bin', firmware)
            assert request('/api/ota', body, kind, timeout=90)['reboot']
            time.sleep(4)
            after = connect()
            assert after['boot'] > status['boot'], (status['boot'], after['boot'])
            report['status_after'] = after
            assert request('/api/config') == report['config']
            passed('Real OTA upload, reboot into updated application and retained configuration')
        for path, local in [('/', 'index.html'), ('/app.css', 'app.css'), ('/app.js', 'app.js'), ('/files.js', 'files.js'), ('/network.js', 'network.js'), ('/pdf-viewer.mjs', 'pdf-viewer.mjs'), ('/report.mjs', 'report.mjs'), ('/pdfjs/pdf.worker.mjs', 'pdfjs/pdf.worker.mjs')]:
            assert request(path, timeout=30) == (ROOT / 'web' / local).read_bytes(), path
        passed('Web application and offline PDF worker match project sources')
        if args.display:
            original = request('/api/config')
            status = request('/api/status')
            if status['mode'] != 'recording': status = request('/api/control', {'action':'start'})
            before = status
            report['display_states'] = []
            try:
                for invalid in (-90,45,360,1.5,'90',True,None):
                    request('/api/display', {'displayRotation':invalid}, expected=400)
                passed('Invalid LCD angles and non-integer types rejected')
                for angle in (90,180,270,0,90,180,270,0):
                    assert request('/api/display', {'displayRotation':angle})['displayRotation']==angle
                    time.sleep(2)
                    status=request('/api/status')
                    assert status['displayRotation']==angle
                    assert status['boot']==before['boot'] and status['file']==before['file'] and status['mode']=='recording'
                    assert status['rows']>before['rows'] and status['sampleAge']<1500
                    assert request('/api/config')==dict(original,displayRotation=angle)
                    report['display_states'].append(status)
                for key in ('dropped','missed','fifoOverflows','ioErrors','magOverruns'):
                    assert status[key]==before[key], (key,before[key],status[key])
                passed('All four orientations applied twice during the same recording, with no new sampling losses')
                request('/api/display', {'displayRotation':90})
                request('/api/control', {'action':'stop'}, timeout=60)
                assert request('/api/config', original)['reboot']
                time.sleep(4)
                status=connect()
                assert status['boot']>before['boot']
                assert request('/api/config')==dict(original,displayRotation=90)
                assert status['displayRotation']==90
                report['display_after_reboot']=status
                passed('90-degree LCD orientation survives reboot independently of sensor settings')
            finally:
                request('/api/display', {'displayRotation':original['displayRotation']})
                time.sleep(.5)
                assert request('/api/config')==original
            passed('Original orientation restored; measurement left running')
        if args.slow_files:
            subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'tests/storage_http.py'),'--base',BASE,'--mib','16','--slow-existing',args.slow_files],check=True,cwd=ROOT)
            passed('Real slow SD download longer than 60 seconds and test directory cleanup')
        if args.files:
            subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'tests/storage_http.py'),'--base',BASE,'--mib','16','--slow'],check=True,cwd=ROOT)
            passed('Real SD transfer suite, including interruption, ranges, SHA-256 and a download longer than 60 seconds')
        report['success'] = True
    except BaseException as error:
        report['success'] = False
        report['error'] = repr(error)
        raise
    finally:
        # A lost Wi-Fi connection must not leave this test's WPD process copying
        # in the background after the supervising test has already failed.
        if usb_process and usb_process.poll() is None:
            usb_process.terminate()
            try: usb_process.wait(timeout=5)
            except subprocess.TimeoutExpired: usb_process.kill();usb_process.wait(timeout=5)
        if usb_log and not usb_log.closed: usb_log.close()
        stop_monitor.set()
        if monitor: monitor.join(timeout=5)
        dll.WlanCloseHandle(handle, None)
        if not args.base: subprocess.run(['netsh', 'wlan', 'connect', 'name=' + args.restore_profile], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert all(ch.isalnum() or ch in '-_' for ch in args.sample_label)
        report_name = ('hardware-'+args.sample_label+'.json') if args.sample_seconds else 'hardware-usb-copy.json' if args.usb_copy else 'hardware-display.json' if args.display else 'hardware-settings.json' if args.settings else 'hardware-ota.json' if args.ota else 'hardware-check.json'
        serialized = json.dumps(report, ensure_ascii=False, indent=2)
        # Keep each attempt so an offline board cannot erase a prior successful test.
        archive = ROOT / 'docs' / 'hardware-runs'
        archive.mkdir(exist_ok=True)
        (archive / (time.strftime('%Y%m%dT%H%M%S-') + report_name)).write_text(serialized, encoding='utf-8')
        (ROOT / 'docs' / report_name).write_text(serialized, encoding='utf-8')
        print('Report saved; PC Wi-Fi unchanged.' if args.base else 'Previous Wi-Fi profile reconnection requested; report saved.', flush=True)


if __name__ == '__main__':
    main()
