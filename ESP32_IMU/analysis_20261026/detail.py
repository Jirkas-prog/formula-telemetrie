from ingest import ROOT
import numpy as np,json
from scipy import signal,ndimage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
for boot,limit in [(178,200),(181,1050)]:
 z=np.load(ROOT/'cache'/f'boot_{boot:06d}_run_001.npz');t=z['time'];v=z['values'];sel=t<limit;t=t[sel];v=v[sel]
 f=signal.sosfiltfilt(signal.butter(3,2,fs=100,output='sos'),np.nan_to_num(v[:,:6]),axis=0)
 fig,ax=plt.subplots(4,1,figsize=(15,10),sharex=True,layout='constrained')
 for j in range(3):
  ax[0].plot(t,f[:,j],label='XYZ'[j]);ax[1].plot(t,f[:,j+3],label='XYZ'[j]);ax[2].plot(t,v[:,j+6],label='XYZ'[j],lw=.7)
 ax[0].set(ylabel='a [g]',title=f'Záznam {boot} / první {limit}s');ax[0].legend(ncol=3);ax[1].set(ylabel='ω [°/s]');ax[1].legend(ncol=3);ax[2].set(ylabel='B [µT]')
 ax[3].plot(t,np.cumsum(f[:,5]-.15)*.01/360);ax[3].set(ylabel='Yaw / 360°',xlabel='Čas [s]')
 fig.savefig(ROOT/'output'/f'detail-{boot}.png',dpi=130);plt.close(fig)
