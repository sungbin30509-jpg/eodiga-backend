from pathlib import Path
from functools import lru_cache

import pandas as pd


# ============================================================
# FLOW:MATE
# AI Coverage Service
#
# 역할
# ------------------------------------------------------------
# 성남 내부 LINK
#        ↓
# LightGBM supported_links.csv와 비교
#        ↓
#
# 성남 내부 + AI 지원
# → flow_ai
#
# 성남 내부 + AI 미지원
# → tmap_fallback
#
# 성남 외부
# → tmap
#
#
# 중요
# ------------------------------------------------------------
# 이 파일은 LightGBM 예측값 자체를 만드는 파일이 아니다.
#
# 현재 LINK가 AI 모델의 지원 대상인지 판별하고
# 어떤 교통정보 소스를 사용할지 결정하기 위한
# Coverage Service이다.
#
#
# LINK Mapping 실패 후보는
#
# status = skipped_mapping_failed
#
# 로 처리하며 전체 Pipeline을 중단하지 않는다.
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


# ============================================================
# 2. AI Integration 폴더
# ============================================================

AI_ROOT = (
    ROOT
    / "ai"
    / "FLOW_AI_INTEGRATION"
)


# ============================================================
# 3. LINK ID 정규화
# ============================================================

def normalize_id(
    value,
):

    if value is None:

        return ""


    text = (
        str(value)
        .strip()
    )


    if text.endswith(
        ".0"
    ):

        text = text[:-2]


    return text


# ============================================================
# 4. 안전한 float 변환
# ============================================================

def safe_float(
    value,
    default=0.0,
):

    try:

        if pd.isna(
            value
        ):

            return float(
                default
            )


        return float(
            value
        )


    except (
        TypeError,
        ValueError,
    ):

        return float(
            default
        )


# ============================================================
# 5. supported_links.csv 자동 탐색
# ============================================================

def find_supported_links_file():

    if not AI_ROOT.exists():

        raise FileNotFoundError(

            "AI Integration 폴더를 "
            "찾을 수 없습니다.\n"
            f"{AI_ROOT}"

        )


    candidates = sorted(

        AI_ROOT.rglob(
            "supported_links.csv"
        )

    )


    if not candidates:

        raise FileNotFoundError(

            "supported_links.csv를 "
            "찾을 수 없습니다.\n"
            f"검색 위치: {AI_ROOT}"

        )


    # 현재는 첫 번째 supported_links.csv 사용
    return candidates[0]


# ============================================================
# 6. supported_links.csv 읽기
#
# LINK_ID가 숫자로 변형되지 않도록
# 문자열로 읽는다.
# ============================================================

@lru_cache(maxsize=1)
def load_supported_links():

    file_path = (
        find_supported_links_file()
    )


    df = (
        pd.read_csv(

            file_path,

            dtype=str,

        )
    )


    if df.empty:

        raise ValueError(

            "supported_links.csv가 "
            "비어 있습니다.\n"
            f"{file_path}"

        )


    # ========================================================
    # LINK ID 컬럼 자동 탐색
    # ========================================================

    preferred_columns = [

        "link_id",

        "LINK_ID",

        "Link_ID",

        "LinkId",

        "linkId",

    ]


    link_column = None


    # --------------------------------------------------------
    # 우선 정확한 이름 탐색
    # --------------------------------------------------------

    for column in preferred_columns:

        if column in df.columns:

            link_column = (
                column
            )

            break


    # --------------------------------------------------------
    # 그래도 없으면
    # "_"와 대소문자를 무시하고 탐색
    # --------------------------------------------------------

    if link_column is None:

        for column in df.columns:

            normalized_column = (

                str(
                    column
                )

                .strip()

                .lower()

                .replace(
                    "_",
                    "",
                )

            )


            if normalized_column == "linkid":

                link_column = (
                    column
                )

                break


    if link_column is None:

        raise ValueError(

            "supported_links.csv에서 "
            "LINK ID 컬럼을 찾지 못했습니다.\n"
            f"현재 컬럼: {df.columns.tolist()}"

        )


    # ========================================================
    # LINK ID Set 생성
    # ========================================================

    supported_links = set()


    for value in df[
        link_column
    ]:

        link_id = (
            normalize_id(
                value
            )
        )


        if link_id:

            supported_links.add(
                link_id
            )


    if not supported_links:

        raise ValueError(

            "supported_links.csv에서 "
            "유효한 LINK_ID를 찾지 못했습니다."

        )


    return {

        "file":
            file_path,

        "link_column":
            link_column,

        "supported_links":
            supported_links,

        "supported_link_count":
            len(
                supported_links
            ),

    }


# ============================================================
# 7. Mapping 실패 후보용 AI Coverage
# ============================================================

