from pathlib import Path
import json

from backend.services.route_engine import (
    build_route_candidates,
    get_route_cache_file,
    make_route_cache_key,
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

from backend.services.route_pipeline import (
    build_pipeline_summary,
)


# ============================================================
# FLOW:MATE
# Dynamic Route Service
#
# 사용자가 Flutter에서 선택한 정확한 POI 좌표
#
# origin lat/lon
# destination lat/lon
#        ↓
# TMAP A/B/C
#        ↓
# MOCT_LINK Mapping
#        ↓
# Seongnam Classification
#        ↓
# AI Coverage
#
# 중요:
# 장소명을 다시 POI 검색하지 않는다.
# 사용자가 선택한 정확한 좌표를 그대로 사용한다.
# ============================================================


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


DYNAMIC_OUTPUT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "dynamic_pipeline"
)


DYNAMIC_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# Flutter에서 사용 가능한 Mapping Quality
# ============================================================

USABLE_MAPPING_QUALITIES = {
    "good",
    "recovered",
    "review",
}


# ============================================================
# 1. POI 검증
# ============================================================

def normalize_poi(
    poi,
    label,
):

    if not isinstance(
        poi,
        dict,
    ):

        raise ValueError(
            f"{label} 정보가 올바르지 않습니다."
        )


    name = (
        str(
            poi.get(
                "name",
                "",
            )
        )
        .strip()
    )


    if not name:

        raise ValueError(
            f"{label} 이름이 없습니다."
        )


    lat = (
        poi.get(
            "lat"
        )
    )

    lon = (
        poi.get(
            "lon"
        )
    )


    try:

        lat = float(
            lat
        )

        lon = float(
            lon
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValueError(
            f"{label} 좌표가 올바르지 않습니다."
        )


    if (
        lat < -90
        or
        lat > 90
    ):

        raise ValueError(
            f"{label} 위도 범위가 올바르지 않습니다."
        )


    if (
        lon < -180
        or
        lon > 180
    ):

        raise ValueError(
            f"{label} 경도 범위가 올바르지 않습니다."
        )


    return {

       "poi_id":
    (
        str(
            poi.get("poi_id")
        ).strip()

        if poi.get("poi_id") not in (
            None,
            "",
        )

        else None
    ),

        "name":
            name,

        "address":
            str(
                poi.get(
                    "address",
                    "",
                )
            ),

        "lat":
            lat,

        "lon":
            lon,

        "source":
            str(
                poi.get(
                    "source",
                    "tmap_poi",
                )
            ),

    }


# ============================================================
# 2. 정확한 좌표 기준 Route Cache
#
# 기존 route_engine의 coordinate hash cache를 그대로 사용
# ============================================================

def get_routes_by_exact_coordinates(
    origin,
    destination,
    force_refresh=False,
):

    cache_file = (
        get_route_cache_file(
            origin,
            destination,
        )
    )


    # --------------------------------------------------------
    # 기존 Cache
    # --------------------------------------------------------

    if (
        cache_file.exists()
        and
        not force_refresh
    ):

        try:

            with open(
                cache_file,
                "r",
                encoding="utf-8",
            ) as file:

                cached_data = (
                    json.load(
                        file
                    )
                )


            cached_data[
                "cached"
            ] = True


            cached_data[
                "exact_coordinate_input"
            ] = True


            return cached_data


        except (
            json.JSONDecodeError,
            OSError,
        ):

            # Cache가 손상된 경우 아래에서 새로 생성
            pass


    # --------------------------------------------------------
    # 실제 TMAP A/B/C 호출
    # --------------------------------------------------------

    routes = (
        build_route_candidates(
            origin,
            destination,
        )
    )


    result = {

        "origin_query":
            origin[
                "name"
            ],

        "destination_query":
            destination[
                "name"
            ],

        "origin":
            origin,

        "destination":
            destination,

        "routes":
            routes,

        "candidate_count":
            len(
                routes
            ),

        "cached":
            False,

        "exact_coordinate_input":
            True,

    }


    # --------------------------------------------------------
    # 기존 Route Cache 구조와 동일하게 저장
    # --------------------------------------------------------

    with open(
        cache_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )


    return result


# ============================================================
# 3. Dynamic Pipeline 결과 저장
# ============================================================

def save_dynamic_pipeline_result(
    request_id,
    final_result,
):

    output_file = (
        DYNAMIC_OUTPUT_DIR
        / f"{request_id}.json"
    )


    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_result,
            file,
            ensure_ascii=False,
            indent=2,
        )


    return output_file


# ============================================================
# 4. Flutter용 Route 응답 생성
# ============================================================

