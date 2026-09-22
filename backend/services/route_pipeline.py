from pathlib import Path
import json

from backend.services.route_engine import (
    get_routes_by_place_names,
)

from backend.services.link_matcher import (
    match_route_candidates,
)

from backend.services.link_classifier import (
    classify_route_candidates,
)

from backend.services.ai_coverage_service import (
    apply_ai_coverage_to_candidates,
)


# ============================================================
# FLOW:MATE
# Universal Route Pipeline
#
# 사용자 장소명
#        ↓
# TMAP POI
#        ↓
# TMAP 자동차 A/B/C
#        ↓
# 국가표준 MOCT_LINK
#        ↓
# 성남 내부 / 경계 / 외부
#        ↓
# AI Coverage
#
#
# 중요
# ------------------------------------------------------------
# 특정 후보의 LINK Mapping이 실패해도
# 전체 Pipeline은 중단하지 않는다.
#
# 예:
#
# A = mapped
# B = mapped
# C = failed
#
# → A/B는 계속 사용
# → C는 실패 상태로 기록
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "pipeline"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 안전한 파일명 생성
# ============================================================

def safe_filename(
    text,
):

    text = (
        str(text)
        .strip()
    )


    invalid_characters = [

        "\\",
        "/",
        ":",
        "*",
        "?",
        '"',
        "<",
        ">",
        "|",
        " ",

    ]


    for char in invalid_characters:

        text = text.replace(
            char,
            "_",
        )


    return text


# ============================================================
# 3. Pipeline Summary 생성
# ============================================================

def build_pipeline_summary(
    final_result,
):

    summary = []


    routes = (
        final_result.get(
            "routes",
            [],
        )
    )


    for route in routes:

        # ====================================================
        # 각 단계 결과
        # ====================================================

        mapping = (
            route.get(
                "link_mapping_v2",
                {},
            )
        )


        classification = (
            route.get(
                "seongnam_classification",
                {},
            )
        )


        coverage = (
            route.get(
                "ai_coverage",
                {},
            )
        )


        mapping_status = (
            mapping.get(
                "status",
                "failed",
            )
        )


        # ====================================================
        # Summary
        # ====================================================

        summary_item = {

            "candidate_id":
                route.get(
                    "candidate_id"
                ),

            "route_label":
                route.get(
                    "route_label"
                ),

            "search_option":
                route.get(
                    "search_option"
                ),

            # ------------------------------------------------
            # TMAP
            # ------------------------------------------------

            "tmap_distance_m":
                route.get(
                    "total_distance_m"
                ),

            "tmap_eta_sec":
                route.get(
                    "tmap_eta_sec"
                ),

            "tmap_eta_min":
                route.get(
                    "tmap_eta_min"
                ),

            # ------------------------------------------------
            # LINK Mapping
            # ------------------------------------------------

            "mapping_status":
                mapping_status,

            "mapping_error":
                mapping.get(
                    "error"
                ),

            "mapping_error_type":
                mapping.get(
                    "error_type"
                ),

            "matched_link_count":
                mapping.get(
                    "matched_link_count",
                    0,
                ),

            "mapping_connectivity_percent":
                mapping.get(
                    "connectivity_percent",
                    0.0,
                ),

            "mapping_coverage_percent":
                mapping.get(
                    "coverage_percent",
                    0.0,
                ),

            "mapping_quality":
                mapping.get(
                    "quality",
                    "failed",
                ),

            "mapping_search_mode":
                mapping.get(
                    "search_mode"
                ),

            # ------------------------------------------------
            # 성남 분류
            # ------------------------------------------------

            "classification_status":
                classification.get(
                    "status"
                ),

            "inside_link_count":
                classification.get(
                    "inside_link_count",
                    0,
                ),

            "boundary_link_count":
                classification.get(
                    "boundary_crossing_link_count",
                    0,
                ),

            "outside_link_count":
                classification.get(
                    "outside_link_count",
                    0,
                ),

            "seongnam_distance_m":
                classification.get(
                    "seongnam_distance_m",
                    0.0,
                ),

            "outside_distance_m":
                classification.get(
                    "outside_distance_m",
                    0.0,
                ),

            "seongnam_distance_ratio_percent":
                classification.get(
                    "seongnam_distance_ratio_percent",
                    0.0,
                ),

            # ------------------------------------------------
            # AI Coverage
            # ------------------------------------------------

            "ai_coverage_status":
                coverage.get(
                    "status"
                ),

            "ai_supported_link_count":
                coverage.get(
                    "ai_supported_link_count",
                    0,
                ),

            "fallback_link_count":
                coverage.get(
                    "tmap_fallback_link_count",
                    0,
                ),

            "outside_tmap_link_count":
                coverage.get(
                    "outside_seongnam_link_count",
                    0,
                ),

            "ai_link_coverage_percent":
                coverage.get(
                    "link_count_coverage_percent",
                    0.0,
                ),

            "ai_distance_coverage_percent":
                coverage.get(
                    "distance_coverage_percent",
                    0.0,
                ),

            "ai_covered_distance_m":
                coverage.get(
                    "ai_covered_distance_m",
                    0.0,
                ),

            "tmap_fallback_distance_m":
                coverage.get(
                    "tmap_fallback_distance_m",
                    0.0,
                ),

            "unsupported_link_count":
                coverage.get(
                    "unsupported_link_count",
                    0,
                ),

        }


        summary.append(
            summary_item
        )


    return summary