def build_skipped_coverage(
    reason,
):

    return {

        "status":
            "skipped_mapping_failed",

        "reason":
            reason,

        "supported_links_file":
            None,

        "model_supported_link_universe_count":
            None,

        "seongnam_route_link_count":
            0,

        "ai_supported_link_count":
            0,

        "tmap_fallback_link_count":
            0,

        "outside_seongnam_link_count":
            0,

        "link_count_coverage_percent":
            0.0,

        "seongnam_route_distance_m":
            0.0,

        "ai_covered_distance_m":
            0.0,

        "tmap_fallback_distance_m":
            0.0,

        "outside_seongnam_distance_m":
            0.0,

        "distance_coverage_percent":
            0.0,

        "unsupported_link_ids":
            [],

        "link_sequence":
            [],

    }


# ============================================================
# 8. Route 1개 AI Coverage 계산
# ============================================================

def apply_ai_coverage_to_route(
    route,
):

    # ========================================================
    # 성남 분류 결과
    # ========================================================

    classification = (
        route.get(

            "seongnam_classification",

            {},

        )
    )


    classification_status = (
        classification.get(
            "status"
        )
    )


    link_sequence = (
        classification.get(

            "link_sequence",

            [],

        )
    )


    result = (
        route.copy()
    )


    # ========================================================
    # LINK Mapping 실패 후보
    #
    # link_classifier.py에서
    #
    # skipped_mapping_failed
    #
    # 로 넘어온 경우
    # ========================================================

    if (

        classification_status

        !=

        "classified"

        or

        not link_sequence

    ):

        reason = (
            classification.get(

                "reason",

                "LINK Mapping 실패로 "
                "AI Coverage 계산을 건너뜁니다.",

            )
        )


        result[
            "ai_coverage"
        ] = (

            build_skipped_coverage(
                reason
            )

        )


        return result


    # ========================================================
    # AI 지원 LINK 정보 로드
    # ========================================================

    support_data = (
        load_supported_links()
    )


    supported_links = (
        support_data[
            "supported_links"
        ]
    )


    # ========================================================
    # 집계 변수
    # ========================================================

    output_sequence = []


    ai_supported_count = 0

    fallback_count = 0

    outside_count = 0


    seongnam_distance_m = 0.0

    ai_covered_distance_m = 0.0

    fallback_distance_m = 0.0

    outside_distance_m = 0.0


    unsupported_link_ids = []


    # ========================================================
    # LINK별 Coverage 판정
    # ========================================================

    for item in link_sequence:

        current = (
            item.copy()
        )


        link_id = normalize_id(

            current.get(
                "LINK_ID"
            )

        )


        position = (
            current.get(

                "seongnam_position",

                "outside",

            )
        )


        overlap_m = safe_float(

            current.get(

                "seongnam_overlap_m",

                0.0,

            ),

            0.0,

        )


        outside_m = safe_float(

            current.get(

                "outside_length_m",

                0.0,

            ),

            0.0,

        )


        # ====================================================
        # CASE 1
        #
        # 성남 완전 외부
        #
        # → TMAP 사용
        # ====================================================

        if position == "outside":

            current[
                "ai_supported"
            ] = False


            current[
                "traffic_source"
            ] = "tmap"


            current[
                "ai_covered_distance_m"
            ] = 0.0


            current[
                "fallback_distance_m"
            ] = 0.0


            outside_count += 1


            outside_distance_m += (
                outside_m
            )


        # ====================================================
        # CASE 2
        #
        # 성남 내부 또는 경계교차
        # ====================================================

        else:

            # ------------------------------------------------
            # 성남과 실제 겹치는 부분
            # ------------------------------------------------

            seongnam_distance_m += (
                overlap_m
            )


            # =================================================
            # AI 지원 LINK
            #
            # → 향후 LightGBM 예측 사용
            # =================================================

            if link_id in supported_links:

                current[
                    "ai_supported"
                ] = True


                current[
                    "traffic_source"
                ] = "flow_ai"


                current[
                    "ai_covered_distance_m"
                ] = overlap_m


                current[
                    "fallback_distance_m"
                ] = 0.0


                ai_supported_count += 1


                ai_covered_distance_m += (
                    overlap_m
                )


            # =================================================
            # AI 미지원 LINK
            #
            # → TMAP fallback
            # =================================================

            else:

                current[
                    "ai_supported"
                ] = False


                current[
                    "traffic_source"
                ] = "tmap_fallback"


                current[
                    "ai_covered_distance_m"
                ] = 0.0


                current[
                    "fallback_distance_m"
                ] = overlap_m


                fallback_count += 1


                fallback_distance_m += (
                    overlap_m
                )


                if link_id:

                    unsupported_link_ids.append(
                        link_id
                    )


            # =================================================
            # Boundary crossing LINK라면
            #
            # 같은 LINK의 성남 밖 부분은
            # 외부 거리로 집계
            # =================================================

            outside_distance_m += (
                outside_m
            )


            if position == "boundary_crossing":

                current[
                    "outside_segment_source"
                ] = "tmap"


            else:

                current[
                    "outside_segment_source"
                ] = None


        output_sequence.append(
            current
        )


    # ========================================================
    # 9. 성남 Route LINK 수
    # ========================================================

    seongnam_link_count = (

        ai_supported_count

        +

        fallback_count

    )


    # ========================================================
    # 10. LINK 개수 기준 AI Coverage
    # ========================================================

    if seongnam_link_count > 0:

        link_coverage_percent = (

            ai_supported_count

            /

            seongnam_link_count

            *

            100

        )


    else:

        link_coverage_percent = 0.0


    # ========================================================
    # 11. 거리 기준 AI Coverage
    #
    # 프로젝트에서 더 중요한 Coverage 지표
    # ========================================================

    if seongnam_distance_m > 0:

        distance_coverage_percent = (

            ai_covered_distance_m

            /

            seongnam_distance_m

            *

            100

        )


    else:

        distance_coverage_percent = 0.0


    # ========================================================
    # 12. 거리 검증용 합계
    # ========================================================

    classified_total_distance_m = (

        seongnam_distance_m

        +

        outside_distance_m

    )


    # ========================================================
    # 13. Unsupported LINK 중복 제거
    #
    # 순서는 유지
    # ========================================================

    unique_unsupported_link_ids = list(

        dict.fromkeys(
            unsupported_link_ids
        )

    )


    # ========================================================
    # 14. 최종 결과
    # ========================================================

    result[
        "ai_coverage"
    ] = {

        "status":
            "analyzed",

        "supported_links_file":
            str(

                support_data[
                    "file"
                ]

            ),

        "supported_links_column":
            support_data[
                "link_column"
            ],

        "model_supported_link_universe_count":
            support_data[
                "supported_link_count"
            ],

        # ----------------------------------------------------
        # LINK Count
        # ----------------------------------------------------

        "seongnam_route_link_count":
            seongnam_link_count,

        "ai_supported_link_count":
            ai_supported_count,

        "tmap_fallback_link_count":
            fallback_count,

        "outside_seongnam_link_count":
            outside_count,

        "link_count_coverage_percent":
            round(

                link_coverage_percent,

                2,

            ),

        # ----------------------------------------------------
        # Distance
        # ----------------------------------------------------

        "seongnam_route_distance_m":
            round(

                seongnam_distance_m,

                2,

            ),

        "ai_covered_distance_m":
            round(

                ai_covered_distance_m,

                2,

            ),

        "tmap_fallback_distance_m":
            round(

                fallback_distance_m,

                2,

            ),

        "outside_seongnam_distance_m":
            round(

                outside_distance_m,

                2,

            ),

        "classified_total_distance_m":
            round(

                classified_total_distance_m,

                2,

            ),

        "distance_coverage_percent":
            round(

                distance_coverage_percent,

                2,

            ),

        # ----------------------------------------------------
        # AI Coverage Gap
        # ----------------------------------------------------

        "unsupported_link_count":
            len(
                unique_unsupported_link_ids
            ),

        "unsupported_link_ids":
            unique_unsupported_link_ids,

        # ----------------------------------------------------
        # LINK별 결과
        # ----------------------------------------------------

        "link_sequence":
            output_sequence,

    }


    return result


