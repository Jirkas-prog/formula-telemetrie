"""Assemble chapters, normalize speech, embed chapter markers, verify decoding."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--deps', required=True)
parser.add_argument('--work', required=True)
args = parser.parse_args()
sys.path.insert(0, args.deps)
import imageio_ffmpeg
from mutagen.mp3 import MP3
from mutagen.id3 import CHAP, CTOC, TIT2, TPE1, TALB, TCON, TDRC, COMM, USLT

root = Path(__file__).resolve().parent.parent
work = Path(args.work).resolve()
work.mkdir(parents=True, exist_ok=True)
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
final = root / 'Podcast_Raspberry_Pi_GNSS.mp3'

def run(args):
    result = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', *args],
                            capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return result

def duration(path):
    with wave.open(str(path), 'rb') as f:
        return f.getnframes() / f.getframerate()

def stamp(seconds):
    total = round(seconds)
    return f'{total // 60:02d}:{total % 60:02d}'

entries = []
for number in range(1, 13):
    audio = root / 'kapitoly' / f'{number:02d}.mp3'
    meta = json.loads(audio.with_suffix('.json').read_text(encoding='utf-8'))
    assert meta['rate'] == '+12%', f'Chapter {number} is not final narration'
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == meta['sha256_audio']
    wav = work / f'{number:02d}.wav'
    run(['-y', '-v', 'error', '-i', str(audio), '-ac', '1', '-ar', '24000',
         '-c:a', 'pcm_s16le', str(wav)])
    meta['pcm_duration_seconds'] = duration(wav)
    meta['wav'] = wav
    entries.append(meta)

silence = work / 'pause.wav'
run(['-y', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono',
     '-t', '0.75', '-c:a', 'pcm_s16le', str(silence)])
files = []
position = 0.0
for i, meta in enumerate(entries):
    meta['start_seconds'] = position
    files.append(meta['wav'])
    position += meta['pcm_duration_seconds']
    if i < len(entries) - 1:
        files.append(silence)
        position += duration(silence)
    meta['end_seconds'] = position
concat = work / 'concat.txt'
concat.write_text('\n'.join("file '" + p.as_posix().replace("'", "'\\''") + "'" for p in files), encoding='utf-8')
assert 1200 <= position <= 1830, f'Duration {position} outside intended range'

print(f'MASTER duration={position:.2f}s ({stamp(position)}), chapters={len(entries)}', flush=True)
analysis = run(['-f', 'concat', '-safe', '0', '-i', str(concat),
                '-af', 'loudnorm=I=-19:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
match = re.search(r'\{\s*"input_i"[\s\S]+?\}', analysis.stderr)
assert match, 'Missing loudness analysis'
measure = json.loads(match[0])
filt = ('loudnorm=I=-19:TP=-1.5:LRA=11:linear=true:'
        f'measured_I={measure["input_i"]}:measured_TP={measure["input_tp"]}:'
        f'measured_LRA={measure["input_lra"]}:measured_thresh={measure["input_thresh"]}:'
        f'offset={measure["target_offset"]}:print_format=json')
encoded = run(['-y', '-f', 'concat', '-safe', '0', '-i', str(concat),
               '-af', filt, '-ac', '1', '-ar', '24000', '-c:a', 'libmp3lame',
               '-b:a', '96k', '-write_xing', '1', str(final)])
outmatch = re.search(r'\{\s*"input_i"[\s\S]+?\}', encoded.stderr)
output_measure = json.loads(outmatch[0]) if outmatch else {}

mp3 = MP3(final)
if mp3.tags is None:
    mp3.add_tags()
tags = mp3.tags
tags.add(TIT2(encoding=3, text='Raspberry Pi a GNSS logger pro formuli — od základů k měření'))
tags.add(TPE1(encoding=3, text='Studijní výklad · syntetický český hlas'))
tags.add(TALB(encoding=3, text='Bakalářka — infrastruktura Raspberry Pi'))
tags.add(TCON(encoding=3, text='Podcast'))
tags.add(TDRC(encoding=3, text='2026-11-18'))
tags.add(COMM(encoding=3, lang='ces', desc='Popis', text='Český studijní podcast. Raspberry Pi 5 / 2 GB, SD -> NVMe, Wi-Fi, GNSS data, Docker, InfluxDB, Grafana, výpočty a ověření spolehlivosti. Syntetický hlas Microsoft cs-CZ-AntoninNeural.'))
tags.add(USLT(encoding=3, lang='ces', desc='Přepis', text=(root / 'scenar.txt').read_text(encoding='utf-8')))
ids = []
for meta in entries:
    key = f'ch{meta["number"]:02d}'
    ids.append(key)
    tags.add(CHAP(element_id=key, start_time=round(meta['start_seconds'] * 1000),
                  end_time=round(meta['end_seconds'] * 1000),
                  sub_frames=[TIT2(encoding=3, text=meta['title'])]))
tags.add(CTOC(element_id='toc', flags=3, child_element_ids=ids,
              sub_frames=[TIT2(encoding=3, text='Kapitoly')]))
mp3.save(v2_version=3)

decode = run(['-v', 'error', '-xerror', '-i', str(final), '-f', 'null', '-'])
assert not decode.stderr.strip(), decode.stderr
check = MP3(final)
assert abs(check.info.length - position) < 0.2
assert len(check.tags.getall('CHAP')) == 12
assert 20 * 60 <= check.info.length <= 30.5 * 60

chapters = ['PODCAST: Raspberry Pi a GNSS logger pro formuli',
            f'Délka: {stamp(check.info.length)} | český syntetický hlas | 12 kapitol', '',
            'Přehrát celý soubor: Podcast_Raspberry_Pi_GNSS.mp3',
            'Jednotlivé kapitoly: složka kapitoly, soubory 01.mp3 až 12.mp3.',
            'Časové značky jsou vloženy také do MP3 (podpora závisí na přehrávači).', '']
chapters += [f'{stamp(m["start_seconds"])}  {m["number"]:02d}. {m["title"]}' for m in entries]
chapters += ['', 'Přepis: scenar.txt', 'Zdroje a výpočty: Zdroje_a_poznamky.txt',
             'Výklad navazuje na aktuální projekt; není potvrzením dosud neprovedených zkoušek.']
(root / 'Poslech_a_kapitoly.txt').write_text('\n'.join(chapters) + '\n', encoding='utf-8')
(root / 'Kapitoly.m3u8').write_text('#EXTM3U\n' + '\n'.join(
    f'#EXTINF:{m["pcm_duration_seconds"]:.0f},{m["number"]:02d}. {m["title"]}\nkapitoly/{m["number"]:02d}.mp3' for m in entries) + '\n', encoding='utf-8')

report = {'file': str(final), 'duration_seconds': check.info.length,
          'duration_display': stamp(check.info.length), 'size_bytes': final.stat().st_size,
          'sample_rate': check.info.sample_rate, 'bitrate': check.info.bitrate,
          'channels': check.info.channels, 'chapters': len(entries),
          'decode_errors': decode.stderr.strip(),
          'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
          'loudness_analysis': measure, 'loudness_encoding': output_measure,
          'chapter_timing': [{k:v for k,v in m.items() if k in ('number','title','start_seconds','end_seconds','pcm_duration_seconds')} for m in entries]}
(root / 'vyroba' / 'overeni.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('chapter_timing','loudness_analysis')}, ensure_ascii=False, indent=2), flush=True)
