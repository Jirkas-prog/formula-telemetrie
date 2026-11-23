from pathlib import Path
import json
p=Path(__file__).resolve().parent/'output/results.json';r=json.loads(p.read_text(encoding='utf-8'))
for x in r['files']:
 if int(x['id'].split('_')[1])<=150:x['evidence']='Charakter signálu odpovídá testu nebo manipulaci; pro jízdu nepoužito.'
p.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
