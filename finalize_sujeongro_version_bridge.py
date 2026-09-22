from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

# ============================================================
# 0. 경로 / 기준
# ============================================================
BASE_DIR = Path(r"C:\Users\문성빈\OneDrive\바탕 화면\FLOWMATE_PHASE2")
BRIDGE_DIR = BASE_DIR / "data" / "nodelink_version_bridge"
OD_PIPELINE_DIR = Path(
    r"C:\Users\문성빈\OneDrive\바탕 화면\flow\FLOWMATE\data\routes\od_pipeline"
)

PAIRWISE_CSV = BRIDGE_DIR / "sujeongro_old_new_pairwise_overlap.csv"
DIAG_JSON = BRIDGE_DIR / "sujeongro_old_new_geometry_diagnostics.json"

OUT_BRIDGE = BRIDGE_DIR / "nodelink_version_bridge.csv"
OUT_RULE = BRIDGE_DIR / "sujeongro_normalization_rule.json"
OUT_VERIFY = BRIDGE_DIR / "sujeongro_final_verification.json"

OLD_VERSION = "2026-08-12"
NEW_VERSION = "2026-09-14"

OLD_ORDER = ["2040016202", "2040016203", "2040020000"]
NEW_ORDER = ["2049001900", "2049002000", "2049002100"]

EXPECTED_PREDECESSOR = "2040016200"
PRIMARY_TOL = 5

RELATION_GROUP_ID = "sujeongro_20260812_20260914_001"
RELATION_TYPE = "N:M_RESEGMENTATION"
NORMALIZATION_METHOD = "contiguous_sequence_resegmentation_v1"


def norm(v):
    return None if v is None else str(v).strip()


def get_route_sequence(route: dict):
    """
    raw Route canonical source:
      link_mapping_v2.link_sequence 우선
      없을 때만 seongnam_classification.link_sequence fallback
    """
    lm = route.get("link_mapping_v2") or {}
    seq = lm.get("link_sequence")
    if isinstance(seq, list) and seq:
        return "link_mapping_v2.link_sequence", seq

    sc = route.get("seongnam_classification") or {}
    seq = sc.get("link_sequence")
    if isinstance(seq, list) and seq:
        return "seongnam_classification.link_sequence", seq

    return None, []


# ============================================================
# 1. 선행 산출물 존재 확인
# ============================================================
for p in [PAIRWISE_CSV, DIAG_JSON]:
    if not p.exists():
        raise FileNotFoundError(f"필수 선행 파일이 없습니다: {p}")

with DIAG_JSON.open("r", encoding="utf-8") as f:
    diag = json.load(f)

with PAIRWISE_CSV.open("r", encoding="utf-8-sig", newline="") as f:
    pair_rows = list(csv.DictReader(f))

# ============================================================
# 2. geometry 최종 안전검증
# ============================================================
whole5 = None
for row in diag.get("whole_chain_sensitivity", []):
    if abs(float(row["tolerance_m"]) - PRIMARY_TOL) < 1e-9:
        whole5 = row
        break

if whole5 is None:
    raise RuntimeError("5m whole-chain coverage 진단값을 찾을 수 없습니다.")

geometry_checks = {
    "direction_match": bool(diag.get("direction_match")),
    "start_endpoint_distance_m": float(diag["start_endpoint_distance_m"]),
    "end_endpoint_distance_m": float(diag["end_endpoint_distance_m"]),
    "old_chain_geometry_length_m": float(diag["old_chain_geometry_length_m"]),
    "new_chain_geometry_length_m": float(diag["new_chain_geometry_length_m"]),
    "chain_length_difference_m": float(diag["chain_length_difference_m"]),
    "old_coverage_ratio_tol5": float(whole5["old_coverage_ratio"]),
    "new_coverage_ratio_tol5": float(whole5["new_coverage_ratio"]),
}

geometry_ok = (
    geometry_checks["direction_match"]
    and geometry_checks["start_endpoint_distance_m"] <= 0.5
    and geometry_checks["end_endpoint_distance_m"] <= 5.0
    and abs(geometry_checks["chain_length_difference_m"]) <= 5.0
    and geometry_checks["old_coverage_ratio_tol5"] >= 0.999
    and geometry_checks["new_coverage_ratio_tol5"] >= 0.99
)

if not geometry_ok:
    print("[STOP] geometry 안전조건을 통과하지 못했습니다.")
    print(json.dumps(geometry_checks, ensure_ascii=False, indent=2))
    raise SystemExit(2)

# ============================================================
# 3. 600 OD raw Route에서 sequence-level topology 재검증
# ============================================================
json_files = sorted(OD_PIPELINE_DIR.rglob("*.json"))

parse_errors = []
routes_with_any_target = 0
exact_triplet_routes = 0
non_exact_routes = []
source_counter = Counter()
prev_links = Counter()
next_links = Counter()

target_set = set(OLD_ORDER)

