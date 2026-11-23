"""Reproducible numerical results, classifications, drift experiments and figures."""
from ingest import ROOT
import json,numpy as np
from scipy import signal,integrate,ndimage,linalg
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold'})
OUT=ROOT/'output';FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
inv=json.loads((OUT/'inventory.json').read_text());quality={x['id']:x for x in json.loads((OUT/'quality.json').read_text())}
vehicle=json.loads((OUT/'vehicle_initial.json').read_text());z=np.load(ROOT/'cache/vehicle.npz');t=z['t'];xy=z['xy'];yaw=z['yaw'];speed=z['speed'];r=z['g'][:,2];along=z['along'];lat=z['lateral']
def save(fig,name):fig.savefig(FIG/f'{name}.png',dpi=170);plt.close(fig)
def clean(x):
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [clean(v) for v in x]
 if isinstance(x,np.ndarray):return clean(x.tolist())
 if isinstance(x,(np.integer,)):return int(x)
 if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
 return x

# Candidate laps are repeated turn motifs, not GPS-verified crossings.
bounds=[781.305,831.405,881.605,937.105,985.605]
laps=[];closed=np.full_like(xy,np.nan);lap_id=np.full(len(t),-1);profiles=[]
fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
for k,(a,b) in enumerate(zip(bounds[:-1],bounds[1:])):
 ix=np.flatnonzero((t>=a-.01)&(t<=b+.01));tt=t[ix];phase=(tt-tt[0])/(tt[-1]-tt[0]);p=xy[ix]-xy[ix[0]];err=p[-1];pc=p-phase[:,None]*err
 closed[ix]=pc;lap_id[ix]=k+1
 profile=np.array([np.interp(np.linspace(0,1,500),phase,x[ix]) for x in [r,along,lat]]).T
 profiles.append(profile)
 distance=integrate.trapezoid(speed[ix],tt);turn=np.rad2deg(yaw[ix[-1]]-yaw[ix[0]])
 row={'lap':k+1,'start_s':float(tt[0]),'end_s':float(tt[-1]),'duration_s':float(tt[-1]-tt[0]),'turn_deg':float(turn),'model_distance_m':float(distance),'closure_error_m':float(np.linalg.norm(err)),'closure_error_fraction':float(np.linalg.norm(err)/distance),'heading_closure_bias_dps':float((turn-360)/(tt[-1]-tt[0])),'model_extent_m':np.ptp(p,axis=0).tolist(),'closed_extent_m':np.ptp(pc,axis=0).tolist()};laps.append(row)
 axs[0].plot(*p.T,label=f'Kandidát {k+1}');axs[1].plot(*pc.T,label=f'Kandidát {k+1}')
for ax,title in zip(axs,['Před polohovým uzavřením','Po vynuceném návratu do počátku']):ax.set(xlabel='x [m]',ylabel='y [m]',title=title);ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.2)
axs[0].legend(fontsize=8);save(fig,'laps-map')
for k in range(len(laps)):
 laps[k]['profile_correlation_previous']=float(np.mean([np.corrcoef(profiles[k][:,j],profiles[k-1][:,j])[0,1] for j in range(3)])) if k else None
fig,axs=plt.subplots(3,1,figsize=(11,7),sharex=True,layout='constrained')
for k,p in enumerate(profiles):
 for j in range(3):axs[j].plot(np.linspace(0,100,len(p)),p[:,j],label=str(k+1),alpha=.8,lw=1)
for ax,label in zip(axs,['Yaw [°/s]','Podélné a [m/s²]','Boční a [m/s²]']):ax.set_ylabel(label);ax.grid(alpha=.2)
axs[0].legend(title='Kandidát kola',ncol=4);axs[2].set_xlabel('Normalizovaný průběh kola [%]');save(fig,'lap-profiles')

