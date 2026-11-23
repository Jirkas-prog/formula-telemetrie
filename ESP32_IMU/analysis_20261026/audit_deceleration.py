"""Re-read all original CSVs and rank longitudinal minima with quality context."""
from pathlib import Path
import sys, json, hashlib, csv, time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import numpy as np
import pandas as pd
from scipy import signal

SOURCE = Path(r'./input/logs')
OUT = ROOT / 'output'
inventory = {r['id']: r for r in json.loads((OUT / 'inventory.json').read_text())}
classes = {r['id']: r for r in json.loads((OUT / 'results.json').read_text())['files']}
mount = json.loads((OUT / 'vehicle_initial.json').read_text())
angle = np.deg2rad(mount['theta_deg'])
axis = np.array([np.cos(angle), np.sin(angle), 0]) @ np.array(mount['rotation'])
zero = np.array(mount['zero'][:3])
sos = signal.butter(3, 2, fs=100, output='sos')
cols = ['time_us','ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps',
        'accel_new','accel_range_g','gyro_range_dps','clip_mask']

def peak(values, times, mask):
    indices = np.flatnonzero(mask & np.isfinite(values))
    if not len(indices): return None
    i = indices[np.argmin(values[indices])]
    return {'acceleration_g': float(values[i]), 'deceleration_ms2': float(-values[i]*9.80665),
            'time_s': float(times[i])}

results=[]
started=time.monotonic()
paths=sorted(SOURCE.glob('*.csv'))
assert len(paths)==len(inventory), 'Source file inventory changed'
for number,p in enumerate(paths,1):
    expected=inventory[p.stem]
    with p.open('rb') as source:
        digest=hashlib.file_digest(source,'sha256').hexdigest()
    assert digest==expected['sha256'], f'Input changed: {p.name}'
    n=int(expected['end_s']*100)+2
    count=np.zeros(n,np.int64); badcount=np.zeros(n,np.int64); freshcount=np.zeros(n,np.int64)
    sums=np.zeros((n,3)); raw_min=np.full(n,np.inf); raw_time=np.full(n,np.nan)
    unmasked_min=np.inf; unmasked_time=None; nonpattern_min=np.inf; nonpattern_time=None
    rows=0; badrows=0; clipping=0; newrows=0; settings=set()
    for df in pd.read_csv(p,usecols=cols,chunksize=200000):
        ts=df.time_us.to_numpy(); ix=(ts//10000).astype(int)
        x=df[['ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps']].to_numpy()
        ranges=df[['accel_range_g','gyro_range_dps']].to_numpy()
        scale=np.repeat(32768/ranges,3,axis=1)
        digital=np.rint(x*scale).astype(np.int32)
        bad=(digital==digital[:,0,None]).all(axis=1) | ~np.isfinite(x).all(axis=1)
        fresh=df.accel_new.to_numpy()==1; good=fresh & ~bad
        long=(x[:,:3]-zero)@axis
        rows+=len(df);badrows+=int(bad.sum());newrows+=int(fresh.sum())
        clipping+=int(np.count_nonzero(df.clip_mask.to_numpy()&7))
        settings.update(map(tuple,np.unique(ranges,axis=0).tolist()))
        count+=np.bincount(ix,minlength=n);badcount+=np.bincount(ix[bad],minlength=n)
        freshcount+=np.bincount(ix[good],minlength=n)
        for k in range(3):sums[:,k]+=np.bincount(ix[good],weights=x[good,k],minlength=n)
        for mask,kind in [(fresh,'all'),(good,'nonpattern')]:
            ids=np.flatnonzero(mask)
            if not len(ids):continue
            j=ids[np.argmin(long[ids])]
            if kind=='all' and long[j]<unmasked_min:unmasked_min=float(long[j]);unmasked_time=float(ts[j]/1e6)
            if kind=='nonpattern' and long[j]<nonpattern_min:nonpattern_min=float(long[j]);nonpattern_time=float(ts[j]/1e6)
        # Keep the exact 500 Hz minimum and timestamp within each 10 ms bin.
        gi=ix[good]; gv=long[good]; gt=ts[good]/1e6
        unique=np.unique(gi);before=raw_min[unique].copy()
        np.minimum.at(raw_min,gi,gv)
        changed=unique[raw_min[unique]<before];raw_time[changed]=np.nan
        matches=gv==raw_min[gi]
        for bin_id,at in zip(gi[matches],gt[matches]):
            if not np.isfinite(raw_time[bin_id]) or at<raw_time[bin_id]:raw_time[bin_id]=at
    assert rows==expected['rows']
    good=(count>0)&(badcount==0)&(freshcount>0)
    edges=np.diff(np.r_[False,good,False].astype(int))
    spans=[(int(a),int(b)) for a,b in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)) if b-a>=100]
    eligible=np.zeros(n,bool);filtered=np.full(n,np.nan);averaged=np.full((n,3),np.nan)
    averaged[freshcount>0]=sums[freshcount>0]/freshcount[freshcount>0,None]
    for a,b in spans:
        eligible[a:b]=True
        # Never filter across acquisition failures or gaps.
        filtered[a:b]=(signal.sosfiltfilt(sos,averaged[a:b],axis=0)-zero)@axis
    times=np.arange(n)*.01+.005
    raw_peak=peak(raw_min,raw_time,eligible)
    filtered_peak=peak(filtered,times,eligible)
    long_spans=sum(b-a for a,b in spans)/100
    flat={
        'file':p.name,'classification':classes[p.stem]['category'],'rows':rows,
        'sha256_matches_previous_audit':True,'digital_fault_rows':badrows,
        'new_accel_rows':newrows,'accel_clipped_rows':clipping,'valid_spans_s':long_spans,
        'unmasked_projection_min_g':unmasked_min,'unmasked_time_s':unmasked_time,
        'nonpattern_projection_min_g':nonpattern_min,'nonpattern_time_s':nonpattern_time,
        'valid_raw_peak':raw_peak,'valid_filtered_2Hz_peak':filtered_peak,
        'range_settings':sorted(settings),
        'projection_note':'Uses fixed mounting and rest offset from run 181; invalid as vehicle acceleration during sensor manipulation.'
    }
    if p.stem=='boot_000181_run_001':
        driving=eligible&(times>=677)&(times<1007)
        flat['driving_raw_peak']=peak(raw_min,raw_time,driving)
        flat['driving_filtered_peak']=peak(filtered,times,driving)
    results.append(flat)
    print(f'{number:02d}/38 {p.stem}: rows={rows:,}, bad={badrows:,}, raw={raw_peak}, filtered={filtered_peak}',flush=True)

