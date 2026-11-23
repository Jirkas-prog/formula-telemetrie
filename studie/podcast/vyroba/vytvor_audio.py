"""Synthesize original Czech educational narration; no device configuration is used."""
import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--deps', required=True)
args = parser.parse_args()
sys.path.insert(0, args.deps)
import edge_tts
from mutagen.mp3 import MP3

ROOT = Path(__file__).resolve().parent.parent
VOICE = 'cs-CZ-AntoninNeural'
RATE = '+12%'
REPLACEMENTS = {
    'Raspberry Pi': 'Rázbery páj', 'Raspberry': 'Rázbery',
    'NVMe': 'en vé em é', 'SSD': 'es es dé', 'SSH': 'es es há',
    'GNSS': 'gé en es es', 'GPS': 'gé pé es', 'SBF': 'es bé ef',
    'PPK': 'pé pé ká', 'RTK': 'er té ká', 'ROS': 'ros',
    'IP': 'í pé', 'USB': 'ú es bé', 'PCI Express': 'pí sí aj expres',
    'rpi-clone': 'ár pí aj kloun', 'fsync': 'ef sink',
    'Docker': 'Dokr', 'Compose': 'Kompóuz', 'InfluxDB': 'Influx dé bé',
    'Python': 'Pajton', 'NumPy': 'Nampaj', 'systemd': 'systém dé',
    'venv': 'venv', 'GitHub': 'Git hab', 'ARM': 'arm',
    'SQLite': 'es kjú el lajt', 'SQL': 'es kjú el', 'API': 'á pé í',
    'JSON': 'džejson', 'YAML': 'jaml', 'HTTP': 'há té té pé',
    'localhost': 'lokal houst', 'Flux': 'flaks', 'OOM': 'ou ou em',
    'Lite': 'lajt', 'Trixie': 'triksi', 'Zephyr': 'zefyr',
}

def chapters():
    source = (ROOT / 'scenar.txt').read_text(encoding='utf-8')
    matches = list(re.finditer(r'^=== (\d+) \| (.+?) ===\s*$', source, re.M))
    result = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        body = source[match.end():end].strip()
        result.append({'number': int(match[1]), 'title': match[2], 'text': body})
    return result

def spoken(text):
    for original, replacement in REPLACEMENTS.items():
        text = re.sub(r'(?<!\w)' + re.escape(original) + r'(?!\w)', replacement, text)
    return text

async def main():
    out = ROOT / 'kapitoly'
    out.mkdir(exist_ok=True)
    sem = asyncio.Semaphore(2)
    entries = chapters()
    print(f'WORDS {sum(len(c["text"].split()) for c in entries)} CHAPTERS {len(entries)}', flush=True)

    async def synth(c):
        audio = out / f'{c["number"]:02d}.mp3'
        receipt = out / f'{c["number"]:02d}.json'
        narration = spoken(f'Kapitola {c["number"]}. {c["title"]}.\n\n{c["text"]}')
        digest = hashlib.sha256((VOICE + RATE + narration).encode('utf-8')).hexdigest()
        if audio.exists() and receipt.exists():
            old = json.loads(receipt.read_text(encoding='utf-8'))
            if old.get('sha256_text_voice_rate') == digest:
                print(f'CACHED {c["number"]:02d} {old["duration_seconds"]:.2f}s', flush=True)
                return
        async with sem:
            for attempt in range(4):
                try:
                    print(f'START {c["number"]:02d} attempt {attempt+1}', flush=True)
                    await asyncio.wait_for(edge_tts.Communicate(narration, VOICE, rate=RATE).save(str(audio)), timeout=240)
                    info = MP3(audio).info
                    words = len(narration.split())
                    if info.length < words / 5:
                        raise RuntimeError('Audio too short relative to narration')
                    meta = {**c, 'text': None, 'voice': VOICE, 'rate': RATE,
                            'sha256_text_voice_rate': digest,
                            'sha256_audio': hashlib.sha256(audio.read_bytes()).hexdigest(),
                            'duration_seconds': info.length, 'word_count': words,
                            'sample_rate': info.sample_rate, 'bitrate': info.bitrate}
                    receipt.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(f'DONE {c["number"]:02d} {info.length:.2f}s', flush=True)
                    return
                except Exception as exc:
                    print(f'RETRY {c["number"]:02d} {type(exc).__name__}: {exc}', flush=True)
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 ** (attempt + 1))
    await asyncio.gather(*(synth(c) for c in entries))

asyncio.run(main())
