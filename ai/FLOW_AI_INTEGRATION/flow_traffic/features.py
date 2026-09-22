"""Shared train/inference feature builder with explicit per-feature availability."""
import numpy as np
import pandas as pd
from .profile import calendar_keys, fit_profile, lookup_profile
from .config import training_end


def stamp(v):
    return np.asarray(v,dtype='datetime64[ns]')


def assemble(samples,history,calendar,weather,c,profile=None,training=False):
    s=samples.copy().reset_index(drop=True)
    features=['link_id','lead_minutes']
    def add(name,values,available):
        s[name]=values
        s['available_at__'+name]=pd.to_datetime(available)
        features.append(name)
    for prefix,times in [('t',s.target_time),('r',s.request_time)]:
        for key,values in [('hour',times.dt.hour),('minute_of_day',times.dt.hour*60+times.dt.minute),('dow',times.dt.dayofweek)]:
            name=prefix+'_'+key; s[name]=values; features.append(name)
    keys=calendar_keys(s.target_time,calendar,c['profile']['bucket_minutes'])
    s['t_weekday_type']=keys.weekday_type; features.append('t_weekday_type')
    traffic=c['features']['traffic']; latency=pd.Timedelta(minutes=traffic['publication_latency_min'])
    n=len(s)
    values={}; traces={}
    def record(name,ix,v,at):
        if name not in values:
            values[name]=np.full(n,np.nan); traces[name]=np.full(n,np.datetime64('NaT','ns'),dtype='datetime64[ns]')
        values[name][ix]=v; traces[name][ix]=stamp(at)
    for lid,group in s.groupby('link_id',sort=False):
        ix=group.index.to_numpy(); h=history[history.link_id==lid].sort_values('timestamp')
        if h.empty:
            continue
        t=stamp(h.timestamp); a=stamp(h.timestamp+latency); speeds=h.speed.to_numpy(float)
        r=stamp(group.request_time); pos=np.searchsorted(a,r,side='right')-1
        safe=np.clip(pos,0,len(h)-1); valid=pos>=0
        latest=np.where(valid,speeds[safe],np.nan); latest_at=np.where(valid,a[safe],np.datetime64('NaT','ns'))
        record('obs_speed_latest',ix,latest,latest_at)
        record('obs_age_min',ix,np.where(valid,(r-t[safe])/np.timedelta64(1,'m'),np.nan),latest_at)
        prev=pos-1; psafe=np.clip(prev,0,len(h)-1); pv=prev>=0
        record('obs_speed_prev',ix,np.where(pv,speeds[psafe],np.nan),np.where(pv,a[psafe],np.datetime64('NaT','ns')))
        record('obs_gap_prev_min',ix,np.where(pv,(t[safe]-t[psafe])/np.timedelta64(1,'m'),np.nan),np.where(pv,latest_at,np.datetime64('NaT','ns')))
        record('obs_delta_recent',ix,np.where(pv,latest-speeds[psafe],np.nan),np.where(pv,latest_at,np.datetime64('NaT','ns')))
        queries=[(f'lag_{m}_speed',r-np.timedelta64(m,'m')) for m in traffic['lags_min']]
        if traffic['daily_weekly']:
            queries += [(f'prev_{name}_target_slot_speed',stamp(group.target_time)-np.timedelta64(m,'m')) for name,m in [('day',1440),('week',10080)]]
        for name,q in queries:
            j=np.searchsorted(t,q); js=np.minimum(j,len(t)-1)
            ok=(j<len(t))&(t[js]==q)&(a[js]<=r)
            record(name,ix,np.where(ok,speeds[js],np.nan),np.where(ok,a[js],np.datetime64('NaT','ns')))
        for w in traffic['rolling_windows_min']:
            left=np.searchsorted(t,r-np.timedelta64(w,'m'),side='right')
            count=np.maximum(0,pos-left+1)
            for stat in ('mean','min','max','std','count'):
                v=[]
                for lo,hi,cnt in zip(left,pos,count):
                    seq=speeds[lo:hi+1] if cnt>0 else []
                    v.append(float(cnt) if stat=='count' else (getattr(np,stat)(seq,ddof=1) if stat=='std' and cnt>1 else (np.nan if stat=='std' or not cnt else getattr(np,stat)(seq))))
                # Zero count is known at r even if there is no observation.
                at=np.where(count>0,latest_at,r) if stat=='count' else np.where(count>0,latest_at,np.datetime64('NaT','ns'))
                record(f'roll_{w}_{stat}',ix,v,at)
    # Ensure unseen links use the same feature schema.
    expected=['obs_speed_latest','obs_age_min','obs_speed_prev','obs_gap_prev_min','obs_delta_recent']+[f'lag_{m}_speed' for m in traffic['lags_min']]+[f'roll_{w}_{st}' for w in traffic['rolling_windows_min'] for st in ('mean','min','max','std','count')]
    if traffic['daily_weekly']: expected += ['prev_day_target_slot_speed','prev_week_target_slot_speed']
    for name in expected:
        add(name,values.get(name,np.full(n,np.nan)),traces.get(name,np.full(n,np.datetime64('NaT','ns'),dtype='datetime64[ns]')))
    # Prequential training profiles: only earlier calendar days, avoiding in-sample target aggregation.
    profile_arrays={f'prof_{v}':np.full(n,np.nan) for v in ('median','p25','p75','n_obs')}
    pat=np.full(n,np.datetime64('NaT','ns'),dtype='datetime64[ns]'); pend=pat.copy(); versions=np.full(n,'none',dtype=object)
    maxtrain=pd.Timestamp(training_end(c))+pd.Timedelta(days=1)
    for day,group in s.groupby(s.request_time.dt.normalize()):
        ix=group.index.to_numpy()
        if training:
            cutoff=min(day,maxtrain)
            p=fit_profile(history[history.timestamp<cutoff],calendar,c)
        else:
            p=profile
        q=lookup_profile(group,p,calendar,c)
        for name in profile_arrays: profile_arrays[name][ix]=q[name].to_numpy()
        if p is not None:
            at=pd.Timestamp(p['source_end'])+latency
            if (group.request_time<at).any(): raise ValueError('Profile was not available at request time')
            pat[ix]=at.to_datetime64(); pend[ix]=pd.Timestamp(p['source_end']).to_datetime64(); versions[ix]=p['version']
    for name,v in profile_arrays.items(): add(name,v,pat)
    s['profile_source_end']=pd.to_datetime(pend); s['profile_version']=versions
    mode=c['features']['weather']['mode']; s['wx_mode']=mode
    if mode!='none':
        wx=c['features']['weather']; vals={v:np.full(n,np.nan) for v in wx['variables']}; wat=np.full(n,np.datetime64('NaT','ns'),dtype='datetime64[ns]'); wobs=wat.copy()
        for stn in wx['stations']:
            w=weather[weather.stnId.astype(str)==str(stn)].copy()
            if w.empty: continue
            if mode=='target_forecast':
                # Exact valid time, newest issue actually available by r. No realized future observations.
                for i,row in s.iterrows():
                    if not np.isnat(wat[i]): continue
                    q=w[(w.valid_time==row.target_time)&(w.available_at<=row.request_time)&(w.issued_at<=row.request_time)].sort_values('issued_at')
                    if q.empty: continue
                    z=q.iloc[-1]
                    if (row.request_time-z.issued_at).total_seconds()/60>wx['max_age_min']: continue
                    wat[i]=z.available_at; wobs[i]=z.issued_at
                    for v in vals: vals[v][i]=z[v]
            else:
                if 'available_at' not in w: w['available_at']=w.obs_time+pd.Timedelta(minutes=wx['publication_latency_min'])
                if (w.available_at<w.obs_time).any(): raise ValueError('Weather availability before observation')
                w=w.sort_values('available_at')
                j=np.searchsorted(stamp(w.available_at),stamp(s.request_time),side='right')-1; safe=np.clip(j,0,len(w)-1)
                age=(stamp(s.request_time)-stamp(w.obs_time)[safe])/np.timedelta64(1,'m')
                ok=(j>=0)&(age>=0)&(age<=wx['max_age_min'])&np.isnat(wat)
                wat[ok]=stamp(w.available_at)[safe[ok]]; wobs[ok]=stamp(w.obs_time)[safe[ok]]
                for v in vals: vals[v][ok]=pd.to_numeric(w[v],errors='coerce').to_numpy()[safe[ok]]
        for v,a in vals.items(): add('wx_'+v,a,wat)
        add('wx_age_min',(stamp(s.request_time)-wobs)/np.timedelta64(1,'m'),wat)
        add('wx_missing',np.isnat(wat).astype(int),stamp(s.request_time))
        s['wx_available_at']=pd.to_datetime(wat); s['wx_observation_or_issue_time']=pd.to_datetime(wobs)
    s['data_badge']=c['run']['data_badge']
    return s,features

