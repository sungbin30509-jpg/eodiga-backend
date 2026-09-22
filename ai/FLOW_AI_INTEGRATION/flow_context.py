"""Recent-traffic / weather / calendar context adapters for TrafficPredictor.set_context().

TrafficPredictor needs, at request_time, observations that are at most `max_age_min` (60) minutes old for a link to be
predicted by the model (output_method=model). Otherwise it falls back to the historical profile (fallback_baseline).
This module ONLY adapts REAL observations; it never fabricates traffic.

Sources (choose one, or concatenate several):
  * ITS 5-min daily-file history (offline, KST naive, slot timestamps)          -> load_its_history()
  * GITS getRoadLinkTrafficInfoList snapshot(s) saved as parquet/csv            -> gits_frame_to_history()
  * GITS live fetch now (needs your own GITS_API_KEY in .env, reuses src/collectors/gits.py) -> fetch_gits_live()
Weather is optional (missing weather -> wx_missing=1, model still runs).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# GITS routeIds whose links overlap the 355 supported links (verified 2026-09-10: 339-343 links per snapshot).
GITS_ROUTES = [("1020000651", "분당수서로"), ("1050000234", "밤고개로/대왕판교로/신수로"), ("1010000011", "경부고속도로"), ("1030000031", "국도 3호선(이천~서울)")]
HISTORY_COLUMNS = ["timestamp", "link_id", "speed"]


def _kst_naive(series: pd.Series) -> pd.Series:
    t = pd.to_datetime(series)
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    return t


def load_its_history(path) -> pd.DataFrame:
    """ITS history parquet with columns timestamp(KST naive, 5-min slots), link_id, speed."""
    h = pd.read_parquet(path, columns=HISTORY_COLUMNS)
    h["timestamp"] = _kst_naive(h.timestamp); h["link_id"] = h.link_id.astype(str); h["speed"] = pd.to_numeric(h.speed, errors="coerce")
    return h.dropna(subset=["speed"]).reset_index(drop=True)


def gits_frame_to_history(gits: pd.DataFrame, floor_to_slot: bool = True) -> pd.DataFrame:
    """Normalised GITS traffic records (from src.collectors.gits / collect_gits_realtime partitions) -> history frame.

    GITS `timestamp` (collDate) carries seconds; the model was trained on 5-minute slot timestamps, so by default
    the timestamp is floored to its 5-minute slot and the newest record per (link_id, slot) is kept.
    Speed 0 / empty rows are dropped (GITS reports 0 when no probe data).
    """
    g = gits.copy()
    g["link_id"] = g.link_id.astype(str)
    g["timestamp"] = _kst_naive(g.timestamp)
    g["speed"] = pd.to_numeric(g.speed, errors="coerce")
    g = g[g.speed.notna() & g.speed.gt(0) & g.timestamp.notna()]
    g = g.sort_values("timestamp")
    if floor_to_slot:
        g["timestamp"] = g.timestamp.dt.floor("5min")
    g = g.drop_duplicates(["link_id", "timestamp"], keep="last")
    return g[HISTORY_COLUMNS].reset_index(drop=True)


def load_gits_snapshot(path, floor_to_slot: bool = True) -> pd.DataFrame:
    p = Path(path)
    g = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, dtype=str)
    return gits_frame_to_history(g, floor_to_slot)


def fetch_gits_live(routes=GITS_ROUTES, floor_to_slot: bool = True, save_dir: Path | None = None) -> pd.DataFrame:
    """Fetch current GITS link traffic for the routes (one request per route). Requires GITS_API_KEY in .env / env.
    Reuses src.collectors.gits (never prints keys or URLs). Returns a history frame; optionally saves the raw frame."""
    from src import config
    from src.collectors import gits
    if not config.has_api_key(config.GITS_API_KEY_NAME):
        raise RuntimeError(f"{config.GITS_API_KEY_NAME} is not set (put your own key in .env next to this file)")
    frames = []
    for rid, name in routes:
        norm, resp, env = gits.collect_route_traffic(rid, name)
        if norm is None:
            print(f"GITS route {rid} returned no data: {gits.sanitized_envelope_summary(env)}")
            continue
        frames.append(norm)
    if not frames:
        raise RuntimeError("GITS returned no traffic records")
    raw = pd.concat(frames, ignore_index=True)
    if save_dir is not None:
        save_dir = Path(save_dir); save_dir.mkdir(parents=True, exist_ok=True)
        stamp = pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y%m%dT%H%M%S")
        raw.to_parquet(save_dir / f"gits_live_{stamp}.parquet", index=False)
    return gits_frame_to_history(raw, floor_to_slot)


def merge_history(*frames: pd.DataFrame) -> pd.DataFrame:
    """Concatenate several history frames; later frames win on duplicate (link_id, timestamp)."""
    h = pd.concat([f[HISTORY_COLUMNS] for f in frames if f is not None and len(f)], ignore_index=True)
    return h.drop_duplicates(["link_id", "timestamp"], keep="last").sort_values(["link_id", "timestamp"]).reset_index(drop=True)


def load_weather(path) -> pd.DataFrame:
    """ASOS hourly rows: stnId(str), obs_time(KST naive), ta, rn_mm, hm, ws, vs. Optional."""
    w = pd.read_parquet(path)
    w["stnId"] = w.stnId.astype(str); w["obs_time"] = _kst_naive(w.obs_time)
    return w.reset_index(drop=True)


def empty_weather() -> pd.DataFrame:
    return pd.DataFrame(columns=["stnId", "obs_time", "ta", "rn_mm", "hm", "ws", "vs"])


# Korean public holidays after the training calendar (2026-09..12). VERIFY before service use.
HOLIDAYS_2026_Q4 = {"2026-09-24": "추석 연휴", "2026-09-25": "추석", "2026-09-26": "추석 연휴", "2026-09-28": "대체공휴일(추석)",
                    "2026-10-03": "개천절", "2026-10-05": "대체공휴일(개천절)", "2026-10-09": "한글날", "2026-12-25": "성탄절"}


def calendar_through(base_calendar: pd.DataFrame, until: str = "2026-12-31") -> pd.DataFrame:
    """Extend the artifact calendar (date, is_public_holiday, holiday_adjacent) to `until` so predict_traffic accepts later dates."""
    cal = base_calendar.copy(); cal["date"] = pd.to_datetime(cal.date).dt.normalize()
    last = cal.date.max()
    rows = []
    for t in pd.date_range(last + pd.Timedelta(days=1), until):
        k = t.strftime("%Y-%m-%d"); prev = (t - pd.Timedelta(days=1)).strftime("%Y-%m-%d"); nxt = (t + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        rows.append({"date": t, "weekday": t.strftime("%a"), "is_public_holiday": k in HOLIDAYS_2026_Q4, "holiday_name": HOLIDAYS_2026_Q4.get(k, ""),
                     "holiday_adjacent": (k not in HOLIDAYS_2026_Q4) and t.dayofweek < 5 and (prev in HOLIDAYS_2026_Q4 or nxt in HOLIDAYS_2026_Q4),
                     "calendar_extension": "handoff_unverified"})
    if not rows:
        return cal
    return pd.concat([cal, pd.DataFrame(rows)], ignore_index=True)


def latest_observation_age(history: pd.DataFrame, request_time, link_ids) -> pd.DataFrame:
    """Diagnostic: per link, newest observation at/before request_time and its age in minutes (None if absent)."""
    r = pd.Timestamp(request_time)
    r = r.tz_convert("Asia/Seoul").tz_localize(None) if r.tzinfo else r
    h = history[history.link_id.isin([str(l) for l in link_ids]) & (history.timestamp <= r)]
    newest = h.groupby("link_id").timestamp.max()
    out = pd.DataFrame({"link_id": [str(l) for l in link_ids]})
    out["latest_observation"] = out.link_id.map(newest)
    out["age_min"] = (r - out.latest_observation).dt.total_seconds() / 60
    return out
