"""Create and fully verify the portable handover without changing any input."""
from pathlib import Path
import hashlib, json, re, zipfile
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
SOURCE=Path('./input/logs')
NAME='Formule_IMU_komplet_2026-10-26_v2_CSV'
FINAL=OUT/(NAME+'.zip')
PARTIAL=OUT/(NAME+'.partial')
assert not FINAL.exists() and not PARTIAL.exists(), 'Archive already exists; preserve it.'
CHUNK=1024*1024
files={}
def add(path,destination):
    assert path.is_file(), path
    assert destination not in files, destination
    files[destination]=path

add(OUT/'pdf/Drivetrain_jizdni_data.pdf','01_Dokumenty/01_Drivetrain_jizdni_data.pdf')
add(OUT/'Analyza_jizd_a_zavery.pdf','01_Dokumenty/02_Analyza_jizd_a_zavery.pdf')
add(OUT/'Analyza_IMU_formule.pdf','01_Dokumenty/03_Puvodni_analyza_IMU.pdf')
add(OUT/'Prohlizec_IMU.html','02_Aplikace/Prohlizec_IMU.html')
add(OUT/'Formule_IMU.fimu','03_Data/Formule_IMU.fimu')
raw=sorted(SOURCE.iterdir())
assert all(p.is_file() for p in raw), 'Unexpected source directory: inspect before packaging.'
assert sum(p.suffix=='.csv' for p in raw)==38
assert sum(p.suffix=='.json' for p in raw)==38
for p in raw: add(p,'03_Data/Puvodni_soubory/'+p.name)
for name in ['Soupiska_zaznamu.xlsx','Brzdne_udalosti.csv','audit_deceleration_all.csv','audit_deceleration_all.json',
             'Analyza_jizd.json','drive_raw.json','inventory.json','quality.json','results.json','manifest.json']:
    add(OUT/name,'04_Tabulky_a_exporty/'+name)
for p in sorted((ROOT/'report_drivetrain/data').glob('*')):add(p,'04_Tabulky_a_exporty/Drivetrain/'+p.name)
add(ROOT/'report_drivetrain/CTI_ME.txt','04_Tabulky_a_exporty/Drivetrain/CTI_ME.txt')
for source,name in [('report_drivetrain','01_Drivetrain'),('report_jizdy','02_Analyza_jizd'),('report','03_Puvodni_analyza')]:
    folder=ROOT/source
    add(folder/'main.tex',f'05_Zdroje_LaTeX/{name}/main.tex')
    if (folder/'values.tex').is_file():add(folder/'values.tex',f'05_Zdroje_LaTeX/{name}/values.tex')
    for p in sorted((folder/'images').glob('*')):add(p,f'05_Zdroje_LaTeX/{name}/images/'+p.name)
    tex=(folder/'main.tex').read_text(encoding='utf-8')
    for image in re.findall(r'\\fig\{([^}]+)\}',tex):assert (folder/'images'/image).is_file(),image

# The distributed app has no external scripts, stylesheets or image dependencies.
class Dependencies(HTMLParser):
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','img','iframe') and a.get('src'):raise AssertionError((tag,a['src']))
        if tag=='link' and a.get('rel')=='stylesheet':raise AssertionError(a)
Dependencies().feed((OUT/'Prohlizec_IMU.html').read_text(encoding='utf-8'))
assert (OUT/'Prohlizec_IMU.html').read_bytes()==(ROOT/'app/viewer.html').read_bytes()

