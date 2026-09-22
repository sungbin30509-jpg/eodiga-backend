from pathlib import Path
import json

import pandas as pd


# ============================================================
# FLOW:MATE / 언제가
# Route Integration Dataset Exporter
#
# 목적
# ------------------------------------------------------------
# batch_od_route_pipeline에서 성공한 OD JSON만 읽어서
# 다른 팀 / FastAPI가 쉽게 사용할 수 있는
# 정규화된 CSV 데이터셋을 생성한다.
#
# 출력
# ------------------------------------------------------------
# 1. success_od_manifest.csv
# 2. route_catalog.csv
# 3. route_links.csv
# 4. route_integration_summary.json
#
# 중요
# ------------------------------------------------------------
# - TMAP API를 새로 호출하지 않는다.
# - 기존 성공 JSON만 읽는다.
# - 실패 JSON은 자동 제외한다.
# - 324/325/600 등 개수를 하드코딩하지 않는다.
# - 나중에 600 OD 완성 후 다시 실행하면 자동 확장된다.
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
    / "integration"
)


SUCCESS_OD_FILE = (
    OUTPUT_DIR
    / "success_od_manifest.csv"
)


ROUTE_CATALOG_FILE = (
    OUTPUT_DIR
    / "route_catalog.csv"
)


ROUTE_LINKS_FILE = (
    OUTPUT_DIR
    / "route_links.csv"
)


SUMMARY_FILE = (
    OUTPUT_DIR
    / "route_integration_summary.json"
)


ALLOWED_QUALITIES = {
    "good",
    "recovered",
    "review",
}


# ============================================================
# Utility
# ============================================================

def clean_text(
    value,
    default="",
):

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return str(value).strip()


