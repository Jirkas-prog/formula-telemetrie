"""Deliver the first revision with original bytes, explicit evidence and no invented tracks."""
from pathlib import Path
import os,sys,json,zipfile,hashlib,shutil,csv
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'output/revize_01'
sys.path.insert(0,str(ROOT/'.deps'));os.environ['MPLCONFIGDIR']=str(ROOT/'.cache/matplotlib')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
audit=json.loads((OUT/'audit.json').read_text(encoding='utf-8')); records={r['id']:r for r in audit['files']}
total=sum(r['rows'] for r in records.values());bad=sum(r['repeat_six_words_rows'] for r in records.values())
assert all(r['archive_byte_identical'] and r['crc_bad']==0 and r['old_rule_disagreements']==0 for r in records.values())
assert all(r['repeat_six_words_rows']==r['repeat_single_byte_rows'] for r in records.values())
affected=[r for r in records.values() if r['repeat_six_words_rows']]
lines=['REVIZE 01 — CO JE SKUTEČNĚ ULOŽENÉ V DATECH','',
 'První krok revize. Nezávisle znovu přečteno všech 38 původních CSV.',
 f'Řádků celkem: {total:,}; opakovaný bajt ve všech šesti osách: {bad:,} ({bad/total:.5%}).',
 'Všech 38 CSV v původním FIMU je podle SHA-256 shodných s originály.',
 'Kontrolní součet CRC prošel u každého řádku. To potvrzuje zápis, nikoli správnost měření.',
 '', 'VELIKOST SOUBORU A DŮVOD VYŘAZENÍ']
for r in affected:
 lines.extend([f"{r['file']}: {r['bytes']/1e6:.2f} MB / {r['rows']:,} řádků.",
  f"  Shodný bajt ve všech 12 bajtech A/G: {r['repeat_six_words_rows']:,} ({r['repeat_six_words_rows']/r['rows']:.5%}).",
  f"  Teplota odpovídá stejnému slovu (s tolerancí zaokrouhlení): {r['temperature_same_word_rows']:,} řádků.",
  f"  První výskyt: {r['first_repeated_word_s']:.6f} s. Souvislé úseky bez vzoru >=1 s: {r['clean_spans_ge1s']}.",
  f"  Čerstvé řádky bez přesné šestiosé shody po prvním výskytu: {r['nonpattern_fresh_rows_after_first_bad']}; jde o izolované výjimky, nikoli obnovenou souvislou jízdu."])
