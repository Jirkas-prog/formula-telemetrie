"""Embed the shared analysis code into the standalone offline HTML."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parent
p=ROOT/'app/viewer.html';s=p.read_text(encoding='utf-8')
if 'id="analysisPanel"' not in s:
    css='''
.analysisPanel{margin:14px 0}.analysisTitle{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.analysisTitle h2{margin:0}.analysisPanel summary{font-size:14px}.analysisPanel input,.analysisPanel select{min-height:40px;border:1px solid var(--line);border-radius:7px;padding:7px;background:white;color:var(--ink);max-width:100%;width:100%}.analysisControls{display:flex;flex-wrap:wrap;align-items:end;gap:10px;margin:12px 0}.analysisControls label{font-size:12px;color:var(--muted);flex:1 1 140px;min-width:0}.analysisControls button{flex:0 1 auto}.peakActions{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.peakActions button{padding:5px 9px;font-size:12px;min-height:38px}.brakeEvents{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;max-height:520px;overflow:auto;margin-top:12px}.brakeEvent{padding:12px;border:1px solid var(--line);border-left:3px solid var(--red);border-radius:8px;min-width:0;background:#fff}.brakeEvent p{margin:7px 0;overflow-wrap:anywhere}.eventHeading{display:flex;justify-content:space-between;gap:8px}.eventHeading strong{font-size:17px}.eventHeading span{font-variant-numeric:tabular-nums;color:var(--muted)}.eventActions{display:flex;gap:6px;flex-wrap:wrap}.eventActions button{font-size:12px;padding:7px 9px;min-height:40px}.statsTable small{display:block;font-size:11px;color:var(--muted)}.statsTable button{padding:5px 8px;min-height:36px;margin:2px}.statsTable td:first-child{font-weight:600}.statsTable{white-space:normal}#analysisScope,#analysisMessage,#auditScope{overflow-wrap:anywhere}#analysisMessage{color:var(--green);min-height:20px}.auditTable{white-space:normal}.auditTable td{overflow-wrap:anywhere}.auditTable button{font-size:12px;white-space:nowrap}.analysisPanel .tablewrap{max-height:480px}@media(max-width:800px){.brakeEvents{grid-template-columns:1fr}}@media(max-width:600px){.analysisControls button{width:100%}.statsTable thead{display:none}.statsTable,.statsTable tbody{display:block}.statsTable tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px 0;border-bottom:1px solid var(--line)}.statsTable td{border:0;padding:0;overflow-wrap:anywhere}.statsTable td:first-child{grid-column:1/-1}.statsTable td:not(:first-child)::before{content:attr(data-label);display:block;font-size:11px;color:var(--muted)}.statsTable button{min-height:40px}.auditTable th,.auditTable td{padding:6px 3px;font-size:11px}.auditTable button{padding:6px 4px;min-height:40px}}
'''
    s=s.replace('</style>',css+'</style>',1)
    panel='''<section class="panel analysisPanel" id="analysisPanel">
<div class="analysisTitle"><h2>Statistiky a brzdné události</h2><button id="refreshAnalysis">Přepočítat okno</button></div>
<p id="analysisScope" class="muted"></p><div id="analysisCards" class="cards"></div>
<p id="analysisNote" class="muted"></p><p id="analysisExposure"></p><p id="analysisMessage" role="status" aria-live="polite"></p>
<details><summary>Statistiky všech os · minimum, maximum a rozptyl</summary><p id="axesMode" class="muted"></p><p class="muted">Klepnutí na extrém přesune kurzor. Tlačítko ⚑ uloží bod. σ je populační směrodatná odchylka; magnetometr počítá jen dostupné 100Hz intervaly.</p><div class="tablewrap"><table class="statsTable"><thead><tr><th>Signál</th><th>Minimum / čas</th><th>Maximum / čas</th><th>Průměr / σ</th><th>Platné vzorky</th></tr></thead><tbody id="axisStats"></tbody></table></div></details>
<details open><summary>Kandidáti brzdění <span id="eventCount" class="muted"></span></summary>
<div class="analysisControls"><label>Práh zpomalení [g]<input id="brakeThreshold" type="number" min=".05" max="2" step=".05" value=".30"></label><label>Minimální délka [s]<input id="brakeDuration" type="number" min=".05" max="30" step=".05" value=".30"></label><label>Řazení<select id="brakeSort"><option value="peak">Nejsilnější nejdříve</option><option value="time">Podle času</option></select></label><button id="exportEvents">Export událostí CSV</button></div>
<p id="eventRule" class="muted"></p><div id="eventList" class="brakeEvents"></div></details>
<details><summary>Porovnání extrémů všech záznamů · audit původních CSV</summary><p id="auditScope" class="muted"></p><div class="tablewrap"><table class="auditTable"><thead><tr><th>Záznam</th><th>Obsah</th><th>Zpomalení 2 Hz</th><th>Syrová špička</th></tr></thead><tbody id="auditRows"></tbody></table></div></details>
</section>
'''
    s=s.replace('<div class="layout">',panel+'<div class="layout">',1)
    s=s.replace('function init(){loadFlags();','function init(){loadFlags();renderAudit();',1)
    s=s.replace("meta=manifest.results.files.find(f=>f.id===id);","meta=manifest.results.files.find(f=>f.id===id);prepareAnalysis();",1)
    s=s.replace('viewCache.clear();renderFlagMarks();draw()}','viewCache.clear();renderFlagMarks();draw();scheduleAnalysis()}',1)
    s=s.replace("for(const id of ['filtered','showbad','mapmode'])$(id).onchange=()=>{viewCache.clear();draw()}","for(const id of ['filtered','showbad','mapmode'])$(id).onchange=()=>{viewCache.clear();draw();if(id==='filtered')scheduleAnalysis()}",1)
    # Upgrade the longitudinal/lateral graph to the same 100 Hz filtered series as statistics.
    s=s.replace('ar=derived?trajectory:data,stride=derived?TC:C','ar=derived?bodyData:data,stride=derived?5:C')
    s=s.replace('Math.floor((start-650.005)*10)','Math.floor((start-(ar[0]||650.005))*100)')
    s=s.replace('Math.ceil((end-650.005)*10)','Math.ceil((end-(ar[0]||650.005))*100)')
    s=s.replace('Math.round((cursor-ar[0])*10)','Math.round((cursor-ar[0])*100)')
    s=s.replace("drawChart('body',[8,9],true)","drawChart('body',[1,2],true)")
    s=s.replace("values('bodyValues',[8,9],true)","values('bodyValues',[1,2],true)")
    s=s.replace('<script>\n\'use strict\';const $=', '<script id="analysis-core"></script>\n<script id="deceleration-audit" type="application/json">[]</script>\n<script>\n\'use strict\';const $=',1)
    s=s.replace('// Local QA/demo','// ANALYSIS-UI-BEGIN\n// ANALYSIS-UI-END\n// Local QA/demo',1)
core=(ROOT/'app/analysis_core.js').read_text(encoding='utf-8')
csv=(ROOT/'app/csv_import.js').read_text(encoding='utf-8')
csv_ui=(ROOT/'app/csv_ui.js').read_text(encoding='utf-8')
if 'id="csv-import"' not in s:
    s=s.replace('<script id="analysis-core">','<script id="csv-import"></script>\n<script id="analysis-core">',1)
    s=re.sub(r'async function openFile\(f\).*?\nfunction init\(', '// CSV-UI-BEGIN\n// CSV-UI-END\nfunction init(',s,count=1)
s=re.sub(r'<script id="csv-import">[\s\S]*?</script>',lambda _: '<script id="csv-import">\n'+csv+'</script>',s,count=1)
s=re.sub(r'// CSV-UI-BEGIN[\s\S]*?// CSV-UI-END',lambda _: '// CSV-UI-BEGIN\n'+csv_ui+'\n// CSV-UI-END',s,count=1)
s=s.replace('Statistiky všech os · minimum, maximum a rozptyl','Statistiky všech os · minima, maxima a průměry')
ui=(ROOT/'app/analysis_ui.js').read_text(encoding='utf-8')
s=re.sub(r'<script id="analysis-core">[\s\S]*?</script>',lambda _: '<script id="analysis-core">\n'+core+'</script>',s,count=1)
s=re.sub(r'// ANALYSIS-UI-BEGIN[\s\S]*?// ANALYSIS-UI-END',lambda _: '// ANALYSIS-UI-BEGIN\n'+ui+'\n// ANALYSIS-UI-END',s,count=1)
audit=json.loads((ROOT/'output/audit_deceleration_all.json').read_text())['files']
inv={r['file']:r for r in json.loads((ROOT/'output/inventory.json').read_text())}
records=[]
for row in audit:
    obj={'id':inv[row['file']]['id'],'sha256':inv[row['file']]['sha256'],'category':row['classification']}
    for key,source in [('raw','valid_raw_peak'),('filtered','valid_filtered_2Hz_peak')]:
        a=row[source];obj[key]={'g':-a['acceleration_g'],'time':a['time_s']} if a and a['acceleration_g']<0 else None
    records.append(obj)
text=json.dumps(records,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
s=re.sub(r'<script id="deceleration-audit" type="application/json">[\s\S]*?</script>',lambda _: '<script id="deceleration-audit" type="application/json">'+text+'</script>',s,count=1)
p.write_text(s,encoding='utf-8');(ROOT/'output/Prohlizec_IMU.html').write_text(s,encoding='utf-8')
print('Viewer rebuilt with shared analysis core and full-file audit.')
