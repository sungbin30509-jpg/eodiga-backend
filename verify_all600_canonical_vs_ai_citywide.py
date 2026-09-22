from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

# =============================================================================
# 0. 프로젝트 경로
# =============================================================================
PHASE2 = Path(r"C:\Users\문성빈\OneDrive\바탕 화면\FLOWMATE_PHASE2")
OD_DIR = Path(
    r"C:\Users\문성빈\OneDrive\바탕 화면\flow\FLOWMATE\data\routes\od_pipeline"
)
BRIDGE_DIR = PHASE2 / "data" / "nodelink_version_bridge"

RULE_JSON = BRIDGE_DIR / "sujeongro_normalization_rule.json"
BRIDGE_CSV = BRIDGE_DIR / "nodelink_version_bridge.csv"

OUT_DIR = BRIDGE_DIR / "final_ai_universe_verification"
OUT_SUMMARY = OUT_DIR / "all600_canonical_vs_ai_citywide_summary.json"
OUT_UNMATCHED_RAW = OUT_DIR / "raw_unmatched_links.csv"
OUT_UNMATCHED_CANON = OUT_DIR / "canonical_unmatched_links.csv"
OUT_CANONICAL_LINKS = OUT_DIR / "canonical_route_links.csv"

# AI팀 universe 파일 경로를 알고 있다면 아래에 직접 넣어도 됨.
# None이면 알려진 프로젝트 루트에서 seongnam_citywide_links_v1.csv를 자동 탐색.
AI_UNIVERSE_OVERRIDE = None

AI_UNIVERSE_FILENAME = "seongnam_citywide_links_v1.csv"

ALLOWED_QUALITY = {"good", "recovered", "review"}

# 이전 전수검증 기준값
EXPECTED = {
    "od_count": 600,
    "pipeline_success_od": 597,
    "usable_routes": 1467,
    "all_route_link_rows": 76808,
    "seongnam_route_link_rows": 47758,
    "raw_seongnam_unique_links": 1065,
    "ai_universe_unique_links": 10708,
    "raw_unmatched_unique_links": 3,
}

EXPECTED_OLD_UNMATCHED = {"2040016202", "2040016203", "2040020000"}