# ============================================================
# 4. Pipeline 상태 계산
# ============================================================

def build_pipeline_status(
    summary,
):

    candidate_count = (
        len(
            summary
        )
    )


    mapped_candidates = [

        item

        for item
        in summary

        if (

            item[
                "mapping_status"
            ]

            ==

            "mapped"

        )

    ]


    failed_candidates = [

        item

        for item
        in summary

        if (

            item[
                "mapping_status"
            ]

            !=

            "mapped"

        )

    ]


    usable_candidate_ids = [

        item[
            "candidate_id"
        ]

        for item
        in mapped_candidates

    ]


    failed_candidate_ids = [

        item[
            "candidate_id"
        ]

        for item
        in failed_candidates

    ]


    if len(
        mapped_candidates
    ) > 0:

        status = "ok"


    else:

        status = (
            "no_usable_candidate"
        )


    return {

        "status":
            status,

        "candidate_count":
            candidate_count,

        "usable_candidate_count":
            len(
                mapped_candidates
            ),

        "mapping_failed_count":
            len(
                failed_candidates
            ),

        "usable_candidate_ids":
            usable_candidate_ids,

        "failed_candidate_ids":
            failed_candidate_ids,

    }


# ============================================================
# 5. 결과 파일 저장
# ============================================================

def save_pipeline_result(
    result,
    origin_query,
    destination_query,
):

    origin_name = (
        safe_filename(
            origin_query
        )
    )


    destination_name = (
        safe_filename(
            destination_query
        )
    )


    output_file = (

        OUTPUT_DIR

        /

        (
            f"{origin_name}"
            f"__to__"
            f"{destination_name}"
            f".json"
        )

    )


    result[
        "pipeline_output_file"
    ] = str(
        output_file
    )


    with open(

        output_file,

        "w",

        encoding="utf-8",

    ) as file:

        json.dump(

            result,

            file,

            ensure_ascii=False,

            indent=2,

        )


    return output_file


# ============================================================
# 6. 터미널 Summary 출력
# ============================================================

