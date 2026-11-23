"""Read-only inventory, complete CRC/sequence audit, fresh-sample 100 Hz cache."""
from pathlib import Path
import os, sys, json, hashlib, zlib, time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ['MPLCONFIGDIR']=str(ROOT/'.cache/matplotlib')
os.environ['NUMBA_CACHE_DIR']=str(ROOT/'.cache/numba')
import numpy as np
import pandas as pd
SOURCE=Path(r'./input/logs')
COLS=['ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps','mx_uT','my_uT','mz_uT','temp_C']

def ingest(p):
    out=ROOT/'cache'/p.stem
    if out.with_suffix('.json').exists() and out.with_suffix('.npz').exists():
        return json.loads(out.with_suffix('.json').read_text(encoding='utf-8'))
    began=time.monotonic();sha=hashlib.sha256();bad=0;lines=0;first=None;last=None;bad_examples=[]
    with p.open('rb') as f:
        header=f.readline();sha.update(header)
        for line in f:
            sha.update(line);lines+=1
            try:
                payload,crc=line.rstrip(b'\r\n').rsplit(b',',1)
                ok=zlib.crc32(payload)==int(crc,16)
            except ValueError:ok=False
            if not ok:
                bad+=1
                if len(bad_examples)<5:bad_examples.append(lines+1)
            if first is None:first=int(line.split(b',',1)[0])
            last=int(line.split(b',',1)[0])
    n=int(last//10000)+1
    sums=np.zeros((n,10));counts=np.zeros((n,4),dtype=np.int32)
    minima=np.full(10,np.inf);maxima=np.full(10,-np.inf)
    seconds=int(last//1000000)+1
    sec_sum=np.zeros((seconds,6));sec_sq=np.zeros((seconds,6));sec_count=np.zeros((seconds,2),dtype=np.int64)
    prev_seq=None;prev_time=None;gaps=[];seq_gaps=0;missing_rows=0;backwards=0;clips=0;overflow=0;badmag=0;fresh=[0,0,0];settings=set()
    for df in pd.read_csv(p,chunksize=200000,usecols=lambda c:c!='crc32'):
        ts=df.time_us.to_numpy(dtype=np.int64);seq=df.seq.to_numpy(dtype=np.int64)
        dt=np.diff(np.r_[prev_time if prev_time is not None else ts[0],ts]);ds=np.diff(np.r_[prev_seq if prev_seq is not None else seq[0]-1,seq])
        seq_gaps+=int(np.count_nonzero(ds!=1));missing_rows+=int(np.maximum(ds-1,0).sum());backwards+=int(np.count_nonzero(dt<0))
        for ix in np.flatnonzero(dt>50000):gaps.append([float((ts[ix]-dt[ix])/1e6),float(ts[ix]/1e6),int(ds[ix]-1)])
        prev_seq=int(seq[-1]);prev_time=int(ts[-1]);idx=(ts//10000).astype(np.int64);sec=(ts//1000000).astype(np.int64)
        vals=df[COLS].to_numpy(dtype=float)
        flags=[df.accel_new.to_numpy()==1,df.gyro_new.to_numpy()==1,(df.mag_new.to_numpy()==1)&(df.mag_valid.to_numpy()==1),np.ones(len(df),dtype=bool)]
        for g,(lo,hi) in enumerate([(0,3),(3,6),(6,9),(9,10)]):
            good=flags[g]&np.isfinite(vals[:,lo:hi]).all(axis=1)
            if g<3:fresh[g]+=int(good.sum())
            b=idx[good];x=vals[good,lo:hi];counts[:,g]+=np.bincount(b,minlength=n).astype(np.int32)
            if len(x):
                minima[lo:hi]=np.minimum(minima[lo:hi],x.min(axis=0));maxima[lo:hi]=np.maximum(maxima[lo:hi],x.max(axis=0))
            for j in range(lo,hi):sums[:,j]+=np.bincount(b,weights=vals[good,j],minlength=n)
            if g<2:
                sec_count[:,g]+=np.bincount(sec[good],minlength=seconds).astype(np.int64)
                for j in range(lo,hi):
                    sec_sum[:,j]+=np.bincount(sec[good],weights=vals[good,j],minlength=seconds)
                    sec_sq[:,j]+=np.bincount(sec[good],weights=vals[good,j]**2,minlength=seconds)
        clips+=int((df.clip_mask!=0).sum());overflow+=int((df.mag_overflow!=0).sum());badmag+=int(((df.mag_new==1)&(df.mag_valid==0)).sum())
        settings.update(tuple(map(int,row)) for row in df[['accel_range_g','gyro_range_dps','accel_rate_hz','gyro_rate_hz','mag_rate_hz','dlpf']].drop_duplicates().to_numpy())
    values=np.full_like(sums,np.nan)
    for g,(lo,hi) in enumerate([(0,3),(3,6),(6,9),(9,10)]):
        valid=counts[:,g]>0;values[valid,lo:hi]=sums[valid,lo:hi]/counts[valid,g,None]
    sec_mean=np.full_like(sec_sum,np.nan);sec_std=np.full_like(sec_sum,np.nan)
    for g,(lo,hi) in enumerate([(0,3),(3,6)]):
        valid=sec_count[:,g]>0
        sec_mean[valid,lo:hi]=sec_sum[valid,lo:hi]/sec_count[valid,g,None]
        sec_std[valid,lo:hi]=np.sqrt(np.maximum(sec_sq[valid,lo:hi]/sec_count[valid,g,None]-sec_mean[valid,lo:hi]**2,0))
    sides={q.name:json.loads(q.read_text(encoding='utf-8')) for q in SOURCE.glob(p.name+'.*.json')}
    m={'id':p.stem,'file':p.name,'bytes':p.stat().st_size,'sha256':sha.hexdigest(),'rows':lines,'bad_crc':bad,'bad_crc_lines':bad_examples,'start_s':first/1e6,'end_s':last/1e6,'duration_s':(last-first)/1e6,'sequence_discontinuities':seq_gaps,'missing_rows':missing_rows,'time_reversals':backwards,'gaps':gaps,'clip_rows':clips,'mag_overflow_rows':overflow,'bad_mag_new_rows':badmag,'fresh_counts':fresh,'raw_min':minima.tolist(),'raw_max':maxima.tolist(),'settings':[list(x) for x in sorted(settings)],'sidecars':sides,'cache_hz':100,'cache_columns':COLS}
    # Averages use only newly acquired readings of each sensor group, never held duplicates.
    np.savez_compressed(out.with_suffix('.npz'),time=np.arange(n,dtype=float)*.01+.005,values=values.astype(np.float32),counts=counts,sec_mean=sec_mean.astype(np.float32),sec_std=sec_std.astype(np.float32),sec_count=sec_count)
    out.with_suffix('.json').write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'{p.name}: {lines:,} rows, {m["duration_s"]:.1f}s, CRC={bad}, missing={missing_rows}, clips={clips}; {time.monotonic()-began:.1f}s',flush=True)
    return m

if __name__=='__main__':
    all_runs=[ingest(p) for p in sorted(SOURCE.glob('*.csv'))]
    (ROOT/'output/inventory.json').write_text(json.dumps(all_runs,indent=2,ensure_ascii=False),encoding='utf-8')
    print('TOTAL',sum(x['rows'] for x in all_runs),'rows',sum(x['duration_s'] for x in all_runs)/3600,'hours',flush=True)