def norm_link_id(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s


def read_csv_dicts(path: Path):
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            return rows, enc
        except UnicodeDecodeError as e:
            last_err = e
    raise last_err


def find_ai_universe():
    if AI_UNIVERSE_OVERRIDE:
        p = Path(AI_UNIVERSE_OVERRIDE)
        if not p.exists():
            raise FileNotFoundError(f"AI_UNIVERSE_OVERRIDE 파일 없음: {p}")
        return p

    search_roots = [
        PHASE2,
        Path(r"C:\Users\문성빈\OneDrive\바탕 화면\flow"),
        Path(r"C:\flow"),
    ]

    candidates = []
    seen = set()

    for root in search_roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob(AI_UNIVERSE_FILENAME):
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    candidates.append(p)
        except PermissionError:
            pass

    if not candidates:
        print("[STOP] seongnam_citywide_links_v1.csv 자동 탐색 실패")
        print("스크립트 상단 AI_UNIVERSE_OVERRIDE에 실제 경로를 넣고 다시 실행하세요.")
        raise SystemExit(10)

    valid = []
    for p in candidates:
        try:
            rows, enc = read_csv_dicts(p)
            if not rows:
                continue
            cols = set(rows[0].keys())
            link_col = next(
                (c for c in ("LINK_ID", "link_id", "Link_ID") if c in cols),
                None
            )
            if not link_col:
                continue

            unique_count = len({
                norm_link_id(r.get(link_col))
                for r in rows
                if norm_link_id(r.get(link_col))
            })
            valid.append((p, unique_count, link_col, enc))
        except Exception:
            continue

    exact = [x for x in valid if x[1] == EXPECTED["ai_universe_unique_links"]]

    print("[INFO] AI universe 후보")
    for p, n, col, enc in valid:
        mark = "  <== 10,708" if n == EXPECTED["ai_universe_unique_links"] else ""
        print(f"  {p} | unique={n:,} | LINK col={col} | enc={enc}{mark}")

    if len(exact) >= 1:
        if len(exact) > 1:
            print(f"[INFO] 10,708 universe 복사본 {len(exact)}개 발견. 첫 번째 파일 사용.")
        return exact[0][0]

    print("[STOP] 발견된 후보 중 unique LINK 10,708인 AI universe가 없습니다.")
    raise SystemExit(11)


def get_link_mapping_seq(route):
    lm = route.get("link_mapping_v2") or {}
    seq = lm.get("link_sequence")
    return seq if isinstance(seq, list) else []


def get_seongnam_seq(route):
    sc = route.get("seongnam_classification") or {}
    seq = sc.get("link_sequence")
    return seq if isinstance(seq, list) else []


def is_seongnam_related(link):
    try:
        overlap = float(link.get("seongnam_overlap_m") or 0)
    except (TypeError, ValueError):
        overlap = 0.0

    if overlap > 0:
        return True

    if link.get("inside_seongnam") is True:
        return True

    pos = str(link.get("seongnam_position") or "").strip().lower()
    return pos in {"inside", "boundary", "boundary_crossing", "intersecting"}


# =============================================================================
# 1. 최종 bridge rule 읽기
# =============================================================================
for required in (RULE_JSON, BRIDGE_CSV):
    if not required.exists():
        raise FileNotFoundError(f"최종 bridge 산출물이 없습니다: {required}")

with RULE_JSON.open("r", encoding="utf-8") as f:
    rule = json.load(f)

old_seq = [norm_link_id(x) for x in rule["raw_sequence_match"]]
new_seq = [norm_link_id(x) for x in rule["canonical_sequence_replace"]]

if rule.get("status") != "verified":
    raise RuntimeError("sujeongro_normalization_rule.json status가 verified가 아닙니다.")

if set(old_seq) != EXPECTED_OLD_UNMATCHED:
    raise RuntimeError(f"old sequence가 예상과 다릅니다: {old_seq}")

print("=" * 100)
print("[1] FINAL BRIDGE RULE")
print("=" * 100)
print("old version       :", rule["old_nodelink_version"])
print("canonical version :", rule["canonical_nodelink_version"])
print("relation type     :", rule["relation_type"])
print("old component     :", " -> ".join(old_seq))
print("new component     :", " -> ".join(new_seq))
print("method            :", rule["normalization_method"])
print()

# =============================================================================
# 2. AI 10,708 universe 로드
# =============================================================================
ai_path = find_ai_universe()
ai_rows, ai_enc = read_csv_dicts(ai_path)

if not ai_rows:
    raise RuntimeError("AI universe CSV가 비어 있습니다.")

ai_cols = set(ai_rows[0].keys())
ai_link_col = next(
    (c for c in ("LINK_ID", "link_id", "Link_ID") if c in ai_cols),
    None
)

if not ai_link_col:
    raise RuntimeError(f"AI universe에서 LINK_ID 컬럼을 찾지 못했습니다: {sorted(ai_cols)}")

ai_links = {
    norm_link_id(r.get(ai_link_col))
    for r in ai_rows
    if norm_link_id(r.get(ai_link_col))
}

print("=" * 100)
print("[2] AI CITYWIDE UNIVERSE")
print("=" * 100)
print("file              :", ai_path)
print("encoding          :", ai_enc)
print("unique LINK_ID    :", f"{len(ai_links):,}")
print()

if len(ai_links) != EXPECTED["ai_universe_unique_links"]:
    raise RuntimeError(
        f"AI universe unique LINK가 {len(ai_links):,}개입니다. "
        f"기대값 {EXPECTED['ai_universe_unique_links']:,}와 달라 중단합니다."
    )

missing_new_in_ai = [x for x in new_seq if x not in ai_links]
if missing_new_in_ai:
    raise RuntimeError(
        f"canonical 신규 수정로 LINK가 AI universe에 없습니다: {missing_new_in_ai}"
    )

# =============================================================================
# 3. 600 OD 읽기 + raw baseline 재현
# =============================================================================
json_files = sorted(OD_DIR.rglob("*.json"))

od_records = {}
ignored_json = []
duplicate_od_ids = []

for path in json_files:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        ignored_json.append({"file": str(path), "reason": f"parse_error: {e!r}"})
        continue

    od_id = str(data.get("od_id") or "").strip()

    if not re.fullmatch(r"OD_\d+", od_id):
        ignored_json.append({"file": str(path), "reason": "not_an_OD_json"})
        continue

    if od_id in od_records:
        duplicate_od_ids.append(
            (od_id, str(od_records[od_id][0]), str(path))
        )
        continue

    od_records[od_id] = (path, data)

if duplicate_od_ids:
    print("[STOP] 중복 od_id 발견:")
    for x in duplicate_od_ids[:20]:
        print(" ", x)
    raise SystemExit(12)

pipeline_success_od = 0
usable_routes = 0
all_route_link_rows = 0
seongnam_route_link_rows = 0

raw_seongnam_links = set()
raw_link_occurrence = Counter()

canonical_rows = []
canonical_links = set()
canonical_link_occurrence = Counter()

target_routes = 0
target_triplet_replacements = 0
target_noncontiguous = []

for od_id in sorted(od_records):
    path, data = od_records[od_id]

    assessment = data.get("pipeline_assessment") or {}
    if assessment.get("success") is True:
        pipeline_success_od += 1

    routes = ((data.get("pipeline_result") or {}).get("routes") or [])
    if not isinstance(routes, list):
        continue

    for route in routes:
        if not isinstance(route, dict):
            continue

        lm = route.get("link_mapping_v2") or {}
        quality = str(lm.get("quality") or "").strip().lower()
        lm_seq = get_link_mapping_seq(route)

        if quality not in ALLOWED_QUALITY or not lm_seq:
            continue

        usable_routes += 1
        all_route_link_rows += len(lm_seq)

        candidate_id = str(route.get("candidate_id") or "")
        route_id = f"{od_id}_{candidate_id}"

        sc_seq_all = get_seongnam_seq(route)
        sc_seq = [
            x for x in sc_seq_all
            if isinstance(x, dict) and is_seongnam_related(x)
        ]

        raw_ids = [norm_link_id(x.get("LINK_ID")) for x in sc_seq]
        raw_ids = [x for x in raw_ids if x]

        seongnam_route_link_rows += len(raw_ids)
        raw_seongnam_links.update(raw_ids)
        raw_link_occurrence.update(raw_ids)

        hit_old = any(x in EXPECTED_OLD_UNMATCHED for x in raw_ids)

        starts = [
            i
            for i in range(len(raw_ids) - len(old_seq) + 1)
            if raw_ids[i:i + len(old_seq)] == old_seq
        ]

        if hit_old:
            target_routes += 1

            old_hit_count = sum(
                1 for x in raw_ids if x in EXPECTED_OLD_UNMATCHED
            )

            if len(starts) != 1 or old_hit_count != len(old_seq):
                target_noncontiguous.append({
                    "od_id": od_id,
                    "candidate_id": candidate_id,
                    "raw_target_ids": [
                        x for x in raw_ids if x in EXPECTED_OLD_UNMATCHED
                    ],
                    "starts": starts,
                })
                continue

        i = 0
        canonical_order = 0

        while i < len(raw_ids):
            if (
                i + len(old_seq) <= len(raw_ids)
                and raw_ids[i:i + len(old_seq)] == old_seq
            ):
                target_triplet_replacements += 1
                raw_component = "|".join(old_seq)

                for new_id in new_seq:
                    canonical_links.add(new_id)
                    canonical_link_occurrence[new_id] += 1

                    canonical_rows.append({
                        "od_id": od_id,
                        "candidate_id": candidate_id,
                        "route_id": route_id,
                        "canonical_order": canonical_order,
                        "route_link_id_raw": raw_component,
                        "raw_source_link_ids": raw_component,
                        "route_nodelink_version": rule["old_nodelink_version"],
                        "canonical_link_id": new_id,
                        "canonical_nodelink_version": rule[
                            "canonical_nodelink_version"
                        ],
                        "normalization_method": rule["normalization_method"],
                        "normalization_status": "verified_local_bridge",
                        "bridge_relation_group_id": rule["rule_id"],
                    })

                    canonical_order += 1

                i += len(old_seq)
                continue

            raw_id = raw_ids[i]

            canonical_links.add(raw_id)
            canonical_link_occurrence[raw_id] += 1

            canonical_rows.append({
                "od_id": od_id,
                "candidate_id": candidate_id,
                "route_id": route_id,
                "canonical_order": canonical_order,
                "route_link_id_raw": raw_id,
                "raw_source_link_ids": raw_id,
                "route_nodelink_version": rule["old_nodelink_version"],
                "canonical_link_id": raw_id,
                "canonical_nodelink_version": rule["canonical_nodelink_version"],
                "normalization_method": "identity_same_link_id",
                "normalization_status": "already_canonical_link_id",
                "bridge_relation_group_id": "",
            })

            canonical_order += 1
            i += 1

if target_noncontiguous:
    print("[STOP] old 수정로 target이 component 규칙과 다르게 나타난 Route가 있습니다.")
    print(json.dumps(target_noncontiguous[:20], ensure_ascii=False, indent=2))
    raise SystemExit(13)

# =============================================================================
# 4. raw baseline sanity check
# =============================================================================
raw_unmatched = sorted(raw_seongnam_links - ai_links)
canon_unmatched = sorted(canonical_links - ai_links)

raw_summary = {
    "od_count": len(od_records),
    "pipeline_success_od": pipeline_success_od,
    "usable_routes": usable_routes,
    "all_route_link_rows": all_route_link_rows,
    "seongnam_route_link_rows": seongnam_route_link_rows,
    "raw_seongnam_unique_links": len(raw_seongnam_links),
    "raw_unmatched_unique_links": len(raw_unmatched),
}

print("=" * 100)
print("[3] RAW 2026-08-12 BASELINE REPRODUCTION")
print("=" * 100)

for k, v in raw_summary.items():
    expected = EXPECTED.get(k)
    suffix = f" / expected={expected:,}" if isinstance(expected, int) else ""
    print(f"{k:<30}: {v:,}{suffix}")

print("raw unmatched LINK_ID         :", raw_unmatched)
print()

sanity_errors = []

for k in (
    "od_count",
    "pipeline_success_od",
    "usable_routes",
    "all_route_link_rows",
    "seongnam_route_link_rows",
    "raw_seongnam_unique_links",
    "raw_unmatched_unique_links",
):
    if raw_summary[k] != EXPECTED[k]:
        sanity_errors.append(
            f"{k}: actual={raw_summary[k]} expected={EXPECTED[k]}"
        )

if set(raw_unmatched) != EXPECTED_OLD_UNMATCHED:
    sanity_errors.append(
        f"raw unmatched set: actual={raw_unmatched}, "
        f"expected={sorted(EXPECTED_OLD_UNMATCHED)}"
    )

if sanity_errors:
    print("[STOP] 이전 전수검증 baseline과 이번 입력 데이터가 일치하지 않습니다.")
    for e in sanity_errors:
        print("  -", e)
    print("잘못된 데이터에 normalization을 적용하지 않기 위해 중단합니다.")
    raise SystemExit(14)

# =============================================================================
# 5. canonical AI universe coverage
# =============================================================================
print("=" * 100)
print("[4] CANONICAL 2026-09-14 COVERAGE")
print("=" * 100)
print(f"target routes containing old component : {target_routes:,}")
print(f"component replacements                 : {target_triplet_replacements:,}")
print(f"canonical Seongnam unique LINK_ID      : {len(canonical_links):,}")
print(f"AI universe matched unique LINK_ID     : {len(canonical_links & ai_links):,}")
print(f"AI universe unmatched unique LINK_ID   : {len(canon_unmatched):,}")
print("canonical unmatched LINK_ID            :", canon_unmatched)
print()

if target_triplet_replacements != target_routes:
    raise RuntimeError(
        f"target route={target_routes}, "
        f"replacement={target_triplet_replacements} 불일치"
    )

if canon_unmatched:
    print("[FAIL] canonical 적용 후에도 AI universe 미매칭 LINK가 남았습니다.")
else:
    print(
        "[PASS] canonical 적용 후 성남 관련 unique LINK의 "
        "AI 10,708 universe 미매칭 = 0"
    )

# =============================================================================
# 6. 산출물 저장
# =============================================================================
OUT_DIR.mkdir(parents=True, exist_ok=True)

with OUT_UNMATCHED_RAW.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=["LINK_ID", "occurrence_count", "status"]
    )
    w.writeheader()

    for lid in raw_unmatched:
        w.writerow({
            "LINK_ID": lid,
            "occurrence_count": raw_link_occurrence[lid],
            "status": "raw_2026-08_unmatched",
        })