def print_pipeline_summary(
    final_result,
):

    summary = (
        final_result.get(
            "pipeline_summary",
            [],
        )
    )


    pipeline_status = (
        final_result.get(
            "pipeline_status",
            {},
        )
    )


    print()

    print(
        "========================================"
    )

    print(
        "Pipeline 최종 결과"
    )

    print(
        "========================================"
    )


    for item in summary:

        print()

        print(
            "----------------------------------------"
        )


        print(

            "경로:",

            item[
                "candidate_id"
            ],

        )


        print(
            "----------------------------------------"
        )


        # ====================================================
        # TMAP Route
        # ====================================================

        print(

            "TMAP 거리:",

            item[
                "tmap_distance_m"
            ],

            "m",

        )


        print(

            "TMAP ETA:",

            item[
                "tmap_eta_min"
            ],

            "분",

        )


        # ====================================================
        # Mapping 실패
        # ====================================================

        if (

            item[
                "mapping_status"
            ]

            !=

            "mapped"

        ):

            print()

            print(
                "LINK Mapping: ❌ FAILED"
            )


            print(

                "오류 종류:",

                item[
                    "mapping_error_type"
                ],

            )


            print(

                "오류 내용:",

                item[
                    "mapping_error"
                ],

            )


            print()

            print(

                "이 Route 후보는 "
                "LINK 기반 후속 계산에서 제외됩니다."

            )


            continue


        # ====================================================
        # Mapping 성공
        # ====================================================

        print()

        print(
            "LINK Mapping: ✅ MAPPED"
        )


        print(

            "LINK 수:",

            item[
                "matched_link_count"
            ],

        )


        print(

            "연결률:",

            item[
                "mapping_connectivity_percent"
            ],

            "%",

        )


        print(

            "Mapping Coverage:",

            item[
                "mapping_coverage_percent"
            ],

            "%",

        )


        print(

            "Mapping Quality:",

            item[
                "mapping_quality"
            ],

        )


        print(

            "탐색 모드:",

            item[
                "mapping_search_mode"
            ],

        )


        # ====================================================
        # 성남 분류
        # ====================================================

        print()

        print(
            "[성남 구간]"
        )


        print(

            "완전 내부 LINK:",

            item[
                "inside_link_count"
            ],

        )


        print(

            "경계 교차 LINK:",

            item[
                "boundary_link_count"
            ],

        )


        print(

            "성남 외부 LINK:",

            item[
                "outside_link_count"
            ],

        )


        print(

            "성남 구간:",

            round(

                item[
                    "seongnam_distance_m"
                ]

                /

                1000,

                3,

            ),

            "km",

        )


        print(

            "성남 외부:",

            round(

                item[
                    "outside_distance_m"
                ]

                /

                1000,

                3,

            ),

            "km",

        )


        print(

            "전체 중 성남 비율:",

            item[
                "seongnam_distance_ratio_percent"
            ],

            "%",

        )


        # ====================================================
        # AI Coverage
        # ====================================================

        print()

        print(
            "[AI Coverage]"
        )


        print(

            "AI 지원 LINK:",

            item[
                "ai_supported_link_count"
            ],

        )


        print(

            "TMAP Fallback LINK:",

            item[
                "fallback_link_count"
            ],

        )


        print(

            "외부 TMAP LINK:",

            item[
                "outside_tmap_link_count"
            ],

        )


        print(

            "AI LINK Coverage:",

            item[
                "ai_link_coverage_percent"
            ],

            "%",

        )


        print(

            "AI Distance Coverage:",

            item[
                "ai_distance_coverage_percent"
            ],

            "%",

        )


        print(

            "AI 담당 거리:",

            round(

                item[
                    "ai_covered_distance_m"
                ]

                /

                1000,

                3,

            ),

            "km",

        )


        print(

            "Fallback 거리:",

            round(

                item[
                    "tmap_fallback_distance_m"
                ]

                /

                1000,

                3,

            ),

            "km",

        )


        print(

            "미지원 LINK:",

            item[
                "unsupported_link_count"
            ],

            "개",

        )


    # ========================================================
    # 전체 상태
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "Pipeline 상태"
    )

    print(
        "========================================"
    )


    print(

        "전체 후보:",

        pipeline_status.get(
            "candidate_count",
            0,
        ),

    )


    print(

        "사용 가능 후보:",

        pipeline_status.get(
            "usable_candidate_count",
            0,
        ),

    )


    print(

        "Mapping 실패 후보:",

        pipeline_status.get(
            "mapping_failed_count",
            0,
        ),

    )


    print(

        "사용 가능 후보 ID:",

        pipeline_status.get(
            "usable_candidate_ids",
            [],
        ),

    )


    print(

        "실패 후보 ID:",

        pipeline_status.get(
            "failed_candidate_ids",
            [],
        ),

    )


    print()

    print(

        "Pipeline Status:",

        pipeline_status.get(
            "status"
        ),

    )


    output_file = (
        final_result.get(
            "pipeline_output_file"
        )
    )


    if output_file:

        print()

        print(
            "결과 저장:"
        )


        print(
            output_file
        )


    print()

    print(
        "========================================"
    )


    if (

        pipeline_status.get(
            "status"
        )

        ==

        "ok"

    ):

        print(
            "Universal Route Pipeline 완료"
        )


    else:

        print(

            "Universal Route Pipeline 완료"
            " - 사용 가능한 LINK Mapping 후보 없음"

        )


    print(
        "========================================"
    )