# Static hold-out: 30 s calibration followed by an independent 60 s integration.
drift=[]
for boot in [158,169,173,177]:
 s=np.load(ROOT/'cache'/f'boot_{boot:06d}_run_001.npz');ts=s['time'];v=s['values']
 for start in np.arange(0,ts[-1]-90,90):
  sec=s['sec_std'][int(start):int(start+90)]
  if len(sec)<90 or not np.isfinite(sec).all() or np.any(np.max(sec[:,:3],axis=1)>.008) or np.any(np.max(sec[:,3:6],axis=1)>.2):continue
  cal=v[(ts>=start)&(ts<start+30),:6];test=v[(ts>=start+30)&(ts<start+90),:6]
  if len(test)<5995 or np.nanmax(np.std(cal[:,:3],axis=0))>.02:continue
  b=np.nanmean(cal,axis=0);testt=np.arange(len(test))*.01
  # Constant orientation baseline, then gyro-propagated orientation (small-angle static test).
  gvec=b[:3];R,_=Rotation.align_vectors([[0,0,1]],[gvec/np.linalg.norm(gvec)])
  abase=(test[:,:3]-b[:3])@R.as_matrix().T*9.80665
  theta=integrate.cumulative_trapezoid(np.deg2rad(test[:,3:6]-b[3:6]),testt,axis=0,initial=0)
  ar=Rotation.from_rotvec(theta).apply(test[:,:3]);ar=(ar-b[:3])@R.as_matrix().T*9.80665
  for seconds in [10,30,60]:
   end=min(len(test),seconds*100);p=[]
   for ac in [abase,ar]:
    vv=integrate.cumulative_trapezoid(ac[:end,:2],testt[:end],axis=0,initial=0);pp=integrate.cumulative_trapezoid(vv,testt[:end],axis=0,initial=0);p.append(float(np.linalg.norm(pp[-1])))
   drift.append({'file':f'boot_{boot:06d}_run_001.csv','calibration_start_s':float(start),'horizon_s':seconds,'fixed_orientation_error_m':p[0],'gyro_orientation_error_m':p[1],'gyro_angle_max_deg':float(np.rad2deg(np.linalg.norm(theta[:end],axis=1)).max())})
drift_summary=[]
for h in [10,30,60]:
 d=[x for x in drift if x['horizon_s']==h];a=np.array([x['gyro_orientation_error_m'] for x in d]);f=np.array([x['fixed_orientation_error_m'] for x in d]);drift_summary.append({'horizon_s':h,'windows':len(d),'gyro_mean_m':a.mean(),'gyro_median_m':np.median(a),'gyro_p95_m':np.percentile(a,95),'fixed_median_m':np.median(f)})
fig,ax=plt.subplots(figsize=(9,4.5),layout='constrained');ax.boxplot([[d['gyro_orientation_error_m'] for d in drift if d['horizon_s']==h] for h in [10,30,60]],tick_labels=['10 s','30 s','60 s'],showfliers=True);ax.set(ylabel='Zdánlivý posun v klidovém úseku [m]',title='Drift po 30 s kalibraci; nezávislé testovací úseky');ax.grid(axis='y',alpha=.2);save(fig,'drift')

# Sensitivity: independently perturb mounting and bias assumptions.
sens=[]
baseR=np.array(vehicle['rotation']);theta0=np.deg2rad(vehicle['theta_deg']);a=z['a'];g=z['g'];dt=.1;n=len(t)
for label,da,db,dyaw in [('Základ',0,0,0),('Montáž −5°',-5,0,0),('Montáž +5°',5,0,0),('Podélný offset −0,02 g',0,-.02*9.80665,0),('Podélný offset +0,02 g',0,.02*9.80665,0),('Gyro bias −0,05 °/s',0,0,-.05),('Gyro bias +0,05 °/s',0,0,.05)]:
 th=theta0+np.deg2rad(da);aa=np.cos(th)*a[:,0]+np.sin(th)*a[:,1]-db;ll=-np.sin(th)*a[:,0]+np.cos(th)*a[:,1];rr=np.deg2rad(g[:,2]-dyaw)
 diag=rr*rr+2/dt**2+1e-6;diag[[0,-1]]-=1/dt**2;diag[0]+=100;rhs=rr*ll;av=(aa[:-1]+aa[1:])/2;rhs[:-1]-=av/dt;rhs[1:]+=av/dt;band=np.zeros((2,n));band[0]=diag;band[1,:-1]=-1/dt**2;vv=linalg.solveh_banded(band,rhs,lower=True);yy=integrate.cumulative_trapezoid(rr,t,initial=0);pp=np.c_[integrate.cumulative_trapezoid(vv*np.cos(yy),t,initial=0),integrate.cumulative_trapezoid(vv*np.sin(yy),t,initial=0)]
 sens.append({'scenario':label,'distance_m':float(integrate.trapezoid(vv,t)),'max_speed_kmh':float(vv.max()*3.6),'endpoint_change_m':float(np.linalg.norm(pp[-1]-xy[-1]))})

