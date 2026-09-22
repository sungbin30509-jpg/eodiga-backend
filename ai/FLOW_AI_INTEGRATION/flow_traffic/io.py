"""IO guards, selected-period digests and atomic checkpoints."""
import hashlib
import json
from pathlib import Path
import pandas as pd
import pyarrow.dataset as ds
from .config import path_for, bounds


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def frame_digest(d):
    return hashlib.sha256(pd.util.hash_pandas_object(d, index=False).to_numpy().tobytes()).hexdigest()


def read_period(c, field, time_column):
    """Filter before materialization; develop never materializes August rows."""
    path = path_for(c,c['data'][field])
    start, end = bounds(c)
    end_exclusive = pd.Timestamp(end) + pd.Timedelta(days=1)
    if path.suffix == '.parquet':
        dataset = ds.dataset(path,format='parquet')
        typ = dataset.schema.field(time_column).type
        import pyarrow as pa
        lo, hi = (start, str(end_exclusive)[:10]) if pa.types.is_string(typ) or pa.types.is_large_string(typ) else (pd.Timestamp(start),end_exclusive)
        expr = (ds.field(time_column)>=lo) & (ds.field(time_column)<hi)
        count = dataset.count_rows(filter=expr)
        if count > c['quality']['max_input_rows']:
            raise ValueError('STOP: input row memory budget exceeded before materialization')
        d = dataset.to_table(filter=expr).to_pandas()
    else:
        # Real monolithic CSV is disallowed: it would read August during develop.
        if c['run']['data_badge'] != 'fixture':
            raise ValueError('Real time-series input requires filterable Parquet')
        d = pd.read_csv(path, dtype={'link_id':str,'LINKID':str,'stnId':str})
        t = pd.to_datetime(d[time_column])
        d = d[(t >= pd.Timestamp(start)) & (t < end_exclusive)].copy()
    d[time_column] = pd.to_datetime(d[time_column])
    if d[time_column].dt.tz is not None:
        raise ValueError('Offline inputs must be explicitly normalized naive KST')
    return d.reset_index(drop=True)
