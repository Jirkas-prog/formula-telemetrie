"""One portable ZIP-based .fimu bundle: byte-identical sources plus derived arrays."""
from ingest import ROOT,SOURCE
import json,zipfile,hashlib,numpy as np
from scipy import signal
OUT=ROOT/'output';inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'));res=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
def finite(x):
 if isinstance(x,dict):return {k:finite(v) for k,v in x.items()}
 if isinstance(x,list):return [finite(v) for v in x]
 if isinstance(x,float) and not np.isfinite(x):return None
 return x
inv=finite(inv)
columns=['t_s','ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps','mx_uT','my_uT','mz_uT','temp_C','bad_fraction','fax_g','fay_g','faz_g','fgx_dps','fgy_dps','fgz_dps']
manifest={'format':'Formula IMU archive','version':1,'created':'2026-10-26','time_basis':'Seconds from beginning of each CSV, not UTC','array_dtype':'float32-le','array_layout':'row-major','columns':columns,'filter':'100 Hz fresh-only 10 ms averages; displayed filtered A/G: 3rd order Butterworth 2 Hz, forward-backward, separate valid spans','results':res,'runs':[],'trajectory_columns':['t_s','x_m','y_m','closed_x_m','closed_y_m','lap','speed_ms','yaw_rad','along_ms2','lat_ms2','naive_x_m','naive_y_m','naive_speed_ms']}
path=OUT/'Formule_IMU.fimu'
with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
 for m in inv:
  name=m['id'];z=np.load(ROOT/'cache'/f'{name}.npz');q=np.load(ROOT/'cache'/f'{name}.quality.npz');t=z['time'];v=z['values'];strict=q['strict'];filtered=np.full((len(t),6),np.nan,dtype='f4')
  edges=np.diff(np.r_[False,strict,False].astype(int))
  for a,b in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
   if b-a>=100:filtered[a:b]=signal.sosfiltfilt(signal.butter(3,2,fs=100,output='sos'),v[a:b,:6],axis=0)
  ar=np.c_[t,v,q['bad_fraction'],filtered].astype('<f4');member=f'derived/{name}.f32';archive.writestr(member,ar.tobytes())
  run={**m,'derived_member':member,'derived_rows':len(t),'raw_member':f'raw/{m["file"]}'};manifest['runs'].append(run)
  archive.write(SOURCE/m['file'],run['raw_member'])
  for side in m['sidecars']:archive.write(SOURCE/side,f'raw/{side}')
  print(name,flush=True)
 tr=np.load(ROOT/'cache/trajectory_final.npz');arr=np.c_[tr['t'],tr['xy'],tr['closed'],tr['lap_id'],tr['speed'],tr['yaw'],tr['along'],tr['lat'],tr['naivexy'],tr['naivev']].astype('<f4');archive.writestr('derived/trajectory181.f32',arr.tobytes());manifest['trajectory_rows']=len(arr)
 archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,allow_nan=False).encode('utf-8'))
 archive.writestr('FORMAT.txt','FIMU v1 is a standard ZIP archive. raw/ contains unmodified CSV files and metadata. SHA-256 hashes are in manifest.json. derived/*.f32 contain little-endian float32 row-major arrays; NaN means unavailable. No absolute GPS position. Closed laps are conditional, not observed. All data can be extracted using 7-Zip.\n')
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print('BUNDLE',path.stat().st_size,flush=True)