# Evidence-based inventory, preserving uncertainty in the requested categories.
records=[]
for m in inv:
 q=quality[m['id']];boot=int(m['id'].split('_')[1]);s=np.load(ROOT/'cache'/f'{m["id"]}.npz');vv=s['values'];ss=s['sec_std'];sm=s['sec_mean'];norm=np.linalg.norm(vv[:,:3],axis=1)
 if boot<=150:
  category='Test / manipulace' if boot not in [145,148,150] or m['id'].endswith('002') else 'Klid / test';evidence='Charakter signálu odpovídá testu nebo manipulaci; pro jízdu nepoužito.';confidence='vysoká';drive=False
 elif boot==181:
  category='Jízda: slalom + kandidáti delších kol';evidence='Jízda přibližně 677–1007 s; 4 kandidáti kol 48,5–55,5 s; od 1008,24 s porucha.';confidence='střední';drive=True
 elif boot==178:
  category='Klid → neplatná data';evidence='Použitelné pouze první 179,17 s bez prokázané jízdy; pak digitální porucha.';confidence='vysoká';drive=False
 elif boot==180:
  category='Neplatná data';evidence='Opakovaná shodná digitální slova; žádný souvislý validní úsek ≥1 s.';confidence='vysoká';drive=False
 else:
  category='Klid / drobné pohyby';evidence='Bez prokázané souvislé jízdy; vhodné spíše pro kontrolu biasu a šumu.';confidence='střední';drive=False
 records.append({'file':m['file'],'id':m['id'],'duration_s':m['duration_s'],'rows':m['rows'],'category':category,'confidence':confidence,'evidence':evidence,'use_for_trajectory':drive,'digital_fault_fraction':q['digital_fault_fraction'],'valid_contiguous_s':sum(b-a for a,b in q['good_spans_ge1s']),'long_route':'kandidát 710–772 s (slalom / přejezd)' if boot==181 else ('nelze určit' if boot in [178,180] else 'neprokázáno'),'long_laps':'4 kandidáti, 781,3–985,6 s' if boot==181 else ('nelze určit' if boot in [178,180] else 'neprokázáno'),'figure_eight':'neprokázáno; střídání zatáček ≠ osmička' if boot==181 else ('nelze určit' if boot in [178,180] else 'neprokázáno'),'skidpad':'neprokázáno' if boot not in [178,180] else 'nelze určit','bad_crc':m['bad_crc'],'missing_rows':m['missing_rows'],'sha256':m['sha256']})

# Clear quality overview of the three longest files.
fig,ax=plt.subplots(figsize=(12,4),layout='constrained')
for i,boot in enumerate([178,180,181]):
 m=next(x for x in inv if x['id']==f'boot_{boot:06d}_run_001');q=quality[m['id']];ax.broken_barh([(0,m['end_s']/60)],(i-.25,.5),facecolors='#d45b57')
 for aa,bb in q['good_spans_ge1s']:ax.broken_barh([(aa/60,(bb-aa)/60)],(i-.25,.5),facecolors='#2c8c79')
ax.set(yticks=[0,1,2],yticklabels=['178','180','181'],xlabel='Čas v souboru [min]',title='Zelená: souvislá data bez digitálního vzoru; červená: porucha');save(fig,'quality')

