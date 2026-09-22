from pathlib import Path
from collections import Counter
import argparse
import csv
import hashlib
import json


# ============================================================
# FLOW:MATE
# Route Adapter v2
#
# TMAP + MOCT_LINK Pipeline
# →
# 교통수요/ETA 모듈 Route / RouteLink 계약
#
#
# Core Route
# ------------------------------------------------------------
# Route
# - route_id
# - origin_location_id
# - destination_location_id
# - links
#
# RouteLink
# - LINK_ID
# - link_order
# - link_length_m
#
#
# Side Metadata
# ------------------------------------------------------------
# - TMAP Route 원본 거리
# - Mapping status / quality
# - coverage / connectivity
# - residual distance
# - broken connection
# - recovery
# - virtual bridge
# - 성남 내부/외부
# - NODE/LINK dataset
#
#
# 중요
# ------------------------------------------------------------
# 원본 Pipeline은 절대 수정하지 않는다.
# LINK_ID는 dedup하지 않는다.
# usable 여부는 quality 기준으로 판정한다.
# ============================================================


# ============================================================
# 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


# ============================================================
# 기본 입력 데이터
# ============================================================

UNIQUE_OD_SUMMARY_PATH = (
    ROOT
    / "data"
    / "generated"
    / "unique_od_summary.csv"
)


# ============================================================
# 출력
# ============================================================

DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "adapter_exports"
)


DEFAULT_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# NODE / LINK Version
# ============================================================

NODE_LINK_DATASET = (
    "[2026-08-12] NODELINKDATA / MOCT_LINK"
)


# ============================================================
# Mapping Quality 정책
# ============================================================

USABLE_MAPPING_QUALITIES = {
    "good",
    "recovered",
    "review",
}


EXCLUDED_MAPPING_QUALITIES = {
    "poor",
    "failed",
}


# ============================================================
# Utility
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


def round_or_none(
    value,
    digits=2,
):

    number = to_float_or_none(
        value
    )

    if number is None:
        return None

    return round(
        number,
        digits,
    )


# ============================================================
# JSON
# ============================================================

def load_json(path):

    path = Path(
        path
    )

    if not path.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다:\n{path}"
        )

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
# Unique OD Summary
#
# od_id
# origin_location_id
# origin_name
# destination_location_id
# destination_name
# ...
# ============================================================

