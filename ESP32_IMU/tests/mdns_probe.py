"""Probe the actual ESP32 mDNS responder and HTTP alias without changing PC DNS."""
import argparse
import gzip
import json
from pathlib import Path
import socket
import struct
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def skip_name(data, pos):
    while pos < len(data):
        size = data[pos]
        pos += 1
        if size == 0:
            return pos
        if size & 0xc0 == 0xc0:
            return pos + 1
        if size > 63 or pos + size > len(data):
            raise ValueError('Malformed DNS name')
        pos += size
    raise ValueError('Truncated DNS name')


def addresses(data):
    _, flags, questions, answers, authority, extra = struct.unpack_from('!6H', data)
    if not flags & 0x8000:
        return set()
    pos = 12
    found = set()
    for _ in range(questions):
        pos = skip_name(data, pos) + 4
    for _ in range(answers + authority + extra):
        pos = skip_name(data, pos)
        kind, cls, ttl, size = struct.unpack_from('!HHIH', data, pos)
        pos += 10
        if kind == 1 and cls & 0x7fff == 1 and size == 4:
            found.add(socket.inet_ntoa(data[pos:pos + size]))
        pos += size
    return found


def probe(name, device_ip, target, local_ip):
    wire = b''.join(bytes([len(label)]) + label.encode('ascii') for label in name.split('.')) + b'\0'
    query = struct.pack('!6H', 0, 0, 1, 0, 0, 0) + wire + struct.pack('!HH', 1, 0x8001)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((local_ip, 0))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.settimeout(.3)
        deadline = time.monotonic() + 5
        next_send = 0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_send:
                sock.sendto(query, (target, 5353))
                next_send = time.monotonic() + 1
            try:
                data, source = sock.recvfrom(4096)
                if source[0] == device_ip:
                    result = addresses(data)
                    if result:
                        return sorted(result)
            except socket.timeout:
                pass
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-ip', required=True)
    parser.add_argument('--hostname', default='imu-test.local')
    args = parser.parse_args()
    socket.inet_aton(args.device_ip)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        route.connect((args.device_ip, 80))
        local_ip = route.getsockname()[0]
    report = {'hostname': args.hostname, 'device_ip': args.device_ip, 'local_ip': local_ip, 'success': False}
    try:
        report['unicast'] = probe(args.hostname, args.device_ip, args.device_ip, local_ip)
        report['multicast'] = probe(args.hostname, args.device_ip, '224.0.0.251', local_ip)
        assert report['unicast'] == report['multicast'] == [args.device_ip], report
        report['windows_resolution'] = sorted({x[4][0] for x in socket.getaddrinfo(args.hostname, 80, socket.AF_INET)})
        assert report['windows_resolution'] == [args.device_ip], report
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://' + args.hostname + '/api/status', timeout=10) as response:
            report['status'] = json.load(response)
        assert report['status']['wifi']['ip'] == args.device_ip
        with opener.open('http://' + args.hostname + '/', timeout=10) as response:
            page = response.read()
            if response.headers.get('Content-Encoding') == 'gzip':
                page = gzip.decompress(page)
        assert page == (ROOT / 'web/index.html').read_bytes()
        report['http_root_bytes'] = len(page)
        report['success'] = True
        print('PASS: unicast, multicast, Windows DNS and HTTP alias all reach ' + args.device_ip)
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        path = ROOT / 'docs' / ('mdns-probe-' + time.strftime('%Y%m%dT%H%M%S') + '.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('REPORT:', path)


if __name__ == '__main__':
    main()