with OUT_UNMATCHED_CANON.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:
    w = csv.DictWriter(
        f,
        fieldnames=[
            "canonical_link_id",
            "occurrence_count",
            "status"
        ]
    )
    w.writeheader()

    for lid in canon_unmatched:
        w.writerow({
            "canonical_link_id": lid,
            "occurrence_count": canonical_link_occurrence[lid],
            "status": "canonical_2026-09_unmatched",
        })

canonical_fields = [
    "od_id",
    "candidate_id",
    "route_id",
    "canonical_order",
    "route_link_id_raw",
    "raw_source_link_ids",
    "route_nodelink_version",
    "canonical_link_id",
    "canonical_nodelink_version",
    "normalization_method",
    "normalization_status",
    "bridge_relation_group_id",
]

with OUT_CANONICAL_LINKS.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:
    w = csv.DictWriter(f, fieldnames=canonical_fields)
    w.writeheader()
    w.writerows(canonical_rows)

final_summary = {
    "status": "PASS" if not canon_unmatched else "FAIL",
    "canonical_standard": rule["canonical_nodelink_version"],
    "ai_universe_file": str(ai_path),
    "ai_universe_unique_links": len(ai_links),
    "input_json_files_found": len(json_files),
    "ignored_non_od_or_parse_error_json": ignored_json,
    "raw_baseline": raw_summary,
    "raw_unmatched_link_ids": raw_unmatched,
    "bridge_rule": {
        "relation_type": rule["relation_type"],
        "old_component": old_seq,
        "canonical_component": new_seq,
        "normalization_method": rule["normalization_method"],
        "target_routes": target_routes,
        "component_replacements": target_triplet_replacements,
    },
    "canonical_result": {
        "seongnam_unique_links": len(canonical_links),
        "matched_unique_links": len(canonical_links & ai_links),
        "unmatched_unique_links": len(canon_unmatched),
        "unmatched_link_ids": canon_unmatched,
    },
    "raw_route_preserved": True,
    "independent_1_to_1_rename_used": False,
}

with OUT_SUMMARY.open("w", encoding="utf-8") as f:
    json.dump(
        final_summary,
        f,
        ensure_ascii=False,
        indent=2
    )

print()
print("=" * 100)
print("[5] OUTPUT")
print("=" * 100)
print("summary          :", OUT_SUMMARY)
print("canonical routes :", OUT_CANONICAL_LINKS)
print("raw unmatched    :", OUT_UNMATCHED_RAW)
print("canon unmatched  :", OUT_UNMATCHED_CANON)
print()

if canon_unmatched:
    raise SystemExit(20)

print("=" * 100)
print("[FINAL PASS]")
print("2026-08-12 raw Route는 보존됨.")
print("수정로 old N:M component만 2026-09-14 canonical sequence로 normalization함.")
print("600 OD 성남 관련 canonical unique LINK -> AI 10,708 universe 미매칭: 0")
print("=" * 100)
