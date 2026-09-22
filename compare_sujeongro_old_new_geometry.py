from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

# ============================================================
# 0. 경로 / 기준
# ============================================================
BASE_DIR = Path(r"C:\Users\문성빈\OneDrive\바탕 화면\FLOWMATE_PHASE2")
BRIDGE_DIR = BASE_DIR / "data" / "nodelink_version_bridge"
OLD_GEOJSON = BRIDGE_DIR / "sujeongro_202608_old_links_geometry.geojson"

OLD_VERSION = "2026-08-12"
NEW_VERSION = "2026-09-14"

OLD_ORDER = ["2040016202", "2040016203", "2040020000"]
NEW_ORDER = ["2049001900", "2049002000", "2049002100"]
TOLERANCES_M = [2.0, 3.0, 5.0, 8.0]
PRIMARY_TOL_M = 5.0

# route_integration.zip의 2026-09-14 원본 CSV geometry_wkt 그대로 사용.
# CRS: ITRF2000 Central Belt, EPSG:5186과 동일한 투영 파라미터.
NEW_LINKS = {
    "2049001900": {
        "F_NODE": "2049148400",
        "T_NODE": "2049204500",
        "ROAD_NAME": "수정로",
        "LENGTH": 172.63786649676,
        "WKT": "LINESTRING (212863.356206 538747.473553, 212864.482808 538768.540292, 212866.178969 538776.078887, 212868.247935 538782.86335, 212873.624915 538799.714931, 212880.92401 538814.125602, 212907.182308 538856.995873, 212913.096404 538866.327892, 212926.715043 538888.712763, 212934.693775 538901.832636)",
    },
    "2049002000": {
        "F_NODE": "2049204500",
        "T_NODE": "2049204600",
        "ROAD_NAME": "수정로",
        "LENGTH": 12.012664349112,
        "WKT": "LINESTRING (212934.693775 538901.832636, 212940.933756 538912.097466)",
    },
    "2049002100": {
        "F_NODE": "2049204600",
        "T_NODE": "2049204700",
        "ROAD_NAME": "수정로",
        "LENGTH": 84.798082677514,
        "WKT": "LINESTRING (212940.933756 538912.097466, 212945.408538 538919.451716, 212954.719797 538934.848901, 212967.817275 538956.51162, 212983.876816 538985.204417)",
    },
}

# 9월 앞/뒤 본선 1-hop (연결성 참고용)
NEW_CONTEXT = {
    "before": {
        "LINK_ID": "2040016200",
        "F_NODE": "2040008701",
        "T_NODE": "2049148400",
        "LENGTH": 192.936641999669,
    },
    "after": {
        "LINK_ID": "2049002700",
        "F_NODE": "2049204700",
        "T_NODE": "2049205100",
        "LENGTH": 88.708562824723,
    },
}

# ============================================================
# 1. 의존성
# ============================================================
try:
    from pyproj import Transformer
    from shapely.geometry import LineString, mapping, shape
    from shapely.ops import transform
    from shapely import wkt
except ImportError as e:
    print("[ERROR] 필요한 패키지가 없습니다:", e)
    print("아래 명령 실행 후 다시 시도하세요:")
    print(r'py -3.11 -m pip install shapely pyproj')
    sys.exit(1)

TO_5186 = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)
TO_4326 = Transformer.from_crs("EPSG:5186", "EPSG:4326", always_xy=True)

# ============================================================
# 2. 유틸
# ============================================================
def line_from_coords(coords):
    return LineString([(float(x), float(y)) for x, y in coords])


def chain_from_order(lines_by_id, order, gap_warn_m=1.0):
    coords = []
    gaps = []
    for i, link_id in enumerate(order):
        c = list(lines_by_id[link_id].coords)
        if i == 0:
            coords.extend(c)
            continue
        px, py = coords[-1]
        sx, sy = c[0]
        gap = math.hypot(px - sx, py - sy)
        gaps.append((order[i - 1], link_id, gap))
        if gap > gap_warn_m:
            print(f"[WARNING] chain gap {order[i-1]} -> {link_id}: {gap:.3f} m")
        if gap < 0.01:
            coords.extend(c[1:])
        else:
            coords.extend(c)
    return LineString(coords), gaps


