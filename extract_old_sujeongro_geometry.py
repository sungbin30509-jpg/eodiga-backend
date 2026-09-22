from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

# ============================================================
# 0. 설정
# ============================================================
OD_PIPELINE_DIR = Path(r"C:\Users\문성빈\OneDrive\바탕 화면\flow\FLOWMATE\data\routes\od_pipeline")
OUTPUT_DIR = Path(r"C:\Users\문성빈\OneDrive\바탕 화면\FLOWMATE_PHASE2\data\nodelink_version_bridge")

TARGET_LINK_IDS = {
    "2040016202",
    "2040016203",
    "2040020000",
}

OLD_NODELINK_VERSION = "2026-08-12"

# ============================================================
# 1. 유틸
# ============================================================
def normalize_link_id(v):
    if v is None:
        return None
    return str(v).strip()


def geometry_coords(link: dict):
    """Route JSON link 객체의 geometry에서 [[lon, lat], ...] 반환."""
    g = link.get("geometry")
    if isinstance(g, dict):
        coords = g.get("coordinates")
    elif isinstance(g, list):
        coords = g
    else:
        coords = None

    if not isinstance(coords, list) or len(coords) < 2:
        return None

    out = []
    for p in coords:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        try:
            out.append([float(p[0]), float(p[1])])
        except (TypeError, ValueError):
            return None
    return out


