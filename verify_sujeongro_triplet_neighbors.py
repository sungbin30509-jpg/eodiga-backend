from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

OD_PIPELINE_DIR = Path(r"C:\Users\문성빈\OneDrive\바탕 화면\flow\FLOWMATE\data\routes\od_pipeline")

OLD_TRIPLET = ["2040016202", "2040016203", "2040020000"]
TARGET_SET = set(OLD_TRIPLET)

def norm(v):
    return None if v is None else str(v).strip()

def get_seq(route: dict):
    """
    canonical raw source 우선:
      1) link_mapping_v2.link_sequence
      2) 없을 때만 seongnam_classification.link_sequence fallback
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

json_files = sorted(OD_PIPELINE_DIR.rglob("*.json"))

print("=" * 88)
print("[INFO] TARGETED ROUTE-SEQUENCE / NEIGHBOR CHECK")
print("=" * 88)
print(f"OD JSON 검색 경로 : {OD_PIPELINE_DIR}")
print(f"JSON 파일 수      : {len(json_files):,}")
print(f"old target chain  : {' -> '.join(OLD_TRIPLET)}")
print()

parse_errors = []
routes_with_any_target = 0
exact_triplet_routes = 0
non_exact_routes = []
triplet_positions = Counter()
prev_links = Counter()
next_links = Counter()
prev_meta = defaultdict(Counter)
next_meta = defaultdict(Counter)
source_counter = Counter()

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
        source_path, seq = get_seq(route)
        if not seq:
            continue

        ids = [norm(x.get("LINK_ID")) if isinstance(x, dict) else None for x in seq]
        hit_idx = [i for i, lid in enumerate(ids) if lid in TARGET_SET]
        if not hit_idx:
            continue

        routes_with_any_target += 1
        source_counter[source_path] += 1

        exact_starts = [
            i for i in range(0, len(ids) - 2)
            if ids[i:i+3] == OLD_TRIPLET
        ]

        if len(exact_starts) == 1 and len(hit_idx) == 3:
            exact_triplet_routes += 1
            s = exact_starts[0]
            triplet_positions[s] += 1

            prev_obj = seq[s - 1] if s > 0 and isinstance(seq[s - 1], dict) else None
            next_obj = seq[s + 3] if s + 3 < len(seq) and isinstance(seq[s + 3], dict) else None

            prev_id = norm(prev_obj.get("LINK_ID")) if prev_obj else "<ROUTE_START>"
            next_id = norm(next_obj.get("LINK_ID")) if next_obj else "<ROUTE_END>"

            prev_links[prev_id] += 1
            next_links[next_id] += 1

            if prev_obj:
                prev_meta[prev_id][(
                    norm(prev_obj.get("F_NODE")),
                    norm(prev_obj.get("T_NODE")),
                    str(prev_obj.get("ROAD_NAME")),
                    str(prev_obj.get("LENGTH")),
                )] += 1

            if next_obj:
                next_meta[next_id][(
                    norm(next_obj.get("F_NODE")),
                    norm(next_obj.get("T_NODE")),
                    str(next_obj.get("ROAD_NAME")),
                    str(next_obj.get("LENGTH")),
                )] += 1
        else:
            non_exact_routes.append({
                "file": str(path),
                "od_id": od_id,
                "candidate_id": candidate_id,
                "hit_indices": hit_idx,
                "target_ids_in_route": [ids[i] for i in hit_idx],
                "exact_starts": exact_starts,
            })

    if idx % 100 == 0:
        print(f"[SCAN] {idx:,}/{len(json_files):,}")

print()
print("=" * 88)
print("[1] SUMMARY")
print("=" * 88)
print(f"parse errors                : {len(parse_errors)}")
print(f"routes containing any old   : {routes_with_any_target}")
print(f"exact contiguous triplet    : {exact_triplet_routes}")
print(f"non-exact / partial routes  : {len(non_exact_routes)}")
print(f"source path                 : {dict(source_counter)}")

print()
print("=" * 88)
print("[2] PREVIOUS LINK FREQUENCY")
print("=" * 88)
for lid, cnt in prev_links.most_common():
    print(f"{lid:<16} {cnt:>5} routes")
    for meta, mc in prev_meta.get(lid, {}).most_common():
        print(f"    F_NODE={meta[0]} T_NODE={meta[1]} ROAD_NAME={meta[2]} LENGTH={meta[3]}  ({mc})")

print()
print("=" * 88)
print("[3] NEXT LINK FREQUENCY")
print("=" * 88)
for lid, cnt in next_links.most_common():
    print(f"{lid:<16} {cnt:>5} routes")
    for meta, mc in next_meta.get(lid, {}).most_common():
        print(f"    F_NODE={meta[0]} T_NODE={meta[1]} ROAD_NAME={meta[2]} LENGTH={meta[3]}  ({mc})")

if non_exact_routes:
    print()
    print("=" * 88)
    print("[4] NON-EXACT SAMPLES (최대 20개)")
    print("=" * 88)
    for row in non_exact_routes[:20]:
        print(row)

print()
print("=" * 88)
if parse_errors:
    print("[WARNING] parse error가 있습니다.")
elif non_exact_routes:
    print("[STOP] 대상 LINK가 일부 Route에서 정확한 연속 triplet이 아닙니다.")
    print("       아직 sequence-level canonical replacement를 확정하지 마세요.")
else:
    print("[OK] 대상 old 3개는 target을 포함한 모든 Route에서 정확히 연속 triplet입니다.")
    print("     위 PREVIOUS/NEXT LINK를 이용해 전후 topology 연결성까지 판단할 수 있습니다.")
print("=" * 88)