def buffered_overlap(a, b, tol_m):
    # a 길이 중 b 중심선에서 tol 이내에 들어가는 길이
    if a.length <= 0:
        return 0.0, 0.0
    inside = a.intersection(b.buffer(tol_m, cap_style=2, join_style=2)).length
    return inside, inside / a.length


def point_xy(p):
    return [round(float(p.x), 3), round(float(p.y), 3)]


def chainage_boundaries(lines_by_id, order):
    out = []
    acc = 0.0
    for i, link_id in enumerate(order):
        line = lines_by_id[link_id]
        if i > 0:
            out.append({
                "between": f"{order[i-1]} | {link_id}",
                "chainage_m": acc,
                "point": line.interpolate(0.0),
            })
        acc += line.length
    return out


def locate_chainage(chainage, lines_by_id, order):
    acc = 0.0
    for link_id in order:
        L = lines_by_id[link_id].length
        if chainage <= acc + L + 1e-6:
            return link_id, max(0.0, min(L, chainage - acc))
        acc += L
    last = order[-1]
    return last, lines_by_id[last].length


# ============================================================
# 3. old GeoJSON 읽기
# ============================================================
if not OLD_GEOJSON.exists():
    raise FileNotFoundError(f"old GeoJSON이 없습니다: {OLD_GEOJSON}")

with OLD_GEOJSON.open("r", encoding="utf-8") as f:
    old_gj = json.load(f)

old_meta = {}
old_4326 = {}
for feat in old_gj.get("features", []):
    p = feat.get("properties") or {}
    link_id = str(p.get("LINK_ID") or "").strip()
    if link_id not in OLD_ORDER:
        continue
    geom = shape(feat["geometry"])
    old_4326[link_id] = geom
    old_meta[link_id] = p

missing = [x for x in OLD_ORDER if x not in old_4326]
if missing:
    raise RuntimeError(f"old GeoJSON에서 LINK_ID 누락: {missing}")

old_5186 = {
    k: transform(TO_5186.transform, g)
    for k, g in old_4326.items()
}
new_5186 = {
    k: wkt.loads(v["WKT"])
    for k, v in NEW_LINKS.items()
}

old_chain, old_gaps = chain_from_order(old_5186, OLD_ORDER)
new_chain, new_gaps = chain_from_order(new_5186, NEW_ORDER)

# ============================================================
# 4. 기본 체인 검증
# ============================================================
print("=" * 84)
print("[1] CHAIN BASIC CHECK")
print("=" * 84)
print(f"old chain geometry length : {old_chain.length:.3f} m")
print(f"new chain geometry length : {new_chain.length:.3f} m")
print(f"difference                : {new_chain.length - old_chain.length:+.3f} m")
print(f"old internal max gap      : {max([g[2] for g in old_gaps] or [0]):.6f} m")
print(f"new internal max gap      : {max([g[2] for g in new_gaps] or [0]):.6f} m")

old_start = old_chain.interpolate(0)
old_end = old_chain.interpolate(old_chain.length)
new_start = new_chain.interpolate(0)
new_end = new_chain.interpolate(new_chain.length)

start_dist = old_start.distance(new_start)
end_dist = old_end.distance(new_end)
reverse_score = old_start.distance(new_end) + old_end.distance(new_start)
forward_score = start_dist + end_dist

print(f"start endpoint distance   : {start_dist:.3f} m")
print(f"end endpoint distance     : {end_dist:.3f} m")
print(f"direction score forward   : {forward_score:.3f}")
print(f"direction score reverse   : {reverse_score:.3f}")
print(f"direction match           : {'YES' if forward_score < reverse_score else 'NO'}")
print(f"new predecessor           : {NEW_CONTEXT['before']['LINK_ID']} -> {NEW_CONTEXT['before']['T_NODE']}")
print(f"new target start F_NODE   : {NEW_LINKS[NEW_ORDER[0]]['F_NODE']}")
print(f"new target end T_NODE     : {NEW_LINKS[NEW_ORDER[-1]]['T_NODE']}")
print(f"new successor             : {NEW_CONTEXT['after']['F_NODE']} -> {NEW_CONTEXT['after']['LINK_ID']}")

