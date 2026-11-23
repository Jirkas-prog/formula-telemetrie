"""Conditional planar vehicle reconstruction; no GPS or forced loop closure."""
from ingest import ROOT
import json,numpy as np
from scipy import signal,linalg,optimize,integrate
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

z=np.load(ROOT/'cache/boot_000181_run_001.npz');t=z['time'];v=z['values']
sel=(t>=650)&(t<1007);t=t[sel][::10];v=v[sel]
base=np.load(ROOT/'cache/boot_000181_run_001.npz');bt=base['time'];bv=base['values'];rest=bv[(bt>=560)&(bt<650),:6]
zero=np.nanmedian(rest,axis=0);up=zero[:3]/np.linalg.norm(zero[:3]);rot,_=Rotation.align_vectors([[0,0,1]],[up]);R=rot.as_matrix()
f=signal.sosfiltfilt(signal.butter(3,2,fs=100,output='sos'),v[:,:6],axis=0)[::10]
a=((f[:,:3]-zero[:3])@R.T)*9.80665;g=(f[:,3:6]-zero[3:6])@R.T;r=np.deg2rad(g[:,2]);n=len(t);dt=.1

def fit(theta,anchor=True,sigma=.5):
    along=np.cos(theta)*a[:,0]+np.sin(theta)*a[:,1]
    lateral=-np.sin(theta)*a[:,0]+np.cos(theta)*a[:,1]
    # Equal acceleration residual weights. First speed is assumed zero in a quiet lead-in.
    diag=r*r+2/dt**2+1e-6;diag[[0,-1]]-=1/dt**2
    rhs=r*lateral;av=(along[:-1]+along[1:])/2
    rhs[:-1]-=av/dt;rhs[1:]+=av/dt
    if anchor:diag[0]+=100
    band=np.zeros((2,n));band[0]=diag;band[1,:-1]=-1/dt**2
    speed=linalg.solveh_banded(band,rhs,lower=True)
    res1=np.diff(speed)/dt-av;res2=r*speed-lateral
    cost=np.mean(res1**2)+np.mean(res2**2)+10*np.mean(np.minimum(speed,0)**2)
    return cost,speed,along,lateral,res1,res2

angles=np.linspace(-np.pi,np.pi,361);costs=np.array([fit(x)[0] for x in angles]);guess=angles[costs.argmin()]
opt=optimize.minimize_scalar(lambda x:fit(x)[0],bounds=(guess-.1,guess+.1),method='bounded');theta=opt.x
cost,speed,along,lateral,res1,res2=fit(theta)
yaw=integrate.cumulative_trapezoid(r,t,initial=0)
xy=np.c_[integrate.cumulative_trapezoid(speed*np.cos(yaw),t,initial=0),integrate.cumulative_trapezoid(speed*np.sin(yaw),t,initial=0)]
naivev=integrate.cumulative_trapezoid(along,t,initial=0)
naivexy=np.c_[integrate.cumulative_trapezoid(naivev*np.cos(yaw),t,initial=0),integrate.cumulative_trapezoid(naivev*np.sin(yaw),t,initial=0)]
summary={'zero':zero.tolist(),'up':up.tolist(),'rotation':R.tolist(),'theta_deg':float(np.rad2deg(theta)),'cost':cost,'speed_minmax': [float(speed.min()),float(speed.max())],'p95_speed':float(np.percentile(speed,95)),'negative_speed_pct':float(np.mean(speed<-.5)*100),'acc_residual_rms':float(np.sqrt(np.mean(res1**2))),'lateral_residual_rms':float(np.sqrt(np.mean(res2**2))),'distance_m':float(integrate.trapezoid(np.maximum(speed,0),t)),'extent':np.ptp(xy,axis=0).tolist(),'net_turns':float((yaw[-1]-yaw[0])/(2*np.pi))}
print(json.dumps(summary,indent=2),flush=True)
(ROOT/'output/vehicle_initial.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
np.savez_compressed(ROOT/'cache/vehicle.npz',t=t,a=a,g=g,speed=speed,yaw=yaw,xy=xy,naivev=naivev,naivexy=naivexy,along=along,lateral=lateral)
fig,ax=plt.subplots(4,1,figsize=(15,11),sharex=True,layout='constrained')
ax[0].plot(t,along/9.80665,label='Podélné');ax[0].plot(t,lateral/9.80665,label='Boční');ax[0].legend();ax[0].set(ylabel='a [g]',title=f'181 / odhad osy dopředu {np.rad2deg(theta):.1f}° od +X k +Y')
ax[1].plot(t,g[:,2]);ax[1].set(ylabel='Yaw rate [°/s]')
ax[2].plot(t,speed*3.6,label='Vozidlový model');ax[2].plot(t,naivev*3.6,label='Integrál podélné a',alpha=.6);ax[2].legend();ax[2].set(ylabel='v [km/h]')
ax[3].plot(t,yaw/(2*np.pi));ax[3].set(ylabel='Otočení / 360°',xlabel='Čas v souboru [s]');fig.savefig(ROOT/'output/vehicle-timeline.png',dpi=140);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,8),layout='constrained');ax.plot(*xy.T,lw=1);ax.scatter(*xy[0],label='Start');ax.set(xlabel='Lokální x [m]',ylabel='Lokální y [m]',title='Podmíněný model – bez uzavírání kol');ax.axis('equal');ax.legend();fig.savefig(ROOT/'output/vehicle-map.png',dpi=140);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4),layout='constrained');ax.plot(np.rad2deg(angles),costs);ax.set(xlabel='Směr dopředu od +X k +Y [°]',ylabel='Kriteriální funkce');fig.savefig(ROOT/'output/mount-fit.png',dpi=140)
