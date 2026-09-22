from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# ============================================================
# FLOW:MATE Route(2026-08-12) vs AI citywide(2026-09-14)
# 600 OD 전체 LINK_ID 호환성 전수검증
#
# 핵심 판정 기준
#   1) Route에서 "성남과 실제로 겹치는 LINK"만 추출
#   2) AI팀 최종 성남 universe 10,708 LINK와 LINK_ID exact join
#   3) segment_link_bridge 포함 여부는 호환성 판정에 사용하지 않음
#   4) 동일 LINK_ID의 F_NODE/T_NODE/ROAD_NAME/LENGTH 차이는 진단용으로 별도 기록
#
# 원본 Route 폴더는 읽기만 하며 수정하지 않습니다.
# ============================================================

DEFAULT_ROUTE_DIR = Path(
    r"C:\Users\문성빈\OneDrive\바탕 화면\flow\FLOWMATE\data\routes\od_pipeline"
)
DEFAULT_PHASE2_ROOT = Path(
    r"C:\Users\문성빈\OneDrive\바탕 화면\FLOWMATE_PHASE2"
)
DEFAULT_OUTPUT_DIR = DEFAULT_PHASE2_ROOT / "data" / "ai_nodelink_compare_all600"

# 이 날짜는 각 pipeline JSON 내부에 저장된 값이 아니라,
# Route팀이 사용한 프로젝트 기준 NODELINK 버전입니다.
ROUTE_NODELINK_VERSION_DECLARED = "[2026-08-12] NODELINKDATA / MOCT_LINK"
AI_NODELINK_VERSION_DECLARED = "2026-09-14 MOCT_LINK"

USABLE_MAPPING_QUALITIES = {"good", "recovered", "review"}
LENGTH_MATCH_TOLERANCE_M = 0.05


def as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def normalize_road_name(value: Any) -> str:
    # 진단용 비교. 공백 차이만 무시하며 이름을 임의 변환하지 않음.
    return "".join(as_str(value).split())


