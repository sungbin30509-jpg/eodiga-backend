from pathlib import Path
import csv
import json
import zipfile
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent

# When copied into FLOWMATE_PHASE2 root, ROOT becomes that project root.
ADAPTER_DIR = ROOT / "data" / "adapter_exports"
OUTPUT_DIR = ROOT / "data" / "ai_nodelink_compare"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CITY_FILENAME = "seongnam_citywide_links_v1.csv"
BRIDGE_FILENAME = "segment_link_bridge_v1.csv"


def read_csv_rows(path: Path):
    last_error = None
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError as e:
            last_error = e
    raise RuntimeError(f"CSV 인코딩을 읽지 못했습니다: {path}\n{last_error}")


def find_col(fieldnames, *candidates):
    if not fieldnames:
        return None
    lookup = {str(x).strip().upper(): x for x in fieldnames if x is not None}
    for c in candidates:
        hit = lookup.get(c.upper())
        if hit is not None:
            return hit
    return None


def find_ai_files():
    city = None
    bridge = None

    for p in ROOT.rglob(CITY_FILENAME):
        if OUTPUT_DIR not in p.parents:
            city = p
            break

    for p in ROOT.rglob(BRIDGE_FILENAME):
        if OUTPUT_DIR not in p.parents:
            bridge = p
            break

    if city is not None:
        return city, bridge

    # If CSVs are not extracted yet, inspect ZIPs under the project root.
    for zpath in ROOT.rglob("*.zip"):
        try:
            with zipfile.ZipFile(zpath, "r") as z:
                names = z.namelist()
                city_members = [n for n in names if Path(n).name == CITY_FILENAME]
                if not city_members:
                    continue

                extract_dir = ROOT / "_ai_nodelink_compare_input"
                extract_dir.mkdir(parents=True, exist_ok=True)
                z.extractall(extract_dir)

                city_hits = list(extract_dir.rglob(CITY_FILENAME))
                bridge_hits = list(extract_dir.rglob(BRIDGE_FILENAME))
                city = city_hits[0] if city_hits else None
                bridge = bridge_hits[0] if bridge_hits else None
                return city, bridge
        except zipfile.BadZipFile:
            continue

    return None, None