def build_frontend_routes(
    final_result,
    pipeline_summary,
    request_id,
):

    summary_by_candidate = {

        item.get(
            "candidate_id"
        ):
        item

        for item
        in pipeline_summary
    }


    frontend_routes = []


    for route in (
        final_result.get(
            "routes",
            [],
        )
    ):

        candidate_id = (
            route.get(
                "candidate_id"
            )
        )


        summary = (
            summary_by_candidate.get(
                candidate_id,
                {},
            )
        )


        mapping_status = (
            summary.get(
                "mapping_status",
                "failed",
            )
        )


        mapping_quality = (
            summary.get(
                "mapping_quality",
                "failed",
            )
        )


        is_usable = (

            mapping_status
            ==
            "mapped"

            and

            mapping_quality
            in
            USABLE_MAPPING_QUALITIES

        )


        geometry = (
            route.get(
                "geometry",
                [],
            )
        )


        navigation_guidance = (
            route.get(
                "navigation_guidance",
                [],
            )
        )


        # --------------------------------------------------------
        # TMAP Current Traffic
        #
        # route_engine.py에서 추출한 현재 교통구간.
        #
        # AI 미래예측값이 아니라
        # TMAP 현재 교통정보이다.
        # --------------------------------------------------------

        traffic_segments = (
            route.get(
                "traffic_segments",
                [],
            )
        )


        if not isinstance(
            traffic_segments,
            list,
        ):

            traffic_segments = []


        frontend_routes.append({

            "route_id":
                (
                    f"{request_id}_"
                    f"{candidate_id}"
                ),

            "candidate_id":
                candidate_id,

            "route_label":
                route.get(
                    "route_label"
                ),

            "search_option":
                route.get(
                    "search_option"
                ),

            "source":
                route.get(
                    "source",
                    "tmap",
                ),

            # -----------------------------------------------
            # TMAP
            # -----------------------------------------------

            "total_distance_m":
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

            # -----------------------------------------------
            # Geometry
            # -----------------------------------------------

            "coordinate_order":
                "lon_lat",

            "geometry_point_count":
                len(
                    geometry
                ),

            "geometry":
                geometry,

            # -----------------------------------------------
            # Navigation Guidance
            # -----------------------------------------------

            "navigation_guidance_count":
                len(
                    navigation_guidance
                ),

            "navigation_guidance":
                navigation_guidance,

            "navigation_schema_version":
                route.get(
                    "navigation_schema_version",
                    "navigation_guidance_v1",
                ),

            # -----------------------------------------------
            # TMAP Current Traffic
            #
            # 현재 교통상태이다.
            # AI 미래 혼잡예측과 구분한다.
            # -----------------------------------------------

            "traffic_segment_count":
                len(
                    traffic_segments
                ),

            "traffic_segments":
                traffic_segments,

            "traffic_schema_version":
                route.get(
                    "traffic_schema_version",
                    "tmap_current_traffic_v1",
                ),

            "traffic_source":
                route.get(
                    "traffic_source",
                    "tmap_current",
                ),

            "has_current_traffic":
                bool(
                    traffic_segments
                ),

            # -----------------------------------------------
            # Mapping
            # -----------------------------------------------

            "mapping_status":
                mapping_status,

            "mapping_quality":
                mapping_quality,

            "mapping_search_mode":
                summary.get(
                    "mapping_search_mode"
                ),

            "mapping_coverage_percent":
                summary.get(
                    "mapping_coverage_percent",
                    0.0,
                ),

            "mapping_connectivity_percent":
                summary.get(
                    "mapping_connectivity_percent",
                    0.0,
                ),

            "matched_link_count":
                summary.get(
                    "matched_link_count",
                    0,
                ),

            "mapping_error":
                summary.get(
                    "mapping_error"
                ),

            # -----------------------------------------------
            # Seongnam
            # -----------------------------------------------

            "inside_link_count":
                summary.get(
                    "inside_link_count",
                    0,
                ),

            "boundary_link_count":
                summary.get(
                    "boundary_link_count",
                    0,
                ),

            "outside_link_count":
                summary.get(
                    "outside_link_count",
                    0,
                ),

            "seongnam_distance_m":
                summary.get(
                    "seongnam_distance_m",
                    0.0,
                ),

            "outside_distance_m":
                summary.get(
                    "outside_distance_m",
                    0.0,
                ),

            "seongnam_distance_ratio_percent":
                summary.get(
                    "seongnam_distance_ratio_percent",
                    0.0,
                ),

            # -----------------------------------------------
            # 현재 AI Coverage
            # -----------------------------------------------

            "ai_supported_link_count":
                summary.get(
                    "ai_supported_link_count",
                    0,
                ),

            "fallback_link_count":
                summary.get(
                    "fallback_link_count",
                    0,
                ),

            "outside_tmap_link_count":
                summary.get(
                    "outside_tmap_link_count",
                    0,
                ),

            "ai_link_coverage_percent":
                summary.get(
                    "ai_link_coverage_percent",
                    0.0,
                ),

            "ai_distance_coverage_percent":
                summary.get(
                    "ai_distance_coverage_percent",
                    0.0,
                ),

            "unsupported_link_count":
                summary.get(
                    "unsupported_link_count",
                    0,
                ),

            # -----------------------------------------------
            # 최종 사용 가능 여부
            # -----------------------------------------------

            "is_usable":
                is_usable,

        })


    return frontend_routes


