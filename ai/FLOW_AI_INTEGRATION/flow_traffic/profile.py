"""Training-only final profile; causal prior-date profiles for training features."""
import pandas as pd
import numpy as np
from .io import frame_digest


def calendar_keys(times,calendar,bucket):
    t=pd.Series(pd.to_datetime(times)).reset_index(drop=True)
    cal=calendar.set_index('date')
    dates=t.dt.normalize()
    q=cal.reindex(dates)
    if q[['is_public_holiday','holiday_adjacent']].isna().any().any():
        raise ValueError('Calendar does not cover requested date')
    typ=np.where(q.is_public_holiday.to_numpy().astype(bool),7,np.where(q.holiday_adjacent.to_numpy().astype(bool),8,t.dt.dayofweek))
    return pd.DataFrame({'weekday_type':typ,'slot':(t.dt.hour*60+t.dt.minute)//bucket})


def fit_profile(d,calendar,c):
    if d.empty:
        return None
    keys=calendar_keys(d.timestamp,calendar,c['profile']['bucket_minutes'])
    keys['link_id']=d.link_id.to_numpy(); keys['speed']=d.speed.to_numpy(); keys['date']=d.timestamp.dt.normalize().to_numpy()
    stats=keys.groupby(['link_id','weekday_type','slot']).agg(median=('speed','median'),p25=('speed',lambda v:v.quantile(.25)),p75=('speed',lambda v:v.quantile(.75)),n_obs=('speed','size'),n_dates=('date','nunique')).reset_index()
    fallback=keys.groupby('link_id').speed.agg(['median','count']).reset_index()
    return {'table':stats,'fallback':fallback,'global':float(d.speed.median()),'source_end':d.timestamp.max(),
            'dates_used':sorted(d.timestamp.dt.strftime('%Y-%m-%d').unique()),'version':frame_digest(d[['timestamp','link_id','speed']])}


def lookup_profile(samples,p,calendar,c):
    n=len(samples)
    if p is None:
        return pd.DataFrame({f'prof_{x}':np.full(n,np.nan) for x in ('median','p25','p75','n_obs')})
    keys=calendar_keys(samples.target_time,calendar,c['profile']['bucket_minutes']); keys['link_id']=samples.link_id.to_numpy()
    q=keys.merge(p['table'],on=['link_id','weekday_type','slot'],how='left',validate='many_to_one')
    fallback=keys[['link_id']].merge(p['fallback'],on='link_id',how='left')['median']
    good=q.n_obs.ge(c['profile']['min_n_obs'])
    result={}
    for stat in ('median','p25','p75'):
        result['prof_'+stat]=q[stat].where(good,fallback).fillna(p['global']).to_numpy()
    result['prof_n_obs']=q.n_obs.fillna(0).to_numpy()
    return pd.DataFrame(result)

