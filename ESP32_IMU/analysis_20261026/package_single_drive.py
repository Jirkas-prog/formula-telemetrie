"""A clean handover containing only the usable 330 s drive, documents and app."""
from pathlib import Path
import sys,json,zipfile,hashlib,zlib,shutil
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'.deps'))
import numpy as np
import pandas as pd
OUT=ROOT.parent/'Formule_jizda_181'
assert not OUT.exists(), 'Preserve the previous handover; choose another destination.'
for folder in ['01_Dokumenty','02_Aplikace','03_Data']:(OUT/folder).mkdir(parents=True,exist_ok=True)
source=Path('./input/logs/boot_000181_run_001.csv')
raw=OUT/'03_Data/Jizda_181_677-1007s.csv';rows=0;first=last=None
with source.open('rb') as src,raw.open('wb') as dst:
 dst.write(src.readline())
 for line in src:
  t=int(line.split(b',',1)[0])
  if t>=1007000000:break
  if t<677000000:continue
  payload,crc=line.rstrip(b'\r\n').rsplit(b',',1);assert zlib.crc32(payload)==int(crc,16)
  dst.write(line);rows+=1
  if first is None:first=t
  last=t
assert rows==165000,(rows,first,last)
df=pd.read_csv(raw);assert df.accel_new.sum()==df.gyro_new.sum()==165000
assert df.mag_valid.sum()==0
digital=np.rint(df[['ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps']].to_numpy()*np.array([2048]*3+[16.384]*3))
assert not np.any((digital==digital[:,0,None]).all(axis=1))
sha=hashlib.sha256(raw.read_bytes()).hexdigest()
with zipfile.ZipFile(ROOT/'output/Formule_IMU.fimu') as original:
 old=json.loads(original.read('manifest.json'));run=next(r for r in old['runs'] if r['id']=='boot_000181_run_001')
 full=np.frombuffer(original.read(run['derived_member']),dtype='<f4').reshape(-1,18)
 # Preserve the format's absolute 100 Hz indices; before the excerpt only time and NaN padding remain.
 data=full[:100700].copy();data[:67700,1:]=np.nan
 assert np.all(data[67700:,11]==0);assert len(data[67700:])==33000
 tr=np.frombuffer(original.read('derived/trajectory181.f32'),dtype='<f4').reshape(-1,13)
 tr=tr[(tr[:,0]>=677)&(tr[:,0]<1007)].copy();assert len(tr)==3300
 selected=next(r.copy() for r in old['results']['files'] if r['id']==run['id'])
 selected.update(file=raw.name,rows=rows,duration_s=330,digital_fault_fraction=0,valid_contiguous_s=330,sha256=sha,
  evidence='Samostatný výřez jediné použitelné jízdy: 677–1007 s. 165 000 původních A/G řádků, bez zjištěného opakovaného digitálního vzoru; CRC všech řádků ověřeno. Časy i pořadová čísla jsou původní. Kompas v tomto úseku nemá platná data. Model trasy je podmíněný odhad bez GPS.')
 res={k:old['results'][k] for k in ['laps','vehicle','drive_stats','bounds','driving_interval_s']}
 res.update(files=[selected],total_rows=rows,total_duration_s=330,digital_fault_rows=0)
 subset=dict(source_file=source.name,source_sha256=run['sha256'],start_s=677,end_exclusive_s=1007,first_source_time_us=first,last_source_time_us=last,
  method='Original CSV lines copied unchanged. Derived filtered values retained from the original analysis so filter boundaries and calibration remain identical to reports. No measurement outside 677–1007 s is included; earlier array indices are NaN padding.',
  calibration_note='Fixed mounting/offset constants fitted from original run 181 are retained. Calibration raw samples are not part of this drive-only handover. No new calibration or path fit was performed.')
 newrun={k:run[k] for k in ['id','settings','cache_hz','cache_columns']}
 newrun.update(file=raw.name,bytes=raw.stat().st_size,rows=rows,sha256=sha,bad_crc=0,start_s=677,window_start_s=677,end_s=1007,duration_s=330,
  fresh_counts=[165000,165000,0],derived_rows=len(data),derived_member=run['derived_member'],raw_member='raw/'+raw.name,sidecars={})
 manifest={k:old[k] for k in ['format','version','created','time_basis','array_dtype','array_layout','columns','filter','trajectory_columns']}
 manifest.update(subset=subset,results=res,runs=[newrun],trajectory_rows=len(tr))
 target=OUT/'03_Data/Jizda_181_677-1007s.fimu'
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  z.write(raw,newrun['raw_member']);z.writestr(newrun['derived_member'],data.astype('<f4').tobytes());z.writestr('derived/trajectory181.f32',tr.astype('<f4').tobytes())
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,allow_nan=False))
  z.writestr('FORMAT.txt','FIMU v1. One original drive excerpt only: 677 <= time_s < 1007. Original CSV rows and timestamps retained; pre-677 derived indices contain only time and NaN padding. Position is a conditional model, not GPS. See manifest subset/calibration_note.\n')
