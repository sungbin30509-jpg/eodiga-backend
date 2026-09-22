from pathlib import Path
from collections import defaultdict
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Route LINK Usage Builder
#
# 목적
# ------------------------------------------------------------
# 완료된 Unique OD의 실제 A/B/C Route 결과를 읽어서
# 성남시 내부/경계 LINK 사용현황을 집계한다.
#
# AI 담당에게 전달할 핵심 산출물:
#
# LINK_ID
# road_name
# od_count
# route_candidate_count
# affected_user_weight
# candidate_user_exposure
# link_length_m
# candidate_cumulative_distance_m
# ai_supported
#
#
# 지표 정의
# ------------------------------------------------------------
# od_count
#   해당 LINK가 등장한 Unique OD 수
#
# route_candidate_count
#   해당 LINK가 등장한 A/B/C Route 후보 수
#
# affected_user_weight
#   같은 OD에서 A/B/C 여러 경로가 같은 LINK를 사용해도
#   해당 OD의 user_count를 한 번만 더한다.
#
# candidate_user_exposure
#   Route 후보별 user_count를 합산한다.
#   대안 경로의 노출량이므로 실제 사용자 수와 구분한다.
#
# candidate_cumulative_distance_m
#   LINK 길이 × Route 후보 등장 횟수
#
# ai_supported
#   현재 AI Coverage 기준 지원 여부
#
# 중요
# ------------------------------------------------------------
# 이 파일은 AI 학습 정답데이터가 아니다.
# Synthetic Route에서 실제 사용되는 LINK의 우선순위를
# AI 팀에 전달하기 위한 Coverage 개선용 통계다.
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


OUTPUT_FILE = (
    OUTPUT_DIR
    / "route_link_usage.csv"
)


SUMMARY_FILE = (
    OUTPUT_DIR
    / "route_link_usage_summary.json"
)


# ============================================================
# 1. 기본 함수
# ============================================================

def clean_text(value, default=""):

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return str(value).strip()


