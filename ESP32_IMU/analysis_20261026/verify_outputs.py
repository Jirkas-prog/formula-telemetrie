from ingest import ROOT
import json,zipfile,hashlib,numpy as np
from PIL import Image,ImageOps,ImageDraw
from pypdf import PdfReader
from openpyxl import load_workbook
out=ROOT/'output';r=json.loads((out/'results.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(out/'Formule_IMU.fimu') as z:
 assert len(z.namelist())==len(set(z.namelist()))
 m=json.loads(z.read('manifest.json'));assert m['results']==r
 for run in m['runs']:
  h=hashlib.sha256()
  with z.open(run['raw_member']) as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
  assert h.hexdigest()==run['sha256'],run['id']
  a=np.frombuffer(z.read(run['derived_member']),dtype='<f4').reshape(-1,18)
  assert len(a)==run['derived_rows'] and np.all(np.diff(a[:,0])>0)
 print('Archive: 38 original CSV SHA-256 hashes match, derived shapes and times valid.')
book=load_workbook(out/'Soupiska_zaznamu.xlsx',data_only=False)
assert book['Soubory'].max_row>=46
for i,row in enumerate(r['files'],9):
 assert book['Soubory'].cell(i,1).value==row['file']
 assert abs(book['Soubory'].cell(i,9).value-row['digital_fault_fraction'])<1e-10
cached=load_workbook(out/'Soupiska_zaznamu.xlsx',data_only=True)
assert cached['Soubory']['B4'].value==38 and cached['Soubory']['F4'].value==3
print('XLSX: 38 records, 2 sheets, numeric values and cached summary formulas verified.')
pdf=PdfReader(ROOT/'report/main.pdf');print('PDF pages',len(pdf.pages))
for i,p in enumerate(pdf.pages,1):
 text=p.extract_text();assert len(text)>200
 assert '@LAPS@' not in text and '\ufffd' not in text
 print(i,text.splitlines()[2][:80] if len(text.splitlines())>2 else text[:80])
files=sorted((out/'pdf-qa').glob('page-*.png'))
for batch in range(0,len(files),4):
 images=[Image.open(p).convert('RGB') for p in files[batch:batch+4]];w=max(im.width for im in images);h=max(im.height for im in images)
 grid=Image.new('RGB',(2*(w+12),2*(h+28)), '#cbd3d8');draw=ImageDraw.Draw(grid)
 for j,im in enumerate(images):x=(j%2)*(w+12);y=(j//2)*(h+28);grid.paste(im,(x,y+22));draw.text((x+5,y+3),f'Page {batch+j+1}',fill='black')
 grid.save(out/'pdf-qa'/f'contact-{batch//4+1}.png')
print('Checks complete')
