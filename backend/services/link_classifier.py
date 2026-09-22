from pathlib import Path
from functools import lru_cache

import pandas as pd


# ============================================================
# FLOW:MATE
# Seongnam LINK Classifier
#
# 역할
# ------------------------------------------------------------
# 국가표준 MOCT_LINK sequence
#        ↓
# Seongnam LINK Universe v2
#        ↓
# 성남 완전 내부 / 경계 교차 / 성남 외부
#
#
# 결과
# ------------------------------------------------------------
# inside
# boundary_crossing
# outside
#
#
# 중요
# ------------------------------------------------------------
# LINK Mapping이 실패한 Route 후보는
# Pipeline 전체를 종료하지 않고
#
# status = skipped_mapping_failed
#
# 로 처리한다.
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
# 2. 성남 LINK Universe
# ============================================================

UNIVERSE_FILE = (
    ROOT
    / "data"
    / "universe"
    / "seongnam_link_universe_v2.parquet"
)


# ============================================================
# 3. ID 정규화
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
# 5. 성남 LINK Universe 로드
#
# 한 번 읽은 뒤 메모리에 Cache
# ============================================================

@lru_cache(maxsize=1)
def load_seongnam_universe():

    if not UNIVERSE_FILE.exists():

        raise FileNotFoundError(

            "성남 LINK Universe 파일을 "
            "찾을 수 없습니다.\n"
            f"{UNIVERSE_FILE}"

        )


    # ========================================================
    # 필요한 컬럼만 읽기
    # ========================================================

    columns = [

        "LINK_ID",

        "ROAD_NAME",

        "geometry_length_m",

        "seongnam_overlap_m",

        "seongnam_overlap_ratio",

        "seongnam_position",

    ]


    universe = (
        pd.read_parquet(

            UNIVERSE_FILE,

            columns=columns,

        )
    )


    if universe.empty:

        raise ValueError(

            "성남 LINK Universe가 "
            "비어 있습니다."

        )


    if "LINK_ID" not in universe.columns:

        raise ValueError(

            "성남 LINK Universe에 "
            "LINK_ID 컬럼이 없습니다."

        )


    # ========================================================
    # LINK_ID 문자열 통일
    # ========================================================

    universe[
        "LINK_ID"
    ] = (

        universe[
            "LINK_ID"
        ]

        .apply(
            normalize_id
        )

    )


    # ========================================================
    # 빈 LINK_ID 제거
    # ========================================================

    universe = universe[

        universe[
            "LINK_ID"
        ]
        !=
        ""

    ].copy()


    # ========================================================
    # 혹시 모를 중복 제거
    # ========================================================

    universe = (

        universe

        .drop_duplicates(

            subset="LINK_ID",

            keep="first",

        )

        .set_index(
            "LINK_ID"
        )

    )


    return universe


# ============================================================
# 6. Route LINK 자체 길이 가져오기
#
# 우선순위:
#
# geometry_length_m
# →
# LENGTH
# →
# 0
# ============================================================

def get_route_link_length(
    link_item,
):

    if (
        link_item.get(
            "geometry_length_m"
        )
        is not None
    ):

        return safe_float(

            link_item.get(
                "geometry_length_m"
            ),

            0.0,

        )


    return safe_float(

        link_item.get(
            "LENGTH",
            0.0,
        ),

        0.0,

    )


# ============================================================
# 7. LINK 1개 성남 분류
# ============================================================