def normalize_id(value):

    text = clean_text(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def safe_float(value, default=0.0):

    try:

        if value is None:
            return default

        if pd.isna(value):
            return default

        return float(value)

    except (TypeError, ValueError):

        return default


def safe_int(value, default=0):

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ============================================================
# 2. JSON 재귀 탐색
# ============================================================

def find_values_by_key(obj, target_key):

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
# 3. Route 목록 찾기
# ============================================================

def get_routes(data):

    pipeline_result = (
        data.get("pipeline_result")
        or
        data
    )

    if not isinstance(
        pipeline_result,
        dict,
    ):
        return []

    routes = pipeline_result.get(
        "routes",
        []
    )

    if isinstance(routes, list):
        return routes

    values = find_values_by_key(
        pipeline_result,
        "routes",
    )

    for value in values:

        if isinstance(value, list):
            return value

    return []


# ============================================================
# 4. Mapping된 LINK Sequence
# ============================================================

def get_link_sequence(route):

    mapping = route.get(
        "link_mapping_v2",
        {},
    )

    if not isinstance(
        mapping,
        dict,
    ):
        return []


    if clean_text(
        mapping.get("status")
    ).lower() != "mapped":

        return []


    sequence = mapping.get(
        "link_sequence",
        []
    )


    if not isinstance(
        sequence,
        list,
    ):

        return []


    return sequence


# ============================================================
# 5. Route 안의 AI / 성남 상태 lookup
#
# 프로젝트 JSON 구조가 조금 달라도 최대한 찾아본다.
# ============================================================

def build_route_status_lookup(route):

    status_lookup = {}


    # --------------------------------------------------------
    # dict/list 안에서 LINK 객체 탐색
    # --------------------------------------------------------

    def walk(obj):

        if isinstance(obj, dict):

            link_id = normalize_id(
                obj.get("LINK_ID")
                or
                obj.get("link_id")
            )


            if link_id:

                existing = status_lookup.setdefault(
                    link_id,
                    {}
                )


                # ============================================
                # AI Source
                # ============================================

                traffic_source = clean_text(
                    obj.get("traffic_source")
                    or
                    obj.get("source")
                    or
                    obj.get("output_source")
                ).lower()


                if traffic_source:

                    existing[
                        "traffic_source"
                    ] = traffic_source


                # ============================================
                # AI supported
                # ============================================

                if "ai_supported" in obj:

                    value = obj.get(
                        "ai_supported"
                    )

                    if isinstance(value, bool):

                        existing[
                            "ai_supported"
                        ] = value

                    else:

                        existing[
                            "ai_supported"
                        ] = (
                            clean_text(
                                value
                            ).lower()
                            in
                            {
                                "true",
                                "1",
                                "yes",
                            }
                        )


                # ============================================
                # Seongnam status
                # ============================================

                if "inside_seongnam" in obj:

                    value = obj.get(
                        "inside_seongnam"
                    )

                    if isinstance(value, bool):

                        existing[
                            "inside_seongnam"
                        ] = value

                    else:

                        existing[
                            "inside_seongnam"
                        ] = (
                            clean_text(
                                value
                            ).lower()
                            in
                            {
                                "true",
                                "1",
                                "yes",
                            }
                        )


                position = clean_text(
                    obj.get("position")
                    or
                    obj.get("seongnam_position")
                    or
                    obj.get("location_class")
                ).lower()


                if position:

                    existing[
                        "position"
                    ] = position


            for value in obj.values():

                walk(value)


        elif isinstance(obj, list):

            for item in obj:

                walk(item)


    walk(route)


    # --------------------------------------------------------
    # unsupported_link_ids가 있다면 명시적으로 false
    # --------------------------------------------------------

    unsupported_values = find_values_by_key(
        route,
        "unsupported_link_ids",
    )


    for value in unsupported_values:

        if not isinstance(value, list):
            continue

        for link_id in value:

            normalized = normalize_id(
                link_id
            )

            if not normalized:
                continue

            status_lookup.setdefault(
                normalized,
                {}
            )[
                "ai_supported"
            ] = False


    return status_lookup


# ============================================================
# 6. LINK의 성남 여부 판정
# ============================================================

def classify_seongnam_link(
    link_id,
    status,
):

    source = clean_text(
        status.get(
            "traffic_source"
        )
    ).lower()


    # --------------------------------------------------------
    # 이미 source가 분명하면 우선 사용
    # --------------------------------------------------------

    if source == "flow_ai":

        return (
            True,
            "internal",
        )


    if source == "tmap_fallback":

        return (
            True,
            "internal",
        )


    if source == "tmap":

        return (
            False,
            "outside",
        )


    # --------------------------------------------------------
    # inside_seongnam
    # --------------------------------------------------------

    if "inside_seongnam" in status:

        if status[
            "inside_seongnam"
        ]:

            return (
                True,
                "internal",
            )

        return (
            False,
            "outside",
        )


    # --------------------------------------------------------
    # position
    # --------------------------------------------------------

    position = clean_text(
        status.get(
            "position"
        )
    ).lower()


    if position in {
        "internal",
        "inside",
        "boundary",
        "crossing",
    }:

        return (
            True,
            position,
        )


    if position in {
        "outside",
        "external",
    }:

        return (
            False,
            position,
        )


    # --------------------------------------------------------
    # 상태를 확정할 수 없으면 None
    # --------------------------------------------------------

    return (
        None,
        "unknown",
    )


# ============================================================
# 7. AI 지원 여부 판정
# ============================================================

def classify_ai_supported(
    status,
):

    source = clean_text(
        status.get(
            "traffic_source"
        )
    ).lower()


    if source == "flow_ai":
        return True


    if source == "tmap_fallback":
        return False


    if "ai_supported" in status:
        return bool(
            status[
                "ai_supported"
            ]
        )


    return None


# ============================================================
# 8. Main
# ============================================================

def build_route_link_usage():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Route LINK Usage Builder"
    )

    print(
        "========================================"
    )


    if not OD_RESULT_DIR.exists():

        raise FileNotFoundError(

            "OD Pipeline 결과 폴더가 없습니다.\n"
            f"{OD_RESULT_DIR}"

        )


    files = sorted(
        OD_RESULT_DIR.glob(
            "OD_*.json"
        )
    )


    if not files:

        raise RuntimeError(
            "분석할 OD 결과 JSON이 없습니다."
        )


    print(
        "발견한 OD 결과 파일:",
        len(files),
    )


    # ========================================================
    # LINK별 통계
    # ========================================================

    stats = defaultdict(

        lambda: {

            "od_ids":
                set(),

            "candidate_keys":
                set(),

            "affected_user_weight":
                0,

            "candidate_user_exposure":
                0,

            "road_names":
                set(),

            "link_length_m":
                0.0,

            "candidate_cumulative_distance_m":
                0.0,

            "ai_supported_values":
                set(),

            "positions":
                set(),

        }

    )


    processed_od_count = 0

    skipped_od_count = 0

    mapped_route_count = 0

    failed_route_count = 0

    unknown_location_link_count = 0


    # ========================================================
    # OD 순회
    # ========================================================

    for file_path in files:

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

        except Exception as error:

            print(
                f"⚠️ Skip {file_path.name} | "
                f"{type(error).__name__}"
            )

            skipped_od_count += 1

            continue


        od_id = clean_text(

            data.get("od_id")
            or
            file_path.stem

        )


        user_count = safe_int(

            data.get(
                "user_count",
                0,
            ),

            0,

        )


        routes = get_routes(
            data
        )


        if not routes:

            skipped_od_count += 1

            continue


        # ----------------------------------------------------
        # OD 단위 중복제거용
        # ----------------------------------------------------

        od_seen_links = set()


        # ====================================================
        # A/B/C 순회
        # ====================================================

        for route in routes:

            if not isinstance(
                route,
                dict,
            ):
                continue


            candidate_id = clean_text(

                route.get(
                    "candidate_id",
                    "?",
                )

            ).upper()


            link_sequence = get_link_sequence(
                route
            )


            if not link_sequence:

                failed_route_count += 1

                continue


            mapped_route_count += 1


            status_lookup = (

                build_route_status_lookup(
                    route
                )

            )


            # ------------------------------------------------
            # 한 Route 내부에서도 동일 LINK가 중복되면
            # candidate count는 한 번만 센다.
            # ------------------------------------------------

            candidate_seen_links = set()


            for link in link_sequence:

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


                status = (
                    status_lookup.get(
                        link_id,
                        {}
                    )
                )


                (
                    inside_seongnam,
                    position,
                ) = classify_seongnam_link(

                    link_id,

                    status,

                )


                # ============================================
                # AI팀 전달용 통계는
                # 성남 내부 / 경계 LINK만 사용
                # ============================================

                if inside_seongnam is False:

                    continue


                if inside_seongnam is None:

                    unknown_location_link_count += 1

                    continue


                ai_supported = (
                    classify_ai_supported(
                        status
                    )
                )


                road_name = clean_text(

                    link.get(
                        "ROAD_NAME"
                    )

                    or

                    link.get(
                        "road_name"
                    )

                )


                link_length_m = safe_float(

                    link.get(
                        "LENGTH"
                    )

                    or

                    link.get(
                        "link_length_m"
                    ),

                    0.0,

                )


                item = stats[
                    link_id
                ]


                if road_name:

                    item[
                        "road_names"
                    ].add(
                        road_name
                    )


                if link_length_m > 0:

                    if (
                        item[
                            "link_length_m"
                        ]
                        <=
                        0
                    ):

                        item[
                            "link_length_m"
                        ] = (
                            link_length_m
                        )


                if position:

                    item[
                        "positions"
                    ].add(
                        position
                    )


                if ai_supported is not None:

                    item[
                        "ai_supported_values"
                    ].add(
                        bool(
                            ai_supported
                        )
                    )


                # ============================================
                # Route 후보 단위
                # ============================================

                if (
                    link_id
                    not in
                    candidate_seen_links
                ):

                    candidate_key = (

                        f"{od_id}:"
                        f"{candidate_id}"

                    )


                    item[
                        "candidate_keys"
                    ].add(
                        candidate_key
                    )


                    item[
                        "candidate_user_exposure"
                    ] += (
                        user_count
                    )


                    item[
                        "candidate_cumulative_distance_m"
                    ] += (
                        link_length_m
                    )


                    candidate_seen_links.add(
                        link_id
                    )


                # ============================================
                # OD 단위
                # ============================================

                od_seen_links.add(
                    link_id
                )


        # ====================================================
        # 같은 OD의 A/B/C에서 중복되어도
        # 사용자 영향도는 한 번만 더한다.
        # ====================================================

        for link_id in od_seen_links:

            item = stats[
                link_id
            ]


            item[
                "od_ids"
            ].add(
                od_id
            )


            item[
                "affected_user_weight"
            ] += (
                user_count
            )


        processed_od_count += 1


    # ========================================================
    # DataFrame 변환
    # ========================================================

    rows = []


    for link_id, value in stats.items():

        ai_values = (
            value[
                "ai_supported_values"
            ]
        )


        # ----------------------------------------------------
        # 동일 LINK에 True/False가 섞이면
        # 데이터 불일치이므로 ambiguous
        # ----------------------------------------------------

        if ai_values == {True}:

            ai_supported = True

            ai_status = (
                "supported"
            )


        elif ai_values == {False}:

            ai_supported = False

            ai_status = (
                "unsupported"
            )


        elif ai_values == {
            True,
            False,
        }:

            ai_supported = None

            ai_status = (
                "conflict"
            )


        else:

            ai_supported = None

            ai_status = (
                "unknown"
            )


        rows.append({

            "link_id":
                link_id,

            "road_name":
                " / ".join(
                    sorted(
                        value[
                            "road_names"
                        ]
                    )
                ),

            "seongnam_position":
                " / ".join(
                    sorted(
                        value[
                            "positions"
                        ]
                    )
                ),

            "od_count":
                len(
                    value[
                        "od_ids"
                    ]
                ),

            "route_candidate_count":
                len(
                    value[
                        "candidate_keys"
                    ]
                ),

            "affected_user_weight":
                value[
                    "affected_user_weight"
                ],

            "candidate_user_exposure":
                value[
                    "candidate_user_exposure"
                ],

            "link_length_m":
                round(
                    value[
                        "link_length_m"
                    ],
                    3,
                ),

            "candidate_cumulative_distance_m":
                round(
                    value[
                        "candidate_cumulative_distance_m"
                    ],
                    3,
                ),

            "ai_supported":
                ai_supported,

            "ai_status":
                ai_status,

        })


    result = pd.DataFrame(
        rows
    )


    # ========================================================
    # 우선순위 정렬
    #
    # AI 미지원 → 사용자 영향 → OD → Route 순
    # ========================================================

    if not result.empty:

        result[
            "_unsupported_priority"
        ] = (

            result[
                "ai_status"
            ]
            ==
            "unsupported"

        ).astype(int)


        result = (

            result

            .sort_values(

                by=[

                    "_unsupported_priority",

                    "affected_user_weight",

                    "od_count",

                    "route_candidate_count",

                ],

                ascending=[

                    False,

                    False,

                    False,

                    False,

                ],

            )

            .drop(
                columns=[
                    "_unsupported_priority"
                ]
            )

            .reset_index(
                drop=True
            )

        )


    # ========================================================
    # 저장
    # ========================================================

    OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True,

    )


    result.to_csv(

        OUTPUT_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # Summary
    # ========================================================

    ai_status_distribution = (

        result[
            "ai_status"
        ]

        .value_counts()

        .to_dict()

        if not result.empty

        else {}

    )


    ai_status_distribution = {

        str(key):
            int(value)

        for key, value
        in ai_status_distribution.items()

    }


    summary = {

        "od_result_file_count":
            len(files),

        "processed_od_count":
            processed_od_count,

        "skipped_od_count":
            skipped_od_count,

        "mapped_route_count":
            mapped_route_count,

        "failed_route_count":
            failed_route_count,

        "unique_seongnam_link_count":
            int(
                len(result)
            ),

        "ai_status_distribution":
            ai_status_distribution,

        "unknown_location_link_events":
            unknown_location_link_count,

        "output_file":
            str(
                OUTPUT_FILE
            ),

        "usage_definition": {

            "affected_user_weight":
                (
                    "Same OD contributes its user_count "
                    "only once per LINK across A/B/C."
                ),

            "candidate_user_exposure":
                (
                    "User_count summed for each route "
                    "candidate containing the LINK."
                ),

        },

    }


    with open(

        SUMMARY_FILE,

        "w",

        encoding="utf-8",

    ) as file:

        json.dump(

            summary,

            file,

            ensure_ascii=False,

            indent=2,

        )


    # ========================================================
    # 출력
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "Route LINK Usage 결과"
    )

    print(
        "========================================"
    )


    print(
        "처리 OD:",
        processed_od_count,
    )


    print(
        "Skip OD:",
        skipped_od_count,
    )


    print(
        "Mapped Route:",
        mapped_route_count,
    )


    print(
        "실패/사용불가 Route:",
        failed_route_count,
    )


    print(
        "성남 Unique LINK:",
        len(result),
    )


    print()

    print(
        "AI Status:"
    )


    for (
        status,
        count,
    ) in (
        ai_status_distribution.items()
    ):

        print(
            f"  {status}:",
            count,
        )


    if not result.empty:

        unsupported = (

            result[
                result[
                    "ai_status"
                ]
                ==
                "unsupported"
            ]

        )


        if not unsupported.empty:

            print()

            print(
                "AI 확대 우선순위 TOP 15"
            )

            print(
                "----------------------------------------"
            )


            columns = [

                "link_id",

                "road_name",

                "od_count",

                "affected_user_weight",

                "route_candidate_count",

            ]


            print(

                unsupported[
                    columns
                ]

                .head(
                    15
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
        OUTPUT_FILE
    )


    print()

    print(
        "Summary:"
    )

    print(
        SUMMARY_FILE
    )


    print()

    print(
        "========================================"
    )

    print(
        "Route LINK Usage 생성 완료"
    )

    print(
        "========================================"
    )


    return result


# ============================================================
# 직접 실행
# ============================================================

if __name__ == "__main__":

    build_route_link_usage()