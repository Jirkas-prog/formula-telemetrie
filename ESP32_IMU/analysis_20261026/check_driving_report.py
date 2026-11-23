from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
from pypdf import PdfReader
from PIL import Image,ImageDraw
a=json.loads((ROOT/'output/Analyza_jizd.json').read_text())
assert len(a['events'])==102
assert abs(a['summary']['long']['min']+1.06690323)<1e-6
assert a['summary']['long']['n']==33000
assert abs(a['summary']['combined_braking_s']-32.09)<1e-6
assert a['source_file_count']==38 and a['source_total_rows']==12536353
pdf=PdfReader(ROOT/'report_jizdy/main.pdf');assert len(pdf.pages)==8
for i,p in enumerate(pdf.pages,1):
    text=p.extract_text();assert len(text)>500 and '\ufffd' not in text
    assert '@EVENT' not in text and '@SHA' not in text
    print(i,len(text),text.splitlines()[2][:85])
folder=ROOT/'output/report_jizdy_qa';files=sorted(folder.glob('page-*.png'))
assert len(files)==8
for batch in range(0,len(files),4):
    pages=[Image.open(p).convert('RGB') for p in files[batch:batch+4]]
    w=pages[0].width;h=pages[0].height;grid=Image.new('RGB',(w*2+24,h*2+60),'#dce3e6');draw=ImageDraw.Draw(grid)
    for j,page in enumerate(pages):
        x=(j%2)*(w+12);y=(j//2)*(h+30);grid.paste(page,(x,y+25));draw.text((x+8,y+5),'Page '+str(batch+j+1),fill='black')
    grid.save(folder/f'contact-{batch//4+1}.png')
print('Numeric checks and PDF text: PASS')
