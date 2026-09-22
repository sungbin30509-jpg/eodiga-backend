from pathlib import Path
from collections import defaultdict
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Unsupported LINK Usage Analyzer
#
# 역할
# ------------------------------------------------------------
# 완료된 Unique OD Route 결과를 읽어서
#
# 성남 내부이지만 AI 미지원이어서
# TMAP fallback을 사용하는 LINK를 집계한다.
#
# 주요 지표
# ------------------------------------------------------------
# od_count
#   해당 LINK를 사용하는 Unique OD 수
#
# affected_user_weight
#   해당 LINK의 영향을 받는 Synthetic 사용자 수
#   ※ 같은 OD의 A/B/C 여러 후보에서 반복되어도
#      OD당 한 번만 사용자 수를 더한다.
#
# route_candidate_count
#   A/B/C 후보 중 해당 LINK가 등장한 횟수
#
# candidate_user_exposure
#   후보별 노출량
#   ※ A/B/C가 모두 같은 LINK를 쓰면 user_count가
#      후보별로 반복 합산될 수 있으므로
#      실제 사용자 수와는 구분해서 사용한다.
# ============================================================


ROOT = Path(__file__).resolve().parents[2]


OD_RESULT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "analysis"
)


OUTPUT_CSV = (
    OUTPUT_DIR
    / "unsupported_link_usage.csv"
)


SUMMARY_JSON = (
    OUTPUT_DIR
    / "unsupported_link_usage_summary.json"
)


# ============================================================
# 1. ID 정리
# ============================================================

def normalize_id(value):

    if value is None:
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


# ============================================================
# 2. JSON 안에서 특정 key의 값 찾기
# ============================================================

def find_values_by_key(
    obj,
    target_key,
):

    found = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            if key == target_key:
                found.append(value)

            found.extend(
                find_values_by_key(
                    value,
                    target_key,
                )
            )

    elif isinstance(obj, list):

        for item in obj:

            found.extend(
                find_values_by_key(
                    item,
                    target_key,
                )
            )

    return found


# ============================================================
# 3. Route 내부 unsupported LINK 찾기
# ============================================================

def extract_unsupported_link_ids(route):

    result = set()

    # --------------------------------------------------------
    # 가장 우선:
    # unsupported_link_ids가 있으면 그대로 사용
    # --------------------------------------------------------

    unsupported_lists = (
        find_values_by_key(
            route,
            "unsupported_link_ids",
        )
    )

    for value in unsupported_lists:

        if isinstance(value, list):

            for link_id in value:

                normalized = normalize_id(
                    link_id
                )

                if normalized:
                    result.add(
                        normalized
                    )

    # --------------------------------------------------------
    # fallback:
    # traffic_source == tmap_fallback 인 LINK 객체 탐색
    # --------------------------------------------------------

    def walk(obj):

        if isinstance(obj, dict):

            traffic_source = str(
                obj.get(
                    "traffic_source",
                    "",
                )
            ).strip().lower()

            if traffic_source == "tmap_fallback":

                link_id = normalize_id(

                    obj.get(
                        "LINK_ID"
                    )

                    or

                    obj.get(
                        "link_id"
                    )

                )

                if link_id:

                    result.add(
                        link_id
                    )

            for value in obj.values():

                walk(
                    value
                )

        elif isinstance(obj, list):

            for item in obj:

                walk(
                    item
                )

    walk(
        route
    )

    return result


# ============================================================
# 4. LINK → ROAD_NAME lookup
# ============================================================

def extract_road_names(route):

    road_names = {}


    mappings = (
        find_values_by_key(
            route,
            "link_sequence",
        )
    )


    for sequence in mappings:

        if not isinstance(
            sequence,
            list,
        ):

            continue


        for link in sequence:

            if not isinstance(
                link,
                dict,
            ):

                continue


            link_id = normalize_id(

                link.get(
                    "LINK_ID"
                )

                or

                link.get(
                    "link_id"
                )

            )


            if not link_id:

                continue


            road_name = str(

                link.get(
                    "ROAD_NAME"
                )

                or

                link.get(
                    "road_name"
                )

                or

                ""

            ).strip()


            if (
                road_name
                and
                link_id not in road_names
            ):

                road_names[
                    link_id
                ] = (
                    road_name
                )


    return road_names


# ============================================================
# 5. routes 찾기
# ============================================================

def find_routes(
    pipeline_result,
):

    if not isinstance(
        pipeline_result,
        dict,
    ):

        return []


    routes = (
        pipeline_result.get(
            "routes"
        )
    )


    if isinstance(
        routes,
        list,
    ):

        return routes


    values = (
        find_values_by_key(
            pipeline_result,
            "routes",
        )
    )


    for value in values:

        if isinstance(
            value,
            list,
        ):

            return value


    return []


# ============================================================
# 6. main
# ============================================================