# ============================================================
# 5. 전체 체인 overlap 민감도
# ============================================================
print()
print("=" * 84)
print("[2] WHOLE-CHAIN GEOMETRY COVERAGE")
print("=" * 84)
whole_sensitivity = []
for tol in TOLERANCES_M:
    old_cov_m, old_cov = buffered_overlap(old_chain, new_chain, tol)
    new_cov_m, new_cov = buffered_overlap(new_chain, old_chain, tol)
    row = {
        "tolerance_m": tol,
        "old_covered_m": old_cov_m,
        "old_coverage_ratio": old_cov,
        "new_covered_m": new_cov_m,
        "new_coverage_ratio": new_cov,
    }
    whole_sensitivity.append(row)
    print(
        f"tol={tol:>4.1f}m | old->new {old_cov_m:8.3f}m ({old_cov*100:7.3f}%)"
        f" | new->old {new_cov_m:8.3f}m ({new_cov*100:7.3f}%)"
    )

# ============================================================
# 6. old x new pairwise overlap
# ============================================================
print()
print("=" * 84)
print(f"[3] PAIRWISE OVERLAP MATRIX @ {PRIMARY_TOL_M:.1f}m")
print("old_ratio = old LINK 길이 중 해당 new LINK corridor와 겹치는 비율")
print("new_ratio = new LINK 길이 중 해당 old LINK corridor와 겹치는 비율")
print("=" * 84)

pair_rows = []
for old_id in OLD_ORDER:
    for new_id in NEW_ORDER:
        o = old_5186[old_id]
        n = new_5186[new_id]
        row = {
            "old_nodelink_version": OLD_VERSION,
            "old_LINK_ID": old_id,
            "old_F_NODE": str(old_meta[old_id].get("F_NODE", "")),
            "old_T_NODE": str(old_meta[old_id].get("T_NODE", "")),
            "old_geometry_length_m": round(o.length, 6),
            "new_nodelink_version": NEW_VERSION,
            "new_LINK_ID": new_id,
            "new_F_NODE": NEW_LINKS[new_id]["F_NODE"],
            "new_T_NODE": NEW_LINKS[new_id]["T_NODE"],
            "new_geometry_length_m": round(n.length, 6),
        }
        for tol in TOLERANCES_M:
            om, oratio = buffered_overlap(o, n, tol)
            nm, nratio = buffered_overlap(n, o, tol)
            suffix = str(int(tol)) if float(tol).is_integer() else str(tol).replace('.', '_')
            row[f"old_overlap_m_tol{suffix}"] = round(om, 6)
            row[f"old_overlap_ratio_tol{suffix}"] = round(oratio, 6)
            row[f"new_overlap_m_tol{suffix}"] = round(nm, 6)
            row[f"new_overlap_ratio_tol{suffix}"] = round(nratio, 6)
        pair_rows.append(row)

# 예쁘게 출력
h = f"{'OLD':<12} {'NEW':<12} {'old_overlap(m)':>14} {'old_ratio':>11} {'new_overlap(m)':>14} {'new_ratio':>11}"
print(h)
print("-" * len(h))
for row in pair_rows:
    print(
        f"{row['old_LINK_ID']:<12} {row['new_LINK_ID']:<12} "
        f"{row['old_overlap_m_tol5']:>14.3f} {row['old_overlap_ratio_tol5']*100:>10.2f}% "
        f"{row['new_overlap_m_tol5']:>14.3f} {row['new_overlap_ratio_tol5']*100:>10.2f}%"
    )

# ============================================================
# 7. 내부 분할점 chainage 비교
# ============================================================
print()
print("=" * 84)
print("[4] SPLIT-NODE PROJECTION")
print("old 내부 경계를 new chain에 투영 / new 내부 경계를 old chain에 투영")
print("=" * 84)

old_boundary_results = []
for b in chainage_boundaries(old_5186, OLD_ORDER):
    p = b["point"]
    ch = new_chain.project(p)
    nearest = new_chain.interpolate(ch)
    dist = p.distance(nearest)
    target_link, within = locate_chainage(ch, new_5186, NEW_ORDER)
    rec = {
        "source": "old_boundary",
        "between": b["between"],
        "projected_chain": "new",
        "projected_chainage_m": ch,
        "nearest_distance_m": dist,
        "falls_on_LINK_ID": target_link,
        "within_link_chainage_m": within,
    }
    old_boundary_results.append(rec)
    print(
        f"OLD boundary {b['between']} -> NEW chainage={ch:.3f} m, "
        f"distance={dist:.3f} m, falls_on={target_link}, within={within:.3f} m"
    )