document={'method':'Fresh original CSV pass. Same estimated forward axis and rest offset as previous analysis. Raw means new accelerometer samples in >=1 s contiguous clean spans. Filter means fresh-only 100 Hz bins, Butterworth order 3 cutoff 2 Hz forward-backward in each separate clean span. Test/manipulation projections are not vehicle deceleration.',
          'files':results,'total_rows':sum(r['rows'] for r in results),'elapsed_s':time.monotonic()-started}
(OUT/'audit_deceleration_all.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'audit_deceleration_all.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f);writer.writerow(['file','classification','rows','digital_fault_rows','valid_seconds','raw_min_g','raw_time_s','filtered_2Hz_min_g','filtered_time_s'])
    for r in results:
        a=r['valid_raw_peak'] or {};b=r['valid_filtered_2Hz_peak'] or {}
        writer.writerow([r['file'],r['classification'],r['rows'],r['digital_fault_rows'],r['valid_spans_s'],a.get('acceleration_g',''),a.get('time_s',''),b.get('acceleration_g',''),b.get('time_s','')])
print('TOTAL',document['total_rows'],'rows;',round(document['elapsed_s'],1),'seconds',flush=True)
for field in ['valid_raw_peak','valid_filtered_2Hz_peak']:
    print(field,[(r['file'],r[field]) for r in sorted((r for r in results if r[field]),key=lambda r:r[field]['acceleration_g'])[:8]],flush=True)