for idx, path in enumerate(json_files, 1):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        parse_errors.append({"file": str(path), "error": repr(e)})
        continue

    routes = ((data.get("pipeline_result") or {}).get("routes") or [])
    if not isinstance(routes, list):
        continue

    for route in routes:
        if not isinstance(route, dict):
            continue

        source_path, seq = get_route_sequence(route)
        if not seq:
            continue

        ids = [norm(x.get("LINK_ID")) if isinstance(x, dict) else None for x in seq]
        hit_idx = [i for i, lid in enumerate(ids) if lid in target_set]
        if not hit_idx:
            continue

        routes_with_any_target += 1
        source_counter[source_path] += 1

        starts = [
            i for i in range(len(ids) - len(OLD_ORDER) + 1)
            if ids[i:i + len(OLD_ORDER)] == OLD_ORDER
        ]

        # target을 하나라도 포함한 Route라면 정확히 한 번 OLD triplet 전체가 연속 등장해야 함
        if len(starts) != 1 or len(hit_idx) != len(OLD_ORDER):
            non_exact_routes.append({
                "file": str(path),
                "candidate_id": route.get("candidate_id"),
                "hit_indices": hit_idx,
                "target_ids": [ids[i] for i in hit_idx],
                "exact_triplet_starts": starts,
            })
            continue

        exact_triplet_routes += 1
        s = starts[0]
        prev_id = ids[s - 1] if s > 0 else "<ROUTE_START>"
        next_id = ids[s + len(OLD_ORDER)] if s + len(OLD_ORDER) < len(ids) else "<ROUTE_END>"
        prev_links[prev_id] += 1
        next_links[next_id] += 1

route_sequence_ok = (
    len(parse_errors) == 0
    and routes_with_any_target > 0
    and exact_triplet_routes == routes_with_any_target
    and len(non_exact_routes) == 0
)

predecessor_ok = (
    sum(prev_links.values()) == exact_triplet_routes
    and set(prev_links.keys()) == {EXPECTED_PREDECESSOR}
)

if not route_sequence_ok or not predecessor_ok:
    print("[STOP] raw Route sequence/topology 검증 실패")
    print("routes_with_any_target :", routes_with_any_target)
    print("exact_triplet_routes   :", exact_triplet_routes)
    print("non_exact_routes       :", len(non_exact_routes))
    print("prev_links             :", dict(prev_links))
    print("next_links             :", dict(next_links))
    raise SystemExit(3)

# ============================================================
# 4. 유효 old↔new pair 추출
# ============================================================
# 5m corridor에서 실질적으로 겹치는 pair만 bridge edge로 사용.
# 현재 케이스는 5개 edge가 나와야 한다.
bridge_pairs = []

for r in pair_rows:
    old_ratio = float(r[f"old_overlap_ratio_tol{PRIMARY_TOL}"])
    new_ratio = float(r[f"new_overlap_ratio_tol{PRIMARY_TOL}"])
    old_m = float(r[f"old_overlap_m_tol{PRIMARY_TOL}"])
    new_m = float(r[f"new_overlap_m_tol{PRIMARY_TOL}"])

    # 경계부 N:M 관계까지 보존하되 0 overlap은 제외
    if max(old_m, new_m) <= 0.5:
        continue

    bridge_pairs.append({
        "relation_group_id": RELATION_GROUP_ID,
        "old_nodelink_version": OLD_VERSION,
        "old_LINK_ID": r["old_LINK_ID"],
        "new_nodelink_version": NEW_VERSION,
        "new_LINK_ID": r["new_LINK_ID"],
        "relation_type": RELATION_TYPE,
        "geometry_tolerance_m": PRIMARY_TOL,
        "old_overlap_m": round(old_m, 6),
        "old_overlap_ratio": round(old_ratio, 6),
        "new_overlap_m": round(new_m, 6),
        "new_overlap_ratio": round(new_ratio, 6),
        "direction_match": True,
        "topology_verified": True,
        "topology_verification_scope": (
            "old/new chains contiguous; shared predecessor 2040016200 verified on all target routes; "
            "downstream raw-route successor not observable where target component is route end"
        ),
        "confidence": "HIGH",
        "normalization_method": NORMALIZATION_METHOD,
        "note": (
            "Do not perform independent LINK_ID rename. "
            "Normalize the contiguous old triplet as one resegmented component."
        ),
    })

expected_edges = {
    ("2040016202", "2049001900"),
    ("2040016203", "2049001900"),
    ("2040016203", "2049002000"),
    ("2040016203", "2049002100"),
    ("2040020000", "2049002100"),
}
actual_edges = {(x["old_LINK_ID"], x["new_LINK_ID"]) for x in bridge_pairs}

if actual_edges != expected_edges:
    print("[STOP] 예상된 N:M bridge edge와 실제 geometry edge가 다릅니다.")
    print("expected:", sorted(expected_edges))
    print("actual  :", sorted(actual_edges))
    raise SystemExit(4)

# ============================================================
# 5. 최종 bridge CSV 저장
# ============================================================
BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

