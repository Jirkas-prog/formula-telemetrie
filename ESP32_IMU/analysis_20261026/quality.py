"""Detect definite digital acquisition faults without changing the source CSV."""
from ingest import ROOT,SOURCE,COLS
import numpy as np,pandas as pd,json

def ranges(mask,dt=.01):
    edges=np.diff(np.r_[False,mask,False].astype(int))
    return [[round(a*dt,3),round(b*dt,3)] for a,b in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1))]

out=[]
for p in sorted(SOURCE.glob('*.csv')):
    z=np.load(ROOT/'cache'/f'{p.stem}.npz');n=len(z['time'])
    count=np.zeros(n,dtype=np.int64);badcount=count.copy();flatcount=count.copy()
    goodsum=np.zeros((n,6));goodcount=np.zeros((n,2),dtype=np.int64)
    bits=np.zeros(16,dtype=np.int64);badrows=0;examples=[];patterns={}
    for d in pd.read_csv(p,chunksize=250000,usecols=lambda c:c in COLS[:6]+['time_us','accel_new','gyro_new','clip_mask']):
        x=d[COLS[:6]].to_numpy();raw=np.rint(x*np.array([2048]*3+[16.384]*3)).astype(np.int32)
        # Exact repeated six 16-bit words are an invalid six-axis measurement.
        # This includes FF FF / 00 00 fills and other repeated digital patterns.
        bad=(raw==raw[:,0,None]).all(axis=1)
        flat=(raw==-1).all(axis=1)
        ix=(d.time_us.to_numpy()//10000).astype(int)
        count+=np.bincount(ix,minlength=n);badcount+=np.bincount(ix[bad],minlength=n);flatcount+=np.bincount(ix[flat],minlength=n)
        badrows+=int(bad.sum())
        if bad.any() and len(examples)<5:
            examples.extend(d.loc[bad].head(5-len(examples)).to_dict('records'))
        u,c=np.unique(raw[bad,0],return_counts=True)
        for a,b in zip(u,c):patterns[str(a)]=patterns.get(str(a),0)+int(b)
        for j,flag in enumerate([d.accel_new.to_numpy()==1,np.ones(len(d),bool)]):
            # A/G rates in this dataset are both 500 Hz and share the fresh flag.
            good=(~bad)&(d.accel_new.to_numpy()==1)
            goodcount[:,j]+=np.bincount(ix[good],minlength=n)
            for k in range(3*j,3*j+3):goodsum[:,k]+=np.bincount(ix[good],weights=x[good,k],minlength=n)
        clip=d.clip_mask.to_numpy(dtype=np.int64)
        for b in range(16):bits[b]+=np.count_nonzero(clip&(1<<b))
    goodvalues=np.full_like(goodsum,np.nan)
    for j in range(2):
        valid=goodcount[:,j]>0;goodvalues[valid,3*j:3*j+3]=goodsum[valid,3*j:3*j+3]/goodcount[valid,j,None]
    frac=np.divide(badcount,count,out=np.full(n,np.nan),where=count>0)
    strict=(count>0)&(badcount==0)&(goodcount[:,0]>0)
    spans=[r for r in ranges(strict) if r[1]-r[0]>=1]
    np.savez_compressed(ROOT/'cache'/f'{p.stem}.quality.npz',bad_fraction=frac.astype('f4'),strict=strict,goodvalues=goodvalues.astype('f4'))
    row={'id':p.stem,'digital_fault_rows':badrows,'all_ff_rows':int(flatcount.sum()),'digital_fault_fraction':badrows/int(count.sum()),'repeated_word_patterns':patterns,'clip_bit_rows':bits.tolist(),'good_spans_ge1s':spans,'examples':examples}
    out.append(row);print(p.stem,badrows,round(row['digital_fault_fraction']*100,2),'%',spans[:12],flush=True)
(ROOT/'output/quality.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
