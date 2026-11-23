"""Repeated on-wire mDNS and HTTP checks; no DNS/hosts/firewall modifications."""
import argparse
import json
import socket
import time
import urllib.request
from mdns_probe import ROOT, probe

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--device-ip', required=True)
p.add_argument('--seconds', type=int, default=900)
a = p.parse_args()
name = 'imu-test.local'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
report = {'device_ip': a.device_ip, 'seconds': a.seconds, 'success': False, 'checks': []}
path = ROOT / 'docs' / ('mdns-soak-' + time.strftime('%Y%m%dT%H%M%S') + '.json')
start = time.monotonic()
try:
    while True:
        row = {'elapsed': round(time.monotonic() - start, 1)}
        report['checks'].append(row)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((a.device_ip, 80))
            local_ip = route.getsockname()[0]
        row['local_ip'] = local_ip
        for key, target in [('unicast', a.device_ip), ('multicast', '224.0.0.251')]:
            row[key] = probe(name, a.device_ip, target, local_ip)
            assert row[key] == [a.device_ip], (key, row)
        row['resolution'] = sorted({x[4][0] for x in socket.getaddrinfo(name, 80, socket.AF_INET)})
        assert row['resolution'] == [a.device_ip], row
        with opener.open('http://' + name + '/api/status', timeout=10) as response:
            status = json.load(response)
        row['boot'] = status['boot']
        row['wifi'] = status['wifi']
        assert row['boot'] == report['checks'][0]['boot'], 'Device rebooted during soak'
        assert status['wifi']['ip'] == a.device_ip and status['wifi']['mdnsStarted']
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('PASS:', row['elapsed'], 'seconds; direct multicast + Windows DNS + HTTP', flush=True)
        if time.monotonic() - start >= a.seconds:
            break
        time.sleep(min(30, a.seconds - (time.monotonic() - start)))
    report['success'] = True
except BaseException as error:
    report['error'] = repr(error)
    raise
finally:
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('REPORT:', path, flush=True)