readme='''FORMULE IMU - KOMPLETNÍ BALÍČEK / 26. 10. 2026

RYCHLÝ START
1. Celý ZIP rozbalte do běžné složky. Prohlížeč nespouštějte přímo uvnitř ZIPu.
2. Otevřete 02_Aplikace/Prohlizec_IMU.html v aktuálním Microsoft Edge nebo Chrome.
3. V aplikaci klepněte na „Otevřít data“ a vyberte 03_Data/Formule_IMU.fimu.
4. Aplikace otevře výchozí použitelný jízdní úsek záznamu 181. Další záznam
   vyberete v seznamu. Karty statistik a brzdných událostí jsou pod přehráváním.
5. Tím samým tlačítkem lze nově otevřít i samostatný CSV log, exportovaný
   výřez nebo Drivetrain/jizda_100Hz_2Hz.csv. Podrobnosti jsou v NAVOD.txt.

Není potřeba instalovat aplikaci, Python ani webový server. Pro prohlížení
přiložených dat není potřeba internet ani připojená ESP32 deska. Soubor FIMU
se vybírá ručně kvůli běžnému zabezpečení přístupu k místním souborům.

01_DOKUMENTY - TŘI PDF
01_Drivetrain_jizdni_data.pdf (9 stran)
  Podklad pro výpočtáře: trvání zatížení, současné podélné a boční stavy,
  klouzavé průměry a podmíněné vztahy pro přepočet na síly a momenty.
02_Analyza_jizd_a_zavery.pdf (8 stran)
  Brzdné události, kombinované manévry, porovnání pasáží a meze závěrů.
03_Puvodni_analyza_IMU.pdf (13 stran)
  Původní audit kvality, průzkumná rekonstrukce trasy a klasifikace souborů.

Čtěte přednostně dokumenty 01 a 02. Původní dokument 03 je zachován pro
dohledatelnost. Novější dokument 02 zpřesňuje výpočty a interpretaci:
kandidáti kol nejsou potvrzená kola stejné trati a jejich časy nelze vydávat
za ověřené zlepšení. Rychlost a poloha v aplikaci jsou podmíněné modelové
odhady, ne referenční měření. Pro interpretaci vozidlových maxim používejte
novější reporty a sekci statistik v aktuální aplikaci.

02_APLIKACE
Samostatný HTML prohlížeč s časovou osou, grafy, odhadem trasy, statistikami,
nastavitelným hledáním brzdných událostí, vlaječkami a exportem výřezů.
Podrobné ovládání je v souboru NAVOD.txt v této složce.

03_DATA
Formule_IMU.fimu: ZIPový datový formát obsahující všech 38 původních CSV,
odvozené přehledové řady, podmíněný model trasy a manifest se SHA-256.
Puvodni_soubory/: všech 38 původních CSV a 38 doprovodných JSON souborů
ze zdrojové složky, zachovaných beze změny. Jsou přiloženy samostatně pro
snadný import do dalších programů. CSV jsou proto záměrně také uvnitř FIMU.
Velká původní CSV mohou překročit kapacitu jednoho listu Excelu; pro práci
s konkrétní pasáží lze z aplikace exportovat menší výřez.

04_TABULKY_A_EXPORTY
Soupiska_zaznamu.xlsx: přehled všech záznamů a původní klasifikace.
Brzdne_udalosti.csv: kandidáti při výchozích parametrech 0,30 g / 0,30 s.
audit_deceleration_all.*: kontrola maxim napříč všemi 38 soubory.
Analyza_jizd.json: výsledky navazující analýzy.
Drivetrain/: filtrovaný 100Hz průběh, zatěžovací stavy, průměry a časové podíly.
Další JSON: inventář, kvalita, původní model a struktura datového formátu.
Vozidlová data v exportu Drivetrain používají filtr 2 Hz; nejsou to syrové
500Hz vzorky. Podrobnosti a jednotky jsou v jeho souboru CTI_ME.txt.

05_ZDROJE_LATEX
Tři editovatelné projekty, každý s main.tex a potřebnými obrázky;
drivetrain má také values.tex. Ke kompilaci lze použít XeLaTeX nebo Tectonic.
Ke čtení hotových PDF nic z toho nepotřebujete.

DŮLEŽITÉ PRO INTERPRETACI
Jízdní závěry vycházejí hlavně z 330 s v souboru boot_000181_run_001.csv,
čas 677-1007 s. Velká část ostatních dat obsahuje digitální poruchu senzoru.
Původní CSV jsme zachovali, včetně vadných částí; nejde o opravená měření.
Orientace senzoru je odhadnutá, dynamický náklon není nezávisle ověřený.
Údaje v dokumentech nejsou přímo měřeným momentem, výkonem, rychlostí,
brzdným tlakem ani garantovaným maximem schopností vozidla.

OSOBNÍ VLAJEČKY
Vlastní značky vytvořené v prohlížeči se ukládají v jeho místním úložišti.
Tento souborový balíček je automaticky nepřebírá. Pro přenos mezi počítači
nejprve v původním prohlížeči použijte „Uložit vlaječky do souboru“ a na
novém počítači „Načíst vlaječky“. Přenos souboru FIMU sám značky nepřenáší.
Testovací značky a QA výřezy nejsou součástí dodávky.

INTEGRITA
MANIFEST_SHA256.json obsahuje velikosti a SHA-256 všech dodaných souborů
kromě samotného manifestu. Při sestavení byly všechny položky finálního ZIPu
znovu přečteny a porovnány. Všech 38 CSV v původní složce, FIMU i tomto
archivu má shodný obsah podle SHA-256. Původní soubory ani firmware se nemění.
'''

