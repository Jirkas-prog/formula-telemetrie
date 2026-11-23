from ingest import ROOT, COLS
import json,numpy as np
from scipy import ndimage,signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
summary=[]
for p in sorted((ROOT/'cache').glob('*.npz')):
 z=np.load(p);v=z['values'];s=z['sec_std'];m=z['sec_mean'];t=z['time'];meta=json.loads(p.with_suffix('.json').read_text())
 quiet=(np.nanmax(s[:,:3],axis=1)<.008)&(np.nanmax(s[:,3:6],axis=1)<.2)
 bias=np.nanmedian(m[quiet,3:6],axis=0) if quiet.any() else np.nanmedian(v[:,3:6],axis=0)
 gy=m[:,3:6]-bias
 g=np.linalg.norm(v[:,:3],axis=1)
 row={'id':p.stem,'duration':round(t[-1],1),'quiet_s':int(quiet.sum()),'gyr_bias':np.round(bias,3).tolist(),'acc_median':np.round(np.nanmedian(v[:,:3],axis=0),3).tolist(),'acc_p99':np.round(np.nanpercentile(np.abs(v[:,:3]),99,axis=0),2).tolist(),'gyro_p99':np.round(np.nanpercentile(np.abs(v[:,3:6]-bias),99,axis=0),1).tolist(),'temp':np.round(np.nanpercentile(v[:,9],[1,99]),1).tolist(),'mag_norm':np.round(np.nanpercentile(np.linalg.norm(v[:,6:9],axis=1),[1,50,99]),1).tolist(),'yaw_deg':round(float(np.nansum(gy[:,2])),1)}
 summary.append(row);print(json.dumps(row),flush=True)
 if t[-1]>150:
  fig,ax=plt.subplots(4,1,figsize=(13,8),sharex=True,layout='constrained')
  sec=np.arange(len(m))
  for i,c in enumerate(['#df6258','#258774','#3e6ab3']):
   ax[0].plot(sec/60,m[:,i],color=c,lw=.7,label='XYZ'[i]);ax[1].plot(sec/60,gy[:,i],color=c,lw=.7,label='XYZ'[i])
  ax[0].set(ylabel='Průměr a [g]',title=p.stem);ax[0].legend(ncol=3)
  ax[1].set(ylabel='Gyro − bias [°/s]');ax[1].set_ylim(-160,160)
  ax[2].plot(sec/60,np.nancumsum(gy[:,2])/360,color='#258774');ax[2].set(ylabel='Integrál Z / 360°')
  ax[3].plot(sec/60,s[:,2],label='σ az [g]');ax[3].fill_between(sec/60,0,.1,where=quiet,color='#4fa58e',alpha=.3,label='Klidový kandidát');ax[3].set(ylabel='Variabilita',xlabel='Čas v souboru [min]');ax[3].legend()
  fig.savefig(ROOT/'output'/f'explore-{p.stem}.png',dpi=125);plt.close(fig)
(ROOT/'output/exploration.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