def classify_link(
    link_item,
):

    universe = (
        load_seongnam_universe()
    )


    link_id = normalize_id(

        link_item.get(
            "LINK_ID"
        )

    )


    if not link_id:

        raise ValueError(

            "LINK 분류 중 "
            "LINK_ID가 없습니다."

        )


    result = (
        link_item.copy()
    )


    route_link_length_m = (
        get_route_link_length(
            link_item
        )
    )


    # ========================================================
    # CASE 1
    #
    # 성남 Universe에 없음
    #
    # → 성남 외부 LINK
    # ========================================================

    if link_id not in universe.index:

        result.update({

            "inside_seongnam":
                False,

            "seongnam_position":
                "outside",

            "seongnam_overlap_m":
                0.0,

            "seongnam_overlap_ratio":
                0.0,

            "link_geometry_length_m":
                route_link_length_m,

            "outside_length_m":
                route_link_length_m,

        })


        return result


    # ========================================================
    # CASE 2
    #
    # 성남 Universe에 존재
    #
    # → inside 또는 boundary_crossing
    # ========================================================

    row = (
        universe.loc[
            link_id
        ]
    )


    universe_geometry_length_m = (
        safe_float(

            row.get(
                "geometry_length_m",
                route_link_length_m,
            ),

            route_link_length_m,

        )
    )


    overlap_m = (
        safe_float(

            row.get(
                "seongnam_overlap_m",
                0.0,
            ),

            0.0,

        )
    )


    overlap_ratio = (
        safe_float(

            row.get(
                "seongnam_overlap_ratio",
                0.0,
            ),

            0.0,

        )
    )


    position = (

        str(

            row.get(

                "seongnam_position",

                "inside",

            )

        )

        .strip()

    )


    # ========================================================
    # Universe의 상태값 방어
    # ========================================================

    if position not in [

        "inside",

        "boundary_crossing",

    ]:

        if overlap_ratio >= 0.99:

            position = "inside"

        else:

            position = "boundary_crossing"


    # ========================================================
    # LINK에서 성남 밖에 있는 부분
    # ========================================================

    outside_length_m = max(

        0.0,

        universe_geometry_length_m

        -

        overlap_m,

    )


    result.update({

        "inside_seongnam":
            True,

        "seongnam_position":
            position,

        "seongnam_overlap_m":
            overlap_m,

        "seongnam_overlap_ratio":
            overlap_ratio,

        "link_geometry_length_m":
            universe_geometry_length_m,

        "outside_length_m":
            outside_length_m,

    })


    return result


# ============================================================
# 8. LINK Sequence 전체 분류
# ============================================================

def classify_link_sequence(
    link_sequence,
):

    if not isinstance(
        link_sequence,
        list,
    ):

        raise ValueError(

            "link_sequence 형식이 "
            "list가 아닙니다."

        )


    classified = []


    for item in link_sequence:

        classified_item = (
            classify_link(
                item
            )
        )


        classified.append(
            classified_item
        )


    return classified


# ============================================================
# 9. Mapping 실패 후보용 결과
# ============================================================

def build_skipped_classification(
    reason,
):

    return {

        "status":
            "skipped_mapping_failed",

        "reason":
            reason,

        "total_link_count":
            0,

        "inside_link_count":
            0,

        "boundary_crossing_link_count":
            0,

        "outside_link_count":
            0,

        "seongnam_intersecting_link_count":
            0,

        "seongnam_distance_m":
            0.0,

        "outside_distance_m":
            0.0,

        "total_classified_distance_m":
            0.0,

        "seongnam_distance_ratio_percent":
            0.0,

        "link_sequence":
            [],

    }


# ============================================================
# 10. Route 1개 분류
# ============================================================