manual='''OFFLINE PROHLÍŽEČ IMU

Otevřete Prohlizec_IMU.html v Edge/Chrome a ručně vyberte soubor
../03_Data/Formule_IMU.fimu nebo samostatné CSV tlačítkem „Otevřít data“.
Použijte rozbalenou složku; localhost ani běžící server nejsou potřeba.

PŘÍMÉ OTEVÍRÁNÍ CSV
Podporovány jsou původní logy ESP32, exportované časové výřezy a časové
řady drivetrainu. Souhrnné tabulky událostí nejsou vstupní časový záznam.
Časový sloupec: time_us (mikrosekundy), t_s nebo time_s (sekundy).
Osy senzoru: ax_g/ay_g/az_g, gx_dps/gy_dps/gz_dps, mx_uT/my_uT/mz_uT.
Vozidlové složky: ax_m_s2 a ay_m_s2, volitelně yaw_deg_s a az_dynamic_m_s2.
Oddělovač čárka nebo středník; desetinná čárka je podporovaná se středníkem.
Kódování UTF-8. Čas musí být relativní, neklesající a kratší než 20 000 s.

Načítání po blocích běží na pozadí, ukazuje průběh a lze je zrušit.
Grafy a statistiky používají 10ms průměry (100 Hz), původní vzorky zůstávají
zachované pro plný export. Prázdná pole se považují za chybějící měření.
Nová filtrace se na CSV neaplikuje; případné filtrované sloupce se převezmou.
Ze samotných os senzoru se neodhaduje orientace vůči autu, brzdění ani trasa.
U dodaných vozidlových složek fungují i statistiky a kandidáti zpomalení.
CRC se při tomto importu nekontroluje; plný původní audit je v balíčku FIMU.
Vlaječky flag_number a flag_label se načtou; jedno číslo 1–999999 na bod,
nejvýše jeden označený bod v každém 10ms intervalu. CSV a FIMU mají oddělené
místní sady značek. Pro přenos značek spolu s CSV použijte označený výřez.

ČASOVÁ OSA A GRAFY
Vyberte záznam, přehrajte jej nebo klepněte na graf pro přesun kurzoru.
Časové okno lze měnit poli Od/Do a ovládáním přiblížení. Grafy zobrazují
hodnoty ve stejném čase; trajektorie je dostupná jen pro odvozený model.
Statistiky os se přepočítávají pro zvolené okno. Vozidlové statistiky
používají 100 Hz a filtr 2 Hz v použitelném jízdním úseku záznamu 181.

BRZDNÉ UDÁLOSTI
Změňte práh a minimální délku. Volba „Zobrazit“ přesune pohled na událost,
„Maximum“ označí vrchol vlaječkou a „Hranice“ přidá dva body pro export.
Počet událostí závisí na nastavených parametrech. Jsou to kandidáti z IMU,
nikoliv změřená sešlápnutí brzdového pedálu. ID se při změně prahů přepočítají.

VLAJEČKY
Vyberte čas a použijte tlačítko vlaječky. Číslo, čas a popis lze změnit.
Každý záznam má vlastní značky; řadí se časově. Pro zálohu a přenos mezi
prohlížeči použijte „Uložit vlaječky do souboru“ / „Načíst vlaječky“.
Místní značky z jiné adresy prohlížeče se neobjeví automaticky.

EXPORT
Vyberte dvě různé vlaječky a „Export mezi vlaječkami“. Oba konce se zahrnou,
pořadí výběru se srovná. „Původní · všechny řádky“ zachovává původní vzorkování;
„Přehled · 100 Hz + filtr“ předává odvozená přehledová data.
Neoznačené řádky mají prázdné flag_number a flag_label. Původní CRC v exportu
s vlaječkami se jmenuje source_crc32 a platí jen pro původní pole.
„Export původního CSV“ vrátí neměněný zdroj bez přidaných vlaječek.
Export načítá data po blocích a lze jej zrušit. Pokud prohlížeč nepodporuje
přímý zápis na disk, paměťový export je omezen na 128 MB; zkraťte pak výřez.

ZDROJE
PDF jsou ve složce ../01_Dokumenty, Excel a CSV výsledky v ../04_Tabulky_a_exporty.
Všechny původní CSV lze otevřít přímo z ../03_Data/Puvodni_soubory.
'''
notes={
    '00_ZACNETE_ZDE.txt':readme.encode('utf-8-sig'),
    '02_Aplikace/NAVOD.txt':manual.encode('utf-8-sig'),
}