def geometry_hash(coords):
    """좌표를 과도하게 반올림하지 않고 안정적인 geometry 식별용 hash 생성."""
    payload = json.dumps(coords, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def polyline_length_m(coords):
    return sum(
        haversine_m(a[0], a[1], b[0], b[1])
        for a, b in zip(coords, coords[1:])
    )


def iter_candidate_sequences(route: dict):
    """
    실제 구조 기준:
      route['link_mapping_v2']['link_sequence']
      route['seongnam_classification']['link_sequence']
    중 존재하는 것을 모두 탐색한다.
    """
    lm = route.get("link_mapping_v2") or {}
    seq = lm.get("link_sequence")
    if isinstance(seq, list):
        yield "link_mapping_v2.link_sequence", seq

    sc = route.get("seongnam_classification") or {}
    seq = sc.get("link_sequence")
    if isinstance(seq, list):
        yield "seongnam_classification.link_sequence", seq


# ============================================================
# 2. 전체 OD JSON 스캔
# ============================================================
if not OD_PIPELINE_DIR.exists():
    raise FileNotFoundError(f"OD pipeline 폴더를 찾을 수 없습니다: {OD_PIPELINE_DIR}")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

json_files = sorted(OD_PIPELINE_DIR.rglob("*.json"))
print(f"[INFO] OD JSON 검색 경로 : {OD_PIPELINE_DIR}")
print(f"[INFO] JSON 파일 수      : {len(json_files):,}")

occurrences = []
parse_errors = []

for idx, path in enumerate(json_files, 1):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        parse_errors.append((str(path), repr(e)))
        continue

    od_id = str(data.get("od_id") or path.stem)
    routes = ((data.get("pipeline_result") or {}).get("routes") or [])

    if not isinstance(routes, list):
        continue

    for route_index, route in enumerate(routes):
        if not isinstance(route, dict):
            continue

        candidate_id = str(route.get("candidate_id") or "")
        route_label = str(route.get("route_label") or "")

        for source_path, seq in iter_candidate_sequences(route):
            for link_index, link in enumerate(seq):
                if not isinstance(link, dict):
                    continue

                link_id = normalize_link_id(link.get("LINK_ID"))
                if link_id not in TARGET_LINK_IDS:
                    continue

                coords = geometry_coords(link)
                occurrences.append({
                    "source_file": str(path),
                    "od_id": od_id,
                    "route_index": route_index,
                    "candidate_id": candidate_id,
                    "route_label": route_label,
                    "source_path": source_path,
                    "link_index": link_index,
                    "sequence": link.get("sequence"),
                    "LINK_ID": link_id,
                    "F_NODE": normalize_link_id(link.get("F_NODE")),
                    "T_NODE": normalize_link_id(link.get("T_NODE")),
                    "ROAD_NAME": link.get("ROAD_NAME"),
                    "LENGTH": link.get("LENGTH"),
                    "geometry": coords,
                    "geometry_hash": geometry_hash(coords) if coords else None,
                    "geometry_point_count": len(coords) if coords else 0,
                    "geometry_geodesic_length_m": round(polyline_length_m(coords), 3) if coords else None,
                })

    if idx % 100 == 0:
        print(f"[SCAN] {idx:,}/{len(json_files):,}")

print(f"[INFO] parse error        : {len(parse_errors):,}")
print(f"[INFO] target occurrence  : {len(occurrences):,}")

# ============================================================
# 3. LINK별 일관성 검증
# ============================================================
by_link = defaultdict(list)
for row in occurrences:
    by_link[row["LINK_ID"]].append(row)

missing = sorted(TARGET_LINK_IDS - set(by_link))
if missing:
    print(f"[ERROR] 발견되지 않은 TARGET LINK: {missing}")

summary_rows = []
geojson_features = []

for link_id in sorted(TARGET_LINK_IDS):
    rows = by_link.get(link_id, [])
    if not rows:
        continue

    # 같은 LINK가 link_mapping_v2 / seongnam_classification 양쪽에 중복될 수 있으므로
    # geometry hash 기준으로 실제 geometry variant를 확인한다.
    geometry_variants = defaultdict(list)
    for r in rows:
        geometry_variants[r["geometry_hash"]].append(r)

    valid_variants = {k: v for k, v in geometry_variants.items() if k is not None}
    print()
    print("=" * 72)
    print(f"LINK_ID              : {link_id}")
    print(f"occurrence count     : {len(rows)}")
    print(f"geometry variants    : {len(valid_variants)}")

    # 메타데이터 일관성도 확인
    for field in ["F_NODE", "T_NODE", "ROAD_NAME", "LENGTH"]:
        vals = sorted({str(r[field]) for r in rows if r[field] is not None})
        print(f"{field:<20}: {vals}")

    if len(valid_variants) != 1:
        print("[WARNING] geometry가 하나로 일치하지 않습니다. 자동 bridge 확정 금지.")
        for h, rs in valid_variants.items():
            print(f"  - hash={h}, occurrence={len(rs)}, sample={rs[0]['source_file']}")
        continue

    h, variant_rows = next(iter(valid_variants.items()))
    sample = variant_rows[0]
    coords = sample["geometry"]

    print(f"geometry hash        : {h}")
    print(f"point count          : {len(coords)}")
    print(f"geometry length(m)   : {sample['geometry_geodesic_length_m']}")
    print(f"start lon/lat        : {coords[0]}")
    print(f"end lon/lat          : {coords[-1]}")
    print(f"sample file          : {sample['source_file']}")

    summary_rows.append({
        "old_nodelink_version": OLD_NODELINK_VERSION,
        "old_LINK_ID": link_id,
        "F_NODE": sample["F_NODE"],
        "T_NODE": sample["T_NODE"],
        "ROAD_NAME": sample["ROAD_NAME"],
        "source_LENGTH_m": sample["LENGTH"],
        "geometry_crs": "EPSG:4326",
        "geometry_hash": h,
        "geometry_point_count": len(coords),
        "geometry_geodesic_length_m": sample["geometry_geodesic_length_m"],
        "occurrence_count_all_paths": len(rows),
        "occurrence_count_this_geometry": len(variant_rows),
        "geometry_variant_count": len(valid_variants),
        "start_lon": coords[0][0],
        "start_lat": coords[0][1],
        "end_lon": coords[-1][0],
        "end_lat": coords[-1][1],
        "geometry_json": json.dumps({"type": "LineString", "coordinates": coords}, ensure_ascii=False),
        "sample_source_file": sample["source_file"],
        "sample_od_id": sample["od_id"],
        "sample_candidate_id": sample["candidate_id"],
        "sample_source_path": sample["source_path"],
    })

    geojson_features.append({
        "type": "Feature",
        "properties": {
            "old_nodelink_version": OLD_NODELINK_VERSION,
            "LINK_ID": link_id,
            "F_NODE": sample["F_NODE"],
            "T_NODE": sample["T_NODE"],
            "ROAD_NAME": sample["ROAD_NAME"],
            "LENGTH": sample["LENGTH"],
            "geometry_hash": h,
            "occurrence_count": len(rows),
            "geometry_variant_count": len(valid_variants),
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
    })

# ============================================================
# 4. 저장
# ============================================================
summary_csv = OUTPUT_DIR / "sujeongro_202608_old_links_geometry.csv"
geojson_path = OUTPUT_DIR / "sujeongro_202608_old_links_geometry.geojson"
occ_csv = OUTPUT_DIR / "sujeongro_202608_old_links_occurrences.csv"
errors_txt = OUTPUT_DIR / "sujeongro_202608_parse_errors.txt"

if summary_rows:
    with summary_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)

with geojson_path.open("w", encoding="utf-8") as f:
    json.dump({
        "type": "FeatureCollection",
        "name": "sujeongro_202608_old_links_geometry",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": geojson_features,
    }, f, ensure_ascii=False, indent=2)

# occurrence CSV에서는 geometry 전체 좌표를 빼고 hash만 남겨 파일 크기를 줄인다.
occ_fields = [
    "source_file", "od_id", "route_index", "candidate_id", "route_label",
    "source_path", "link_index", "sequence", "LINK_ID", "F_NODE", "T_NODE",
    "ROAD_NAME", "LENGTH", "geometry_hash", "geometry_point_count",
    "geometry_geodesic_length_m",
]
with occ_csv.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=occ_fields)
    w.writeheader()
    for r in occurrences:
        w.writerow({k: r.get(k) for k in occ_fields})

with errors_txt.open("w", encoding="utf-8") as f:
    for p, e in parse_errors:
        f.write(f"{p}\t{e}\n")

print()
print("=" * 72)
print("[DONE] 저장 완료")
print(f"summary CSV : {summary_csv}")
print(f"GeoJSON     : {geojson_path}")
print(f"occurrences : {occ_csv}")
print(f"parse errors: {errors_txt}")

# 핵심 안전장치
if len(summary_rows) != 3:
    print("[STOP] old 3개 모두 단일 geometry로 확정되지 않았습니다.")
    raise SystemExit(2)

print("[OK] old 3개 모두 단일 geometry로 추출됨. 다음 단계에서 2026-09-14 geometry와 비교 가능.")