# ============================================================
# 5. 핵심 Dynamic Route 함수
#
# Flutter에서 선택한 정확한 POI 두 개를 받는다.
#
# 장소명 재검색 없음.
# ============================================================

def generate_dynamic_routes(
    origin,
    destination,
    force_refresh=False,
    save_result=True,
):

    # ========================================================
    # 입력 검증
    # ========================================================

    origin = (
        normalize_poi(
            origin,
            "출발지",
        )
    )


    destination = (
        normalize_poi(
            destination,
            "목적지",
        )
    )


    # ========================================================
    # 출발지 = 목적지 방지
    # ========================================================

    if (

        abs(
            origin[
                "lat"
            ]
            -
            destination[
                "lat"
            ]
        )
        <
        0.000001

        and

        abs(
            origin[
                "lon"
            ]
            -
            destination[
                "lon"
            ]
        )
        <
        0.000001

    ):

        raise ValueError(
            "출발지와 목적지가 동일합니다."
        )


    # ========================================================
    # 요청 ID
    #
    # 좌표 기반 SHA256
    # ========================================================

    cache_key = (
        make_route_cache_key(
            origin,
            destination,
        )
    )


    request_id = (
        f"DYN_{cache_key}"
    )


    # ========================================================
    # STEP 1
    #
    # 정확한 좌표 → TMAP A/B/C
    # ========================================================

    route_result = (
        get_routes_by_exact_coordinates(

            origin=origin,

            destination=destination,

            force_refresh=force_refresh,

        )
    )


    route_cache_hit = (
        route_result.get(
            "cached",
            False,
        )
    )


    # ========================================================
    # STEP 2
    #
    # TMAP Route → MOCT_LINK
    # ========================================================

    matched_result = (
        match_route_candidates(

            route_result,

            verbose=False,

        )
    )


    # ========================================================
    # STEP 3
    #
    # Seongnam Classification
    # ========================================================

    classified_result = (
        classify_route_candidates(
            matched_result
        )
    )


    # ========================================================
    # STEP 4
    #
    # 현재 AI Coverage
    # ========================================================

    final_result = (
        apply_ai_coverage_to_candidates(
            classified_result
        )
    )


    # ========================================================
    # Summary
    # ========================================================

    pipeline_summary = (
        build_pipeline_summary(
            final_result
        )
    )


    final_result[
        "pipeline_summary"
    ] = (
        pipeline_summary
    )


    # ========================================================
    # Flutter용 Route
    # ========================================================

    frontend_routes = (
        build_frontend_routes(

            final_result=final_result,

            pipeline_summary=pipeline_summary,

            request_id=request_id,

        )
    )


    usable_routes = [

        route

        for route
        in frontend_routes

        if route.get(
            "is_usable"
        )

    ]


    # ========================================================
    # Pipeline 저장
    # ========================================================

    output_file = None


    if save_result:

        final_result[
            "dynamic_request"
        ] = {

            "request_id":
                request_id,

            "origin":
                origin,

            "destination":
                destination,

            "route_cache_hit":
                route_cache_hit,

        }


        output_file = (
            save_dynamic_pipeline_result(

                request_id,

                final_result,

            )
        )


    # ========================================================
    # API 응답
    # ========================================================

    return {

        "status":
            (
                "success"
                if usable_routes
                else
                "no_usable_candidate"
            ),

        "request_id":
            request_id,

        "origin":
            origin,

        "destination":
            destination,

        "candidate_count":
            len(
                frontend_routes
            ),

        "usable_candidate_count":
            len(
                usable_routes
            ),

        "routes":
            frontend_routes,

        # 기존 좌표 Cache가 있으면 TMAP 신규 Route 호출 없음
        "route_cache_hit":
            route_cache_hit,

        "tmap_route_api_called":
            not route_cache_hit,

        "tmap_route_api_call_count":
            (
                0
                if route_cache_hit
                else
                3
            ),

        "pipeline_output_file":
            (
                str(
                    output_file
                )
                if output_file
                else None
            ),

    }