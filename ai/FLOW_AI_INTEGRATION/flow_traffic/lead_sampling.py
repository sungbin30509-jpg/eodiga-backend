"""Target-anchored exact labels with bounded sampling intermediates."""
import numpy as np
import pandas as pd
from .config import training_end


def split_of(t,c):
    d=pd.Series(pd.to_datetime(t)).dt.normalize()
    result=pd.Series('outside',index=d.index)
    result[d.between(pd.Timestamp(c['periods']['train']['start']),pd.Timestamp(training_end(c)))]='train'
    key='validation' if c['run']['stage']=='develop' else 'final_test'
    result[d.between(pd.Timestamp(c['periods'][key]['start']),pd.Timestamp(c['periods'][key]['end']))]=key
    return result


def bin_ids(values,bins):
    a=np.asarray(values); out=np.full(len(a),-1,dtype=int)
    for i,(lo,hi) in enumerate(bins): out[(a>=lo)&((a<hi) if i<len(bins)-1 else (a<=hi))]=i
    return out


def build_samples(d,c):
    grid=np.asarray(c['lead']['lead_grid']); k=c['lead']['samples_per_target']; rng=np.random.default_rng(c['run']['seed'])
    bins=bin_ids(grid,c['model']['lead_bins']); strata=sorted(set(bins)); frames=[]
    target_parts=split_of(d.timestamp,c).to_numpy()
    possible=np.empty((len(d),len(grid)),dtype=bool)
    linkcodes,links=pd.factorize(d.link_id,sort=True); hours=d.timestamp.dt.hour.to_numpy()
    counts={'lead_minutes':np.zeros(len(grid),dtype=np.int64),'target_hour':np.zeros(24,dtype=np.int64),'link_id':np.zeros(len(links),dtype=np.int64)}
    for j,lead in enumerate(grid):
        req=d.timestamp-pd.Timedelta(minutes=int(lead))
        valid=(split_of(req,c).to_numpy()==target_parts)&(target_parts!='outside'); possible[:,j]=valid
        counts['lead_minutes'][j]=valid.sum()
        counts['target_hour']+=np.bincount(hours[valid],minlength=24)
        counts['link_id']+=np.bincount(linkcodes[valid],minlength=len(links))
    expected=int(np.minimum(possible.sum(axis=1),k).sum())
    if expected>c['quality']['max_samples']:
        raise ValueError('STOP: sample memory budget exceeded before sample expansion; revise resource budget/config explicitly')
    for start in range(0,len(d),25000):
        stop=min(start+25000,len(d)); mask=possible[start:stop]; size=stop-start
        scores=rng.random(mask.shape); scores[~mask]=np.inf
        strategy=c['lead']['lead_sampling_strategy']
        choices=np.full((size,k),-1,dtype=int)
        if strategy=='fixed_list':
            priority=np.broadcast_to(np.arange(len(grid)),mask.shape).astype(float).copy(); priority[~mask]=np.inf
        elif strategy=='uniform_random': priority=scores.copy()
        else:
            # Each stratum gets one draw before another draw from the same stratum.
            # Random stratum ordering avoids favoring short leads when k is small.
            priority=np.full(mask.shape,np.inf)
            stratum_order=np.argsort(rng.random((size,len(strata))),axis=1)
            stratum_rank=np.argsort(stratum_order,axis=1)
            for b in strata:
                cols=np.flatnonzero(bins==b)
                rank=np.argsort(np.argsort(scores[:,cols],axis=1),axis=1)
                priority[:,cols]=rank*len(strata)+stratum_rank[:,strata.index(b),None]+scores[:,cols]*.001
            priority[~mask]=np.inf
        for slot in range(k):
            best=np.argmin(priority,axis=1); valid=np.isfinite(priority[np.arange(size),best])
            choices[valid,slot]=best[valid]; priority[np.arange(size),best]=np.inf
        row,slot=np.nonzero(choices>=0); chosen=choices[row,slot]
        f=d.iloc[start+row][['link_id','corridor_name','timestamp','speed']].reset_index(drop=True).rename(columns={'timestamp':'target_time','speed':'y_speed_kmh'})
        f['lead_minutes']=grid[chosen]; f['request_time']=f.target_time-pd.to_timedelta(f.lead_minutes,unit='min'); f['sample_weight']=1.
        frames.append(f)
    s=pd.concat(frames,ignore_index=True).sort_values(['request_time','link_id','target_time']).reset_index(drop=True)
    s['target_hour']=s.target_time.dt.hour
    summaries={}
    for key,values in [('lead_minutes',grid),('target_hour',np.arange(24)),('link_id',links)]:
        q=pd.DataFrame({key:values,'possible':counts[key]})
        q=q.merge(s.groupby(key).size().rename('sampled').reset_index(),on=key,how='left').fillna({'sampled':0})
        q['sampled']=q.sampled.astype(int); q['possible_share']=q.possible/q.possible.sum(); q['sampled_share']=q.sampled/q.sampled.sum()
        q['sampling_rate']=np.divide(q.sampled,q.possible,out=np.zeros(len(q)),where=q.possible>0)
        summaries[key]=q.to_dict('records')
    summaries['boundary_purged_candidates']=int(len(d)*len(grid)-counts['lead_minutes'].sum())
    summaries['weighting']='Selected rows weight 1; same sampled cohort across candidates. Diagnostic proportions are not population-unbiased.'
    return s,summaries
