"""Stage 1: independently re-read every original row; preserve all previous outputs."""
from pathlib import Path
import sys, os, json, hashlib, zlib, zipfile, csv, time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ['MPLCONFIGDIR']=str(ROOT/'.cache/matplotlib')
import numpy as np
import pandas as pd
OUT=ROOT/'output/revize_01'; OUT.mkdir(exist_ok=True)
SOURCE=Path('./input/logs')
old_inv={r['id']:r for r in json.loads((ROOT/'output/inventory.json').read_text())}
old_q={r['id']:r for r in json.loads((ROOT/'output/quality.json').read_text())}
axes=['ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps']
results=[]; evidence=[]; started=time.monotonic()

def spans(mask,dt=.01):
    e=np.diff(np.r_[False,mask,False].astype('i1'))
    return [(int(a),int(b)) for a,b in zip(np.flatnonzero(e==1),np.flatnonzero(e==-1))]

with zipfile.ZipFile(ROOT/'output/Formule_IMU.fimu') as archive:
    manifest=json.loads(archive.read('manifest.json')); archived={r['id']:r for r in manifest['runs']}
    assert set(old_inv)==set(p.stem for p in SOURCE.glob('*.csv'))==set(archived)
    for number,p in enumerate(sorted(SOURCE.glob('*.csv')),1):
        inv=old_inv[p.stem]; n=int(inv['end_s']*100)+2
        count=np.zeros(n,np.int64); badcount=count.copy(); ac=count.copy(); gc=count.copy(); mc=count.copy()
        sums=np.zeros((n,6)); rows=badrows=bytefill=tempfill=crc_bad=nonfinite=fresh_disagree=old_diff=0
        first_bad=None; after_good=[]; patterns={}; after_fresh=0; examples=0; previous_time=-1; time_backwards=0
        sha=hashlib.sha256()
        with p.open('rb') as f:
            header=f.readline();sha.update(header)
            for line in f:
                sha.update(line)
                try:
                    payload,crc=line.rstrip(b'\r\n').rsplit(b',',1)
                    if zlib.crc32(payload)!=int(crc,16):crc_bad+=1
                except ValueError:crc_bad+=1
        digest=sha.hexdigest()
        with archive.open(archived[p.stem]['raw_member']) as f: bundle_sha=hashlib.file_digest(f,'sha256').hexdigest()
        assert digest==inv['sha256']==bundle_sha, p.name
        for df in pd.read_csv(p,chunksize=200000):
            x=df[axes].to_numpy(); scales=np.repeat(32768/df[['accel_range_g','gyro_range_dps']].to_numpy(),3,axis=1)
            finite=np.isfinite(x).all(axis=1); raw=np.rint(np.nan_to_num(x)*scales).astype('i4')
            equal=(raw==raw[:,0,None]).all(axis=1)&finite
            word=raw[:,0]&65535; repeated_byte=equal&((word>>8)==(word&255))
            temp_raw=np.rint((df.temp_C.to_numpy()-21)*333.87)
            temp_match=repeated_byte&(np.abs(temp_raw-raw[:,0])<=2)
            old_raw=np.rint(np.nan_to_num(x)*np.array([2048]*3+[16.384]*3)).astype('i4')
            old_mask=(old_raw==old_raw[:,0,None]).all(axis=1)
            bad=equal|~finite
            ts=df.time_us.to_numpy(); ix=(ts//10000).astype(int)
            time_backwards+=int(np.count_nonzero(np.diff(np.r_[previous_time,ts])<0)); previous_time=int(ts[-1])
            fresh_a=df.accel_new.to_numpy()==1; fresh_g=df.gyro_new.to_numpy()==1
            fresh_m=(df.mag_new.to_numpy()==1)&(df.mag_valid.to_numpy()==1)&(df.mag_overflow.to_numpy()==0)&np.isfinite(df[['mx_uT','my_uT','mz_uT']].to_numpy()).all(axis=1)
            if first_bad is None and bad.any():first_bad=float(ts[np.flatnonzero(bad)[0]]/1e6)
            good=~bad
            if first_bad is not None:
                candidate=good&(ts/1e6>=first_bad)&(fresh_a|fresh_g);after_fresh+=int(candidate.sum())
                after_good.extend(df.loc[candidate,['time_us','seq',*axes,'temp_C','accel_new','gyro_new','mag_new','mag_valid']].head(max(0,40-len(after_good))).to_dict('records'))
            count+=np.bincount(ix,minlength=n); badcount+=np.bincount(ix[bad],minlength=n)
            for j,(fresh,counts) in enumerate([(fresh_a,ac),(fresh_g,gc)]):
                keep=good&fresh;counts+=np.bincount(ix[keep],minlength=n)
                for k in range(j*3,j*3+3):sums[:,k]+=np.bincount(ix[keep],weights=x[keep,k],minlength=n)
            mc+=np.bincount(ix[fresh_m],minlength=n)
            u,c=np.unique(raw[equal,0],return_counts=True)
            for a,b in zip(u,c):patterns[str(a)]=patterns.get(str(a),0)+int(b)
            # Exact rows retain CRC and all original fields; no manufactured correction.
            selected=np.flatnonzero(bad)[:max(0,8-examples)]
            if len(selected):
                for j in selected:
                    item=df.iloc[j].to_dict();item.update(file=p.name,source_line=rows+int(j)+2,word_hex=f'{word[j]:04X}',same_byte=bool(repeated_byte[j]),temperature_matches=bool(temp_match[j]));evidence.append(item)
                examples+=len(selected)
            rows+=len(df);badrows+=int(bad.sum());bytefill+=int(repeated_byte.sum());tempfill+=int(temp_match.sum());nonfinite+=int((~finite).sum());fresh_disagree+=int((fresh_a!=fresh_g).sum());old_diff+=int((old_mask!=bad).sum())
        assert rows==inv['rows']; assert badrows==old_q[p.stem]['digital_fault_rows'] or old_diff
        mean=np.full((n,6),np.nan)
        for j,c in enumerate([ac,gc]):
            valid=c>0;mean[valid,3*j:3*j+3]=sums[valid,3*j:3*j+3]/c[valid,None]
        strict=(count>0)&(badcount==0)&(ac>0)&(gc>0)
        allspans=spans(strict); longspans=[(a,b) for a,b in allspans if b-a>=100]
        mixed=(badcount>0)&((ac>0)|(gc>0)); rejected_mag=(badcount>0)&(mc>0)
        raw_available=(ac>0)&(gc>0);short_clean=sum(b-a for a,b in allspans if b-a<100)/100
        dynamics=[]
        # Evidence of motion, not proof of vehicle movement: 5 s clean windows.
        for a,b in longspans:
            for at in range(a,b-499,500):
                v=mean[at:at+500]; dynamics.append([at/100,float(np.max(np.std(v[:,:3],axis=0))),float(np.max(np.std(v[:,3:],axis=0))),float(np.mean(np.linalg.norm(v[:,:3],axis=1)))])
        dynamics.sort(key=lambda a:a[1],reverse=True)
        r=dict(file=p.name,id=p.stem,bytes=p.stat().st_size,rows=rows,duration_s=inv['duration_s'],sha256=digest,archive_byte_identical=True,crc_bad=crc_bad,time_backwards=time_backwards,
            repeat_six_words_rows=badrows,repeat_single_byte_rows=bytefill,temperature_same_word_rows=tempfill,nonfinite_rows=nonfinite,old_rule_disagreements=old_diff,accel_gyro_fresh_flag_disagreements=fresh_disagree,
            first_repeated_word_s=first_bad,nonpattern_fresh_rows_after_first_bad=after_fresh,after_bad_examples=after_good,
            pattern_counts=patterns,unflagged_rows=rows-badrows,clean_spans_ge1s=[[a/100,b/100] for a,b in longspans],short_clean_bins_s=short_clean,
            mixed_bins_with_unflagged_samples=int(mixed.sum()),mixed_bin_fresh_accel_rows=int(ac[mixed].sum()),mixed_bin_fresh_gyro_rows=int(gc[mixed].sum()),
            fresh_mag_rows_behind_ag_mask=int(mc[rejected_mag].sum()),mag_bins_behind_ag_mask=int(rejected_mag.sum()),strongest_clean_5s_windows=dynamics[:5])
        np.savez_compressed(OUT/(p.stem+'.npz'),count=count,badcount=badcount,accel_count=ac,gyro_count=gc,mag_count=mc,clean_means=mean.astype('f4'))
        results.append(r)
        print(f'{number}/38 {p.stem}: rows={rows}, equal={badrows}, one-byte={bytefill}, CRC={crc_bad}, rule_diff={old_diff}, mixed={mixed.sum()}, mag_hidden={mc[rejected_mag].sum()}',flush=True)

report=dict(stage=1,method='Independent full original CSV pass; actual per-row ranges; exact reconstructed integer words; archive SHA-256; row CRC; separate freshness per sensor. Repeated words are excluded from physical inference, not removed from source.',files=results,elapsed_s=time.monotonic()-started)
(OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
columns=['file','bytes','rows','duration_s','crc_bad','repeat_six_words_rows','repeat_single_byte_rows','temperature_same_word_rows','old_rule_disagreements','unflagged_rows','first_repeated_word_s','nonpattern_fresh_rows_after_first_bad','short_clean_bins_s','mixed_bins_with_unflagged_samples','mixed_bin_fresh_accel_rows','mixed_bin_fresh_gyro_rows','fresh_mag_rows_behind_ag_mask','archive_byte_identical']
with (OUT/'Prehled_revize.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(results)
with (OUT/'Dukazy_puvodnich_radku.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(evidence[0]));w.writeheader();w.writerows(evidence)
print('FINISHED',round(report['elapsed_s'],1),'s',flush=True)
