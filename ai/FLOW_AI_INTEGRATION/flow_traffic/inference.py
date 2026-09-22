"""Artifact-only reload plus injected observation frames; no implicit live data access."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .features import assemble
from .models import predict_candidate
from .io import digest


def local_time(value):
    t=pd.Timestamp(value)
    return t.tz_convert('Asia/Seoul').tz_localize(None) if t.tzinfo else t


def iso(t):
    return local_time(t).tz_localize('Asia/Seoul').isoformat()


class TrafficPredictor:
    @classmethod
    def load(cls,path):
        obj=cls(); obj.root=Path(path).resolve()
        obj.meta=json.loads((obj.root/'bundle.json').read_text(encoding='utf-8'))
        for rel,h in obj.meta['files'].items():
            p=(obj.root/rel).resolve()
            if not p.is_relative_to(obj.root) or digest(p)!=h: raise ValueError('Artifact digest mismatch')
        obj.cfg=obj.meta['config']; obj.profile=json.loads((obj.root/'profile.json').read_text())
        obj.profile['table']=pd.read_parquet(obj.root/'profile.parquet'); obj.profile['fallback']=pd.read_parquet(obj.root/'profile_fallback.parquet')
        obj.profile['source_end']=pd.Timestamp(obj.profile['source_end'])
        obj.calendar=pd.read_parquet(obj.root/'calendar.parquet')
        obj.history=pd.DataFrame(columns=['timestamp','link_id','speed'])
        obj.weather=pd.DataFrame(columns=['obs_time','stnId']+obj.cfg['features']['weather']['variables'])
        return obj

    def set_context(self,history,weather=None,calendar=None):
        self.history=history.copy()
        self.history['timestamp']=pd.to_datetime(self.history.timestamp)
        if self.history.timestamp.dt.tz is not None:
            self.history['timestamp']=self.history.timestamp.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
        self.history['link_id']=self.history.link_id.astype(str)
        if self.history.duplicated(['link_id','timestamp']).any(): raise ValueError('Duplicate live context keys')
        if weather is not None: self.weather=weather.copy()
        for col in ('obs_time','issued_at','available_at','valid_time'):
            if col in self.weather:
                self.weather[col]=pd.to_datetime(self.weather[col])
                if self.weather[col].dt.tz is not None:
                    self.weather[col]=self.weather[col].dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
        if calendar is not None:
            self.calendar=calendar.copy()
            self.calendar['date']=pd.to_datetime(self.calendar.date).dt.normalize()
        return self

    def predict_traffic(self,request_time,target_times,link_ids):
        r=local_time(request_time); targets=[local_time(t) for t in target_times]
        if len(set(targets))!=len(targets) or len(set(link_ids))!=len(link_ids): raise ValueError('Duplicate target/link request')
        if not targets or not link_ids: raise ValueError('Empty request')
        if any(t<r or t.second or t.microsecond or t.minute%5 for t in targets): raise ValueError('Targets must be future/current 5-minute slots')
        if r < pd.Timestamp(self.meta['trained_information_available_at']): raise ValueError('Model trained after request cutoff')
        sample=pd.DataFrame([{'link_id':str(l),'request_time':r,'target_time':t,'lead_minutes':(t-r).total_seconds()/60} for l in link_ids for t in targets])
        f,_=assemble(sample,self.history,self.calendar,self.weather,self.cfg,profile=self.profile)
        prediction=predict_candidate(f,self.root/'model',self.cfg)
        supported=self.cfg['inference']['supported_lead_minutes']
        # Null support is deliberately unvalidated; provisional developer predictions are explicitly tagged.
        upper=self.cfg['lead']['max_lead_minutes'] if supported is None else supported
        results=[]
        for i,row in f.iterrows():
            within=self.cfg['lead']['min_lead_minutes']<=row.lead_minutes<=upper
            current=pd.notna(row.obs_speed_latest) and row.obs_age_min<=self.cfg['features']['traffic']['max_age_min']
            known=row.link_id in self.meta['known_links']
            method='model'; value=float(prediction[i])
            if row.lead_minutes==0 and current:
                method='live_observed'; value=float(row.obs_speed_latest)
            elif not within or not current or not known:
                method='fallback_baseline'; value=float(row.prof_median)
            thresholds=self.cfg['inference']['congestion_thresholds_kmh']
            level=['jam','slow','moderate','free'][int(np.searchsorted(thresholds,value,side='right'))]
            availability={'traffic_observation_time':iso(r-pd.Timedelta(minutes=float(row.obs_age_min))) if current else None,
                          'traffic_available_at':iso(row['available_at__obs_speed_latest']) if current else None,
                          'weather_mode':self.cfg['features']['weather']['mode'],
                          'weather_as_of':iso(row.wx_available_at) if 'wx_available_at' in row and pd.notna(row.wx_available_at) else None,
                          'historical_profile_version':row.profile_version,'profile_available_at':iso(row['available_at__prof_median'])}
            results.append({'request_time':iso(r),'target_time':iso(row.target_time),'lead_minutes':float(row.lead_minutes),'link_id':row.link_id,
                'predicted_speed_kmh':value,'congestion_level':level,'congestion_policy':'analytical_thresholds_not_official',
                'output_method':method,'model_version':self.meta['run_id'],'information_available_at':availability,
                'lead_within_support':bool(within and supported is not None),'within_provisional_training_range':bool(within),
                'support_status':'unvalidated_provisional' if supported is None else 'validation_declared','data_badge':self.cfg['run']['data_badge']})
        return results
