from pathlib import Path
import argparse
import json
import shutil


# ============================================================
# FLOW:MATE
# TMAP / MOCT_LINK Team Share Sample Exporter
#
# 목적
# ------------------------------------------------------------
# 이미 저장되어 있는 Route Pipeline JSON만 읽어서
# 팀원에게 전달할 실제 샘플 패키지를 자동 생성한다.
#
# TMAP API 호출 없음
# POI API 호출 없음
# Route API 호출 없음
#
#
# 생성 대상
# ------------------------------------------------------------
# sample_good.json
# sample_recovered.json
# sample_review.json
# sample_poor.json
# sample_failed.json
# sample_partial_success_od.json
#
# + 원본 JSON 복사
# + NODE/LINK 정보
# + README
# + manifest.json
# ============================================================


# ============================================================
# 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


DEFAULT_INPUT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "team_share"
    / "route_samples"
)


# ============================================================
# NODE / LINK Dataset
# ============================================================

NODE_LINK_DATASET = (
    "[2026-08-12] NODELINKDATA / MOCT_LINK"
)


# ============================================================
# Mapping 정책
# ============================================================

USABLE_QUALITIES = {
    "good",
    "recovered",
    "review",
}


EXCLUDED_QUALITIES = {
    "poor",
    "failed",
}


TARGET_SAMPLE_TYPES = [
    "good",
    "recovered",
    "review",
    "poor",
    "failed",
]


# ============================================================
# JSON Utility
# ============================================================

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


