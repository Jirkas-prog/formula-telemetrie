import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(fileURLToPath(import.meta.url)),out=path.join(root,'output');
const r=JSON.parse(await fs.readFile(path.join(out,'results.json'),'utf8'));
const wb=Workbook.create(),s=wb.worksheets.add('Soubory'),d=wb.worksheets.add('Úseky a kola');
for(const sheet of [s,d]){sheet.showGridLines=false;sheet.getRange('A1:L65').format.font={name:'Arial',size:10,color:'#203344'};sheet.getRange('A1:L65').format.verticalAlignment='center';sheet.getRange('A1:L65').format.rowHeight=24;sheet.tabColor='#203b55'}
function title(sh,cell,text){sh.getRange(cell).values=[[text]];sh.getRange(cell).format.font={size:15,bold:true};}
function head(sh,range){sh.getRange(range).format={fill:'#203b55',font:{name:'Arial',size:10,bold:true,color:'#ffffff'},horizontalAlignment:'center',verticalAlignment:'center',rowHeight:32,wrapText:true};}
title(s,'A2','Soupiska záznamů IMU formule');
s.getRange('A3').values=[['Klasifikace podle měření; „neprokázáno“ neznamená, že manévr určitě neproběhl.']];
s.getRange('A4').values=[['Soubory']];s.getRange('B4').formulas=[['=COUNTA(A9:A46)']];s.getRange('C4').values=[['Celkem [h]']];s.getRange('D4').formulas=[['=SUM(B9:B46)/60']];s.getRange('D4').setNumberFormat('0.00');
s.getRange('E4').values=[['S digitální poruchou']];s.getRange('F4').formulas=[['=COUNTIFS(I9:I46,">0")']];
s.getRange('A6').values=[['Souvislá doba = úseky bez zjištěného digitálního vzoru ≥1 s. Není to doba jízdy.']];
const headers=['Soubor','Doba [min]','Souvislá data [min]','Zařazení','Dlouhá trasa / rovinka','Delší kola','Osmička','Kruh / skidpad','Chybné řádky [%]','Jistota zařazení','Důvod / použití'];
const rows=r.files.map(x=>[x.file,x.duration_s/60,x.valid_contiguous_s/60,x.category,x.long_route,x.long_laps,x.figure_eight,x.skidpad,x.digital_fault_fraction,x.confidence,x.evidence]);
s.getRange('A8:K46').values=[headers,...rows];s.tables.add('A8:K46',true,'SoupiskaIMU');head(s,'A8:K8');
const widths=[32,12,16,43,42,33,48,18,16,17,92];widths.forEach((w,i)=>s.getRangeByIndexes(0,i,46,1).format.columnWidth=w);
s.getRange('B9:C46').setNumberFormat('0.00');s.getRange('I9:I46').setNumberFormat('0.00%');s.getRange('B9:C46').format.horizontalAlignment='right';s.getRange('I9:I46').format.horizontalAlignment='right';
s.getRange('I9:I46').conditionalFormats.add('cellIs',{operator:'greaterThan',formula:0,format:{fill:'#fbe6e4',font:{bold:true,color:'#9b322b'}}});
s.getRange('D9:D46').conditionalFormats.add('containsText',{text:'Jízda:',format:{fill:'#e1efe8',font:{bold:true,color:'#236a54'}}});
s.freezePanes.freezeRows(8);s.freezePanes.freezeColumns(1);
title(d,'A2','Použitelné úseky a kandidáti kol');
d.getRange('A3').values=[['Všechny časy jsou od začátku daného CSV. Bez referenční polohy nelze potvrdit průjezd startovní čárou.']];
const segments=[
 ['boot_000178_run_001.csv',0,179.17,'Klidový kandidát','vysoká','Následující část je poškozená při akvizici.'],
 ['boot_000180_run_001.csv',0,3521.4,'Neplatná data','vysoká','Žádný souvislý validní úsek ≥1 s.'],
 ['boot_000181_run_001.csv',0,677,'Převážně klid','střední','Magnetometr končí v 534,295 s.'],
 ['boot_000181_run_001.csv',677,710,'Rozjezd / manévry','střední','Změny podélného zrychlení a směru.'],
 ['boot_000181_run_001.csv',710,772,'Slalom / delší přejezd','střední','Dlouhá rovinka je pouze kandidát; střídají se zatáčky.'],
 ['boot_000181_run_001.csv',781.305,985.605,'4 kandidáti delších kol','střední','Podobné zatáčky a přibližně jedna otáčka na úsek.'],
 ['boot_000181_run_001.csv',1008.24,10665.266637,'Digitální porucha','vysoká','Nevyužívat pro rekonstrukci pohybu.']];
