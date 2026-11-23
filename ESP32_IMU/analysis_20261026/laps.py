from ingest import ROOT
import numpy as np,json
from scipy import signal,integrate
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
z=np.load(ROOT/'cache/vehicle.npz');t=z['t'];g=z['g'][:,2];a=z['along'];lat=z['lateral'];yaw=z['yaw'];v=z['speed'];xy=z['xy']
sel=t>=780;x=np.c_[g[sel],a[sel],lat[sel]];x=(x-x.mean(axis=0))/x.std(axis=0)
lags=np.arange(100,1000);corr=np.array([np.mean([np.corrcoef(x[:-lag,j],x[lag:,j])[0,1] for j in range(3)]) for lag in lags]);pk=signal.find_peaks(corr,prominence=.1)[0];best=sorted(pk,key=lambda i:corr[i],reverse=True)[:8]
print('PERIODS',[(round(lags[i]*.1,1),round(corr[i],3)) for i in best],flush=True)
peaks=signal.find_peaks(g,height=80,prominence=100,distance=70)[0]
print('YAW PEAKS',[(round(t[i],1),round(g[i],1),round(yaw[i]/(2*np.pi),2)) for i in peaks],flush=True)
fig,ax=plt.subplots(2,1,figsize=(14,7),layout='constrained');ax[0].plot(t,g);ax[0].scatter(t[peaks],g[peaks],color='red');
for i in peaks:ax[0].annotate(f'{t[i]:.1f}',(t[i],g[i]),fontsize=7,rotation=70)
ax[0].set(xlim=(775,1007),ylabel='Yaw [°/s]',xlabel='Čas [s]');ax[1].plot(lags*.1,corr);ax[1].set(xlabel='Posun [s]',ylabel='Průměrná korelace 3 kanálů');fig.savefig(ROOT/'output/lap-detection.png',dpi=140)
(ROOT/'output/lap_initial.json').write_text(json.dumps({'periods':[[float(lags[i]*.1),float(corr[i])] for i in best],'yaw_peaks':[[float(t[i]),float(g[i]),float(yaw[i]/(2*np.pi))] for i in peaks]},indent=2),encoding='utf-8')