def normalize_id(
    value,
):

    text = clean_text(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def safe_float(
    value,
    default=None,
):

    try:

        if value is None:
            return default

        if pd.isna(value):
            return default

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


def safe_int(
    value,
    default=0,
):

    try:

        if value is None:
            return default

        return int(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


def safe_bool(
    value,
    default=None,
):

    if isinstance(
        value,
        bool,
    ):
        return value

    text = clean_text(
        value
    ).lower()

    if text in {
        "true",
        "1",
        "yes",
    }:
        return True

    if text in {
        "false",
        "0",
        "no",
    }:
        return False

    return default


# ============================================================
# Route quality
# ============================================================

def get_mapping_quality(
    route,
):

    mapping = (
        route.get(
            "link_mapping_v2",
            {}
        )
        or
        {}
    )

    return clean_text(
        mapping.get(
            "quality"
        )
    ).lower()


def route_is_usable(
    route,
):

    mapping = (
        route.get(
            "link_mapping_v2",
            {}
        )
        or
        {}
    )


    status = clean_text(
        mapping.get(
            "status"
        )
    ).lower()


    quality = clean_text(
        mapping.get(
            "quality"
        )
    ).lower()


    return (
        status == "mapped"
        and
        quality
        in
        ALLOWED_QUALITIES
    )


# ============================================================
# Main
# ============================================================

def export_route_integration_dataset():

    print()
    print(
        "========================================"
    )
    print(
        "FLOW:MATE Route Integration Export"
    )
    print(
        "========================================"
    )


    if not OD_RESULT_DIR.exists():

        raise FileNotFoundError(
            f"OD 결과 폴더가 없습니다.\n"
            f"{OD_RESULT_DIR}"
        )


    files = sorted(
        OD_RESULT_DIR.glob(
            "OD_*.json"
        )
    )


    if not files:

        raise RuntimeError(
            "OD JSON 파일이 없습니다."
        )


    print(
        "전체 OD JSON:",
        len(files),
    )


    success_od_rows = []
    route_rows = []
    link_rows = []


    success_od_count = 0
    failed_od_count = 0

    total_route_count = 0
    mapped_route_count = 0
    usable_route_count = 0
    excluded_quality_route_count = 0


    # ========================================================
    # OD JSON 순회
    # ========================================================

    for file_path in files:

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
                f"⚠️ JSON 읽기 실패: "
                f"{file_path.name} | "
                f"{type(error).__name__}"
            )

            continue


        batch_status = clean_text(
            data.get(
                "batch_status"
            )
        ).lower()


        # ====================================================
        # 실패 OD 제외
        # ====================================================

        if batch_status != "success":

            failed_od_count += 1

            continue


        success_od_count += 1


        od_id = clean_text(
            data.get(
                "od_id"
            )
            or
            file_path.stem
        )


        user_count = safe_int(
            data.get(
                "user_count"
            ),
            0,
        )


        origin = (
            data.get(
                "origin"
            )
            or
            {}
        )


        destination = (
            data.get(
                "destination"
            )
            or
            {}
        )


        pipeline_result = (
            data.get(
                "pipeline_result"
            )
            or
            {}
        )


        routes = (
            pipeline_result.get(
                "routes"
            )
            or
            []
        )


        # ====================================================
        # 성공 OD manifest
        # ====================================================

        success_od_rows.append({

            "od_id":
                od_id,

            "user_count":
                user_count,

            "origin_location_id":
                clean_text(
                    origin.get(
                        "location_id"
                    )
                ),

            "origin_name":
                clean_text(
                    origin.get(
                        "input_name"
                    )
                ),

            "origin_lat":
                safe_float(
                    origin.get(
                        "lat"
                    )
                ),

            "origin_lon":
                safe_float(
                    origin.get(
                        "lon"
                    )
                ),

            "destination_location_id":
                clean_text(
                    destination.get(
                        "location_id"
                    )
                ),

            "destination_name":
                clean_text(
                    destination.get(
                        "input_name"
                    )
                ),

            "destination_region":
                clean_text(
                    destination.get(
                        "region"
                    )
                ),

            "destination_lat":
                safe_float(
                    destination.get(
                        "lat"
                    )
                ),

            "destination_lon":
                safe_float(
                    destination.get(
                        "lon"
                    )
                ),

            "route_candidate_count":
                len(
                    routes
                )
                if isinstance(
                    routes,
                    list,
                )
                else 0,

        })


        if not isinstance(
            routes,
            list,
        ):

            continue


        # ====================================================
        # Route 순회
        # ====================================================

        for route in routes:

            if not isinstance(
                route,
                dict,
            ):

                continue


            total_route_count += 1


            candidate_id = clean_text(
                route.get(
                    "candidate_id"
                )
            ).upper()


            route_id = (
                f"{od_id}_"
                f"{candidate_id}"
            )


            mapping = (
                route.get(
                    "link_mapping_v2",
                    {}
                )
                or
                {}
            )


            mapping_status = clean_text(
                mapping.get(
                    "status"
                )
            ).lower()


            mapping_quality = clean_text(
                mapping.get(
                    "quality"
                )
            ).lower()


            is_mapped = (
                mapping_status
                ==
                "mapped"
            )


            is_usable = (
                route_is_usable(
                    route
                )
            )


            if is_mapped:

                mapped_route_count += 1


            if is_usable:

                usable_route_count += 1


            elif (
                is_mapped
                and
                mapping_quality
                not in
                ALLOWED_QUALITIES
            ):

                excluded_quality_route_count += 1


            classification = (
                route.get(
                    "seongnam_classification",
                    {}
                )
                or
                {}
            )


            coverage = (
                route.get(
                    "ai_coverage",
                    {}
                )
                or
                {}
            )


            # =================================================
            # Route Catalog
            # =================================================

            route_rows.append({

                "route_id":
                    route_id,

                "od_id":
                    od_id,

                "user_count":
                    user_count,

                "candidate_id":
                    candidate_id,

                "route_label":
                    clean_text(
                        route.get(
                            "route_label"
                        )
                    ),

                "search_option":
                    clean_text(
                        route.get(
                            "search_option"
                        )
                    ),

                "total_distance_m":
                    safe_float(
                        route.get(
                            "total_distance_m"
                        )
                    ),

                "tmap_eta_sec":
                    safe_float(
                        route.get(
                            "tmap_eta_sec"
                        )
                    ),

                "tmap_eta_min":
                    safe_float(
                        route.get(
                            "tmap_eta_min"
                        )
                    ),

                "geometry_point_count":
                    safe_int(
                        route.get(
                            "geometry_point_count"
                        )
                    ),

                "mapping_status":
                    mapping_status,

                "mapping_quality":
                    mapping_quality,

                "mapping_search_mode":
                    clean_text(
                        mapping.get(
                            "search_mode"
                        )
                    ),

                "mapping_connectivity_percent":
                    safe_float(
                        mapping.get(
                            "connectivity_percent"
                        )
                    ),

                "mapping_coverage_percent":
                    safe_float(
                        mapping.get(
                            "coverage_percent"
                        )
                    ),

                "mapping_length_ratio":
                    safe_float(
                        mapping.get(
                            "length_ratio"
                        )
                    ),

                "matched_link_count":
                    safe_int(
                        mapping.get(
                            "matched_link_count"
                        )
                    ),

                "is_usable":
                    is_usable,

                "inside_link_count":
                    safe_int(
                        classification.get(
                            "inside_link_count"
                        )
                    ),

                "boundary_crossing_link_count":
                    safe_int(
                        classification.get(
                            "boundary_crossing_link_count"
                        )
                    ),

                "outside_link_count":
                    safe_int(
                        classification.get(
                            "outside_link_count"
                        )
                    ),

                "seongnam_distance_m":
                    safe_float(
                        classification.get(
                            "seongnam_distance_m"
                        )
                    ),

                "outside_distance_m":
                    safe_float(
                        classification.get(
                            "outside_distance_m"
                        )
                    ),

                "seongnam_distance_ratio_percent":
                    safe_float(
                        classification.get(
                            "seongnam_distance_ratio_percent"
                        )
                    ),

                "ai_supported_link_count":
                    safe_int(
                        coverage.get(
                            "ai_supported_link_count"
                        )
                    ),

                "tmap_fallback_link_count":
                    safe_int(
                        coverage.get(
                            "tmap_fallback_link_count"
                        )
                    ),

                "outside_seongnam_link_count":
                    safe_int(
                        coverage.get(
                            "outside_seongnam_link_count"
                        )
                    ),

                "ai_link_coverage_percent":
                    safe_float(
                        coverage.get(
                            "link_count_coverage_percent"
                        )
                    ),

                "ai_distance_coverage_percent":
                    safe_float(
                        coverage.get(
                            "distance_coverage_percent"
                        )
                    ),

                "model_supported_link_universe_count":
                    safe_int(
                        coverage.get(
                            "model_supported_link_universe_count"
                        )
                    ),

            })


            # =================================================
            # LINK export는 mapped route만
            # =================================================

            if not is_mapped:

                continue


            link_sequence = (
                coverage.get(
                    "link_sequence"
                )
                or
                classification.get(
                    "link_sequence"
                )
                or
                mapping.get(
                    "link_sequence"
                )
                or
                []
            )


            if not isinstance(
                link_sequence,
                list,
            ):

                continue


            # =================================================
            # Route Links
            # =================================================

            for index, link in enumerate(
                link_sequence
            ):

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


                link_rows.append({

                    "route_id":
                        route_id,

                    "od_id":
                        od_id,

                    "user_count":
                        user_count,

                    "candidate_id":
                        candidate_id,

                    "link_order":
                        safe_int(
                            link.get(
                                "sequence"
                            ),
                            index,
                        ),

                    "link_id":
                        link_id,

                    "f_node":
                        normalize_id(
                            link.get(
                                "F_NODE"
                            )
                        ),

                    "t_node":
                        normalize_id(
                            link.get(
                                "T_NODE"
                            )
                        ),

                    "road_name":
                        clean_text(
                            link.get(
                                "ROAD_NAME"
                            )
                        ),

                    "link_length_m":
                        safe_float(
                            link.get(
                                "LENGTH"
                            )
                        ),

                    "max_speed_kmh":
                        safe_float(
                            link.get(
                                "MAX_SPD"
                            )
                        ),

                    "route_position_m":
                        safe_float(
                            link.get(
                                "route_position_m"
                            )
                        ),

                    "inside_seongnam":
                        safe_bool(
                            link.get(
                                "inside_seongnam"
                            )
                        ),

                    "seongnam_position":
                        clean_text(
                            link.get(
                                "seongnam_position"
                            )
                        ),

                    "seongnam_overlap_m":
                        safe_float(
                            link.get(
                                "seongnam_overlap_m"
                            )
                        ),

                    "seongnam_overlap_ratio":
                        safe_float(
                            link.get(
                                "seongnam_overlap_ratio"
                            )
                        ),

                    "outside_length_m":
                        safe_float(
                            link.get(
                                "outside_length_m"
                            )
                        ),

                    "ai_supported":
                        safe_bool(
                            link.get(
                                "ai_supported"
                            )
                        ),

                    "traffic_source":
                        clean_text(
                            link.get(
                                "traffic_source"
                            )
                        ),

                    "ai_covered_distance_m":
                        safe_float(
                            link.get(
                                "ai_covered_distance_m"
                            )
                        ),

                    "fallback_distance_m":
                        safe_float(
                            link.get(
                                "fallback_distance_m"
                            )
                        ),

                    "mapping_quality":
                        mapping_quality,

                    "route_is_usable":
                        is_usable,

                })


    # ========================================================
    # DataFrames
    # ========================================================

    success_df = pd.DataFrame(
        success_od_rows
    )

    route_df = pd.DataFrame(
        route_rows
    )

    link_df = pd.DataFrame(
        link_rows
    )


    # ========================================================
    # Validation
    # ========================================================

    if not success_df.empty:

        duplicate_od = (
            success_df[
                "od_id"
            ]
            .duplicated()
            .sum()
        )

        if duplicate_od > 0:

            raise RuntimeError(
                f"OD 중복 "
                f"{duplicate_od}개 발견"
            )


    if not route_df.empty:

        duplicate_routes = (
            route_df[
                "route_id"
            ]
            .duplicated()
            .sum()
        )

        if duplicate_routes > 0:

            raise RuntimeError(
                f"Route ID 중복 "
                f"{duplicate_routes}개 발견"
            )


    # ========================================================
    # Sorting
    # ========================================================

    if not success_df.empty:

        success_df = (
            success_df
            .sort_values(
                "od_id"
            )
            .reset_index(
                drop=True
            )
        )


    if not route_df.empty:

        route_df = (
            route_df
            .sort_values(
                [
                    "od_id",
                    "candidate_id",
                ]
            )
            .reset_index(
                drop=True
            )
        )


    if not link_df.empty:

        link_df = (
            link_df
            .sort_values(
                [
                    "od_id",
                    "candidate_id",
                    "link_order",
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


    success_df.to_csv(
        SUCCESS_OD_FILE,
        index=False,
        encoding="utf-8-sig",
    )


    route_df.to_csv(
        ROUTE_CATALOG_FILE,
        index=False,
        encoding="utf-8-sig",
    )


    link_df.to_csv(
        ROUTE_LINKS_FILE,
        index=False,
        encoding="utf-8-sig",
    )


    # ========================================================
    # Summary
    # ========================================================

    quality_distribution = {}

    if not route_df.empty:

        quality_distribution = {

            str(key):
                int(value)

            for key, value
            in (
                route_df[
                    "mapping_quality"
                ]
                .value_counts(
                    dropna=False
                )
                .to_dict()
                .items()
            )

        }


    traffic_source_distribution = {}

    if not link_df.empty:

        traffic_source_distribution = {

            str(key):
                int(value)

            for key, value
            in (
                link_df[
                    "traffic_source"
                ]
                .value_counts(
                    dropna=False
                )
                .to_dict()
                .items()
            )

        }


    summary = {

        "total_json_file_count":
            len(files),

        "success_od_count":
            success_od_count,

        "failed_od_count":
            failed_od_count,

        "route_candidate_count":
            total_route_count,

        "mapped_route_count":
            mapped_route_count,

        "usable_route_count":
            usable_route_count,

        "excluded_quality_route_count":
            excluded_quality_route_count,

        "route_link_row_count":
            int(
                len(
                    link_df
                )
            ),

        "unique_link_count":
            int(
                link_df[
                    "link_id"
                ].nunique()
            )
            if not link_df.empty
            else 0,

        "mapping_quality_distribution":
            quality_distribution,

        "traffic_source_distribution":
            traffic_source_distribution,

        "outputs": {

            "success_od_manifest":
                str(
                    SUCCESS_OD_FILE
                ),

            "route_catalog":
                str(
                    ROUTE_CATALOG_FILE
                ),

            "route_links":
                str(
                    ROUTE_LINKS_FILE
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
    # Terminal 출력
    # ========================================================

    print()
    print(
        "========================================"
    )
    print(
        "Route Integration Dataset 결과"
    )
    print(
        "========================================"
    )


    print(
        "성공 OD:",
        success_od_count,
    )


    print(
        "실패 OD 제외:",
        failed_od_count,
    )


    print(
        "전체 Route 후보:",
        total_route_count,
    )


    print(
        "Mapped Route:",
        mapped_route_count,
    )


    print(
        "사용 가능 Route:",
        usable_route_count,
    )


    print(
        "품질 제외 Route:",
        excluded_quality_route_count,
    )


    print(
        "Route × LINK 행:",
        f"{len(link_df):,}",
    )


    print(
        "Unique LINK:",
        (
            link_df[
                "link_id"
            ].nunique()
            if not link_df.empty
            else 0
        ),
    )


    print()

    print(
        "Mapping Quality:"
    )


    for (
        quality,
        count,
    ) in (
        quality_distribution.items()
    ):

        print(
            f"  {quality}:",
            count,
        )


    print()

    print(
        "Traffic Source:"
    )


    for (
        source,
        count,
    ) in (
        traffic_source_distribution.items()
    ):

        print(
            f"  {source}:",
            count,
        )


    print()

    print(
        "Success OD:"
    )
    print(
        SUCCESS_OD_FILE
    )


    print()

    print(
        "Route Catalog:"
    )
    print(
        ROUTE_CATALOG_FILE
    )


    print()

    print(
        "Route Links:"
    )
    print(
        ROUTE_LINKS_FILE
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
        "Route Integration Export 완료"
    )
    print(
        "========================================"
    )


    return (
        success_df,
        route_df,
        link_df,
    )


# ============================================================
# 직접 실행
# ============================================================

if __name__ == "__main__":

    export_route_integration_dataset()