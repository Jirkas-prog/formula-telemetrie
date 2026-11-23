"""Real-board network checks. Preserve secrets by omitting unchanged passwords."""
import argparse,copy,json,socket,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import hardware_check as hw
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--gateway',required=True);a=p.parse_args();hw.BASE=a.base.rstrip('/')
request=hw.request
report={'checks':[]}
def passed(s): report['checks'].append(s);print('PASS:',s,flush=True)
def wait_connected(ssid):
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            status=request('/api/status',timeout=2)
            if status['wifi']['connected'] and status['wifi']['ssid']==ssid:return status
        except OSError:pass
        time.sleep(1)
    raise AssertionError('Wi-Fi did not reconnect')
original=request('/api/wifi');original_payload={'settings':original['settings'],'networks':[{'ssid':n['ssid']} for n in original['networks']]}
try:
    assert original['networks'][0]['ssid']=='LAB-WIFI' and original['networks'][0]['hasPassword']
    assert 'password' not in json.dumps(original)
    report['initial']=original
    for change in ({'hostname':'bad.local'},{'hostname':'Bad Name'},{'apIp':'192.168.4.255'},{'apIp':'999.1.1.1'},
                   {'dhcp':False,'ip':'192.168.4.5','subnet':'255.255.255.0','gateway':'192.168.4.1','dns':'1.1.1.1'},
                   {'dhcp':False,'ip':'10.32.176.138','subnet':'255.0.255.0','gateway':a.gateway,'dns':a.gateway}):
        bad=copy.deepcopy(original_payload);bad['settings'].update(change);request('/api/wifi',bad,expected=400)
    bad=copy.deepcopy(original_payload);bad['networks']*=2;request('/api/wifi',bad,expected=400)
    bad=copy.deepcopy(original_payload);bad['networks'][0]['password']='short';request('/api/wifi',bad,expected=400)
    assert request('/api/wifi')['settings']==original['settings']
    passed('Invalid hostnames, IPs, overlapping subnets, duplicate SSIDs and short passwords rejected without changing settings')
    before=request('/api/status')
    changed=copy.deepcopy(original_payload)
    changed['settings'].update(hostname='imu-test-qa',apIp='192.168.7.1',dhcp=False,ip=original['status']['ip'],subnet='255.255.255.0',gateway=a.gateway,dns=a.gateway)
    changed['networks'].insert(0,{'ssid':'IMU-QA-unavailable-network','password':'test-only-123'})
    request('/api/wifi',changed);time.sleep(2)
    status=wait_connected('LAB-WIFI')
    assert status['wifi']['ip']==original['status']['ip'] and status['wifi']['apIp']=='192.168.7.1'
    assert socket.gethostbyname('imu-test-qa.local')==original['status']['ip']
    assert status['boot']==before['boot'] and status['file']==before['file'] and status['mode']==before['mode']
    report['after_fallback']=status
    passed('Unavailable first-priority network falls back to LAB-WIFI with its saved password; static IP, AP IP and new mDNS alias work without restart')
    request('/api/wifi',original_payload);time.sleep(2);status=wait_connected('LAB-WIFI')
    assert request('/api/wifi')['settings']==original['settings']
    passed('Original priority, DHCP, hotspot IP and alias restored; existing password preserved')
    if status['mode'] in ('recording','paused'):request('/api/control',{'action':'stop'},timeout=60)
    if status['storageOwner']=='usb':request('/api/usb/release',{})
    config=request('/api/config');request('/api/config',config);time.sleep(5);status=wait_connected('LAB-WIFI')
    assert status['boot']>before['boot']
    after=request('/api/wifi');assert after['settings']==original['settings'] and after['networks']==original['networks']
    assert socket.gethostbyname('imu-test.local')==after['status']['ip']
    report['after_reboot']=after;report['boot']=status['boot']
    passed('Wi-Fi priorities, retained credential, DHCP and alias survive device reboot; LAN alias resolves')
    report['success']=True
except BaseException as e:
    report['error']=repr(e)
    try:request('/api/wifi',original_payload)
    except OSError:pass
    raise
finally:
    (ROOT/'docs/hardware-wifi.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