lines+=['','KONKRÉTNÍ PŘÍKLAD',
 '180, čas 0,000526 s: ax=ay=az=-0,00049 g; gx=gy=gz=-0,061 °/s.',
 'Při rozsazích ±16 g / ±2000 °/s převod dává šestkrát -1 = 0xFFFF.',
 'Teplota 21,00 °C po zpětném převodu s rozlišením CSV odpovídá témuž slovu.',
 'Nejde jen o stejná fyzikální čísla v různých jednotkách: shoduje se rekonstruovaný digitální obsah.',
 'Všech 9 784 717 původně označených řádků má i silnější znak: horní a dolní bajt slova jsou stejné.',
 'Pouhé přehození os nebo endianity tento obsah neopraví. Nezávislé původní hodnoty v těchto řádcích chybí.',
 '', 'CO SE ZNOVU PROVĚŘILO',
 'Rozsahy se pro výpočet četly z každého původního řádku. Rozdíl proti původnímu pravidlu: 0 řádků.',
 'Čerstvost akcelerometru a gyroskopu se posuzovala samostatně; příznaky se v této sadě neliší.',
 'Za maskou poruch A/G se nenašel žádný čerstvý platný vzorek magnetometru.',
 'Ve 180 jsou po začátku poruchy 4 a ve 181 10 řádků bez přesné shody všech šesti slov.',
 'Tyto izolované výjimky leží mezi poruchami; část stále obsahuje opakované hodnoty, jiné skoky a saturaci.',
 'Nejde o novou souvislou trasu. Jsou zveřejněné v Izolovane_vyjimky.csv a audit.json.',
 'Na přechodu do poruchy ve 181 jsou navíc 3 neoznačené čerstvé vzorky ve smíšeném 10ms intervalu.',
 'Původní graf tento interval preventivně skryl celý. Takto krátký fragment neumožní doplnit trasu.',
 '', 'PŘÍČINA A MÍRA JISTOTY',
 'Doloženo: opakovaný obsah už je v původním CSV; nejde o chybné sestavení FIMU ani pozdější změnu SD dat.',
 'Ve zdrojovém sampleTask se kontroluje návratový stav readFIFO, nikoli opakovaný obsah vzorků.',
 'Úspěch přenosové funkce se tak mohl zaměnit za správné měření. CRC vzniká až nad těmito čísly.',
 'Přesný spouštěč (FIFO, komunikace, stav senzoru, chyba obsluhy) nelze z uložených CSV určit.',
 'Nelze prokázat vadný hardware. Firmware má tento stav detekovat a hlásit místo tichého pokračování.',
 'Základ převodu jednotek odpovídá firmware a datasheetu ICM-20948:',
 'https://invensense.tdk.com/wp-content/uploads/2024/03/DS-000189-ICM-20948-v1.6.pdf',
 '', 'CO JE V NOVÉM BALÍČKU',
 'Formule_IMU_revize_01.fimu obsahuje všech 38 původních CSV, původní odvozené řady a audit revize.',
 'Žádné chybné hodnoty nebyly interpolací vydány za měření; nové souvislé jízdy se nepodařilo doložit.',
 'Klasifikace nově odděluje integritu souboru, dostupnost měření a možnost odhadu trasy.',
 'Původní kandidátní model trasy 181 je zachovaný, nikoli nově potvrzený; není to GPS měření.',
 'Prohlížeč: Zobrazit i neplatná data nyní skutečně přepne na nefiltrované 100Hz průměry.',
 'Diagnostika ukáže i chybný obsah s červeným pozadím; fyzikální statistiky jej dál vylučují.',
 'Export původního CSV nadále poskytuje všechny původní řádky v plném vzorkování.',
 '', 'DALŠÍ KROK',
 'Revize jízdních PDF naváže na tuto kontrolu. Stávající PDF se v kroku 01 nepřepisují.',
 'Jejich maxima nelze rozšířit o chybné úseky. Nová zpráva musí vysvětlit i selhání sběru a nejistoty.',
 'Firmware nebyl v tomto kroku změněn ani nahrán do desky.']