# ============================================================
# 15. A/B/C 전체 AI Coverage
# ============================================================

def apply_ai_coverage_to_candidates(
    classified_result,
):

    routes = (
        classified_result.get(

            "routes",

            [],

        )
    )


    if not routes:

        raise ValueError(

            "Route 결과에 "
            "routes가 없습니다."

        )


    analyzed_routes = []


    for route in routes:

        analyzed_route = (
            apply_ai_coverage_to_route(
                route
            )
        )


        analyzed_routes.append(
            analyzed_route
        )


    result = (
        classified_result.copy()
    )


    result[
        "routes"
    ] = (
        analyzed_routes
    )


    # ========================================================
    # 16. 전체 후보 Summary
    # ========================================================

    analyzed_count = sum(

        1

        for route
        in analyzed_routes

        if (

            route

            .get(
                "ai_coverage",
                {},
            )

            .get(
                "status"
            )

            ==

            "analyzed"

        )

    )


    skipped_count = (

        len(
            analyzed_routes
        )

        -

        analyzed_count

    )


    result[
        "ai_coverage_summary"
    ] = {

        "candidate_count":
            len(
                analyzed_routes
            ),

        "analyzed_candidate_count":
            analyzed_count,

        "skipped_candidate_count":
            skipped_count,

    }


    return result


# ============================================================
# 17. 모듈 직접 실행
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE"
    )

    print(
        "AI Coverage Service"
    )

    print(
        "========================================"
    )


    data = (
        load_supported_links()
    )


    print()

    print(
        "supported_links.csv:"
    )


    print(
        data[
            "file"
        ]
    )


    print()

    print(
        "LINK ID 컬럼:"
    )


    print(
        data[
            "link_column"
        ]
    )


    print()

    print(
        "현재 AI 지원 LINK:"
    )


    print(
        f"{data['supported_link_count']:,}"
    )


    print()

    print(
        "주의:"
    )


    print(
        "이 파일은 AI 예측 실행이 아니라 "
        "AI 지원 가능 LINK Coverage를 판별합니다."
    )


    print()

    print(
        "========================================"
    )

    print(
        "ai_coverage_service.py 준비 완료"
    )

    print(
        "========================================"
    )