new_boundary_results = []
for b in chainage_boundaries(new_5186, NEW_ORDER):
    p = b["point"]
    ch = old_chain.project(p)
    nearest = old_chain.interpolate(ch)
    dist = p.distance(nearest)
    target_link, within = locate_chainage(ch, old_5186, OLD_ORDER)
    rec = {
        "source": "new_boundary",
        "between": b["between"],
        "projected_chain": "old",
        "projected_chainage_m": ch,
        "nearest_distance_m": dist,
        "falls_on_LINK_ID": target_link,
        "within_link_chainage_m": within,
    }
    new_boundary_results.append(rec)
    print(
        f"NEW boundary {b['between']} -> OLD chainage={ch:.3f} m, "
        f"distance={dist:.3f} m, falls_on={target_link}, within={within:.3f} m"
    )

# ============================================================
# 8. 진단 파일 저장 (아직 최종 bridge 아님)
# ============================================================
BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

pair_csv = BRIDGE_DIR / "sujeongro_old_new_pairwise_overlap.csv"
with pair_csv.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
    writer.writeheader()
    writer.writerows(pair_rows)

# overlay GeoJSON: old/new를 한 파일에 넣어 QGIS/geojson.io 등에서 확인 가능
overlay_features = []
for link_id in OLD_ORDER:
    overlay_features.append({
        "type": "Feature",
        "properties": {
            "version": OLD_VERSION,
            "kind": "old",
            "LINK_ID": link_id,
            "F_NODE": str(old_meta[link_id].get("F_NODE", "")),
            "T_NODE": str(old_meta[link_id].get("T_NODE", "")),
        },
        "geometry": mapping(old_4326[link_id]),
    })

for link_id in NEW_ORDER:
    g4326 = transform(TO_4326.transform, new_5186[link_id])
    overlay_features.append({
        "type": "Feature",
        "properties": {
            "version": NEW_VERSION,
            "kind": "new",
            "LINK_ID": link_id,
            "F_NODE": NEW_LINKS[link_id]["F_NODE"],
            "T_NODE": NEW_LINKS[link_id]["T_NODE"],
        },
        "geometry": mapping(g4326),
    })

overlay_geojson = BRIDGE_DIR / "sujeongro_old_new_overlay.geojson"
with overlay_geojson.open("w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection", "features": overlay_features}, f, ensure_ascii=False, indent=2)

# 진단 JSON
diagnostics = {
    "status": "diagnostic_only_not_final_bridge",
    "old_nodelink_version": OLD_VERSION,
    "new_nodelink_version": NEW_VERSION,
    "projected_crs": "EPSG:5186",
    "primary_tolerance_m": PRIMARY_TOL_M,
    "old_order": OLD_ORDER,
    "new_order": NEW_ORDER,
    "old_chain_geometry_length_m": old_chain.length,
    "new_chain_geometry_length_m": new_chain.length,
    "chain_length_difference_m": new_chain.length - old_chain.length,
    "start_endpoint_distance_m": start_dist,
    "end_endpoint_distance_m": end_dist,
    "direction_forward_score_m": forward_score,
    "direction_reverse_score_m": reverse_score,
    "direction_match": bool(forward_score < reverse_score),
    "whole_chain_sensitivity": whole_sensitivity,
    "old_boundary_projection_to_new": old_boundary_results,
    "new_boundary_projection_to_old": new_boundary_results,
    "new_context": NEW_CONTEXT,
    "note": "이 파일은 geometry 진단 결과이며 nodelink_version_bridge 최종 확정 파일이 아님",
}

diag_json = BRIDGE_DIR / "sujeongro_old_new_geometry_diagnostics.json"
with diag_json.open("w", encoding="utf-8") as f:
    json.dump(diagnostics, f, ensure_ascii=False, indent=2)

print()
print("=" * 84)
print("[DONE] geometry 비교 진단 파일 저장")
print(f"pairwise CSV : {pair_csv}")
print(f"overlay      : {overlay_geojson}")
print(f"diagnostics  : {diag_json}")
print("[IMPORTANT] 아직 최종 nodelink_version_bridge.csv를 만들지 않았습니다.")
print("            위 수치 확인 후 1:1 / 1:N / N:M 관계를 확정합니다.")