(OUT/'CTI_ME_REVIZE.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
exceptions=[]
for r in affected:
 for row in r['after_bad_examples']:exceptions.append(dict(file=r['file'],**row,assessment='isolated_unverified_not_a_recovered_track'))
with (OUT/'Izolovane_vyjimky.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(exceptions[0]));w.writeheader();w.writerows(exceptions)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig=plt.figure(figsize=(13,8),layout='constrained');grid=fig.add_gridspec(2,3,height_ratios=[1,1.2]);ax=fig.add_subplot(grid[0,:])
for i,r in enumerate(affected):
 pct=100*r['repeat_six_words_rows']/r['rows'];ax.barh(i,100-pct,color='#238477');ax.barh(i,pct,left=100-pct,color='#c6504b')
 ax.text(1,i,f"{r['bytes']/1e6:.0f} MB · {pct:.5f} % opakovaný bajt",va='center',color='white',fontweight='bold')
ax.set(yticks=range(3),yticklabels=['Záznam 178','Záznam 180','Záznam 181'],xlim=[0,100],xlabel='Podíl skutečných řádků CSV [%]',title='Velikost souboru neznamená množství použitelného měření');ax.invert_yaxis()
for col,r in enumerate(affected):
 at=r['first_repeated_word_s'];parts=[];p=Path('./input/logs')/r['file']
 for d in pd.read_csv(p,chunksize=100000,usecols=['time_us','ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps']):
  t=d.time_us/1e6;sub=d.loc[(t>=max(0,at-.3))&(t<at+.6)]
  if len(sub):parts.append(sub)
  if t.iloc[-1]>at+.6:break
 d=pd.concat(parts);t=d.time_us.to_numpy()/1e6;words=np.rint(d.iloc[:,1:].to_numpy()*np.array([2048]*3+[16.384]*3))
 ax=fig.add_subplot(grid[1,col]);colors=['#c6504b','#238477','#356f9f','#9c59a4','#b58e28','#333333']
 for j in range(6):ax.plot(t-at,words[:,j],color=colors[j],lw=1,alpha=.75,label=['aX','aY','aZ','gX','gY','gZ'][j])
 ax.axvspan(0,.6,color='#c6504b',alpha=.10);ax.axvline(0,color='#888',lw=.8);ax.grid(alpha=.15)
 ax.set(title=f"{r['id'].split('_')[1].lstrip('0')} · začátek {at:.6f} s",xlabel='Čas od prvního opakování [s]',ylabel='Zpětně převedené 16bitové slovo')
 if col==0:ax.legend(ncol=3,fontsize=8)
fig.suptitle('Nezávislá revize originálních CSV · šest kanálů se po poruše překrývá',fontsize=15,fontweight='bold')
fig.savefig(OUT/'Dukaz_poruchy.png',dpi=150);plt.close(fig)

target=OUT/'Formule_IMU_revize_01.fimu';partial=OUT/'Formule_IMU_revize_01.partial'
assert not target.exists() and not partial.exists(), 'Preserve existing revision'
with zipfile.ZipFile(ROOT/'output/Formule_IMU.fimu') as source, zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as dest:
 manifest=json.loads(source.read('manifest.json'));manifest['revision']='01-integrity-recheck';manifest['quality_audit_member']='audit/revision01.json'
 for r in manifest['results']['files']:
  q=records[r['id']];r['integrity_verified']=True;r['revision01']=q
  if q['repeat_six_words_rows']:
   r['evidence']+=f" Revize 01: originál a FIMU shodné; CRC bez chyby. {q['repeat_six_words_rows']:,} řádků obsahuje opakovaný bajt ve všech osách; {q['nonpattern_fresh_rows_after_first_bad']} izolovaných výjimek po začátku poruchy netvoří obnovenou jízdu. Pro kontrolu zapněte Zobrazit i neplatná data."
  else:r['evidence']+=' Revize 01: soubor je neporušený, bez opakovaného digitálního vzoru. Nezařazení do modelu trasy neznamená poškozený soubor; pohyb a stání nelze určit jen z velikosti souboru.'
 for i,entry in enumerate(source.infolist()):
  if entry.filename=='manifest.json':continue
  with source.open(entry) as a,dest.open(entry.filename,'w') as b:shutil.copyfileobj(a,b,1024*1024)
  if i%20==0:print('Repacked',i,flush=True)
 dest.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,allow_nan=False).encode())
 dest.write(OUT/'audit.json','audit/revision01.json')
 for name in ['CTI_ME_REVIZE.txt','Prehled_revize.csv','Dukazy_puvodnich_radku.csv','Izolovane_vyjimky.csv','Dukaz_poruchy.png']:dest.write(OUT/name,'audit/'+name)
with zipfile.ZipFile(partial) as z:
 for r in manifest['runs']:
  with z.open(r['raw_member']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==r['sha256']
  ar=np.frombuffer(z.read(r['derived_member']),dtype='<f4').reshape(-1,18);assert len(ar)==r['derived_rows']
 assert z.testzip() is None
partial.rename(target)
shutil.copy2(ROOT/'output/Prohlizec_IMU.html',OUT/'Prohlizec_IMU.html')
items=['Formule_IMU_revize_01.fimu','Prohlizec_IMU.html','CTI_ME_REVIZE.txt','audit.json','Prehled_revize.csv','Dukazy_puvodnich_radku.csv','Izolovane_vyjimky.csv','Dukaz_poruchy.png']
checks={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in items}
(OUT/'SHA256.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
with zipfile.ZipFile(OUT/'Revize_01_aplikace_a_data.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
 for name in [*items,'SHA256.json']:z.write(OUT/name,name,compress_type=zipfile.ZIP_STORED if name.endswith('.fimu') else zipfile.ZIP_DEFLATED)
print('Verified revision',target.stat().st_size,'bytes; originals and derived rows retained.',flush=True)