# Overview includes a warning marker exactly where acquisition fails.
src=np.load(ROOT/'cache/boot_000181_run_001.npz');tt=src['time'];vv=src['values'];keep=tt<1030;tt=tt[keep];vv=vv[keep]
fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
for j,c in enumerate(['#d65b50','#2b8b73','#3773b3']):ax[0].plot(tt[::10],vv[::10,j],color=c,lw=.6,label='XYZ'[j]);ax[1].plot(tt[::10],vv[::10,j+3],color=c,lw=.6)
ax[0].set(ylabel='a [g]',ylim=(-1.5,1.5),title='Záznam 181: klid, jízda a počátek poruchy');ax[0].legend(ncol=3);ax[1].set(ylabel='ω [°/s]',ylim=(-180,180));ax[2].plot(tt[::10],np.linalg.norm(vv[::10,6:9],axis=1),color='#7563aa');ax[2].set(ylabel='|B| [µT]',xlabel='Čas v souboru [s]')
for aa in ax:aa.axvspan(1008.24,1030,color='#e36b62',alpha=.15);aa.axvline(677,color='#666',lw=.8,ls='--');aa.grid(alpha=.2)
save(fig,'overview181')

# Trajectory and measured/derived signals have matching time intervals.
fig,ax=plt.subplots(1,2,figsize=(12,7),layout='constrained');pts=ax[0].scatter(xy[::4,0],xy[::4,1],c=t[::4],s=3,cmap='viridis');ax[0].set_aspect('equal');ax[0].set(xlabel='Lokální x [m]',ylabel='Lokální y [m]',title='Podmíněný model celé jízdy');fig.colorbar(pts,ax=ax[0],label='Čas [s]');ax[1].plot(t,speed*3.6,label='Vozidlový model');ax[1].plot(t,z['naivev']*3.6,label='Prostý integrál podélné a',alpha=.7);ax[1].set(xlabel='Čas [s]',ylabel='Rychlost [km/h]',title='Rychlost není přímo měřená');ax[1].legend(fontsize=8);save(fig,'trajectory')

fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained');ax[0].plot(t,along/9.80665,label='Podélné',color='#d65b50');ax[0].plot(t,lat/9.80665,label='Boční',color='#2b8b73');ax[0].legend(ncol=2);ax[0].set(ylabel='Filtrované a [g]',title='Použitelný jízdní úsek: filtr 2 Hz, odhad roviny vozidla');ax[1].plot(t,r,color='#3773b3');ax[1].set(ylabel='Yaw [°/s]');ax[2].plot(t,yaw/(2*np.pi),color='#7563aa');ax[2].set(ylabel='Otočení / 360°',xlabel='Čas v souboru [s]')
for a in ax:
 for k,(start,end) in enumerate(zip(bounds[:-1],bounds[1:])):a.axvspan(start,end,color=['#abc9dc','#d7dfb6'][k%2],alpha=.25)
 a.grid(alpha=.2)
save(fig,'drive-signals')

# True extrema of 100 Hz averaged data, separate from 2 Hz filtered values.
good=src['values'][(src['time']>=677)&(src['time']<1007)]
stats={'raw100_min':np.nanmin(good[:,:6],axis=0),'raw100_max':np.nanmax(good[:,:6],axis=0),'filtered_long_min_g':along.min()/9.80665,'filtered_long_max_g':along.max()/9.80665,'filtered_lat_min_g':lat.min()/9.80665,'filtered_lat_max_g':lat.max()/9.80665,'yaw_min_dps':r.min(),'yaw_max_dps':r.max()}
mag=src['time'][src['counts'][:,2]>0]
result=clean({'files':records,'laps':laps,'drift_windows':drift,'drift_summary':drift_summary,'sensitivity':sens,'vehicle':vehicle,'drive_stats':stats,'mag181_last_fresh_s':mag[-1],'total_rows':sum(m['rows'] for m in inv),'digital_fault_rows':sum(q['digital_fault_rows'] for q in quality.values()),'total_duration_s':sum(m['duration_s'] for m in inv),'bounds':bounds,'driving_interval_s':[677,1007]})
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
np.savez_compressed(ROOT/'cache/trajectory_final.npz',t=t,xy=xy,closed=closed,lap_id=lap_id,speed=speed,yaw=yaw,along=along,lat=lat,naivexy=z['naivexy'],naivev=z['naivev'])
print(json.dumps(clean({'laps':laps,'drift_summary':drift_summary,'sensitivity':sens,'drive_stats':stats,'mag181_last_fresh_s':mag[-1]}),ensure_ascii=True,indent=2),flush=True)