# ============================================================
# 7. 핵심 함수
#
# 장소명
# →
# A/B/C
# →
# LINK
# →
# 성남
# →
# AI Coverage
# ============================================================

def run_route_pipeline(
    origin_query,
    destination_query,
    origin_region_hint=None,
    destination_region_hint=None,
    force_route_refresh=False,
    save_result=True,
    verbose=True,
):

    # ========================================================
    # 시작 출력
    # ========================================================

    if verbose:

        print()

        print(
            "========================================"
        )

        print(
            "FLOW:MATE Universal Route Pipeline"
        )

        print(
            "========================================"
        )


        print(

            "출발:",

            origin_query,

        )


        print(

            "도착:",

            destination_query,

        )


    # ========================================================
    # STEP 1
    #
    # 장소명
    # →
    # TMAP POI
    # →
    # A/B/C
    # ========================================================

    if verbose:

        print()

        print(
            "[1/4] TMAP 장소검색 + A/B/C Route"
        )


    route_result = (
        get_routes_by_place_names(

            origin_query=(
                origin_query
            ),

            destination_query=(
                destination_query
            ),

            origin_region_hint=(
                origin_region_hint
            ),

            destination_region_hint=(
                destination_region_hint
            ),

            force_refresh=(
                force_route_refresh
            ),

        )
    )


    if verbose:

        print()

        print(

            "출발 POI:",

            route_result[
                "origin"
            ][
                "name"
            ],

        )


        print(

            "도착 POI:",

            route_result[
                "destination"
            ][
                "name"
            ],

        )


        print(

            "Route Cache:",

            route_result[
                "cached"
            ],

        )


    # ========================================================
    # STEP 2
    #
    # TMAP A/B/C
    # →
    # MOCT_LINK
    # ========================================================

    if verbose:

        print()

        print(
            "[2/4] 국가표준 LINK Matching"
        )


    matched_result = (
        match_route_candidates(

            route_result,

            verbose=verbose,

        )
    )


    # ========================================================
    # STEP 3
    #
    # LINK
    # →
    # 성남 내부 / 경계 / 외부
    # ========================================================

    if verbose:

        print()

        print(
            "[3/4] 성남 내부 / 외부 판별"
        )


    classified_result = (
        classify_route_candidates(
            matched_result
        )
    )


    # ========================================================
    # STEP 4
    #
    # 성남 LINK
    # →
    # AI 지원 / TMAP fallback
    # ========================================================

    if verbose:

        print()

        print(
            "[4/4] AI Coverage 계산"
        )


    final_result = (
        apply_ai_coverage_to_candidates(
            classified_result
        )
    )


    # ========================================================
    # Pipeline Summary
    # ========================================================

    summary = (
        build_pipeline_summary(
            final_result
        )
    )


    final_result[
        "pipeline_summary"
    ] = (
        summary
    )


    # ========================================================
    # Pipeline 전체 상태
    # ========================================================

    pipeline_status = (
        build_pipeline_status(
            summary
        )
    )


    final_result[
        "pipeline_status"
    ] = (
        pipeline_status
    )


    # ========================================================
    # 결과 저장
    # ========================================================

    if save_result:

        save_pipeline_result(

            final_result,

            origin_query,

            destination_query,

        )


    # ========================================================
    # 터미널 출력
    # ========================================================

    if verbose:

        print_pipeline_summary(
            final_result
        )


    return final_result


# ============================================================
# 8. 직접 실행 테스트
# ============================================================

if __name__ == "__main__":

    run_route_pipeline(

        origin_query="판교역",

        destination_query="잠실역",

        origin_region_hint="성남시",

        destination_region_hint="서울특별시",

    )