def classify_route(
    route,
):

    mapping = (
        route.get(

            "link_mapping_v2",

            {},

        )
    )


    mapping_status = (
        mapping.get(
            "status"
        )
    )


    link_sequence = (
        mapping.get(

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
    # 예:
    #
    # 판교역 → 잠실역 C
    #
    # TMAP Route 자체는 존재하지만
    # MOCT_LINK topology mapping 실패
    #
    # → 전체 Pipeline은 계속
    # ========================================================

    if (

        mapping_status

        !=

        "mapped"

        or

        not link_sequence

    ):

        reason = (
            mapping.get(

                "error",

                "LINK Mapping 결과가 없습니다.",

            )
        )


        result[
            "seongnam_classification"
        ] = (

            build_skipped_classification(
                reason
            )

        )


        return result


    # ========================================================
    # 정상 LINK 분류
    # ========================================================

    classified_sequence = (
        classify_link_sequence(
            link_sequence
        )
    )


    # ========================================================
    # Count
    # ========================================================

    total_count = (
        len(
            classified_sequence
        )
    )


    inside_count = sum(

        1

        for item
        in classified_sequence

        if (

            item[
                "seongnam_position"
            ]

            ==

            "inside"

        )

    )


    boundary_count = sum(

        1

        for item
        in classified_sequence

        if (

            item[
                "seongnam_position"
            ]

            ==

            "boundary_crossing"

        )

    )


    outside_count = sum(

        1

        for item
        in classified_sequence

        if (

            item[
                "seongnam_position"
            ]

            ==

            "outside"

        )

    )


    # ========================================================
    # 성남 내부 실제 길이
    #
    # boundary_crossing LINK는
    # overlap 부분만 성남 길이에 포함
    # ========================================================

    seongnam_distance_m = sum(

        safe_float(

            item.get(
                "seongnam_overlap_m",
                0.0,
            ),

            0.0,

        )

        for item
        in classified_sequence

    )


    # ========================================================
    # 성남 외부 길이
    #
    # outside LINK 전체
    # +
    # boundary_crossing의 성남 바깥 부분
    # ========================================================

    outside_distance_m = sum(

        safe_float(

            item.get(
                "outside_length_m",
                0.0,
            ),

            0.0,

        )

        for item
        in classified_sequence

    )


    # ========================================================
    # 전체 분류 길이
    # ========================================================

    total_classified_distance_m = (

        seongnam_distance_m

        +

        outside_distance_m

    )


    # ========================================================
    # 전체 경로 중 성남 구간 비율
    # ========================================================

    if total_classified_distance_m > 0:

        seongnam_distance_ratio = (

            seongnam_distance_m

            /

            total_classified_distance_m

            *

            100

        )


    else:

        seongnam_distance_ratio = 0.0


    # ========================================================
    # 결과
    # ========================================================

    result[
        "seongnam_classification"
    ] = {

        "status":
            "classified",

        "total_link_count":
            total_count,

        "inside_link_count":
            inside_count,

        "boundary_crossing_link_count":
            boundary_count,

        "outside_link_count":
            outside_count,

        "seongnam_intersecting_link_count":
            (
                inside_count

                +

                boundary_count
            ),

        "seongnam_distance_m":
            round(

                seongnam_distance_m,

                2,

            ),

        "outside_distance_m":
            round(

                outside_distance_m,

                2,

            ),

        "total_classified_distance_m":
            round(

                total_classified_distance_m,

                2,

            ),

        "seongnam_distance_ratio_percent":
            round(

                seongnam_distance_ratio,

                2,

            ),

        "link_sequence":
            classified_sequence,

    }


    return result


# ============================================================
# 11. A/B/C 전체 성남 분류
# ============================================================

def classify_route_candidates(
    matched_result,
):

    routes = (
        matched_result.get(

            "routes",

            [],

        )
    )


    if not routes:

        raise ValueError(

            "Route 결과에 "
            "routes가 없습니다."

        )


    classified_routes = []


    for route in routes:

        classified_route = (
            classify_route(
                route
            )
        )


        classified_routes.append(
            classified_route
        )


    result = (
        matched_result.copy()
    )


    result[
        "routes"
    ] = (
        classified_routes
    )


    # ========================================================
    # Classification Summary
    # ========================================================

    classified_count = sum(

        1

        for route
        in classified_routes

        if (

            route

            .get(
                "seongnam_classification",
                {},
            )

            .get(
                "status"
            )

            ==

            "classified"

        )

    )


    skipped_count = (

        len(
            classified_routes
        )

        -

        classified_count

    )


    result[
        "seongnam_classification_summary"
    ] = {

        "candidate_count":
            len(
                classified_routes
            ),

        "classified_candidate_count":
            classified_count,

        "skipped_candidate_count":
            skipped_count,

    }


    return result


# ============================================================
# 12. 모듈 직접 실행 확인
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
        "Seongnam LINK Classifier"
    )

    print(
        "========================================"
    )


    print()

    print(
        "Universe:"
    )


    print(
        UNIVERSE_FILE
    )


    universe = (
        load_seongnam_universe()
    )


    print()

    print(
        "성남 LINK:",
        f"{len(universe):,}",
    )


    print()

    print(
        "상태별 LINK:"
    )


    if (
        "seongnam_position"
        in
        universe.columns
    ):

        print(

            universe[
                "seongnam_position"
            ]

            .value_counts()

            .to_string()

        )


    print()

    print(
        "========================================"
    )

    print(
        "link_classifier.py 준비 완료"
    )

    print(
        "========================================"
    )