def bool_text(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def find_ai_citywide(phase2_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        if explicit.exists():
            return explicit
        raise FileNotFoundError(f"지정한 AI citywide 파일이 없습니다: {explicit}")

    # 1) 이전 검증에서 풀어둔 폴더 우선
    preferred_root = phase2_root / "_ai_nodelink_compare_input"
    if preferred_root.exists():
        found = sorted(preferred_root.rglob("seongnam_citywide_links_v1.csv"))
        if found:
            return found[0]

    # 2) Phase2 내부에 이미 CSV가 있으면 사용
    found = [
        p for p in phase2_root.rglob("seongnam_citywide_links_v1.csv")
        if "ai_nodelink_compare_all600" not in str(p)
    ]
    if found:
        return sorted(found)[0]

    # 3) 확인용 ZIP 안에서 citywide CSV만 추출
    zip_candidates = sorted(phase2_root.glob("*.zip"))
    for zip_path in zip_candidates:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = [
                    n for n in zf.namelist()
                    if n.replace("\\", "/").endswith("/seongnam_citywide_links_v1.csv")
                    or n == "seongnam_citywide_links_v1.csv"
                ]
                if not members:
                    continue

                extract_root = phase2_root / "_ai_nodelink_compare_input"
                extract_root.mkdir(parents=True, exist_ok=True)
                member = members[0]
                target = extract_root / "seongnam_citywide_links_v1.csv"
                with zf.open(member) as src, target.open("wb") as dst:
                    dst.write(src.read())
                return target
        except zipfile.BadZipFile:
            continue

    raise FileNotFoundError(
        "seongnam_citywide_links_v1.csv를 찾지 못했습니다.\n"
        "AI팀 확인용 ZIP 또는 CSV를 FLOWMATE_PHASE2 폴더에 두거나 "
        "--ai-citywide 경로를 지정하세요."
    )


def load_ai_universe(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    universe: dict[str, dict[str, str]] = {}
    duplicate_ids: list[str] = []
    blank_ids = 0
    row_count = 0

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"LINK_ID", "F_NODE", "T_NODE", "ROAD_NAME", "LENGTH"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"AI citywide CSV 필수 컬럼 누락: {sorted(missing)}\n"
                f"현재 컬럼: {reader.fieldnames}"
            )

        for row in reader:
            row_count += 1
            link_id = as_str(row.get("LINK_ID"))
            if not link_id:
                blank_ids += 1
                continue
            if link_id in universe:
                duplicate_ids.append(link_id)
                continue
            universe[link_id] = row

    meta = {
        "row_count": row_count,
        "unique_link_count": len(universe),
        "blank_link_id_rows": blank_ids,
        "duplicate_link_id_count": len(duplicate_ids),
        "duplicate_link_ids_sample": duplicate_ids[:20],
    }
    return universe, meta


def is_usable_route(route: dict[str, Any]) -> tuple[bool, str, str]:
    mapping = route.get("link_mapping_v2") or {}
    status = as_str(mapping.get("status")).lower()
    quality = as_str(mapping.get("quality")).lower()

    usable = (
        status == "mapped"
        and quality in USABLE_MAPPING_QUALITIES
        and bool(mapping.get("link_sequence"))
    )
    return usable, status, quality


def is_seongnam_relevant(link: dict[str, Any]) -> bool:
    # 내부 LINK + 경계통과 LINK 모두 포함.
    # 가장 강한 기준은 실제 성남 overlap 길이가 0보다 큰지 여부.
    overlap = as_float(link.get("seongnam_overlap_m"))
    if overlap is not None and overlap > 0:
        return True

    if link.get("inside_seongnam") is True:
        return True

    pos = as_str(link.get("seongnam_position")).lower()
    if pos in {
        "inside",
        "boundary",
        "boundary_crossing",
        "crossing",
        "intersecting",
    }:
        return True

    return False


def compare_attributes(
    route_record: dict[str, str],
    ai_row: dict[str, str] | None,
) -> dict[str, Any]:
    if ai_row is None:
        return {
            "ai_exists": False,
            "f_node_match": None,
            "t_node_match": None,
            "road_name_match": None,
            "length_diff_m": None,
            "length_match_0_05m": None,
            "all_core_attributes_match": None,
        }

    route_f = as_str(route_record.get("F_NODE"))
    route_t = as_str(route_record.get("T_NODE"))
    route_road = normalize_road_name(route_record.get("ROAD_NAME"))
    route_len = as_float(route_record.get("LENGTH"))

    ai_f = as_str(ai_row.get("F_NODE"))
    ai_t = as_str(ai_row.get("T_NODE"))
    ai_road = normalize_road_name(ai_row.get("ROAD_NAME"))
    ai_len = as_float(ai_row.get("LENGTH"))

    f_match = route_f == ai_f if route_f and ai_f else None
    t_match = route_t == ai_t if route_t and ai_t else None
    road_match = route_road == ai_road if route_road and ai_road else None

    length_diff = None
    length_match = None
    if route_len is not None and ai_len is not None:
        length_diff = abs(route_len - ai_len)
        length_match = length_diff <= LENGTH_MATCH_TOLERANCE_M

    checks = [f_match, t_match, road_match, length_match]
    available_checks = [x for x in checks if x is not None]
    all_match = all(available_checks) if available_checks else None

    return {
        "ai_exists": True,
        "f_node_match": f_match,
        "t_node_match": t_match,
        "road_name_match": road_match,
        "length_diff_m": length_diff,
        "length_match_0_05m": length_match,
        "all_core_attributes_match": all_match,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FLOW:MATE 600 OD Route LINK vs AI 2026-09-14 성남 citywide LINK 전수검증"
    )
    parser.add_argument(
        "--route-dir",
        type=Path,
        default=DEFAULT_ROUTE_DIR,
        help="600개 OD_*.json이 있는 od_pipeline 폴더",
    )
    parser.add_argument(
        "--phase2-root",
        type=Path,
        default=DEFAULT_PHASE2_ROOT,
        help="FLOWMATE_PHASE2 루트",
    )
    parser.add_argument(
        "--ai-citywide",
        type=Path,
        default=None,
        help="seongnam_citywide_links_v1.csv 직접 지정(선택)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="검증 결과 저장 폴더",
    )
    args = parser.parse_args()

    route_dir: Path = args.route_dir
    phase2_root: Path = args.phase2_root
    output_dir: Path = args.output_dir

    print("=" * 72)
    print("FLOW:MATE 600 OD Route LINK vs AI 2026-09-14 NODELINK 전수검증")
    print("=" * 72)

    if not route_dir.exists():
        raise FileNotFoundError(f"Route 원본 폴더가 없습니다: {route_dir}")

    route_files = sorted(route_dir.glob("OD_*.json"))
    print(f"Route source  : {route_dir}")
    print(f"OD JSON files: {len(route_files)}")
    if not route_files:
        raise RuntimeError("OD_*.json 파일을 찾지 못했습니다.")

    ai_path = find_ai_citywide(phase2_root, args.ai_citywide)
    print(f"AI citywide  : {ai_path}")

    ai_universe, ai_meta = load_ai_universe(ai_path)
    print(
        "AI universe  : "
        f"{ai_meta['unique_link_count']:,} unique LINK_ID "
        f"(rows={ai_meta['row_count']:,}, duplicates={ai_meta['duplicate_link_id_count']})"
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Output streams
    # ------------------------------------------------------------------
    route_links_path = output_dir / "route_links.csv"
    seongnam_links_path = output_dir / "route_links_seongnam_only.csv"

    route_fields = [
        "od_id",
        "route_id",
        "candidate_id",
        "mapping_status",
        "mapping_quality",
        "link_order",
        "LINK_ID",
        "link_length_m",
        "F_NODE",
        "T_NODE",
        "road_name",
        "MAX_SPD",
        "inside_seongnam",
        "seongnam_position",
        "seongnam_overlap_m",
        "seongnam_overlap_ratio",
        "ai_citywide_exists",
    ]

    all_writer_file = route_links_path.open(
        "w", encoding="utf-8-sig", newline=""
    )
    sn_writer_file = seongnam_links_path.open(
        "w", encoding="utf-8-sig", newline=""
    )
    all_writer = csv.DictWriter(all_writer_file, fieldnames=route_fields)
    sn_writer = csv.DictWriter(sn_writer_file, fieldnames=route_fields)
    all_writer.writeheader()
    sn_writer.writeheader()

    # ------------------------------------------------------------------
    # Counters / unique registries
    # ------------------------------------------------------------------
    parsed_od_count = 0
    parse_error_files: list[dict[str, str]] = []
    successful_pipeline_od_count = 0
    usable_route_count = 0
    excluded_route_count = 0
    usable_quality_counts: Counter[str] = Counter()
    excluded_quality_counts: Counter[str] = Counter()

    all_route_link_rows = 0
    seongnam_route_link_rows = 0
    all_unique_links: set[str] = set()
    seongnam_unique_links: set[str] = set()

    # LINK_ID -> first Route record for unique-level comparison
    first_seongnam_record: dict[str, dict[str, str]] = {}
    # Route source internal consistency check
    route_attr_variants: defaultdict[str, set[tuple[str, str, str, str]]] = defaultdict(set)

    per_od_summary: list[dict[str, Any]] = []

    try:
        for idx, json_path in enumerate(route_files, start=1):
            if idx == 1 or idx % 50 == 0 or idx == len(route_files):
                print(f"처리 중: {idx}/{len(route_files)}")

            try:
                with json_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                parse_error_files.append(
                    {"file": str(json_path), "error": f"{type(e).__name__}: {e}"}
                )
                continue

            parsed_od_count += 1
            od_id = as_str(data.get("od_id")) or json_path.stem

            assessment = data.get("pipeline_assessment") or {}
            if assessment.get("success") is True:
                successful_pipeline_od_count += 1

            routes = (data.get("pipeline_result") or {}).get("routes") or []

            od_usable_routes = 0
            od_seongnam_links = 0

            for route in routes:
                candidate_id = as_str(route.get("candidate_id"))
                route_id = f"{od_id}_{candidate_id}" if candidate_id else od_id

                usable, mapping_status, mapping_quality = is_usable_route(route)
                if not usable:
                    excluded_route_count += 1
                    excluded_quality_counts[mapping_quality or mapping_status or "unknown"] += 1
                    continue

                usable_route_count += 1
                od_usable_routes += 1
                usable_quality_counts[mapping_quality] += 1

                classification = route.get("seongnam_classification") or {}
                seq = classification.get("link_sequence") or []

                # fallback: 분류 sequence가 없으면 map matching sequence 사용.
                # 이 경우 성남 내부 여부는 알 수 없으므로 전체 handoff만 기록됨.
                if not seq:
                    seq = (route.get("link_mapping_v2") or {}).get("link_sequence") or []

                for pos, link in enumerate(seq):
                    link_id = as_str(link.get("LINK_ID"))
                    if not link_id:
                        continue

                    sequence = link.get("sequence")
                    if sequence is None:
                        sequence = pos

                    length = as_float(link.get("LENGTH"))
                    f_node = as_str(link.get("F_NODE"))
                    t_node = as_str(link.get("T_NODE"))
                    road_name = as_str(link.get("ROAD_NAME"))
                    max_spd = link.get("MAX_SPD")

                    inside_value = link.get("inside_seongnam")
                    seongnam_position = as_str(link.get("seongnam_position"))
                    overlap_m = as_float(link.get("seongnam_overlap_m"))
                    overlap_ratio = as_float(link.get("seongnam_overlap_ratio"))

                    ai_exists = link_id in ai_universe

                    out_row = {
                        "od_id": od_id,
                        "route_id": route_id,
                        "candidate_id": candidate_id,
                        "mapping_status": mapping_status,
                        "mapping_quality": mapping_quality,
                        "link_order": sequence,
                        "LINK_ID": link_id,
                        "link_length_m": "" if length is None else length,
                        "F_NODE": f_node,
                        "T_NODE": t_node,
                        "road_name": road_name,
                        "MAX_SPD": "" if max_spd is None else max_spd,
                        "inside_seongnam": bool_text(
                            inside_value if isinstance(inside_value, bool) else None
                        ),
                        "seongnam_position": seongnam_position,
                        "seongnam_overlap_m": "" if overlap_m is None else overlap_m,
                        "seongnam_overlap_ratio": "" if overlap_ratio is None else overlap_ratio,
                        "ai_citywide_exists": bool_text(ai_exists),
                    }

                    all_writer.writerow(out_row)
                    all_route_link_rows += 1
                    all_unique_links.add(link_id)

                    route_attr_variants[link_id].add(
                        (
                            f_node,
                            t_node,
                            normalize_road_name(road_name),
                            "" if length is None else f"{length:.6f}",
                        )
                    )

                    if is_seongnam_relevant(link):
                        sn_writer.writerow(out_row)
                        seongnam_route_link_rows += 1
                        od_seongnam_links += 1
                        seongnam_unique_links.add(link_id)

                        if link_id not in first_seongnam_record:
                            first_seongnam_record[link_id] = {
                                "LINK_ID": link_id,
                                "F_NODE": f_node,
                                "T_NODE": t_node,
                                "ROAD_NAME": road_name,
                                "LENGTH": "" if length is None else str(length),
                                "first_od_id": od_id,
                                "first_route_id": route_id,
                                "first_link_order": str(sequence),
                            }

            per_od_summary.append(
                {
                    "od_id": od_id,
                    "pipeline_success": bool_text(assessment.get("success") is True),
                    "usable_route_count": od_usable_routes,
                    "seongnam_route_link_rows": od_seongnam_links,
                }
            )
    finally:
        all_writer_file.close()
        sn_writer_file.close()

    # ------------------------------------------------------------------
    # Unique Seongnam LINK compatibility
    # ------------------------------------------------------------------
    unique_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    attr_mismatch_rows: list[dict[str, Any]] = []
    length_diffs: list[float] = []

    f_node_mismatch = 0
    t_node_mismatch = 0
    road_name_mismatch = 0
    length_mismatch = 0
    core_attr_mismatch_unique = 0
    exact_ai_matches = 0

    for link_id in sorted(seongnam_unique_links):
        route_rec = first_seongnam_record[link_id]
        ai = ai_universe.get(link_id)
        cmp = compare_attributes(route_rec, ai)

        if ai is not None:
            exact_ai_matches += 1

        if cmp["f_node_match"] is False:
            f_node_mismatch += 1
        if cmp["t_node_match"] is False:
            t_node_mismatch += 1
        if cmp["road_name_match"] is False:
            road_name_mismatch += 1
        if cmp["length_match_0_05m"] is False:
            length_mismatch += 1
        if cmp["all_core_attributes_match"] is False:
            core_attr_mismatch_unique += 1
        if cmp["length_diff_m"] is not None:
            length_diffs.append(cmp["length_diff_m"])

        row = {
            "LINK_ID": link_id,
            "ai_citywide_exists": bool_text(cmp["ai_exists"]),
            "route_F_NODE": route_rec.get("F_NODE", ""),
            "ai_F_NODE": as_str(ai.get("F_NODE")) if ai else "",
            "F_NODE_match": bool_text(cmp["f_node_match"]),
            "route_T_NODE": route_rec.get("T_NODE", ""),
            "ai_T_NODE": as_str(ai.get("T_NODE")) if ai else "",
            "T_NODE_match": bool_text(cmp["t_node_match"]),
            "route_road_name": route_rec.get("ROAD_NAME", ""),
            "ai_road_name": as_str(ai.get("ROAD_NAME")) if ai else "",
            "road_name_match": bool_text(cmp["road_name_match"]),
            "route_length_m": route_rec.get("LENGTH", ""),
            "ai_length_m": as_str(ai.get("LENGTH")) if ai else "",
            "length_abs_diff_m": (
                "" if cmp["length_diff_m"] is None else cmp["length_diff_m"]
            ),
            "length_match_within_0_05m": bool_text(cmp["length_match_0_05m"]),
            "all_core_attributes_match": bool_text(cmp["all_core_attributes_match"]),
            "ai_UPDATEDATE": as_str(ai.get("UPDATEDATE")) if ai else "",
            "ai_dominant_district": as_str(ai.get("dominant_district")) if ai else "",
            "ai_crosses_city_boundary": as_str(ai.get("crosses_city_boundary")) if ai else "",
            "first_od_id": route_rec.get("first_od_id", ""),
            "first_route_id": route_rec.get("first_route_id", ""),
            "first_link_order": route_rec.get("first_link_order", ""),
        }
        unique_rows.append(row)

        if not cmp["ai_exists"]:
            missing_rows.append(row)
        elif cmp["all_core_attributes_match"] is False:
            attr_mismatch_rows.append(row)

    unique_fields = [
        "LINK_ID",
        "ai_citywide_exists",
        "route_F_NODE",
        "ai_F_NODE",
        "F_NODE_match",
        "route_T_NODE",
        "ai_T_NODE",
        "T_NODE_match",
        "route_road_name",
        "ai_road_name",
        "road_name_match",
        "route_length_m",
        "ai_length_m",
        "length_abs_diff_m",
        "length_match_within_0_05m",
        "all_core_attributes_match",
        "ai_UPDATEDATE",
        "ai_dominant_district",
        "ai_crosses_city_boundary",
        "first_od_id",
        "first_route_id",
        "first_link_order",
    ]

    write_csv(
        output_dir / "seongnam_unique_link_compatibility.csv",
        unique_fields,
        unique_rows,
    )
    write_csv(
        output_dir / "seongnam_missing_in_ai.csv",
        unique_fields,
        missing_rows,
    )
    write_csv(
        output_dir / "seongnam_attribute_mismatches.csv",
        unique_fields,
        attr_mismatch_rows,
    )

    # ------------------------------------------------------------------
    # Route source 자체에서 동일 LINK_ID metadata가 서로 다른 경우
    # ------------------------------------------------------------------
    source_conflict_rows: list[dict[str, Any]] = []
    for link_id, variants in sorted(route_attr_variants.items()):
        if len(variants) > 1:
            for i, variant in enumerate(sorted(variants), start=1):
                f_node, t_node, road_name, length = variant
                source_conflict_rows.append(
                    {
                        "LINK_ID": link_id,
                        "variant_no": i,
                        "F_NODE": f_node,
                        "T_NODE": t_node,
                        "road_name_normalized": road_name,
                        "length_m": length,
                        "variant_count_for_LINK_ID": len(variants),
                    }
                )

    write_csv(
        output_dir / "route_source_attribute_conflicts.csv",
        [
            "LINK_ID",
            "variant_no",
            "F_NODE",
            "T_NODE",
            "road_name_normalized",
            "length_m",
            "variant_count_for_LINK_ID",
        ],
        source_conflict_rows,
    )

    write_csv(
        output_dir / "per_od_summary.csv",
        [
            "od_id",
            "pipeline_success",
            "usable_route_count",
            "seongnam_route_link_rows",
        ],
        per_od_summary,
    )

    write_csv(
        output_dir / "parse_errors.csv",
        ["file", "error"],
        parse_error_files,
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    seongnam_unique_count = len(seongnam_unique_links)
    match_rate = (
        exact_ai_matches / seongnam_unique_count * 100
        if seongnam_unique_count
        else 0.0
    )

    max_length_diff = max(length_diffs) if length_diffs else None
    p95_length_diff = None
    if length_diffs:
        sd = sorted(length_diffs)
        p95_index = max(0, math.ceil(len(sd) * 0.95) - 1)
        p95_length_diff = sd[p95_index]

    compatibility_verdict = (
        "LINK_ID_FULL_MATCH"
        if seongnam_unique_count > 0 and exact_ai_matches == seongnam_unique_count
        else "LINK_ID_MISMATCH_PRESENT"
    )

    summary = {
        "route_source": {
            "route_dir": str(route_dir),
            "od_json_file_count": len(route_files),
            "parsed_od_count": parsed_od_count,
            "parse_error_count": len(parse_error_files),
            "pipeline_success_od_count": successful_pipeline_od_count,
            "route_nodelink_version_declared": ROUTE_NODELINK_VERSION_DECLARED,
            "route_nodelink_version_embedded_in_pipeline_json": False,
            "note": (
                "pipeline JSON에는 source=MOCT_LINK는 있으나 snapshot 날짜 문자열은 "
                "직접 저장되어 있지 않아, 버전 날짜는 Route팀 프로젝트 기준 선언값을 사용함."
            ),
        },
        "ai_source": {
            "citywide_file": str(ai_path),
            "ai_nodelink_version_declared": AI_NODELINK_VERSION_DECLARED,
            **ai_meta,
        },
        "route_processing": {
            "usable_mapping_qualities": sorted(USABLE_MAPPING_QUALITIES),
            "usable_route_count": usable_route_count,
            "excluded_route_count": excluded_route_count,
            "usable_quality_counts": dict(usable_quality_counts),
            "excluded_quality_counts": dict(excluded_quality_counts),
            "all_route_link_rows": all_route_link_rows,
            "all_unique_link_ids": len(all_unique_links),
            "seongnam_route_link_rows": seongnam_route_link_rows,
            "seongnam_unique_link_ids": seongnam_unique_count,
        },
        "compatibility": {
            "primary_rule": (
                "성남과 실제로 겹치는 Route LINK_ID가 AI 10,708 citywide universe에 "
                "exact LINK_ID로 존재하는지"
            ),
            "segment_link_bridge_used_for_compatibility": False,
            "matched_seongnam_unique_link_ids": exact_ai_matches,
            "missing_seongnam_unique_link_ids": len(missing_rows),
            "link_id_match_rate_percent": round(match_rate, 6),
            "verdict": compatibility_verdict,
        },
        "attribute_diagnostics_for_matched_LINK_ID": {
            "F_NODE_mismatch_unique": f_node_mismatch,
            "T_NODE_mismatch_unique": t_node_mismatch,
            "ROAD_NAME_mismatch_unique": road_name_mismatch,
            "LENGTH_mismatch_over_0_05m_unique": length_mismatch,
            "any_core_attribute_mismatch_unique": core_attr_mismatch_unique,
            "max_length_abs_diff_m": max_length_diff,
            "p95_length_abs_diff_m": p95_length_diff,
            "length_tolerance_m": LENGTH_MATCH_TOLERANCE_M,
            "route_source_attribute_conflict_link_ids": sum(
                1 for variants in route_attr_variants.values() if len(variants) > 1
            ),
        },
        "outputs": {
            "route_links": str(route_links_path),
            "route_links_seongnam_only": str(seongnam_links_path),
            "seongnam_unique_link_compatibility": str(
                output_dir / "seongnam_unique_link_compatibility.csv"
            ),
            "seongnam_missing_in_ai": str(
                output_dir / "seongnam_missing_in_ai.csv"
            ),
            "seongnam_attribute_mismatches": str(
                output_dir / "seongnam_attribute_mismatches.csv"
            ),
            "route_source_attribute_conflicts": str(
                output_dir / "route_source_attribute_conflicts.csv"
            ),
            "per_od_summary": str(output_dir / "per_od_summary.csv"),
            "parse_errors": str(output_dir / "parse_errors.csv"),
        },
    }

    summary_path = output_dir / "compatibility_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 72)
    print("검증 완료")
    print("=" * 72)
    print(f"OD JSON 파일                : {len(route_files):,}")
    print(f"정상 파싱 OD                : {parsed_od_count:,}")
    print(f"파싱 오류                   : {len(parse_error_files):,}")
    print(f"Pipeline success OD          : {successful_pipeline_od_count:,}")
    print(f"사용 가능 Route             : {usable_route_count:,}")
    print(f"전체 Route-LINK 행          : {all_route_link_rows:,}")
    print(f"전체 unique LINK_ID         : {len(all_unique_links):,}")
    print(f"성남 관련 Route-LINK 행     : {seongnam_route_link_rows:,}")
    print(f"성남 관련 unique LINK_ID    : {seongnam_unique_count:,}")
    print(
        f"AI 10,708 universe 매칭     : "
        f"{exact_ai_matches:,}/{seongnam_unique_count:,}"
    )
    print(f"성남 LINK_ID 매칭률         : {match_rate:.4f}%")
    print(f"성남 미매칭 unique LINK     : {len(missing_rows):,}")
    print(f"F_NODE 불일치 unique        : {f_node_mismatch:,}")
    print(f"T_NODE 불일치 unique        : {t_node_mismatch:,}")
    print(f"ROAD_NAME 불일치 unique     : {road_name_mismatch:,}")
    print(f"LENGTH >0.05m 불일치 unique : {length_mismatch:,}")
    if max_length_diff is None:
        print("최대 LENGTH 차이(m)         : N/A")
    else:
        print(f"최대 LENGTH 차이(m)         : {max_length_diff:.6f}")
    print(f"최종 LINK_ID 판정           : {compatibility_verdict}")
    print()
    print(f"결과 폴더: {output_dir}")
    print()
    print("AI팀 전달 핵심 파일:")
    print("- route_links.csv")
    print("- route_links_seongnam_only.csv")
    print("- seongnam_unique_link_compatibility.csv")
    print("- seongnam_missing_in_ai.csv")
    print("- compatibility_summary.json")

    if len(route_files) != 600:
        print()
        print(
            f"[주의] OD_*.json이 600개가 아니라 {len(route_files)}개입니다. "
            "경로를 다시 확인하세요."
        )

    if ai_meta["unique_link_count"] != 10708:
        print()
        print(
            f"[주의] AI citywide unique LINK_ID가 10,708개가 아니라 "
            f"{ai_meta['unique_link_count']:,}개입니다."
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 72)
        print("실행 실패")
        print("=" * 72)
        print(f"{type(exc).__name__}: {exc}")
        raise