d.getRange('A6:G13').values=[['Soubor','Od [s]','Do [s]','Délka [s]','Typ úseku','Jistota','Podklad'],...segments.map(x=>[x[0],x[1],x[2],null,x[3],x[4],x[5]])];
for(let i=7;i<=13;i++)d.getRange(`D${i}`).formulas=[[`=C${i}-B${i}`]];d.tables.add('A6:G13',true,'UsekyIMU');head(d,'A6:G6');d.getRange('B7:D13').setNumberFormat('0.00');
title(d,'A16','Časy kol jsou kandidáti, vzdálenosti jsou modelové');
d.getRange('A17').values=[['Polohové uzavření je předpoklad. Uvedená chyba je neuzavření modelu před korekcí, nikoli známá chyba vůči GPS.']];
d.getRange('A19:I23').values=[['Kandidát','Od [s]','Do [s]','Čas [s]','Otočení [°]','Model délky [m]','Neuzavření [m]','Neuzavření / délka','Korelace s předchozím'],...r.laps.map(x=>[x.lap,x.start_s,x.end_s,null,x.turn_deg,x.model_distance_m,x.closure_error_m,null,x.profile_correlation_previous??'n.a.'])];
for(let i=20;i<=23;i++){d.getRange(`D${i}`).formulas=[[`=C${i}-B${i}`]];d.getRange(`H${i}`).formulas=[[`=G${i}/F${i}`]]}head(d,'A19:I19');d.getRange('B20:G23').setNumberFormat('0.0');d.getRange('H20:H23').setNumberFormat('0.0%');d.getRange('I20:I23').setNumberFormat('0.000');d.getRange('I20:I23').format.horizontalAlignment='right';
title(d,'A26','Drift v klidových kandidátech');
d.getRange('A27').values=[['30 s kalibrace + nezávislá integrace; nejde o změřenou polohovou chybu během jízdy.']];
d.getRange('A29:F32').values=[['Horizont [s]','Počet oken','Průměr [m]','Medián [m]','95. percentil [m]','Pevná orientace: medián [m]'],...r.drift_summary.map(x=>[x.horizon_s,x.windows,x.gyro_mean_m,x.gyro_median_m,x.gyro_p95_m,x.fixed_median_m])];head(d,'A29:F29');d.getRange('C30:F32').setNumberFormat('0.00');
d.getRange('A35').values=[['Osmička / skidpad: v použitelných datech nepotvrzeno. Střídání levé a pravé zatáčky samo o sobě nestačí.']];
d.getRange('A37').values=[['Zdroj: 38 CSV z dodané složky logs. Detailní SHA-256 a kontrola CRC jsou v manifestu datového balíčku.']];
[32,14,14,14,32,28,73,23,27].forEach((w,i)=>d.getRangeByIndexes(0,i,38,1).format.columnWidth=w);
d.freezePanes.freezeRows(6);d.freezePanes.freezeColumns(1);
wb.recalculate();
console.log((await wb.inspect({kind:'region',sheetId:'Soubory',range:'A4:F4',maxChars:2000})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?',options:{useRegex:true,maxResults:20},maxChars:2000})).ndjson);
for(const [sheet,name] of [[s,'excel-soubory'],[d,'excel-useky']]){const png=await wb.render({sheetName:sheet.name,range:sheet===s?'A1:F17':'A16:I32',scale:1,format:'png'});await fs.writeFile(path.join(out,name+'.png'),new Uint8Array(await png.arrayBuffer()))}
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'Soupiska_zaznamu.xlsx'));
console.log('XLSX complete');