def analyze_unsupported_link_usage():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Unsupported LINK Usage"
    )

    print(
        "========================================"
    )


    if not OD_RESULT_DIR.exists():

        raise FileNotFoundError(

            "OD 결과 폴더가 없습니다.\n"
            f"{OD_RESULT_DIR}"

        )


    files = sorted(
        OD_RESULT_DIR.glob(
            "OD_*.json"
        )
    )


    print(
        "발견한 OD 결과 파일:",
        len(files),
    )


    if not files:

        raise RuntimeError(

            "분석할 OD 결과 JSON이 없습니다."

        )


    # LINK별 집계
    stats = defaultdict(
        lambda: {
            "od_ids": set(),
            "candidate_keys": set(),
            "affected_user_weight": 0,
            "candidate_user_exposure": 0,
            "road_names": set(),
        }
    )


    processed_od = 0
    skipped_od = 0
    usable_candidate_count = 0


    for file_path in files:

        # ----------------------------------------------------
        # Batch가 현재 파일을 쓰는 순간과 겹칠 수도 있으므로
        # 읽기 실패 파일은 안전하게 Skip
        # --------------------------------------------------------

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(
                    file
                )

        except Exception as error:

            print(
                f"⚠️ Skip: {file_path.name} | "
                f"{type(error).__name__}"
            )

            skipped_od += 1
            continue


        od_id = str(

            data.get(
                "od_id"
            )

            or

            file_path.stem

        )


        user_count = int(

            data.get(
                "user_count",
                0,
            )

            or

            0

        )


        pipeline_result = (

            data.get(
                "pipeline_result"
            )

            or

            data

        )


        routes = (
            find_routes(
                pipeline_result
            )
        )


        if not routes:

            skipped_od += 1
            continue


        # ----------------------------------------------------
        # OD 전체 기준 LINK 집합
        #
        # affected_user_weight는
        # 같은 LINK가 A/B/C에 반복되어도 OD당 1번만 더함
        # --------------------------------------------------------

        od_unsupported_links = set()


        for route in routes:

            if not isinstance(
                route,
                dict,
            ):

                continue


            mapping = (

                route.get(
                    "link_mapping_v2",
                    {}
                )

            )


            if (

                isinstance(
                    mapping,
                    dict,
                )

                and

                mapping.get(
                    "status"
                )
                !=
                "mapped"

            ):

                continue


            candidate_id = str(

                route.get(
                    "candidate_id",
                    "?",
                )

            )


            unsupported_links = (
                extract_unsupported_link_ids(
                    route
                )
            )


            road_names = (
                extract_road_names(
                    route
                )
            )


            usable_candidate_count += 1


            # ------------------------------------------------
            # Candidate 단위
            # ------------------------------------------------

            for link_id in unsupported_links:

                candidate_key = (
                    f"{od_id}:{candidate_id}"
                )


                stats[
                    link_id
                ][
                    "candidate_keys"
                ].add(
                    candidate_key
                )


                stats[
                    link_id
                ][
                    "candidate_user_exposure"
                ] += (
                    user_count
                )


                road_name = (
                    road_names.get(
                        link_id,
                        "",
                    )
                )


                if road_name:

                    stats[
                        link_id
                    ][
                        "road_names"
                    ].add(
                        road_name
                    )


            od_unsupported_links.update(
                unsupported_links
            )


        # ----------------------------------------------------
        # OD 단위
        # ----------------------------------------------------

        for link_id in od_unsupported_links:

            stats[
                link_id
            ][
                "od_ids"
            ].add(
                od_id
            )


            stats[
                link_id
            ][
                "affected_user_weight"
            ] += (
                user_count
            )


        processed_od += 1


    # ========================================================
    # DataFrame
    # ========================================================

    rows = []


    for (
        link_id,
        value,
    ) in stats.items():

        road_names = sorted(
            value[
                "road_names"
            ]
        )


        rows.append({

            "link_id":
                link_id,

            "road_name":
                " / ".join(
                    road_names
                ),

            "od_count":
                len(
                    value[
                        "od_ids"
                    ]
                ),

            "affected_user_weight":
                value[
                    "affected_user_weight"
                ],

            "route_candidate_count":
                len(
                    value[
                        "candidate_keys"
                    ]
                ),

            "candidate_user_exposure":
                value[
                    "candidate_user_exposure"
                ],

        })


    result = pd.DataFrame(
        rows
    )


    if not result.empty:

        result = (

            result

            .sort_values(

                by=[
                    "affected_user_weight",
                    "od_count",
                    "route_candidate_count",
                ],

                ascending=[
                    False,
                    False,
                    False,
                ],

            )

            .reset_index(
                drop=True
            )

        )


    OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True,

    )


    result.to_csv(

        OUTPUT_CSV,

        index=False,

        encoding="utf-8-sig",

    )


    summary = {

        "od_result_files_found":
            len(
                files
            ),

        "processed_od_count":
            processed_od,

        "skipped_od_count":
            skipped_od,

        "usable_candidate_count":
            usable_candidate_count,

        "unique_unsupported_link_count":
            int(
                len(
                    result
                )
            ),

        "output_file":
            str(
                OUTPUT_CSV
            ),

    }


    with open(
        SUMMARY_JSON,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(

            summary,

            file,

            ensure_ascii=False,

            indent=2,

        )


    print()

    print(
        "========================================"
    )

    print(
        "분석 결과"
    )

    print(
        "========================================"
    )


    print(
        "처리 OD:",
        processed_od,
    )


    print(
        "Skip OD:",
        skipped_od,
    )


    print(
        "사용 가능 Route 후보:",
        usable_candidate_count,
    )


    print(
        "AI 미지원 Unique LINK:",
        len(
            result
        ),
    )


    if not result.empty:

        print()

        print(
            "상위 10개 미지원 LINK"
        )

        print(
            "----------------------------------------"
        )


        display_columns = [

            "link_id",
            "road_name",
            "od_count",
            "affected_user_weight",
            "route_candidate_count",

        ]


        print(

            result[
                display_columns
            ]

            .head(
                10
            )

            .to_string(
                index=False
            )

        )


    print()

    print(
        "결과:"
    )

    print(
        OUTPUT_CSV
    )


    print()

    print(
        "Summary:"
    )

    print(
        SUMMARY_JSON
    )


    print()

    print(
        "========================================"
    )

    print(
        "Unsupported LINK Usage 분석 완료"
    )

    print(
        "========================================"
    )


    return result


# ============================================================
# 7. 직접 실행
# ============================================================

if __name__ == "__main__":

    analyze_unsupported_link_usage()