def load_unique_od_lookup(
    path=UNIQUE_OD_SUMMARY_PATH,
):

    path = Path(
        path
    )

    if not path.exists():
        return {}

    lookup = {}

    with open(
        path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            od_id = clean_string(
                row.get(
                    "od_id"
                )
            )

            if od_id is None:
                continue

            lookup[
                od_id
            ] = {

                "od_id":
                    od_id,

                "origin_location_id":
                    clean_string(
                        row.get(
                            "origin_location_id"
                        )
                    ),

                "origin_name":
                    clean_string(
                        row.get(
                            "origin_name"
                        )
                    ),

                "destination_location_id":
                    clean_string(
                        row.get(
                            "destination_location_id"
                        )
                    ),

                "destination_name":
                    clean_string(
                        row.get(
                            "destination_name"
                        )
                    ),

                "destination_region":
                    clean_string(
                        row.get(
                            "destination_region"
                        )
                    ),

                "user_count":
                    to_int_or_none(
                        row.get(
                            "user_count"
                        )
                    ),

            }

    return lookup


# ============================================================
# Pipeline 구조 해제
#
# Batch:
#
# {
#   od_id,
#   pipeline_result: {...}
# }
#
# Dynamic:
#
# {
#   dynamic_request: {
#       request_id
#   },
#   routes: [...]
# }
# ============================================================

def extract_pipeline(
    raw_data,
):

    if not isinstance(
        raw_data,
        dict,
    ):
        raise ValueError(
            "입력 JSON 최상위가 object가 아닙니다."
        )

    # --------------------------------------------------------
    # Batch OD
    # --------------------------------------------------------

    if isinstance(
        raw_data.get(
            "pipeline_result"
        ),
        dict,
    ):

        return {

            "source_type":
                "batch_od",

            "source_id":
                clean_string(
                    raw_data.get(
                        "od_id"
                    )
                ),

            "wrapper":
                raw_data,

            "pipeline":
                raw_data[
                    "pipeline_result"
                ],

        }

    # --------------------------------------------------------
    # Dynamic
    # --------------------------------------------------------

    dynamic_request = (
        raw_data.get(
            "dynamic_request"
        )
    )

    if isinstance(
        dynamic_request,
        dict,
    ):

        return {

            "source_type":
                "dynamic",

            "source_id":
                clean_string(
                    dynamic_request.get(
                        "request_id"
                    )
                ),

            "wrapper":
                raw_data,

            "pipeline":
                raw_data,

        }

    # --------------------------------------------------------
    # Generic Pipeline
    # --------------------------------------------------------

    if isinstance(
        raw_data.get(
            "routes"
        ),
        list,
    ):

        return {

            "source_type":
                "pipeline",

            "source_id":
                clean_string(
                    raw_data.get(
                        "od_id"
                    )
                    or
                    raw_data.get(
                        "request_id"
                    )
                ),

            "wrapper":
                raw_data,

            "pipeline":
                raw_data,

        }

    raise ValueError(
        "지원하지 않는 Pipeline JSON 구조입니다."
    )


# ============================================================
# Location Metadata
# ============================================================

def normalize_location_metadata(
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
            "source": None,
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
# 좌표 기반 Source ID fallback
#
# Dynamic Route에서 request_id가 없을 경우만 사용
# ============================================================

def build_coordinate_source_id(
    origin,
    destination,
):

    parts = [

        str(
            origin.get(
                "lat"
            )
        ),

        str(
            origin.get(
                "lon"
            )
        ),

        str(
            destination.get(
                "lat"
            )
        ),

        str(
            destination.get(
                "lon"
            )
        ),

    ]

    raw = "|".join(
        parts
    )

    digest = (
        hashlib
        .sha256(
            raw.encode(
                "utf-8"
            )
        )
        .hexdigest()[
            :16
        ]
    )

    return (
        f"DYN_{digest}"
    )


# ============================================================
# Location ID Resolve
#
# 우선순위:
#
# 1. CLI override
# 2. unique_od_summary.csv
# 3. unresolved
#
#
# TMAP poi_id를 내부 location_id로 사용하지 않는다.
# ============================================================

def resolve_location_ids(
    source_id,
    source_type,
    od_lookup,
    origin_location_id_override=None,
    destination_location_id_override=None,
):

    origin_id = clean_string(
        origin_location_id_override
    )

    destination_id = clean_string(
        destination_location_id_override
    )

    source = None


    # --------------------------------------------------------
    # 명시적 override
    # --------------------------------------------------------

    if (
        origin_id is not None
        and
        destination_id is not None
    ):

        return {

            "resolved":
                True,

            "origin_location_id":
                origin_id,

            "destination_location_id":
                destination_id,

            "resolution_source":
                "explicit_override",

            "od_metadata":
                None,

        }


    # --------------------------------------------------------
    # Synthetic OD
    # --------------------------------------------------------

    if (
        source_type
        == "batch_od"
        and
        source_id
        in
        od_lookup
    ):

        od = (
            od_lookup[
                source_id
            ]
        )

        origin_id = (
            origin_id
            or
            od.get(
                "origin_location_id"
            )
        )

        destination_id = (
            destination_id
            or
            od.get(
                "destination_location_id"
            )
        )

        source = (
            "unique_od_summary"
        )

        return {

            "resolved":
                (
                    origin_id
                    is not None
                    and
                    destination_id
                    is not None
                ),

            "origin_location_id":
                origin_id,

            "destination_location_id":
                destination_id,

            "resolution_source":
                source,

            "od_metadata":
                od,

        }


    # --------------------------------------------------------
    # Dynamic POI는 아직 canonical location registry 미확정
    # --------------------------------------------------------

    return {

        "resolved":
            False,

        "origin_location_id":
            origin_id,

        "destination_location_id":
            destination_id,

        "resolution_source":
            None,

        "od_metadata":
            None,

    }


# ============================================================
# Mapping
# ============================================================

def extract_mapping(
    route,
):

    for key in (
        "link_mapping_v2",
        "link_mapping",
        "mapping",
    ):

        value = (
            route.get(
                key
            )
        )

        if isinstance(
            value,
            dict,
        ):
            return value

    return {}


# ============================================================
# Quality
#
# status=mapped가 아니라 quality를 기준으로 판정
# ============================================================

def get_mapping_quality(
    mapping,
):

    quality = clean_string(
        mapping.get(
            "quality"
        )
    )

    if quality is None:
        return None

    return (
        quality
        .lower()
    )


def is_usable_quality(
    mapping,
):

    return (
        get_mapping_quality(
            mapping
        )
        in
        USABLE_MAPPING_QUALITIES
    )


# ============================================================
# RouteLink
#
# 절대 LINK_ID dedup 하지 않는다.
# ============================================================

def adapt_route_links(
    mapping,
):

    raw_links = (
        mapping.get(
            "link_sequence",
            []
        )
    )

    if not isinstance(
        raw_links,
        list,
    ):
        return []


    result = []


    for index, item in enumerate(
        raw_links
    ):

        if not isinstance(
            item,
            dict,
        ):
            continue


        link_id = clean_string(
            item.get(
                "LINK_ID"
            )
        )

        if link_id is None:

            raise ValueError(
                "LINK_ID가 없는 RouteLink가 있습니다. "
                f"index={index}"
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


        if link_length_m is None:

            raise ValueError(
                "LINK LENGTH가 없습니다. "
                f"LINK_ID={link_id}"
            )


        if link_length_m < 0:

            raise ValueError(
                "LINK LENGTH가 음수입니다. "
                f"LINK_ID={link_id}"
            )


        result.append({

            "LINK_ID":
                str(
                    link_id
                ),

            "link_order":
                link_order,

            "link_length_m":
                round(
                    link_length_m,
                    2,
                ),

        })


    # --------------------------------------------------------
    # Route 진행순서 유지
    # --------------------------------------------------------

    result.sort(
        key=lambda row:
        row[
            "link_order"
        ]
    )


    return result


# ============================================================
# Duplicate LINK 검사
#
# 정보만 기록.
# 절대 dedup 하지 않는다.
# ============================================================

def analyze_duplicate_links(
    route_links,
):

    counter = Counter(

        item[
            "LINK_ID"
        ]

        for item
        in route_links

    )


    duplicates = {

        link_id:
            count

        for link_id, count
        in counter.items()

        if count > 1

    }


    return {

        "has_duplicate_link_ids":
            bool(
                duplicates
            ),

        "duplicate_link_id_count":
            len(
                duplicates
            ),

        "duplicate_occurrences":
            duplicates,

    }


# ============================================================
# Virtual Bridge 총 길이
#
# 현재 raw 구조의 길이 필드가 존재하면 합산.
# 없으면 None.
# ============================================================

def calculate_virtual_bridge_length(
    virtual_bridges,
):

    if not isinstance(
        virtual_bridges,
        list,
    ):
        return None


    total = 0.0

    found = False


    for bridge in virtual_bridges:

        if not isinstance(
            bridge,
            dict,
        ):
            continue


        length = None


        for key in (
            "length_m",
            "bridge_length_m",
            "distance_m",
            "length",
        ):

            length = to_float_or_none(
                bridge.get(
                    key
                )
            )

            if length is not None:
                break


        if length is not None:

            total += length

            found = True


    if not found:
        return None


    return round(
        total,
        2,
    )


# ============================================================
# Residual / Unmapped Distance
#
# 명시적인 unmapped_distance_m이 있으면 사용.
#
# 없으면:
#
# tmap_geometry_length_m
# × (1 - coverage_percent / 100)
#
# 로 추정.
#
# 이 값은 정확한 물리적 gap 길이가 아니라
# coverage 기반 추정치임을 metadata에 명시한다.
# ============================================================

def calculate_residual_distance(
    mapping,
):

    explicit_keys = (
        "unmapped_distance_m",
        "residual_distance_m",
    )


    for key in explicit_keys:

        value = to_float_or_none(
            mapping.get(
                key
            )
        )

        if value is not None:

            return {

                "residual_distance_m":
                    round(
                        max(
                            0.0,
                            value,
                        ),
                        2,
                    ),

                "residual_distance_method":
                    f"mapping_field:{key}",

            }


    tmap_geometry_length_m = (
        to_float_or_none(
            mapping.get(
                "tmap_geometry_length_m"
            )
        )
    )


    coverage_percent = (
        to_float_or_none(
            mapping.get(
                "coverage_percent"
            )
        )
    )


    if (
        tmap_geometry_length_m
        is not None
        and
        coverage_percent
        is not None
    ):

        residual = (

            tmap_geometry_length_m

            *

            max(
                0.0,
                1.0
                -
                (
                    coverage_percent
                    /
                    100.0
                ),
            )

        )


        return {

            "residual_distance_m":
                round(
                    residual,
                    2,
                ),

            "residual_distance_method":
                "coverage_estimate",

        }


    return {

        "residual_distance_m":
            None,

        "residual_distance_method":
            None,

    }


# ============================================================
# 성남 Classification Metadata
# ============================================================

def build_seongnam_metadata(
    route,
):

    classification = (
        route.get(
            "seongnam_classification"
        )
    )


    if not isinstance(
        classification,
        dict,
    ):

        classification = (
            route.get(
                "link_classification"
            )
        )


    if not isinstance(
        classification,
        dict,
    ):

        return None


    raw_links = (
        classification.get(
            "link_sequence",
            []
        )
    )


    link_classification = []


    if isinstance(
        raw_links,
        list,
    ):

        for index, item in enumerate(
            raw_links
        ):

            if not isinstance(
                item,
                dict,
            ):
                continue


            link_classification.append({

                "LINK_ID":
                    clean_string(
                        item.get(
                            "LINK_ID"
                        )
                    ),

                "link_order":
                    to_int_or_none(
                        item.get(
                            "sequence",
                            index,
                        )
                    ),

                "inside_seongnam":
                    item.get(
                        "inside_seongnam"
                    ),

                "seongnam_position":
                    clean_string(
                        item.get(
                            "seongnam_position"
                        )
                    ),

                "seongnam_overlap_m":
                    round_or_none(
                        item.get(
                            "seongnam_overlap_m"
                        )
                    ),

                "outside_length_m":
                    round_or_none(
                        item.get(
                            "outside_length_m"
                        )
                    ),

            })


    return {

        "status":
            classification.get(
                "status"
            ),

        "total_link_count":
            classification.get(
                "total_link_count"
            ),

        "inside_link_count":
            classification.get(
                "inside_link_count"
            ),

        "boundary_crossing_link_count":
            classification.get(
                "boundary_crossing_link_count"
            ),

        "outside_link_count":
            classification.get(
                "outside_link_count"
            ),

        "seongnam_intersecting_link_count":
            classification.get(
                "seongnam_intersecting_link_count"
            ),

        "seongnam_distance_m":
            round_or_none(
                classification.get(
                    "seongnam_distance_m"
                )
            ),

        "outside_distance_m":
            round_or_none(
                classification.get(
                    "outside_distance_m"
                )
            ),

        "total_classified_distance_m":
            round_or_none(
                classification.get(
                    "total_classified_distance_m"
                )
            ),

        "seongnam_distance_ratio_percent":
            round_or_none(
                classification.get(
                    "seongnam_distance_ratio_percent"
                )
            ),

        "link_classification":
            link_classification,

    }


# ============================================================
# Mapping Metadata
# ============================================================

def build_mapping_metadata(
    route,
    mapping,
    route_links,
):

    virtual_bridges = (
        mapping.get(
            "recovery_virtual_bridges",
            []
        )
    )


    if not isinstance(
        virtual_bridges,
        list,
    ):
        virtual_bridges = []


    mapped_link_length_sum_m = sum(

        item[
            "link_length_m"
        ]

        for item
        in route_links

    )


    residual_info = (
        calculate_residual_distance(
            mapping
        )
    )


    duplicate_info = (
        analyze_duplicate_links(
            route_links
        )
    )


    tmap_route_distance_m = (
        to_float_or_none(
            route.get(
                "total_distance_m"
            )
        )
    )


    tmap_geometry_length_m = (
        to_float_or_none(
            mapping.get(
                "tmap_geometry_length_m"
            )
        )
    )


    matched_geometry_length_m = (
        to_float_or_none(
            mapping.get(
                "matched_geometry_length_m"
            )
        )
    )


    geometry_length_delta_m = None


    if (
        tmap_geometry_length_m
        is not None
        and
        matched_geometry_length_m
        is not None
    ):

        geometry_length_delta_m = round(

            (
                tmap_geometry_length_m
                -
                matched_geometry_length_m
            ),

            2,

        )


    return {

        "mapping_status":
            clean_string(
                mapping.get(
                    "status"
                )
            ),

        "mapping_quality":
            get_mapping_quality(
                mapping
            ),

        "mapping_method":
            clean_string(
                mapping.get(
                    "method"
                )
            ),

        "search_mode":
            clean_string(
                mapping.get(
                    "search_mode"
                )
            ),

        "coverage_percent":
            round_or_none(
                mapping.get(
                    "coverage_percent"
                )
            ),

        "connectivity_percent":
            round_or_none(
                mapping.get(
                    "connectivity_percent"
                )
            ),

        "length_ratio":
            round_or_none(
                mapping.get(
                    "length_ratio"
                ),
                digits=4,
            ),

        "matched_link_count":
            to_int_or_none(
                mapping.get(
                    "matched_link_count"
                )
            ),

        "broken_connections":
            to_int_or_none(
                mapping.get(
                    "broken_connections"
                )
            ),

        # ----------------------------------------------------
        # 거리
        # ----------------------------------------------------

        "tmap_route_distance_m":
            round_or_none(
                tmap_route_distance_m
            ),

        "tmap_geometry_length_m":
            round_or_none(
                tmap_geometry_length_m
            ),

        "matched_geometry_length_m":
            round_or_none(
                matched_geometry_length_m
            ),

        "mapped_link_length_sum_m":
            round(
                mapped_link_length_sum_m,
                2,
            ),

        "geometry_length_delta_m":
            geometry_length_delta_m,

        "residual_distance_m":
            residual_info[
                "residual_distance_m"
            ],

        "residual_distance_method":
            residual_info[
                "residual_distance_method"
            ],

        # ----------------------------------------------------
        # Recovery
        # ----------------------------------------------------

        "recovery_used":
            bool(
                mapping.get(
                    "recovery_used",
                    False,
                )
            ),

        "virtual_bridge_count":
            to_int_or_none(
                mapping.get(
                    "recovery_virtual_bridge_count"
                )
            )
            or
            len(
                virtual_bridges
            ),

        "virtual_bridge_total_length_m":
            calculate_virtual_bridge_length(
                virtual_bridges
            ),

        "virtual_bridges":
            virtual_bridges,

        # ----------------------------------------------------
        # Duplicate LINK
        # ----------------------------------------------------

        **duplicate_info,

    }


# ============================================================
# Failed / Excluded Route Metadata
# ============================================================

def build_excluded_metadata(
    source_id,
    route,
    mapping,
):

    candidate_id = (
        clean_string(
            route.get(
                "candidate_id"
            )
        )
        or
        "UNKNOWN"
    )


    route_id = (
        f"{source_id}_"
        f"{candidate_id}"
    )


    return {

        "route_id":
            route_id,

        "candidate_id":
            candidate_id,

        "mapping_status":
            clean_string(
                mapping.get(
                    "status"
                )
            ),

        "mapping_quality":
            get_mapping_quality(
                mapping
            ),

        "search_mode":
            clean_string(
                mapping.get(
                    "search_mode"
                )
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

        "reason":
            (
                "mapping_quality_not_usable"
            ),

    }


# ============================================================
# Core Adapter
# ============================================================

def adapt_route_result(
    raw_data,
    origin_location_id=None,
    destination_location_id=None,
    allow_unresolved_locations=False,
):

    extracted = (
        extract_pipeline(
            raw_data
        )
    )


    pipeline = (
        extracted[
            "pipeline"
        ]
    )


    source_type = (
        extracted[
            "source_type"
        ]
    )


    source_id = (
        extracted[
            "source_id"
        ]
    )


    origin_metadata = (
        normalize_location_metadata(
            pipeline.get(
                "origin"
            )
        )
    )


    destination_metadata = (
        normalize_location_metadata(
            pipeline.get(
                "destination"
            )
        )
    )


    # ========================================================
    # Source ID fallback
    # ========================================================

    if source_id is None:

        source_id = (
            build_coordinate_source_id(
                origin_metadata,
                destination_metadata,
            )
        )


    # ========================================================
    # Location IDs
    # ========================================================

    od_lookup = (
        load_unique_od_lookup()
    )


    location_resolution = (
        resolve_location_ids(

            source_id=
                source_id,

            source_type=
                source_type,

            od_lookup=
                od_lookup,

            origin_location_id_override=
                origin_location_id,

            destination_location_id_override=
                destination_location_id,

        )
    )


    if (
        not
        location_resolution[
            "resolved"
        ]
        and
        not
        allow_unresolved_locations
    ):

        raise ValueError(
            "origin_location_id / "
            "destination_location_id를 "
            "해결하지 못했습니다. "
            "Dynamic TMAP POI는 아직 "
            "Location Registry 규칙이 확정되지 않았습니다."
        )


    resolved_origin_id = (
        location_resolution[
            "origin_location_id"
        ]
    )


    resolved_destination_id = (
        location_resolution[
            "destination_location_id"
        ]
    )


    # ========================================================
    # Routes
    # ========================================================

    raw_routes = (
        pipeline.get(
            "routes",
            []
        )
    )


    if not isinstance(
        raw_routes,
        list,
    ):

        raise ValueError(
            "routes가 list가 아닙니다."
        )


    routes = []

    route_metadata = {}

    excluded_routes = []


    for index, route in enumerate(
        raw_routes
    ):

        if not isinstance(
            route,
            dict,
        ):
            continue


        candidate_id = (
            clean_string(
                route.get(
                    "candidate_id"
                )
            )
            or
            str(
                index
            )
        )


        route_id = (
            f"{source_id}_"
            f"{candidate_id}"
        )


        mapping = (
            extract_mapping(
                route
            )
        )


        quality = (
            get_mapping_quality(
                mapping
            )
        )


        # ====================================================
        # quality 기반 필터링
        # ====================================================

        if (
            quality
            not in
            USABLE_MAPPING_QUALITIES
        ):

            excluded_routes.append(

                build_excluded_metadata(

                    source_id=
                        source_id,

                    route=
                        route,

                    mapping=
                        mapping,

                )

            )

            continue


        route_links = (
            adapt_route_links(
                mapping
            )
        )


        # quality는 usable인데 LINK가 없으면
        # 데이터 일관성 오류이므로 제외
        if not route_links:

            excluded_routes.append({

                "route_id":
                    route_id,

                "candidate_id":
                    candidate_id,

                "mapping_status":
                    clean_string(
                        mapping.get(
                            "status"
                        )
                    ),

                "mapping_quality":
                    quality,

                "reason":
                    "usable_quality_but_empty_link_sequence",

            })

            continue


        # ====================================================
        # Core Route
        # ====================================================

        routes.append({

            "route_id":
                route_id,

            "origin_location_id":
                resolved_origin_id,

            "destination_location_id":
                resolved_destination_id,

            "links":
                route_links,

        })


        # ====================================================
        # Side Metadata
        # ====================================================

        route_metadata[
            route_id
        ] = {

            "candidate_id":
                candidate_id,

            "route_label":
                clean_string(
                    route.get(
                        "route_label"
                    )
                ),

            "search_option":
                clean_string(
                    route.get(
                        "search_option"
                    )
                ),

            "source":
                clean_string(
                    route.get(
                        "source"
                    )
                )
                or
                "tmap",

            "tmap_eta_sec":
                to_float_or_none(
                    route.get(
                        "tmap_eta_sec"
                    )
                ),

            "tmap_eta_min":
                to_float_or_none(
                    route.get(
                        "tmap_eta_min"
                    )
                ),

            "mapping":
                build_mapping_metadata(

                    route=
                        route,

                    mapping=
                        mapping,

                    route_links=
                        route_links,

                ),

            "seongnam":
                build_seongnam_metadata(
                    route
                ),

        }


    # ========================================================
    # Route 순서
    #
    # 원본 A/B/C 순서를 그대로 유지
    # ========================================================


    # ========================================================
    # 결과 상태
    # ========================================================

    if not routes:

        status = (
            "no_usable_routes"
        )

    elif (
        not
        location_resolution[
            "resolved"
        ]
    ):

        status = (
            "location_unresolved"
        )

    else:

        status = (
            "success"
        )


    # ========================================================
    # 최종 Output
    # ========================================================

    return {

        "schema_version":
            "route_adapter_v2",

        "status":
            status,

        "source_type":
            source_type,

        "source_id":
            source_id,

        # ====================================================
        # 계약 / Version
        # ====================================================

        "contract": {

            "route_id_rule":
                (
                    "{source_id}_{candidate_id}"
                ),

            "usable_mapping_qualities":
                [
                    "good",
                    "recovered",
                    "review",
                ],

            "excluded_mapping_qualities":
                [
                    "poor",
                    "failed",
                ],

            "link_order_base":
                0,

            "LINK_ID_type":
                "string",

            "link_length_unit":
                "m",

            "node_link_dataset":
                NODE_LINK_DATASET,

            "link_deduplication":
                False,

        },

        # ====================================================
        # Location
        # ====================================================

        "location_resolution": {

            "resolved":
                location_resolution[
                    "resolved"
                ],

            "resolution_source":
                location_resolution[
                    "resolution_source"
                ],

            "origin_location_id":
                resolved_origin_id,

            "destination_location_id":
                resolved_destination_id,

            "origin_source_metadata":
                origin_metadata,

            "destination_source_metadata":
                destination_metadata,

            "synthetic_od_metadata":
                location_resolution[
                    "od_metadata"
                ],

        },

        # ====================================================
        # 팀원 ETA/Demand 모듈 입력
        # ====================================================

        "routes":
            routes,

        # ====================================================
        # Side Metadata
        # ====================================================

        "route_metadata":
            route_metadata,

        "excluded_routes":
            excluded_routes,

        # ====================================================
        # Summary
        # ====================================================

        "summary": {

            "input_route_count":
                len(
                    raw_routes
                ),

            "usable_route_count":
                len(
                    routes
                ),

            "excluded_route_count":
                len(
                    excluded_routes
                ),

            "usable_route_ids":
                [
                    route[
                        "route_id"
                    ]
                    for route
                    in routes
                ],

            "excluded_route_ids":
                [
                    route[
                        "route_id"
                    ]
                    for route
                    in excluded_routes
                ],

        },

    }


# ============================================================
# File Adapter
# ============================================================

def adapt_file(
    input_path,
    output_path=None,
    origin_location_id=None,
    destination_location_id=None,
    allow_unresolved_locations=False,
):

    input_path = Path(
        input_path
    )


    raw_data = (
        load_json(
            input_path
        )
    )


    adapted = (
        adapt_route_result(

            raw_data=
                raw_data,

            origin_location_id=
                origin_location_id,

            destination_location_id=
                destination_location_id,

            allow_unresolved_locations=
                allow_unresolved_locations,

        )
    )


    if output_path is None:

        output_path = (

            DEFAULT_OUTPUT_DIR

            /

            (
                f"{input_path.stem}"
                "_route_adapter_v2.json"
            )

        )


    save_json(
        adapted,
        output_path,
    )


    return (
        adapted,
        Path(
            output_path
        ),
    )


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "FLOW:MATE 실제 TMAP/MOCT_LINK "
            "Route 결과를 교통모듈 Route 계약으로 변환"
        )

    )


    parser.add_argument(

        "--input",

        required=True,

        help=(
            "OD Pipeline 또는 Dynamic Pipeline JSON"
        ),

    )


    parser.add_argument(

        "--output",

        default=None,

        help=(
            "출력 JSON 경로"
        ),

    )


    parser.add_argument(

        "--origin-location-id",

        default=None,

        help=(
            "Location Registry 확정 전 "
            "명시적으로 origin ID 지정"
        ),

    )


    parser.add_argument(

        "--destination-location-id",

        default=None,

        help=(
            "Location Registry 확정 전 "
            "명시적으로 destination ID 지정"
        ),

    )


    parser.add_argument(

        "--allow-unresolved-locations",

        action="store_true",

        help=(
            "location_id가 없어도 진단용 "
            "Adapter 결과 생성을 허용"
        ),

    )


    args = parser.parse_args()


    adapted, output_path = (
        adapt_file(

            input_path=
                args.input,

            output_path=
                args.output,

            origin_location_id=
                args.origin_location_id,

            destination_location_id=
                args.destination_location_id,

            allow_unresolved_locations=
                args.allow_unresolved_locations,

        )
    )


    print()

    print(
        "=========================================="
    )

    print(
        "FLOW:MATE Route Adapter v2"
    )

    print(
        "=========================================="
    )


    print(
        "Status:",
        adapted[
            "status"
        ],
    )


    print(
        "Source:",
        adapted[
            "source_id"
        ],
    )


    location = (
        adapted[
            "location_resolution"
        ]
    )


    print(
        "Origin Location ID:",
        location[
            "origin_location_id"
        ],
    )


    print(
        "Destination Location ID:",
        location[
            "destination_location_id"
        ],
    )


    print(
        "Location Source:",
        location[
            "resolution_source"
        ],
    )


    summary = (
        adapted[
            "summary"
        ]
    )


    print()

    print(
        "입력 Route:",
        summary[
            "input_route_count"
        ],
    )


    print(
        "사용 Route:",
        summary[
            "usable_route_count"
        ],
    )


    print(
        "제외 Route:",
        summary[
            "excluded_route_count"
        ],
    )


    print(
        "사용 Route IDs:",
        summary[
            "usable_route_ids"
        ],
    )


    print(
        "제외 Route IDs:",
        summary[
            "excluded_route_ids"
        ],
    )


    print()

    print(
        "저장 완료:"
    )

    print(
        output_path
    )


    print(
        "=========================================="
    )

    print()


if __name__ == "__main__":

    main()