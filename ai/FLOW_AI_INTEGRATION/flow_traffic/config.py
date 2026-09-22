"""Strict new-pipeline YAML configuration; no legacy config or credentials imported."""
from pathlib import Path
import copy
import json
import hashlib
import yaml
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, sort_keys=True, default=str, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def path_for(cfg, value, output=False):
    p = (ROOT / value).resolve()
    if not p.is_relative_to(ROOT):
        raise ValueError('Path must stay inside repository')
    if cfg['run']['data_badge'] == 'fixture':
        if not p.is_relative_to(ROOT / 'data/fixture'):
            raise ValueError('Fixture IO must stay in data/fixture, including artifacts')
    elif output and not p.is_relative_to(ROOT / 'runs/traffic_v5'):
        raise ValueError('Real outputs must stay in runs/traffic_v5; existing artifacts are protected')
    return p


def load_config(path, stage=None):
    cfg = yaml.safe_load(Path(path).read_text(encoding='utf-8-sig'))
    if stage:
        cfg['run']['stage'] = stage
    validate(cfg)
    return cfg


def validate(c):
    if c['run']['stage'] not in ('develop', 'final-test') or c['run']['data_badge'] not in ('fixture', 'real'):
        raise ValueError('Invalid stage/data badge')
    if not 1 <= c['run']['threads'] <= 4:
        raise ValueError('Use 1–4 threads; no collector contention')
    if c['model']['family'] != 'lightgbm':
        raise ValueError('Only LightGBM is supported')
    lead = c['lead']
    if not 5 <= lead['min_lead_minutes'] <= lead['max_lead_minutes']:
        raise ValueError('Training lead must start at >=5; zero is observed-state inference only')
    grid = lead['lead_grid']
    if len(set(grid)) != len(grid) or any(x % 5 or not lead['min_lead_minutes'] <= x <= lead['max_lead_minutes'] for x in grid):
        raise ValueError('Unique 5-minute leads within configured bounds required')
    if lead['lead_sampling_strategy'] not in ('grid_stratified', 'uniform_random', 'fixed_list'):
        raise ValueError('Unknown lead sampling strategy')
    if not 1 <= lead['samples_per_target'] <= len(grid):
        raise ValueError('Invalid samples_per_target')
    support=c['inference']['supported_lead_minutes']
    if support is not None and not lead['min_lead_minutes'] <= support <= lead['max_lead_minutes']:
        raise ValueError('Declared support must stay within the configured training range')
    for key, maximum in [('lead_bins', lead['max_lead_minutes']), ('target_time_bins', 1440)]:
        bins = c['model'][key]
        start = lead['min_lead_minutes'] if key == 'lead_bins' else 0
        if not bins or bins[0][0] != start or bins[-1][1] != maximum:
            raise ValueError('Bins must cover the whole configured range')
        if any(a >= b for a,b in bins) or any(bins[i][1] != bins[i+1][0] for i in range(len(bins)-1)):
            raise ValueError('Bins must be contiguous and disjoint')
    if not set(c['model']['structures']) <= {'single', 'lead_bins', 'target_time_bins'} or not c['model']['structures']:
        raise ValueError('Unknown/empty model structures')
    previous = None
    for part in ('train', 'validation', 'final_test'):
        period = c['periods'][part]
        begin, end = pd.Timestamp(period['start']), pd.Timestamp(period['end'])
        if begin > end or (previous is not None and begin <= previous):
            raise ValueError('Chronological nonoverlapping periods required')
        previous = end
    if c['run']['data_badge'] == 'real':
        expected = [('2026-03-01','2026-06-30'),('2026-07-01','2026-07-31'),('2026-08-01','2026-08-31')]
        actual = [(c['periods'][p]['start'],c['periods'][p]['end']) for p in ('train','validation','final_test')]
        if actual != expected:
            raise ValueError('Real v5 protocol fixes March–June / July / August')
    if c['features']['weather']['mode'] not in ('none', 'request_observed', 'target_forecast'):
        raise ValueError('Invalid weather mode')
    if c['features']['weather']['mode'] == 'target_forecast' and not c['data'].get('forecast'):
        raise ValueError('target_forecast requires a genuine issued forecast archive')
    for value in c['data'].values():
        if value:
            path_for(c, value)
    path_for(c, c['output']['root'], output=True)
    for item in (c['features']['traffic'], c['features']['weather']):
        if item['publication_latency_min'] < 0:
            raise ValueError('Negative publication latency is forbidden')


def protocol(cfg):
    """Design locked with July; output directory, run ID and stage are not design."""
    return {k: copy.deepcopy(cfg[k]) for k in ('periods','lead','features','model','profile','quality','inference')}


def bounds(c):
    return c['periods']['train']['start'], c['periods']['validation' if c['run']['stage']=='develop' else 'final_test']['end']


def training_end(c):
    return c['periods']['train' if c['run']['stage']=='develop' else 'validation']['end']