fieldnames = [
    "relation_group_id",
    "old_nodelink_version",
    "old_LINK_ID",
    "new_nodelink_version",
    "new_LINK_ID",
    "relation_type",
    "geometry_tolerance_m",
    "old_overlap_m",
    "old_overlap_ratio",
    "new_overlap_m",
    "new_overlap_ratio",
    "direction_match",
    "topology_verified",
    "topology_verification_scope",
    "confidence",
    "normalization_method",
    "note",
]

with OUT_BRIDGE.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(bridge_pairs)

# ============================================================
# 6. canonical normalization rule 저장
# ============================================================
normalization_rule = {
    "rule_id": RELATION_GROUP_ID,
    "status": "verified",
    "old_nodelink_version": OLD_VERSION,
    "canonical_nodelink_version": NEW_VERSION,
    "relation_type": RELATION_TYPE,
    "raw_sequence_match": OLD_ORDER,
    "canonical_sequence_replace": NEW_ORDER,
    "required_predecessor_LINK_ID": EXPECTED_PREDECESSOR,
    "required_predecessor_match_count": exact_triplet_routes,
    "observed_next_LINK_ID_counts": dict(next_links),
    "normalization_method": NORMALIZATION_METHOD,
    "normalization_status": "verified_local_bridge",
    "preserve_raw_route": True,
    "independent_link_id_rename_allowed": False,
    "instructions": [
        "원본 Route LINK_ID와 2026-08-12 버전은 그대로 보존한다.",
        "old 3개를 개별 1:1 치환하지 않는다.",
        "Route에서 old triplet이 연속으로 나타날 때 component 단위로 new triplet으로 교체한다.",
        "canonical sequence 생성 후 인접 중복 LINK_ID가 생기지 않도록 sequence 단위로 처리한다.",
        "AI 입력 및 최종 coverage 검증은 2026-09-14 canonical LINK_ID를 사용한다.",
    ],
    "recommended_lineage_fields": [
        "route_link_id_raw",
        "route_nodelink_version",
        "canonical_link_id",
        "canonical_nodelink_version",
        "normalization_method",
        "normalization_status",
        "bridge_relation_group_id",
        "raw_source_link_ids",
    ],
    "important_schema_note": (
        "이번 관계는 N:M이므로 route_link_id_raw 하나에 canonical_link_id 하나를 "
        "기계적으로 붙이는 단순 1:1 스키마만으로는 완전한 lineage를 표현할 수 없다. "
        "raw_source_link_ids 또는 별도 bridge table을 함께 보존해야 한다."
    ),
}

with OUT_RULE.open("w", encoding="utf-8") as f:
    json.dump(normalization_rule, f, ensure_ascii=False, indent=2)

# ============================================================
# 7. 최종 검증 로그 저장
# ============================================================
verification = {
    "status": "PASS",
    "geometry_checks": geometry_checks,
    "json_file_count_scanned": len(json_files),
    "parse_error_count": len(parse_errors),
    "routes_with_any_old_target": routes_with_any_target,
    "exact_contiguous_triplet_routes": exact_triplet_routes,
    "non_exact_or_partial_routes": len(non_exact_routes),
    "sequence_source_counts": dict(source_counter),
    "previous_LINK_ID_counts": dict(prev_links),
    "next_LINK_ID_counts": dict(next_links),
    "bridge_edge_count": len(bridge_pairs),
    "bridge_edges": sorted([list(x) for x in actual_edges]),
    "conclusion": (
        "2026-08-12 old 수정로 3개와 2026-09-14 new 수정로 3개는 "
        "동일 물리구간의 N:M resegmentation component로 검증됨."
    ),
}

with OUT_VERIFY.open("w", encoding="utf-8") as f:
    json.dump(verification, f, ensure_ascii=False, indent=2)

# ============================================================
# 8. 출력
# ============================================================
print("=" * 92)
print("[PASS] SUJEONGRO NODELINK VERSION BRIDGE FINALIZED")
print("=" * 92)
print(f"JSON files scanned          : {len(json_files)}")
print(f"parse errors                : {len(parse_errors)}")
print(f"routes containing old       : {routes_with_any_target}")
print(f"exact contiguous triplet    : {exact_triplet_routes}")
print(f"non-exact / partial routes  : {len(non_exact_routes)}")
print(f"previous LINK counts        : {dict(prev_links)}")
print(f"next LINK counts            : {dict(next_links)}")
print()
print(f"relation type               : {RELATION_TYPE}")
print(f"bridge edges                : {len(bridge_pairs)}")
for x in bridge_pairs:
    print(
        f"  {x['old_LINK_ID']} -> {x['new_LINK_ID']} | "
        f"old={x['old_overlap_ratio']*100:.2f}% "
        f"new={x['new_overlap_ratio']*100:.2f}%"
    )
print()
print(f"[SAVE] {OUT_BRIDGE}")
print(f"[SAVE] {OUT_RULE}")
print(f"[SAVE] {OUT_VERIFY}")
print()
print("[IMPORTANT]")
print("개별 LINK_ID 1:1 rename 금지.")
print(
    "canonical normalization은 "
    "2040016202 -> 2040016203 -> 2040020000 "
    "전체 연속 sequence를 "
    "2049001900 -> 2049002000 -> 2049002100 "
    "으로 component 단위 교체."
)
