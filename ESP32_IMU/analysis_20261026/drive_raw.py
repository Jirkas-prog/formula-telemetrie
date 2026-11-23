from ingest import ROOT,SOURCE,COLS
import pandas as pd,numpy as np,json
out=[]
for d in pd.read_csv(SOURCE/'boot_000181_run_001.csv',chunksize=100000):
 s=d[(d.time_us>=677000000)&(d.time_us<1007000000)&(d.accel_new==1)]
 if len(s):out.append(s)
 if d.time_us.iloc[-1]>1007000000:break
d=pd.concat(out);result={'samples':len(d),'flag_mismatches':int((d.accel_new!=d.gyro_new).sum()),'clip_rows':int((d.clip_mask!=0).sum()),'extrema':[]}
for col in COLS[:6]:
 imin=d[col].idxmin();imax=d[col].idxmax();result['extrema'].append({'axis':col,'min':float(d.loc[imin,col]),'min_time_s':float(d.loc[imin,'time_us']/1e6),'max':float(d.loc[imax,col]),'max_time_s':float(d.loc[imax,'time_us']/1e6),'p01':float(d[col].quantile(.01)),'p99':float(d[col].quantile(.99))})
(ROOT/'output/drive_raw.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axs=plt.subplots(2,2,figsize=(12,6),layout='constrained')
for col,center in enumerate([863.907255,898.331268]):
 ss=d[(d.time_us/1e6>center-.2)&(d.time_us/1e6<center+.2)];tt=ss.time_us/1e6-center
 for j,color in enumerate(['#c8524a','#25816d','#266da1']):
  axs[0,col].plot(tt,ss[COLS[j]],label='XYZ'[j],color=color,lw=1)
  axs[1,col].plot(tt,ss[COLS[j+3]],label='XYZ'[j],color=color,lw=1)
 axs[0,col].set(title=f'Událost {center:.3f} s',ylabel='a [g]');axs[1,col].set(xlabel='Čas od události [s]',ylabel='ω [°/s]');axs[0,col].legend(ncol=3)
fig.savefig(ROOT/'output/figures/transients.png',dpi=170)