with zipfile.ZipFile(target) as z:
 assert len(json.loads(z.read('manifest.json'))['runs'])==1
 assert z.read(newrun['raw_member'])==raw.read_bytes();assert z.testzip() is None
 a=np.frombuffer(z.read(newrun['derived_member']),dtype='<f4').reshape(-1,18)
 assert np.isnan(a[:67700,1:]).all();assert np.array_equal(a[67700:],full[67700:100700],equal_nan=True)
shutil.copy2(ROOT/'output/Prohlizec_IMU.html',OUT/'02_Aplikace/Prohlizec_IMU.html')
shutil.copy2(ROOT/'report_drivetrain/data/jizda_100Hz_2Hz.csv',OUT/'03_Data/Jizda_181_vozidlo_100Hz_2Hz.csv')
for source_name,dest in [('output/pdf/Drivetrain_jizdni_data.pdf','01_Drivetrain.pdf'),('output/Analyza_jizd_a_zavery.pdf','02_Analyza_jizdy.pdf'),('output/Analyza_IMU_formule.pdf','03_Puvodni_analyza_IMU.pdf')]:
 shutil.copy2(ROOT/source_name,OUT/'01_Dokumenty'/dest)
# The review document belongs beside the original reports; forensic data stays outside this clean folder.
note=(ROOT/'output/revize_01/CTI_ME_REVIZE.txt').read_text(encoding='utf-8-sig')
note=note[:note.index('CO JE V NOVÉM BALÍČKU')]+'''CO JE V TÉTO SLOŽCE
Tři původní PDF jsou doplněna touto revizí kvality. Jízdní čísla se nezměnila.
Přiložená data obsahují pouze 677–1007 s záznamu 181; poruchové úseky nejsou přiložené.
165 000 původních A/G řádků má platné CRC a neobsahuje zjištěný opakovaný digitální vzor.
Grafy, filtrované hodnoty a podmíněný model trasy jsou převzaté z původní analýzy.
Neproběhlo nové měření ani potvrzení absolutní přesnosti trasy. Kompas v jízdě není dostupný.
Ostatní zde jmenované CSV a detailní důkazy jsou v pracovním archivu revize, nikoli v této složce.
Čtěte přednostně 01_Drivetrain.pdf a 02_Analyza_jizdy.pdf. Dokument 03 je původní průzkum.
'''
(OUT/'01_Dokumenty/04_Revize_kvality.txt').write_text(note,encoding='utf-8-sig')
readme='''FORMULE / JEDNA POUŽITELNÁ JÍZDA

1. Otevřete 02_Aplikace/Prohlizec_IMU.html v Edge nebo Chrome.
2. Klepněte na Otevřít data a vyberte 03_Data/Jizda_181_677-1007s.fimu.
3. Aplikace ukáže jediný záznam, jeho grafy, statistiky, vlaječky a podmíněný model trasy.

Pouze 330 s ze záznamu 181 (677–1007 s v původní časové ose).
Jizda_181_677-1007s.csv: 165 000 původních řádků; A/G 500 Hz, beze změny čísel,
časových značek, pořadových čísel a CRC. Lze otevřít i přímo v aplikaci jako osy senzoru.
Jizda_181_vozidlo_100Hz_2Hz.csv: 33 000 filtrovaných vozidlových bodů pro další výpočty.
FIMU: tentýž CSV výřez a odvozené řady. Pro úplný pohled s modelem trasy otevírejte FIMU.

Vše je lokální, bez připojené desky a bez internetu. Prohlížeč nevyžaduje instalaci.
Výsledky modelu polohy a rychlosti nejsou GPS měření. Kompas zde nemá platné nové vzorky.
Kalibrační konstanty a filtr jsou převzaté z původní analýzy, proto čísla odpovídají PDF.
Předchozí kalibrační měření ani vadný konec záznamu nejsou součástí této složky.

Dokumenty čtěte v pořadí 01, 02, 04. Dokument 03 je původní průzkumná analýza
a zahrnuje i porovnání dalších záznamů, které zde datově přiložené nejsou.
Vlastní vlaječky mají pro tento výřez samostatné uložení; starý plný FIMU se nepřepisuje.
'''
(OUT/'ZACNETE_ZDE.txt').write_text(readme,encoding='utf-8-sig')
print(json.dumps(dict(folder=str(OUT),raw_rows=rows,first_us=first,last_us=last,raw_sha256=sha,
 files=[str(p.relative_to(OUT)) for p in OUT.rglob('*') if p.is_file()],bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())),ensure_ascii=False,indent=2),flush=True)