def safe_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_csv(path: Path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    print()
    print("============================================================")
    print("FLOW:MATE 전체 Route LINK vs AI NODELINK 호환성 검증")
    print("============================================================")
    print()

    if not ADAPTER_DIR.exists():
        raise FileNotFoundError(f"adapter_exports 폴더가 없습니다:\n{ADAPTER_DIR}")

    adapter_files = sorted(ADAPTER_DIR.glob("*route_adapter*.json"))
    if not adapter_files:
        raise FileNotFoundError(f"Route Adapter JSON이 없습니다:\n{ADAPTER_DIR}")

    city_path, bridge_path = find_ai_files()
    if city_path is None:
        raise FileNotFoundError(
            "AI팀 seongnam_citywide_links_v1.csv를 찾지 못했습니다.\n"
            "AI팀 ZIP 또는 CSV를 FLOWMATE_PHASE2 폴더 안에 넣고 다시 실행하세요."
        )

    print(f"Adapter files : {len(adapter_files)}")
    print(f"AI universe   : {city_path}")
    print(f"AI bridge     : {bridge_path if bridge_path else '없음(선택사항)'}")
    print()

    city_rows = read_csv_rows(city_path)
    if not city_rows:
        raise RuntimeError("AI universe CSV가 비어 있습니다.")

    city_fields = list(city_rows[0].keys())
    c_link = find_col(city_fields, "LINK_ID", "LINKID")
    c_fnode = find_col(city_fields, "F_NODE", "FNODE")
    c_tnode = find_col(city_fields, "T_NODE", "TNODE")
    c_road = find_col(city_fields, "ROAD_NAME", "ROADNAME", "ROAD_NM")
    c_len = find_col(city_fields, "LENGTH", "LINK_LENGTH", "LINK_LENGTH_M", "LENGTH_M")
    c_update = find_col(city_fields, "UPDATEDATE", "UPDATE_DATE", "UPD_DATE")

    if c_link is None:
        raise RuntimeError(f"AI universe에서 LINK_ID 컬럼을 찾지 못했습니다. 컬럼={city_fields}")

    ai_by_link = {}
    duplicate_ai_ids = Counter()
    for r in city_rows:
        lid = str(r.get(c_link, "")).strip()
        if not lid:
            continue
        if lid in ai_by_link:
            duplicate_ai_ids[lid] += 1
        else:
            ai_by_link[lid] = r

    bridge_ids = set()
    if bridge_path is not None:
        bridge_rows = read_csv_rows(bridge_path)
        if bridge_rows:
            b_fields = list(bridge_rows[0].keys())
            b_link = find_col(b_fields, "LINK_ID", "LINKID")
            if b_link:
                bridge_ids = {
                    str(r.get(b_link, "")).strip()
                    for r in bridge_rows
                    if str(r.get(b_link, "")).strip()
                }

    route_rows = []
    versions = Counter()
    statuses = Counter()
    file_errors = []
    usable_route_count = 0
    excluded_route_count = 0

    for idx, path in enumerate(adapter_files, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            file_errors.append({"file": str(path), "error": repr(e)})
            continue

        contract = data.get("contract", {}) if isinstance(data, dict) else {}
        version = contract.get("node_link_dataset")
        versions[str(version or "UNKNOWN")] += 1
        statuses[str(data.get("status", "UNKNOWN"))] += 1

        source_id = data.get("source_id") or path.stem
        route_metadata = data.get("route_metadata", {}) or {}
        routes = data.get("routes", []) or []
        excluded_routes = data.get("excluded_routes", []) or []

        usable_route_count += len(routes)
        excluded_route_count += len(excluded_routes)

        # route_id -> LINK_ID -> classification row
        class_map = {}
        for route_id, meta in route_metadata.items():
            cls = (
                (meta or {})
                .get("seongnam", {})
                .get("link_classification", [])
                or []
            )
            class_map[route_id] = {
                str(x.get("LINK_ID")): x
                for x in cls
                if x.get("LINK_ID") is not None
            }

        for route in routes:
            route_id = str(route.get("route_id", ""))
            candidate_id = (
                (route_metadata.get(route_id) or {}).get("candidate_id")
                or route_id.rsplit("_", 1)[-1]
            )
            per_route_cls = class_map.get(route_id, {})

            for link in route.get("links", []) or []:
                lid = str(link.get("LINK_ID", "")).strip()
                if not lid:
                    continue

                cls = per_route_cls.get(lid, {})
                inside = cls.get("inside_seongnam")
                position = cls.get("seongnam_position")
                ai = ai_by_link.get(lid)
                old_len = safe_float(link.get("link_length_m"))
                new_len = safe_float(ai.get(c_len)) if ai is not None and c_len else None
                diff = abs(old_len - new_len) if old_len is not None and new_len is not None else None

                route_rows.append({
                    "source_id": source_id,
                    "route_id": route_id,
                    "candidate_id": candidate_id,
                    "LINK_ID": lid,
                    "link_order": link.get("link_order"),
                    "route_link_length_m": old_len,
                    "inside_seongnam": inside,
                    "seongnam_position": position,
                    "found_in_ai_citywide_universe": ai is not None,
                    "ai_F_NODE": ai.get(c_fnode, "") if ai is not None and c_fnode else "",
                    "ai_T_NODE": ai.get(c_tnode, "") if ai is not None and c_tnode else "",
                    "ai_ROAD_NAME": ai.get(c_road, "") if ai is not None and c_road else "",
                    "ai_LENGTH_m": new_len if new_len is not None else "",
                    "length_abs_diff_m": diff if diff is not None else "",
                    "ai_UPDATEDATE": ai.get(c_update, "") if ai is not None and c_update else "",
                    "found_in_ai_segment_bridge": lid in bridge_ids,
                    "route_nodelink_dataset": version or "UNKNOWN",
                })

        if idx % 100 == 0 or idx == len(adapter_files):
            print(f"처리 중: {idx}/{len(adapter_files)} adapter files")

    # Full route-links file for teammate handoff.
    route_link_fields = [
        "source_id", "route_id", "candidate_id", "LINK_ID", "link_order",
        "route_link_length_m", "inside_seongnam", "seongnam_position",
        "route_nodelink_dataset",
    ]
    write_csv(
        OUTPUT_DIR / "route_links_all_routes.csv",
        [{k: r.get(k, "") for k in route_link_fields} for r in route_rows],
        route_link_fields,
    )

    comparison_fields = list(route_rows[0].keys()) if route_rows else []
    if route_rows:
        write_csv(OUTPUT_DIR / "all_route_link_compatibility.csv", route_rows, comparison_fields)

    # Unique inside LINK_ID summary.
    inside_rows = [r for r in route_rows if r.get("inside_seongnam") is True]
    inside_by_link = defaultdict(list)
    for r in inside_rows:
        inside_by_link[r["LINK_ID"]].append(r)

    unique_inside_rows = []
    for lid, occurrences in sorted(inside_by_link.items()):
        first = occurrences[0]
        ai = ai_by_link.get(lid)
        diffs = [safe_float(x.get("length_abs_diff_m")) for x in occurrences]
        diffs = [x for x in diffs if x is not None]
        unique_inside_rows.append({
            "LINK_ID": lid,
            "route_occurrence_count": len(occurrences),
            "found_in_ai_citywide_universe": ai is not None,
            "found_in_ai_segment_bridge": lid in bridge_ids,
            "ai_F_NODE": first.get("ai_F_NODE", ""),
            "ai_T_NODE": first.get("ai_T_NODE", ""),
            "ai_ROAD_NAME": first.get("ai_ROAD_NAME", ""),
            "route_length_example_m": first.get("route_link_length_m", ""),
            "ai_LENGTH_m": first.get("ai_LENGTH_m", ""),
            "max_length_abs_diff_m_across_occurrences": max(diffs) if diffs else "",
            "ai_UPDATEDATE": first.get("ai_UPDATEDATE", ""),
        })

    unique_fields = [
        "LINK_ID", "route_occurrence_count", "found_in_ai_citywide_universe",
        "found_in_ai_segment_bridge", "ai_F_NODE", "ai_T_NODE", "ai_ROAD_NAME",
        "route_length_example_m", "ai_LENGTH_m",
        "max_length_abs_diff_m_across_occurrences", "ai_UPDATEDATE",
    ]
    write_csv(OUTPUT_DIR / "inside_link_unique_comparison.csv", unique_inside_rows, unique_fields)

    missing_inside = [r for r in unique_inside_rows if not r["found_in_ai_citywide_universe"]]
    write_csv(OUTPUT_DIR / "inside_link_missing_in_ai.csv", missing_inside, unique_fields)

    # Also list route-side outside links for clarity; do NOT count them as incompatibility.
    outside_rows = [r for r in route_rows if r.get("inside_seongnam") is False]
    outside_unique = sorted({r["LINK_ID"] for r in outside_rows})
    with (OUTPUT_DIR / "outside_unique_link_ids.txt").open("w", encoding="utf-8") as f:
        for lid in outside_unique:
            f.write(lid + "\n")

    unique_route_links = {r["LINK_ID"] for r in route_rows}
    unique_inside_links = set(inside_by_link)
    matched_inside_links = {
        r["LINK_ID"]
        for r in unique_inside_rows
        if r["found_in_ai_citywide_universe"]
    }
    bridge_inside_links = unique_inside_links & bridge_ids

    all_inside_diffs = [safe_float(r.get("length_abs_diff_m")) for r in inside_rows]
    all_inside_diffs = [x for x in all_inside_diffs if x is not None]

    summary = {
        "route_adapter_file_count": len(adapter_files),
        "route_adapter_file_error_count": len(file_errors),
        "route_adapter_status_counts": dict(statuses),
        "route_nodelink_dataset_counts": dict(versions),
        "usable_route_count": usable_route_count,
        "excluded_route_count": excluded_route_count,
        "route_link_row_count": len(route_rows),
        "route_unique_link_count": len(unique_route_links),
        "inside_route_link_row_count": len(inside_rows),
        "inside_unique_link_count": len(unique_inside_links),
        "ai_citywide_row_count": len(city_rows),
        "ai_citywide_unique_link_count": len(ai_by_link),
        "ai_citywide_duplicate_link_id_count": len(duplicate_ai_ids),
        "inside_unique_link_matched_count": len(matched_inside_links),
        "inside_unique_link_missing_count": len(unique_inside_links - matched_inside_links),
        "inside_unique_link_match_percent": round(
            100.0 * len(matched_inside_links) / len(unique_inside_links), 4
        ) if unique_inside_links else None,
        "inside_unique_link_bridge_count": len(bridge_inside_links),
        "inside_unique_link_bridge_percent": round(
            100.0 * len(bridge_inside_links) / len(unique_inside_links), 4
        ) if unique_inside_links else None,
        "inside_length_abs_diff_max_m": max(all_inside_diffs) if all_inside_diffs else None,
        "inside_length_abs_diff_mean_m": (
            sum(all_inside_diffs) / len(all_inside_diffs)
            if all_inside_diffs else None
        ),
        "ai_universe_file": str(city_path),
        "ai_bridge_file": str(bridge_path) if bridge_path else None,
        "note": (
            "AI universe가 성남 10,708 LINK universe이므로 성남 외부 Route LINK는 "
            "미매칭이어도 버전 불일치로 계산하지 않음."
        ),
        "file_errors": file_errors,
    }

    (OUTPUT_DIR / "compatibility_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("============================================================")
    print("검증 완료")
    print("============================================================")
    print(f"Route Adapter 파일      : {len(adapter_files)}")
    print(f"사용 가능 Route         : {usable_route_count}")
    print(f"전체 Route-LINK 행      : {len(route_rows)}")
    print(f"전체 unique LINK_ID     : {len(unique_route_links)}")
    print(f"성남 내부 unique LINK   : {len(unique_inside_links)}")
    print(f"AI universe 내부 매칭   : {len(matched_inside_links)}/{len(unique_inside_links)}")
    print(f"성남 내부 매칭률        : {summary['inside_unique_link_match_percent']}%")
    print(f"성남 내부 미매칭 unique : {summary['inside_unique_link_missing_count']}")
    print(f"Bridge 포함 내부 unique : {len(bridge_inside_links)}/{len(unique_inside_links)}")
    print(f"Route NODELINK 버전들   : {dict(versions)}")
    print(f"최대 길이 차이(m)       : {summary['inside_length_abs_diff_max_m']}")
    print()
    print("결과 폴더:")
    print(OUTPUT_DIR)
    print()
    print("생성 파일:")
    print("- route_links_all_routes.csv")
    print("- all_route_link_compatibility.csv")
    print("- inside_link_unique_comparison.csv")
    print("- inside_link_missing_in_ai.csv")
    print("- outside_unique_link_ids.txt")
    print("- compatibility_summary.json")


if __name__ == "__main__":
    main()
