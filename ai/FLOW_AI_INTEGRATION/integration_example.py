"""Minimal end-to-end example: TMAP route -> standard LINK_IDs -> TrafficPredictor -> future speed per (link, target_time).

Run from this folder (any location on disk):
    python integration_example.py                         # context = ITS snapshot 2026-08-28..31, request 2026-09-01 00:00 KST
    python integration_example.py --context gits-file     # context = real GITS snapshot 2026-09-10 20:4x KST
    python integration_example.py --context gits-live     # context = GITS now (needs your own GITS_API_KEY in .env)
    python integration_example.py --links 2050019200 2050028700 --request 2026-09-01T00:00:00+09:00 --leads 5 30 60 120
Exit code 0 only when every supported link returned output_method=model.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from flow_traffic.inference import TrafficPredictor  # noqa: E402
import flow_context as fc  # noqa: E402

ARTIFACT = HERE / "artifact"
CTX = HERE / "context"


def build_context(mode: str):
    """Returns (history, weather, request_time_default). Only real observations."""
    if mode == "its-snapshot":
        hist = fc.load_its_history(CTX / "its_history_tail_2026-08-28_to_08-31.parquet")
        wx = fc.load_weather(CTX / "asos_hourly_tail_2026-08-25_to_09-01.parquet")
        return hist, wx, pd.Timestamp("2026-09-01 00:00")  # = earliest request the artifact accepts; ITS obs 23:55 is 5 min old
    if mode == "gits-file":
        hist = fc.load_gits_snapshot(CTX / "gits_snapshot_2026-09-10_2042KST.parquet")
        return hist, fc.empty_weather(), hist.timestamp.max() + pd.Timedelta(minutes=5)
    if mode == "gits-live":
        hist = fc.fetch_gits_live(save_dir=HERE / "context" / "live")
        now = pd.Timestamp.now(tz="Asia/Seoul").floor("5min").tz_localize(None)
        return hist, fc.empty_weather(), now
    raise ValueError(mode)


def fallback_reason(row: dict, pred: TrafficPredictor, age: dict) -> str:
    cfg = pred.cfg
    if row["link_id"] not in pred.meta["known_links"]:
        return "link not in supported 355 links (model has no data for it)"
    a = age.get(row["link_id"])
    if a is None or pd.isna(a):
        return "no traffic observation for this link at/before request_time in the supplied context"
    if a > cfg["features"]["traffic"]["max_age_min"]:
        return f"newest observation is {a:.0f} min old (> {cfg['features']['traffic']['max_age_min']} min)"
    if not (cfg["lead"]["min_lead_minutes"] <= row["lead_minutes"] <= cfg["lead"]["max_lead_minutes"]):
        return f"lead {row['lead_minutes']:.0f} min outside training range {cfg['lead']['min_lead_minutes']}-{cfg['lead']['max_lead_minutes']}"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--context", choices=["its-snapshot", "gits-file", "gits-live"], default="its-snapshot")
    ap.add_argument("--links", nargs="*", help="standard LINK_IDs from the TMAP route mapping (default: 4 supported + 1 unsupported demo)")
    ap.add_argument("--request", help="request_time ISO (KST); default depends on --context")
    ap.add_argument("--leads", nargs="*", type=int, default=[5, 30, 60, 120, 240], help="minutes after request_time -> target_times")
    ap.add_argument("--json", action="store_true", help="print full result list as JSON")
    a = ap.parse_args()

    # 1) load artifact (sha256-verified) and context
    pred = TrafficPredictor.load(ARTIFACT)
    hist, wx, r_default = build_context(a.context)
    cal = fc.calendar_through(pred.calendar, "2026-12-31")
    pred.set_context(hist, wx, cal)
    print(f"model_version={pred.meta['run_id']} role={pred.meta['model_role']} known_links={len(pred.meta['known_links'])}")
    print(f"context: {len(hist)} observations, {hist.link_id.nunique()} links, {hist.timestamp.min()} .. {hist.timestamp.max()} (KST)")

    # 2) the values the TMAP side hands over: standard LINK_IDs (10-digit strings) + request_time + target_times
    links = a.links or ["2050019200", "2050028700", "2060104700", "2040010100", "9999999999"]
    r = pd.Timestamp(a.request) if a.request else r_default
    r = r.tz_convert("Asia/Seoul").tz_localize(None) if r.tzinfo else r
    targets = [r + pd.Timedelta(minutes=m) for m in a.leads]  # absolute future 5-min slots
    print(f"request_time={r}  target_times={[t.strftime('%H:%M') for t in targets]}")

    # 3) predict (all links x all targets in one call)
    res = pred.predict_traffic(r, targets, links)
    age = fc.latest_observation_age(hist, r, links).set_index("link_id").age_min.to_dict()
    ok = True
    for x in res:
        line = f"{x['link_id']} target={x['target_time'][11:16]} lead={x['lead_minutes']:>5.0f} speed={x['predicted_speed_kmh']:6.1f} km/h {x['congestion_level']:<8} method={x['output_method']} support={x['support_status']}"
        if x["output_method"] != "model":
            line += f"  <- {fallback_reason(x, pred, age)}"
            if x["link_id"] in pred.meta["known_links"]:
                ok = False
        print(line)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    n_model = sum(x["output_method"] == "model" for x in res)
    print(f"{n_model}/{len(res)} predictions via model; {'OK' if ok else 'FALLBACK on supported links'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