def save_json(
    data,
    path,
):

    path = Path(
        path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# 문자열 정리
# ============================================================

def clean_string(value):

    if value is None:
        return None

    text = (
        str(value)
        .strip()
    )

    if not text:
        return None

    if text.lower() in {
        "none",
        "null",
    }:
        return None

    return text


# ============================================================
# 숫자 변환
# ============================================================

def to_float_or_none(value):

    if value is None:
        return None

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


def to_int_or_none(value):

    if value is None:
        return None

    try:

        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# Batch Wrapper → Pipeline Result
#
# 지원 예시
#
# {
#   "batch_status": "success",
#   "od_id": "OD_000324",
#   "pipeline_result": {...}
# }
#
# 또는 Pipeline JSON 자체
# ============================================================

def extract_pipeline_result(
    raw_data,
    source_path,
):

    if not isinstance(
        raw_data,
        dict,
    ):

        return None


    if isinstance(
        raw_data.get(
            "pipeline_result"
        ),
        dict,
    ):

        pipeline = raw_data[
            "pipeline_result"
        ]

        od_id = (
            clean_string(
                raw_data.get(
                    "od_id"
                )
            )
            or
            source_path.stem
        )

        return {
            "od_id":
                od_id,

            "pipeline":
                pipeline,

            "wrapper":
                raw_data,

            "source_type":
                "batch_od",
        }


    if isinstance(
        raw_data.get(
            "routes"
        ),
        list,
    ):

        od_id = (
            clean_string(
                raw_data.get(
                    "od_id"
                )
            )
            or
            source_path.stem
        )

        return {
            "od_id":
                od_id,

            "pipeline":
                raw_data,

            "wrapper":
                raw_data,

            "source_type":
                "pipeline",
        }


    return None


# ============================================================
# Geometry 추출
#
# 현재/과거 Pipeline 구조 차이가 있더라도
# 가능한 키를 순서대로 확인한다.
# ============================================================

def extract_geometry(route):

    candidates = [
        route.get(
            "geometry"
        ),
        route.get(
            "coordinates"
        ),
        route.get(
            "route_geometry"
        ),
    ]


    for geometry in candidates:

        if isinstance(
            geometry,
            list,
        ):

            return geometry


    return []


# ============================================================
# Mapping 객체 추출
# ============================================================

def extract_mapping(route):

    candidates = [
        route.get(
            "link_mapping_v2"
        ),
        route.get(
            "link_mapping"
        ),
        route.get(
            "mapping"
        ),
    ]


    for mapping in candidates:

        if isinstance(
            mapping,
            dict,
        ):

            return mapping


    return {}


# ============================================================
# Mapping Category 판정
#
# good
# recovered
# review
# poor
# failed
# ============================================================

def get_mapping_category(route):

    mapping = extract_mapping(
        route
    )


    status = (
        clean_string(
            mapping.get(
                "status"
            )
        )
        or
        ""
    ).lower()


    quality = (
        clean_string(
            mapping.get(
                "quality"
            )
        )
        or
        ""
    ).lower()


    # --------------------------------------------------------
    # 명시적 quality 우선
    # --------------------------------------------------------

    if quality in {
        "good",
        "recovered",
        "review",
        "poor",
        "failed",
    }:

        return quality


    # --------------------------------------------------------
    # status가 failed
    # --------------------------------------------------------

    if status in {
        "failed",
        "error",
        "mapping_failed",
    }:

        return "failed"


    # --------------------------------------------------------
    # Route 자체에 Mapping error가 존재하는 경우
    # --------------------------------------------------------

    mapping_error = (
        mapping.get(
            "error"
        )
        or
        mapping.get(
            "mapping_error"
        )
        or
        route.get(
            "mapping_error"
        )
    )


    if mapping_error:

        return "failed"


    # --------------------------------------------------------
    # Mapping 객체 자체가 거의 없는 경우
    # --------------------------------------------------------

    if not mapping:

        return "failed"


    return None


# ============================================================
# 사용 가능 여부
# ============================================================

def is_usable_route(route):

    category = (
        get_mapping_category(
            route
        )
    )

    return (
        category
        in
        USABLE_QUALITIES
    )


# ============================================================
# Location 정보
#
# location_id는 아직 만들지 않는다.
# 원본 POI 정보를 그대로 전달한다.
# ============================================================

def build_location_sample(
    location,
):

    if not isinstance(
        location,
        dict,
    ):

        return {
            "poi_id": None,
            "name": None,
            "address": None,
            "lat": None,
            "lon": None,
        }


    return {

        "poi_id":
            clean_string(
                location.get(
                    "poi_id"
                )
            ),

        "name":
            clean_string(
                location.get(
                    "name"
                )
            ),

        "address":
            clean_string(
                location.get(
                    "address"
                )
            ),

        "lat":
            to_float_or_none(
                location.get(
                    "lat"
                )
            ),

        "lon":
            to_float_or_none(
                location.get(
                    "lon"
                )
            ),

        "source":
            clean_string(
                location.get(
                    "source"
                )
            ),

    }


# ============================================================
# LINK Sequence 표준화
#
# 여기서 만드는 것은 최종 Route Adapter가 아니라
# 팀원 검증용 Sample View다.
#
# 원본:
# sequence
# LINK_ID
# LENGTH
#
# →
#
# LINK_ID
# link_order
# link_length_m
# ============================================================

def build_link_sequence_sample(
    mapping,
):

    raw_sequence = (
        mapping.get(
            "link_sequence",
            []
        )
    )


    if not isinstance(
        raw_sequence,
        list,
    ):

        return []


    links = []


    for index, item in enumerate(
        raw_sequence
    ):

        if not isinstance(
            item,
            dict,
        ):

            continue


        link_id = (
            clean_string(
                item.get(
                    "LINK_ID"
                )
            )
        )


        raw_order = (
            item.get(
                "sequence",
                index,
            )
        )


        try:

            link_order = int(
                raw_order
            )

        except (
            TypeError,
            ValueError,
        ):

            link_order = index


        link_length_m = (
            to_float_or_none(
                item.get(
                    "LENGTH"
                )
            )
        )


        link_sample = {

            "LINK_ID":
                link_id,

            "link_order":
                link_order,

            "link_length_m":
                link_length_m,

        }


        # ----------------------------------------------------
        # 있으면 참고용 원본 필드도 일부 보존
        # ----------------------------------------------------

        optional_fields = {

            "ROAD_NAME":
                item.get(
                    "ROAD_NAME"
                ),

            "ROAD_NO":
                item.get(
                    "ROAD_NO"
                ),

            "MAX_SPD":
                item.get(
                    "MAX_SPD"
                ),

            "F_NODE":
                item.get(
                    "F_NODE"
                ),

            "T_NODE":
                item.get(
                    "T_NODE"
                ),

        }


        for key, value in (
            optional_fields.items()
        ):

            if value is not None:

                link_sample[
                    key
                ] = value


        links.append(
            link_sample
        )


    links.sort(
        key=lambda item:
        item.get(
            "link_order",
            0,
        )
    )


    return links


# ============================================================
# 성남 분류 정보 추출
#
# Pipeline 버전에 따라 필드가 조금 달라도
# 존재하는 정보만 전달한다.
# ============================================================

def build_seongnam_sample(route):

    result = {}


    direct_keys = [
        "inside_link_count",
        "boundary_link_count",
        "outside_link_count",
        "seongnam_distance_m",
        "outside_distance_m",
        "seongnam_distance_ratio_percent",
    ]


    for key in direct_keys:

        if key in route:

            result[
                key
            ] = route[
                key
            ]


    nested_candidates = [
        "seongnam_classification",
        "link_classification",
        "classification",
    ]


    for key in nested_candidates:

        value = (
            route.get(
                key
            )
        )

        if isinstance(
            value,
            dict,
        ):

            result[
                key
            ] = value


    return result


# ============================================================
# Route Sample 생성
# ============================================================

def build_route_sample(
    od_id,
    pipeline,
    route,
    source_file,
):

    mapping = extract_mapping(
        route
    )


    category = (
        get_mapping_category(
            route
        )
    )


    geometry = (
        extract_geometry(
            route
        )
    )


    links = (
        build_link_sequence_sample(
            mapping
        )
    )


    return {

        "sample_info": {

            "od_id":
                od_id,

            "candidate_id":
                route.get(
                    "candidate_id"
                ),

            "mapping_category":
                category,

            "usable":
                (
                    category
                    in
                    USABLE_QUALITIES
                ),

            "source_file":
                source_file.name,

        },


        "dataset": {

            "node_link_dataset":
                NODE_LINK_DATASET,

            "geometry_crs":
                "WGS84",

            "coordinate_order":
                "longitude_latitude",

            "LINK_ID_type":
                "string",

            "distance_unit":
                "m",

            "link_length_unit":
                "m",

            "tmap_eta_unit":
                "sec",

            "link_order_base":
                0,

        },


        "origin":
            build_location_sample(
                pipeline.get(
                    "origin"
                )
            ),


        "destination":
            build_location_sample(
                pipeline.get(
                    "destination"
                )
            ),


        "route": {

            "route_id":
                route.get(
                    "route_id"
                ),

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

            "source":
                route.get(
                    "source",
                    "tmap",
                ),

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

            "geometry_point_count":
                len(
                    geometry
                ),

            "geometry":
                geometry,

        },


        "mapping": {

            "status":
                mapping.get(
                    "status"
                ),

            "quality":
                mapping.get(
                    "quality"
                ),

            "search_mode":
                mapping.get(
                    "search_mode"
                ),

            "coverage_percent":
                mapping.get(
                    "coverage_percent"
                ),

            "connectivity_percent":
                mapping.get(
                    "connectivity_percent"
                ),

            "matched_link_count":
                mapping.get(
                    "matched_link_count"
                ),

            "recovery_used":
                mapping.get(
                    "recovery_used"
                ),

            "recovery_virtual_bridge_count":
                mapping.get(
                    "recovery_virtual_bridge_count"
                ),

            "error":
                (
                    mapping.get(
                        "error"
                    )
                    or
                    mapping.get(
                        "mapping_error"
                    )
                    or
                    route.get(
                        "mapping_error"
                    )
                ),

            "link_sequence":
                links,

        },


        "seongnam":
            build_seongnam_sample(
                route
            ),

    }


# ============================================================
# Partial Success OD Sample
#
# 예:
#
# A good
# B poor
# C recovered
#
# → 최종 usable Route = 2개
# ============================================================

def build_partial_od_sample(
    od_id,
    pipeline,
    routes,
    source_file,
):

    route_samples = []


    usable_candidate_ids = []

    excluded_candidate_ids = []


    for route in routes:

        sample = (
            build_route_sample(

                od_id=od_id,

                pipeline=pipeline,

                route=route,

                source_file=source_file,

            )
        )


        route_samples.append(
            sample
        )


        candidate_id = (
            clean_string(
                route.get(
                    "candidate_id"
                )
            )
        )


        if is_usable_route(
            route
        ):

            usable_candidate_ids.append(
                candidate_id
            )

        else:

            excluded_candidate_ids.append(
                candidate_id
            )


    return {

        "sample_type":
            "partial_success_od",

        "od_id":
            od_id,

        "source_file":
            source_file.name,

        "route_count":
            len(
                routes
            ),

        "usable_route_count":
            len(
                usable_candidate_ids
            ),

        "excluded_route_count":
            len(
                excluded_candidate_ids
            ),

        "usable_candidate_ids":
            usable_candidate_ids,

        "excluded_candidate_ids":
            excluded_candidate_ids,

        "policy": {

            "good":
                "use",

            "recovered":
                "use",

            "review":
                "use",

            "poor":
                "exclude",

            "failed":
                "exclude",

        },

        "routes":
            route_samples,

    }


# ============================================================
# README 생성
# ============================================================

def build_readme(
    found_samples,
    partial_found,
    scanned_files,
    valid_pipeline_files,
):

    found_names = [
        key
        for key, value
        in found_samples.items()
        if value is not None
    ]


    missing_names = [
        key
        for key, value
        in found_samples.items()
        if value is None
    ]


    lines = [

        "# FLOW:MATE TMAP / MOCT_LINK 실제 샘플",
        "",
        "이 폴더는 현재 저장되어 있는 실제 TMAP Route 및 "
        "MOCT_LINK Map Matching 결과에서 자동 추출한 "
        "팀 통합 검증용 샘플입니다.",
        "",
        "최종 Route Adapter 출력이 아니라, "
        "원본 구조와 실제 필드를 먼저 확인하기 위한 자료입니다.",
        "",
        "## 1. 데이터 기준",
        "",
        f"- NODE/LINK Dataset: `{NODE_LINK_DATASET}`",
        "- TMAP Route geometry CRS: `WGS84`",
        "- Geometry 좌표 순서: `[longitude, latitude]`",
        "- LINK_ID: `MOCT_LINK`의 국가표준 LINK_ID",
        "- LINK_ID 자료형: `string`",
        "- TMAP 자체 LINK_ID를 사용하는 구조가 아님",
        "- Distance: meter",
        "- LINK length: meter",
        "- TMAP ETA: second",
        "- link_order: 현재 원본 sequence 기준 0-based",
        "",
        "## 2. Route 후보",
        "",
        "- Route A = searchOption 0 = traffic_optimal",
        "- Route B = searchOption 2 = minimum_time",
        "- Route C = searchOption 10 = shortest",
        "",
        "A/B/C 세 후보가 항상 모두 최종 사용되는 것은 아닙니다.",
        "",
        "## 3. Mapping Quality 정책",
        "",
        "- good → 사용",
        "- recovered → 사용",
        "- review → 사용",
        "- poor → 제외",
        "- failed → 제외",
        "",
        "특정 Route 후보 하나가 제외되어도 OD 전체를 "
        "실패 처리하지 않고, 남아 있는 사용 가능 Route를 계속 사용합니다.",
        "",
        "따라서 최종 Route 후보 개수는 1~3개가 될 수 있습니다.",
        "",
        "## 4. Location ID",
        "",
        "현재 이 샘플에서는 `origin_location_id`와 "
        "`destination_location_id`를 임의로 만들지 않았습니다.",
        "",
        "TMAP `poi_id` 역시 서비스 내부 `location_id`로 "
        "직접 고정하지 않습니다.",
        "",
        "기존 Synthetic Location Master의 `ORG_*** / HOME_***`와 "
        "실제 TMAP POI를 비교한 뒤 Location Adapter / Registry 정책을 "
        "확정할 예정입니다.",
        "",
        "## 5. 샘플 파일",
        "",
    ]


    for name in TARGET_SAMPLE_TYPES:

        if name in found_names:

            lines.append(
                f"- `sample_{name}.json` : 실제 {name} Route 샘플"
            )

        else:

            lines.append(
                f"- `{name}` : 현재 저장 데이터에서 샘플을 찾지 못함"
            )


    if partial_found:

        lines.append(
            "- `sample_partial_success_od.json` : "
            "A/B/C 중 일부만 사용 가능한 실제 OD"
        )

    else:

        lines.append(
            "- Partial Success OD : "
            "현재 저장 데이터에서 샘플을 찾지 못함"
        )


    lines.extend([
        "",
        "## 6. Raw Sources",
        "",
        "`raw_sources/`에는 위 샘플 생성에 사용된 원본 Pipeline JSON을 "
        "수정하지 않고 그대로 복사해두었습니다.",
        "",
        "Adapter를 설계할 때 Sample View뿐 아니라 원본 구조도 "
        "함께 확인할 수 있습니다.",
        "",
        "## 7. AI / LightGBM",
        "",
        "현재 이 샘플 패키지의 AI Coverage 관련 값은 "
        "최종 LightGBM Prediction 계약으로 사용하지 않습니다.",
        "",
        "최종 Predictor 패키지를 받은 뒤 별도 "
        "`TrafficPrediction` Adapter를 구성할 예정입니다.",
        "",
        "## 8. Scan 정보",
        "",
        f"- 스캔한 JSON 파일 수: {scanned_files}",
        f"- 유효 Pipeline JSON 수: {valid_pipeline_files}",
        "",
    ])


    if missing_names:

        lines.extend([
            "## 9. 현재 찾지 못한 Mapping 샘플",
            "",
        ])

        for name in missing_names:

            lines.append(
                f"- {name}"
            )


    return "\n".join(
        lines
    )


# ============================================================
# Main Export
# ============================================================

def export_samples(
    input_dir,
    output_dir,
):

    input_dir = Path(
        input_dir
    )


    output_dir = Path(
        output_dir
    )


    if not input_dir.exists():

        raise FileNotFoundError(
            "입력 폴더를 찾을 수 없습니다:\n"
            f"{input_dir}"
        )


    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    raw_output_dir = (
        output_dir
        / "raw_sources"
    )


    raw_output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    # ========================================================
    # 찾은 Quality Sample
    # ========================================================

    found_samples = {

        "good":
            None,

        "recovered":
            None,

        "review":
            None,

        "poor":
            None,

        "failed":
            None,

    }


    partial_success = None

    partial_success_fallback = None


    scanned_files = 0

    valid_pipeline_files = 0


    # ========================================================
    # 모든 저장 JSON Scan
    # ========================================================

    json_files = sorted(
        input_dir.rglob(
            "*.json"
        )
    )


    for source_path in json_files:

        scanned_files += 1


        try:

            raw_data = (
                load_json(
                    source_path
                )
            )

        except Exception:

            continue


        extracted = (
            extract_pipeline_result(
                raw_data,
                source_path,
            )
        )


        if extracted is None:

            continue


        pipeline = (
            extracted[
                "pipeline"
            ]
        )


        routes = (
            pipeline.get(
                "routes",
                []
            )
        )


        if not isinstance(
            routes,
            list,
        ):

            continue


        if not routes:

            continue


        valid_pipeline_files += 1


        od_id = (
            extracted[
                "od_id"
            ]
        )


        # ====================================================
        # Route 단위 Quality 샘플 탐색
        # ====================================================

        for route in routes:

            if not isinstance(
                route,
                dict,
            ):

                continue


            category = (
                get_mapping_category(
                    route
                )
            )


            if (
                category
                in
                found_samples
                and
                found_samples[
                    category
                ]
                is None
            ):

                found_samples[
                    category
                ] = {

                    "source_path":
                        source_path,

                    "od_id":
                        od_id,

                    "pipeline":
                        pipeline,

                    "route":
                        route,

                }


        # ====================================================
        # Partial Success OD 탐색
        #
        # 사용 가능 Route가 1개 이상 존재하면서
        # 제외 Route도 1개 이상 존재
        # ====================================================

        usable_count = sum(

            1

            for route
            in routes

            if (
                isinstance(
                    route,
                    dict,
                )
                and
                is_usable_route(
                    route
                )
            )

        )


        excluded_count = (
            len(
                routes
            )
            -
            usable_count
        )


        if (
            usable_count >= 1
            and
            excluded_count >= 1
        ):

            candidate_ids = {

                clean_string(
                    route.get(
                        "candidate_id"
                    )
                )

                for route
                in routes

                if isinstance(
                    route,
                    dict,
                )

            }


            # ------------------------------------------------
            # 가장 좋은 예:
            # A/B/C 세 후보가 모두 있고 그중 일부 제외
            # ------------------------------------------------

            if (
                partial_success
                is None
                and
                {
                    "A",
                    "B",
                    "C",
                }.issubset(
                    candidate_ids
                )
            ):

                partial_success = {

                    "source_path":
                        source_path,

                    "od_id":
                        od_id,

                    "pipeline":
                        pipeline,

                    "routes":
                        routes,

                }


            # ------------------------------------------------
            # A/B/C 완전체가 없어도 fallback 후보 보관
            # ------------------------------------------------

            if (
                partial_success_fallback
                is None
            ):

                partial_success_fallback = {

                    "source_path":
                        source_path,

                    "od_id":
                        od_id,

                    "pipeline":
                        pipeline,

                    "routes":
                        routes,

                }


        # ====================================================
        # 필요한 샘플을 전부 찾았으면 계속 스캔할 필요가 없음
        #
        # 단 partial도 확보되어야 종료
        # ====================================================

        all_quality_found = all(

            value is not None

            for value
            in found_samples.values()

        )


        if (
            all_quality_found
            and
            partial_success
            is not None
        ):

            break


    # ========================================================
    # 정확한 A/B/C partial이 없으면 fallback 사용
    # ========================================================

    if partial_success is None:

        partial_success = (
            partial_success_fallback
        )


    # ========================================================
    # Quality Sample 저장
    # ========================================================

    copied_raw_sources = set()


    manifest_samples = {}


    for category, info in (
        found_samples.items()
    ):

        if info is None:

            manifest_samples[
                category
            ] = {

                "found":
                    False,

                "file":
                    None,

            }

            continue


        output_file = (

            output_dir

            /

            f"sample_{category}.json"

        )


        sample = (
            build_route_sample(

                od_id=info[
                    "od_id"
                ],

                pipeline=info[
                    "pipeline"
                ],

                route=info[
                    "route"
                ],

                source_file=info[
                    "source_path"
                ],

            )
        )


        save_json(
            sample,
            output_file,
        )


        manifest_samples[
            category
        ] = {

            "found":
                True,

            "file":
                output_file.name,

            "od_id":
                info[
                    "od_id"
                ],

            "candidate_id":
                info[
                    "route"
                ].get(
                    "candidate_id"
                ),

            "source_file":
                info[
                    "source_path"
                ].name,

        }


        copied_raw_sources.add(
            info[
                "source_path"
            ]
        )


    # ========================================================
    # Partial Success 저장
    # ========================================================

    partial_manifest = {

        "found":
            False,

        "file":
            None,

    }


    if partial_success is not None:

        partial_output = (

            output_dir

            /

            "sample_partial_success_od.json"

        )


        partial_sample = (
            build_partial_od_sample(

                od_id=partial_success[
                    "od_id"
                ],

                pipeline=partial_success[
                    "pipeline"
                ],

                routes=partial_success[
                    "routes"
                ],

                source_file=partial_success[
                    "source_path"
                ],

            )
        )


        save_json(
            partial_sample,
            partial_output,
        )


        partial_manifest = {

            "found":
                True,

            "file":
                partial_output.name,

            "od_id":
                partial_success[
                    "od_id"
                ],

            "source_file":
                partial_success[
                    "source_path"
                ].name,

            "usable_route_count":
                partial_sample[
                    "usable_route_count"
                ],

            "excluded_route_count":
                partial_sample[
                    "excluded_route_count"
                ],

        }


        copied_raw_sources.add(
            partial_success[
                "source_path"
            ]
        )


    # ========================================================
    # Raw Source 원본 그대로 복사
    # ========================================================

    for source_path in (
        copied_raw_sources
    ):

        destination = (

            raw_output_dir

            /

            source_path.name

        )


        shutil.copy2(
            source_path,
            destination,
        )


    # ========================================================
    # NODE / LINK 정보
    # ========================================================

    node_link_info = {

        "dataset":
            NODE_LINK_DATASET,

        "link_table":
            "MOCT_LINK",

        "LINK_ID_type":
            "string",

        "geometry_source":
            "TMAP automobile route",

        "geometry_crs":
            "WGS84",

        "coordinate_order":
            [
                "longitude",
                "latitude",
            ],

        "distance_unit":
            "m",

        "link_length_unit":
            "m",

        "tmap_eta_unit":
            "sec",

        "link_order_base":
            0,

        "important_note":
            (
                "LINK_ID는 TMAP 자체 LINK_ID가 아니라 "
                "TMAP Route geometry를 MOCT_LINK에 "
                "Map Matching하여 얻은 국가표준 LINK_ID입니다."
            ),

        "route_candidates": {

            "A": {
                "search_option":
                    "0",
                "name":
                    "traffic_optimal",
            },

            "B": {
                "search_option":
                    "2",
                "name":
                    "minimum_time",
            },

            "C": {
                "search_option":
                    "10",
                "name":
                    "shortest",
            },

        },

        "mapping_policy": {

            "good":
                "use",

            "recovered":
                "use",

            "review":
                "use",

            "poor":
                "exclude",

            "failed":
                "exclude",

        },

        "location_id_policy": {

            "status":
                "not_finalized",

            "tmap_poi_id_is_internal_location_id":
                False,

            "existing_synthetic_ids":
                [
                    "ORG_***",
                    "HOME_***",
                ],

            "next_step":
                (
                    "실제 TMAP POI 샘플과 기존 "
                    "Synthetic Location Master를 비교한 뒤 "
                    "Location Adapter / Registry 규칙 확정"
                ),

        },

    }


    save_json(

        node_link_info,

        output_dir
        / "node_link_info.json",

    )


    # ========================================================
    # Manifest
    # ========================================================

    manifest = {

        "package":
            "FLOW:MATE TMAP_MOCT_LINK_ROUTE_SAMPLES",

        "node_link_dataset":
            NODE_LINK_DATASET,

        "input_directory":
            str(
                input_dir
            ),

        "scanned_json_files":
            scanned_files,

        "valid_pipeline_files":
            valid_pipeline_files,

        "samples":
            manifest_samples,

        "partial_success_od":
            partial_manifest,

        "raw_source_count":
            len(
                copied_raw_sources
            ),

    }


    save_json(

        manifest,

        output_dir
        / "manifest.json",

    )


    # ========================================================
    # README
    # ========================================================

    readme_text = (
        build_readme(

            found_samples=
                found_samples,

            partial_found=(
                partial_success
                is not None
            ),

            scanned_files=
                scanned_files,

            valid_pipeline_files=
                valid_pipeline_files,

        )
    )


    with open(

        output_dir
        / "README.md",

        "w",

        encoding="utf-8",

    ) as file:

        file.write(
            readme_text
        )


    return manifest


# ============================================================
# CLI
# ============================================================

def main():

    parser = (
        argparse.ArgumentParser(

            description=(
                "저장된 실제 TMAP/MOCT_LINK "
                "Pipeline 결과에서 팀 공유용 샘플 자동 생성"
            )

        )
    )


    parser.add_argument(

        "--input-dir",

        default=str(
            DEFAULT_INPUT_DIR
        ),

        help=(
            "OD Pipeline JSON 폴더"
        ),

    )


    parser.add_argument(

        "--output-dir",

        default=str(
            DEFAULT_OUTPUT_DIR
        ),

        help=(
            "샘플 출력 폴더"
        ),

    )


    args = (
        parser.parse_args()
    )


    print()

    print(
        "=========================================="
    )

    print(
        "FLOW:MATE Sample Exporter"
    )

    print(
        "=========================================="
    )

    print()

    print(
        "입력 폴더:"
    )

    print(
        args.input_dir
    )

    print()

    print(
        "출력 폴더:"
    )

    print(
        args.output_dir
    )

    print()


    manifest = (
        export_samples(

            input_dir=
                args.input_dir,

            output_dir=
                args.output_dir,

        )
    )


    print(
        "------------------------------------------"
    )

    print(
        "스캔 완료"
    )

    print(
        "------------------------------------------"
    )


    print(
        "스캔 JSON:",
        manifest[
            "scanned_json_files"
        ],
    )


    print(
        "유효 Pipeline:",
        manifest[
            "valid_pipeline_files"
        ],
    )


    print()


    print(
        "[Mapping Sample]"
    )


    for category in (
        TARGET_SAMPLE_TYPES
    ):

        info = (
            manifest[
                "samples"
            ][
                category
            ]
        )


        if info[
            "found"
        ]:

            print(
                f"  {category:10s}"
                f" -> FOUND "
                f"({info['od_id']} / "
                f"Route {info['candidate_id']})"
            )

        else:

            print(
                f"  {category:10s}"
                " -> NOT FOUND"
            )


    print()


    partial = (
        manifest[
            "partial_success_od"
        ]
    )


    if partial[
        "found"
    ]:

        print(
            "Partial Success OD -> FOUND"
        )

        print(
            "  OD:",
            partial[
                "od_id"
            ],
        )

        print(
            "  usable:",
            partial[
                "usable_route_count"
            ],
        )

        print(
            "  excluded:",
            partial[
                "excluded_route_count"
            ],
        )

    else:

        print(
            "Partial Success OD -> NOT FOUND"
        )


    print()

    print(
        "=========================================="
    )

    print(
        "샘플 패키지 생성 완료"
    )

    print(
        "=========================================="
    )

    print(
        DEFAULT_OUTPUT_DIR
        if args.output_dir
        == str(
            DEFAULT_OUTPUT_DIR
        )
        else args.output_dir
    )

    print()


if __name__ == "__main__":

    main()