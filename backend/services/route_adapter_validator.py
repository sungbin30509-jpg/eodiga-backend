from pathlib import Path
from collections import Counter
import csv
import json

from backend.services.route_adapter import (
    adapt_route_result,
    load_json,
    NODE_LINK_DATASET,
    USABLE_MAPPING_QUALITIES,
)


# ============================================================
# FLOW:MATE
# Route Adapter Validator v2
#
# 핵심 변경
# ------------------------------------------------------------
# 성공한 Route Pipeline만 Adapter 검증
#
# TMAP quota 실패:
#   HTTP 429
#   QUOTA_EXCEEDED
#   Limit Exceeded
#
# 는 Adapter ERROR가 아니라 PENDING_QUOTA로 분류
#
# TMAP API 호출 없음
# ============================================================


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


INPUT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "adapter_validation"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


SUMMARY_JSON = (
    OUTPUT_DIR
    / "route_adapter_validation_summary_v2.json"
)


RESULT_CSV = (
    OUTPUT_DIR
    / "route_adapter_validation_results_v2.csv"
)


# ============================================================
# 저장 Utility
# ============================================================

def save_json(data, path):

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


def save_csv(rows, path):

    if not rows:
        return

    fieldnames = list(
        rows[0].keys()
    )

    with open(
        path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


# ============================================================
# 파일 종류 판정
# ============================================================

def classify_input_json(
    raw_data,
    json_path,
):

    if not isinstance(
        raw_data,
        dict,
    ):

        return {
            "category": "NON_OD",
            "od_id": None,
            "reason": "json_root_not_object",
        }


    od_id = raw_data.get(
        "od_id"
    )


    # --------------------------------------------------------
    # OD 파일인지 확인
    # --------------------------------------------------------

    is_od_file = (
        isinstance(
            od_id,
            str,
        )
        and
        od_id.startswith(
            "OD_"
        )
    )


    if not is_od_file:

        return {
            "category": "NON_OD",
            "od_id": od_id,
            "reason": "not_od_json",
        }


    # --------------------------------------------------------
    # 성공 Pipeline
    # --------------------------------------------------------

    pipeline_result = raw_data.get(
        "pipeline_result"
    )


    if isinstance(
        pipeline_result,
        dict,
    ):

        return {
            "category": "PIPELINE_READY",
            "od_id": od_id,
            "reason": None,
        }


    # --------------------------------------------------------
    # Batch 실패
    # --------------------------------------------------------

    batch_status = str(
        raw_data.get(
            "batch_status",
            ""
        )
    ).lower()


    error_message = str(
        raw_data.get(
            "error_message",
            ""
        )
    )


    error_upper = (
        error_message.upper()
    )


    # --------------------------------------------------------
    # TMAP quota
    # --------------------------------------------------------

    quota_markers = [
        "HTTP STATUS: 429",
        "QUOTA_EXCEEDED",
        "LIMIT EXCEEDED",
    ]


    if (
        batch_status == "failed"
        and
        any(
            marker in error_upper
            for marker
            in quota_markers
        )
    ):

        return {
            "category": "PENDING_QUOTA",
            "od_id": od_id,
            "reason": "TMAP_QUOTA_EXCEEDED",
        }


    # --------------------------------------------------------
    # 다른 Pipeline 실패
    # --------------------------------------------------------

    if batch_status == "failed":

        return {
            "category": "PIPELINE_FAILED",
            "od_id": od_id,
            "reason": error_message[:500],
        }


    # --------------------------------------------------------
    # 알 수 없는 OD 구조
    # --------------------------------------------------------

    return {
        "category": "OD_UNKNOWN",
        "od_id": od_id,
        "reason": "pipeline_result_missing",
    }


# ============================================================
# 개별 Route 검증
# ============================================================

def validate_route(
    route,
    route_metadata,
):

    errors = []
    warnings = []


    route_id = route.get(
        "route_id"
    )


    if not isinstance(
        route_id,
        str,
    ) or not route_id:

        errors.append(
            "invalid_route_id"
        )


    if not route.get(
        "origin_location_id"
    ):

        errors.append(
            "missing_origin_location_id"
        )


    if not route.get(
        "destination_location_id"
    ):

        errors.append(
            "missing_destination_location_id"
        )


    links = route.get(
        "links",
        []
    )


    if not isinstance(
        links,
        list,
    ):

        errors.append(
            "links_not_list"
        )

        return errors, warnings


    if not links:

        errors.append(
            "empty_links"
        )

        return errors, warnings


    orders = []
    link_ids = []


    for index, link in enumerate(
        links
    ):

        if not isinstance(
            link,
            dict,
        ):

            errors.append(
                f"invalid_link_object:{index}"
            )

            continue


        link_id = link.get(
            "LINK_ID"
        )


        if not isinstance(
            link_id,
            str,
        ) or not link_id:

            errors.append(
                f"invalid_LINK_ID:{index}"
            )


        link_ids.append(
            link_id
        )


        link_order = link.get(
            "link_order"
        )


        if not isinstance(
            link_order,
            int,
        ):

            errors.append(
                f"invalid_link_order:{index}"
            )

        else:

            orders.append(
                link_order
            )


        link_length_m = link.get(
            "link_length_m"
        )


        if not isinstance(
            link_length_m,
            (int, float),
        ):

            errors.append(
                f"invalid_link_length:{index}"
            )

        elif link_length_m <= 0:

            errors.append(
                f"nonpositive_link_length:{index}"
            )


    # --------------------------------------------------------
    # 0-based 연속 순서 검사
    # --------------------------------------------------------

    expected_orders = list(
        range(
            len(
                links
            )
        )
    )


    if orders != expected_orders:

        errors.append(
            "non_contiguous_link_order"
        )


    # --------------------------------------------------------
    # 동일 LINK 재등장 검사
    #
    # 오류가 아니라 Warning
    # --------------------------------------------------------

    counter = Counter(
        link_ids
    )


    duplicates = {

        link_id: count

        for link_id, count
        in counter.items()

        if (
            link_id is not None
            and
            count > 1
        )

    }


    if duplicates:

        warnings.append(
            "duplicate_LINK_ID_present"
        )


    mapping = route_metadata.get(
        "mapping",
        {}
    )


    quality = mapping.get(
        "mapping_quality"
    )


    if quality not in USABLE_MAPPING_QUALITIES:

        errors.append(
            f"invalid_usable_quality:{quality}"
        )


    metadata_duplicate = bool(
        mapping.get(
            "has_duplicate_link_ids"
        )
    )


    if (
        metadata_duplicate
        !=
        bool(
            duplicates
        )
    ):

        errors.append(
            "duplicate_metadata_mismatch"
        )


    return errors, warnings


# ============================================================
# Adapter 결과 검증
# ============================================================

def validate_adapted_result(
    adapted,
):

    errors = []
    warnings = []


    contract = adapted.get(
        "contract",
        {}
    )


    if (
        contract.get(
            "node_link_dataset"
        )
        !=
        NODE_LINK_DATASET
    ):

        errors.append(
            "node_link_dataset_mismatch"
        )


    routes = adapted.get(
        "routes",
        []
    )


    if not isinstance(
        routes,
        list,
    ):

        return [
            "routes_not_list"
        ], warnings


    if len(
        routes
    ) > 3:

        errors.append(
            "usable_route_count_over_3"
        )


    location = adapted.get(
        "location_resolution",
        {}
    )


    if (
        adapted.get(
            "source_type"
        )
        ==
        "batch_od"
        and
        not location.get(
            "resolved"
        )
    ):

        errors.append(
            "batch_location_unresolved"
        )


    # --------------------------------------------------------
    # route_id 중복
    # --------------------------------------------------------

    route_ids = [

        route.get(
            "route_id"
        )

        for route
        in routes

    ]


    if (
        len(
            route_ids
        )
        !=
        len(
            set(
                route_ids
            )
        )
    ):

        errors.append(
            "duplicate_route_id_within_OD"
        )


    route_metadata = adapted.get(
        "route_metadata",
        {}
    )


    for route in routes:

        route_id = route.get(
            "route_id"
        )


        metadata = route_metadata.get(
            route_id
        )


        if not isinstance(
            metadata,
            dict,
        ):

            errors.append(
                f"missing_route_metadata:{route_id}"
            )

            continue


        route_errors, route_warnings = (
            validate_route(
                route,
                metadata,
            )
        )


        for error in route_errors:

            errors.append(
                f"{route_id}:{error}"
            )


        for warning in route_warnings:

            warnings.append(
                f"{route_id}:{warning}"
            )


    summary = adapted.get(
        "summary",
        {}
    )


    if (
        summary.get(
            "usable_route_count"
        )
        !=
        len(
            routes
        )
    ):

        errors.append(
            "usable_route_count_mismatch"
        )


    excluded_routes = adapted.get(
        "excluded_routes",
        []
    )


    if (
        summary.get(
            "excluded_route_count"
        )
        !=
        len(
            excluded_routes
        )
    ):

        errors.append(
            "excluded_route_count_mismatch"
        )


    return errors, warnings


# ============================================================
# Main Validation
# ============================================================

def run_validation():

    json_files = sorted(
        INPUT_DIR.glob(
            "*.json"
        )
    )


    result_rows = []


    total_json_files = 0

    total_od_files = 0

    non_od_files = 0


    pipeline_ready_count = 0

    pending_quota_count = 0

    pipeline_failed_count = 0

    od_unknown_count = 0


    adapter_success_count = 0

    adapter_error_count = 0


    validation_pass_count = 0

    validation_fail_count = 0


    route_count_distribution = Counter()

    quality_counts = Counter()


    global_route_ids = []

    duplicate_link_routes = []

    recovered_routes = []

    review_routes = []


    examples_by_route_count = {
        "0": None,
        "1": None,
        "2": None,
        "3": None,
    }


    pending_quota_examples = []

    pipeline_failed_examples = []

    adapter_errors = []


    # ========================================================
    # Scan
    # ========================================================

    for json_path in json_files:

        total_json_files += 1


        try:

            raw_data = load_json(
                json_path
            )

        except Exception as error:

            non_od_files += 1

            result_rows.append({

                "file":
                    json_path.name,

                "od_id":
                    "",

                "pipeline_status":
                    "INVALID_JSON",

                "adapter_status":
                    "NOT_RUN",

                "validation_status":
                    "NOT_RUN",

                "usable_route_count":
                    "",

                "excluded_route_count":
                    "",

                "origin_location_id":
                    "",

                "destination_location_id":
                    "",

                "errors":
                    str(
                        error
                    ),

                "warnings":
                    "",

            })

            continue


        classification = (
            classify_input_json(
                raw_data,
                json_path,
            )
        )


        category = classification[
            "category"
        ]


        od_id = classification[
            "od_id"
        ]


        # ====================================================
        # NON OD
        # ====================================================

        if category == "NON_OD":

            non_od_files += 1


            result_rows.append({

                "file":
                    json_path.name,

                "od_id":
                    od_id or "",

                "pipeline_status":
                    "NON_OD",

                "adapter_status":
                    "NOT_RUN",

                "validation_status":
                    "NOT_RUN",

                "usable_route_count":
                    "",

                "excluded_route_count":
                    "",

                "origin_location_id":
                    "",

                "destination_location_id":
                    "",

                "errors":
                    "",

                "warnings":
                    classification[
                        "reason"
                    ],

            })

            continue


        total_od_files += 1


        # ====================================================
        # QUOTA PENDING
        # ====================================================

        if category == "PENDING_QUOTA":

            pending_quota_count += 1


            if len(
                pending_quota_examples
            ) < 10:

                pending_quota_examples.append(
                    od_id
                )


            result_rows.append({

                "file":
                    json_path.name,

                "od_id":
                    od_id,

                "pipeline_status":
                    "PENDING_QUOTA",

                "adapter_status":
                    "NOT_RUN",

                "validation_status":
                    "NOT_RUN",

                "usable_route_count":
                    "",

                "excluded_route_count":
                    "",

                "origin_location_id":
                    "",

                "destination_location_id":
                    "",

                "errors":
                    "",

                "warnings":
                    "TMAP_QUOTA_EXCEEDED",

            })

            continue


        # ====================================================
        # 다른 Pipeline 실패
        # ====================================================

        if category == "PIPELINE_FAILED":

            pipeline_failed_count += 1


            if len(
                pipeline_failed_examples
            ) < 10:

                pipeline_failed_examples.append({
                    "od_id":
                        od_id,

                    "reason":
                        classification[
                            "reason"
                        ],
                })


            result_rows.append({

                "file":
                    json_path.name,

                "od_id":
                    od_id,

                "pipeline_status":
                    "PIPELINE_FAILED",

                "adapter_status":
                    "NOT_RUN",

                "validation_status":
                    "NOT_RUN",

                "usable_route_count":
                    "",

                "excluded_route_count":
                    "",

                "origin_location_id":
                    "",

                "destination_location_id":
                    "",

                "errors":
                    classification[
                        "reason"
                    ],

                "warnings":
                    "",

            })

            continue


        # ====================================================
        # Unknown OD
        # ====================================================

        if category == "OD_UNKNOWN":

            od_unknown_count += 1


            result_rows.append({

                "file":
                    json_path.name,

                "od_id":
                    od_id,

                "pipeline_status":
                    "OD_UNKNOWN",

                "adapter_status":
                    "NOT_RUN",

                "validation_status":
                    "NOT_RUN",

                "usable_route_count":
                    "",

                "excluded_route_count":
                    "",

                "origin_location_id":
                    "",

                "destination_location_id":
                    "",

                "errors":
                    classification[
                        "reason"
                    ],

                "warnings":
                    "",

            })

            continue


        # ====================================================
        # 여기부터 Pipeline Ready
        # ====================================================

        pipeline_ready_count += 1


        try:

            adapted = adapt_route_result(
                raw_data
            )

            adapter_success_count += 1


        except Exception as error:

            adapter_error_count += 1


            adapter_errors.append({

                "od_id":
                    od_id,

                "file":
                    json_path.name,

                "error":
                    str(
                        error
                    ),

            })


            result_rows.append({

                "file":
                    json_path.name,

                "od_id":
                    od_id,

                "pipeline_status":
                    "READY",

                "adapter_status":
                    "ERROR",

                "validation_status":
                    "NOT_RUN",

                "usable_route_count":
                    "",

                "excluded_route_count":
                    "",

                "origin_location_id":
                    "",

                "destination_location_id":
                    "",

                "errors":
                    str(
                        error
                    ),

                "warnings":
                    "",

            })

            continue


        # ====================================================
        # Contract 검증
        # ====================================================

        errors, warnings = (
            validate_adapted_result(
                adapted
            )
        )


        if errors:

            validation_status = "FAIL"

            validation_fail_count += 1

        else:

            validation_status = "PASS"

            validation_pass_count += 1


        routes = adapted.get(
            "routes",
            []
        )


        excluded_routes = adapted.get(
            "excluded_routes",
            []
        )


        usable_count = len(
            routes
        )


        route_count_distribution[
            usable_count
        ] += 1


        count_key = str(
            usable_count
        )


        if (
            count_key
            in
            examples_by_route_count
            and
            examples_by_route_count[
                count_key
            ]
            is None
        ):

            examples_by_route_count[
                count_key
            ] = od_id


        metadata = adapted.get(
            "route_metadata",
            {}
        )


        duplicate_route_count = 0


        for route in routes:

            route_id = route[
                "route_id"
            ]


            global_route_ids.append(
                route_id
            )


            route_metadata = metadata.get(
                route_id,
                {}
            )


            mapping = route_metadata.get(
                "mapping",
                {}
            )


            quality = mapping.get(
                "mapping_quality"
            )


            quality_counts[
                quality
            ] += 1


            if quality == "recovered":

                recovered_routes.append(
                    route_id
                )


            if quality == "review":

                review_routes.append(
                    route_id
                )


            if mapping.get(
                "has_duplicate_link_ids"
            ):

                duplicate_route_count += 1

                duplicate_link_routes.append({

                    "route_id":
                        route_id,

                    "duplicates":
                        mapping.get(
                            "duplicate_occurrences"
                        ),

                })


        location = adapted.get(
            "location_resolution",
            {}
        )


        result_rows.append({

            "file":
                json_path.name,

            "od_id":
                od_id,

            "pipeline_status":
                "READY",

            "adapter_status":
                adapted.get(
                    "status"
                ),

            "validation_status":
                validation_status,

            "usable_route_count":
                usable_count,

            "excluded_route_count":
                len(
                    excluded_routes
                ),

            "origin_location_id":
                location.get(
                    "origin_location_id"
                ),

            "destination_location_id":
                location.get(
                    "destination_location_id"
                ),

            "errors":
                " | ".join(
                    errors
                ),

            "warnings":
                " | ".join(
                    warnings
                ),

        })


    # ========================================================
    # route_id 전역 충돌
    # ========================================================

    route_id_counter = Counter(
        global_route_ids
    )


    duplicate_route_ids = {

        route_id: count

        for route_id, count
        in route_id_counter.items()

        if count > 1

    }


    # ========================================================
    # Summary
    # ========================================================

    summary = {

        "validator_version":
            "route_adapter_validator_v2",

        "node_link_dataset":
            NODE_LINK_DATASET,

        "input_directory":
            str(
                INPUT_DIR
            ),

        "file_counts": {

            "total_json_files":
                total_json_files,

            "total_od_files":
                total_od_files,

            "non_od_files":
                non_od_files,

        },

        "pipeline_counts": {

            "ready":
                pipeline_ready_count,

            "pending_quota":
                pending_quota_count,

            "failed_other":
                pipeline_failed_count,

            "unknown":
                od_unknown_count,

        },

        "adapter_counts": {

            "success":
                adapter_success_count,

            "error":
                adapter_error_count,

        },

        "validation_counts": {

            "pass":
                validation_pass_count,

            "fail":
                validation_fail_count,

        },

        "usable_route_count_distribution": {

            "0":
                route_count_distribution[
                    0
                ],

            "1":
                route_count_distribution[
                    1
                ],

            "2":
                route_count_distribution[
                    2
                ],

            "3":
                route_count_distribution[
                    3
                ],

        },

        "examples_by_usable_route_count":
            examples_by_route_count,

        "mapping_quality_counts":
            dict(
                quality_counts
            ),

        "total_exported_routes":
            len(
                global_route_ids
            ),

        "global_route_id_unique":
            (
                len(
                    duplicate_route_ids
                )
                ==
                0
            ),

        "duplicate_route_ids":
            duplicate_route_ids,

        "duplicate_link_route_count":
            len(
                duplicate_link_routes
            ),

        "duplicate_link_routes":
            duplicate_link_routes,

        "recovered_route_count":
            len(
                recovered_routes
            ),

        "review_route_count":
            len(
                review_routes
            ),

        "pending_quota_examples":
            pending_quota_examples,

        "pipeline_failed_examples":
            pipeline_failed_examples,

        "adapter_errors":
            adapter_errors,

    }


    save_json(
        summary,
        SUMMARY_JSON,
    )


    save_csv(
        result_rows,
        RESULT_CSV,
    )


    return summary


# ============================================================
# CLI
# ============================================================

def main():

    print()

    print(
        "=========================================="
    )

    print(
        "FLOW:MATE Route Adapter Validator v2"
    )

    print(
        "=========================================="
    )

    print()


    summary = run_validation()


    files = summary[
        "file_counts"
    ]

    pipeline = summary[
        "pipeline_counts"
    ]

    adapter = summary[
        "adapter_counts"
    ]

    validation = summary[
        "validation_counts"
    ]


    print(
        "[Files]"
    )

    print(
        "전체 JSON:",
        files[
            "total_json_files"
        ],
    )

    print(
        "OD JSON:",
        files[
            "total_od_files"
        ],
    )

    print(
        "Non-OD JSON:",
        files[
            "non_od_files"
        ],
    )


    print()

    print(
        "[Route Pipeline]"
    )

    print(
        "READY:",
        pipeline[
            "ready"
        ],
    )

    print(
        "PENDING_QUOTA:",
        pipeline[
            "pending_quota"
        ],
    )

    print(
        "FAILED_OTHER:",
        pipeline[
            "failed_other"
        ],
    )

    print(
        "UNKNOWN:",
        pipeline[
            "unknown"
        ],
    )


    print()

    print(
        "[Route Adapter]"
    )

    print(
        "Adapter 성공:",
        adapter[
            "success"
        ],
    )

    print(
        "Adapter 오류:",
        adapter[
            "error"
        ],
    )

    print(
        "Validation PASS:",
        validation[
            "pass"
        ],
    )

    print(
        "Validation FAIL:",
        validation[
            "fail"
        ],
    )


    print()

    print(
        "[Usable Route Count]"
    )


    distribution = summary[
        "usable_route_count_distribution"
    ]


    examples = summary[
        "examples_by_usable_route_count"
    ]


    for count in (
        "0",
        "1",
        "2",
        "3",
    ):

        print(
            f"  {count} Route : "
            f"{distribution[count]} OD"
            f" / example={examples[count]}"
        )


    print()

    print(
        "[Mapping Quality]"
    )


    for quality, count in (
        summary[
            "mapping_quality_counts"
        ].items()
    ):

        print(
            f"  {quality}: {count}"
        )


    print()

    print(
        "전체 Export Route:",
        summary[
            "total_exported_routes"
        ],
    )

    print(
        "전역 route_id Unique:",
        summary[
            "global_route_id_unique"
        ],
    )

    print(
        "Duplicate LINK Route:",
        summary[
            "duplicate_link_route_count"
        ],
    )

    print(
        "Recovered Route:",
        summary[
            "recovered_route_count"
        ],
    )

    print(
        "Review Route:",
        summary[
            "review_route_count"
        ],
    )


    print()

    print(
        "=========================================="
    )

    print(
        "저장:"
    )

    print(
        SUMMARY_JSON
    )

    print(
        RESULT_CSV
    )

    print(
        "=========================================="
    )

    print()


if __name__ == "__main__":

    main()