with zipfile.ZipFile(OUT/'Formule_IMU.fimu') as fimu:
    fm=json.loads(fimu.read('manifest.json'))
    assert len(fm['runs'])==38
    expected={r['file']:r['sha256'] for r in fm['runs']}
    assert set(expected)=={p.name for p in raw if p.suffix=='.csv'}
    for i,r in enumerate(fm['runs'],1):
        with fimu.open(r['raw_member']) as stream:
            sha=hashlib.file_digest(stream,'sha256').hexdigest()
        assert sha==r['sha256'], r['file']
        if i%10==0 or i==38:print(f'FIMU: verified original CSV {i}/38',flush=True)

entries=[]
with zipfile.ZipFile(PARTIAL,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
    for relative,content in notes.items():
        archive.writestr(NAME+'/'+relative,content)
        entries.append(dict(path=relative,bytes=len(content),sha256=hashlib.sha256(content).hexdigest()))
    for count,(relative,p) in enumerate(files.items(),1):
        before=p.stat(); sha=hashlib.sha256()
        info=zipfile.ZipInfo.from_file(p,NAME+'/'+relative)
        info.compress_type=zipfile.ZIP_STORED if p.suffix.lower()=='.fimu' else zipfile.ZIP_DEFLATED
        info._compresslevel=6
        with p.open('rb') as source,archive.open(info,'w') as target:
            while chunk:=source.read(CHUNK):sha.update(chunk);target.write(chunk)
        after=p.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns), p
        digest=sha.hexdigest()
        if p.parent==SOURCE and p.suffix=='.csv':assert digest==expected[p.name],p.name
        entries.append(dict(path=relative,bytes=before.st_size,sha256=digest))
        if count%10==0 or count==len(files):print(f'Packaged {count}/{len(files)} files',flush=True)
    manifest=dict(format='Formula IMU complete handover',version=1,date='2026-10-26',
        source_csv_count=38,source_json_count=38,pdf_count=3,files=entries)
    content=json.dumps(manifest,indent=2,ensure_ascii=False).encode('utf-8')
    archive.writestr(NAME+'/MANIFEST_SHA256.json',content)

print('Verifying every archived file (decompression + CRC + SHA-256)...',flush=True)
with zipfile.ZipFile(PARTIAL) as archive:
    assert len(archive.namelist())==len(entries)+1
    assert len(set(archive.namelist()))==len(archive.namelist())
    assert json.loads(archive.read(NAME+'/MANIFEST_SHA256.json'))==manifest
    for i,row in enumerate(entries,1):
        info=archive.getinfo(NAME+'/'+row['path']);assert info.file_size==row['bytes']
        with archive.open(info) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256'],row['path']
        if i%20==0 or i==len(entries):print(f'Archive verified {i}/{len(entries)} files',flush=True)
PARTIAL.rename(FINAL)
with FINAL.open('rb') as stream: final_sha=hashlib.file_digest(stream,'sha256').hexdigest()
(OUT/(NAME+'.sha256')).write_text(final_sha+'  '+FINAL.name+'\n',encoding='ascii')
print(json.dumps(dict(path=str(FINAL),bytes=FINAL.stat().st_size,unpacked_bytes=sum(r['bytes'] for r in entries),
                     files=len(entries)+1,sha256=final_sha),indent=2),flush=True)
