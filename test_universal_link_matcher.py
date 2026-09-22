import json
from pathlib import Path

from backend.services.route_engine import (
    get_routes_by_place_names,
)

from backend.services.link_matcher import (
    match_route_candidates,
)


# ============================================================
# FLOW:MATE
# Universal Route → LINK Test
#
# 성남시청
# →
# 강남역
#
# TMAP A/B/C
# →
# MOCT_LINK
# ============================================================


ROOT = Path(__file__).resolve().parent


OUTPUT_DIR = (
    ROOT
    / "data"
    / "routes"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


OUTPUT_FILE = (
    OUTPUT_DIR
    / "universal_route_link_test.json"
)


def main():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE"
    )

    print(
        "Universal Route → LINK Test"
    )

    print(
        "========================================"
    )


    # ========================================================
    # 1. 장소명 → TMAP A/B/C
    # ========================================================

    print()

    print(
        "[1/2] TMAP A/B/C Route 준비"
    )


    route_result = (
        get_routes_by_place_names(

            origin_query="성남시청",

            destination_query="강남역",

            origin_region_hint="성남시",

            destination_region_hint="서울특별시",

        )
    )


    print()

    print(
        "출발:",
        route_result[
            "origin"
        ][
            "name"
        ],
    )


    print(
        "도착:",
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
    # 2. A/B/C → MOCT_LINK
    # ========================================================

    print()

    print(
        "[2/2] 국가표준 LINK Matching"
    )


    matched_result = (
        match_route_candidates(

            route_result,

            verbose=True,

        )
    )


    # ========================================================
    # 결과 저장
    # ========================================================

    with open(

        OUTPUT_FILE,

        "w",

        encoding="utf-8",

    ) as file:

        json.dump(

            matched_result,

            file,

            ensure_ascii=False,

            indent=2,

        )


    # ========================================================
    # 최종 요약
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "A/B/C LINK Mapping 최종 결과"
    )

    print(
        "========================================"
    )


    for route in matched_result[
        "routes"
    ]:

        mapping = (
            route[
                "link_mapping_v2"
            ]
        )


        print()

        print(
            "경로:",
            route[
                "candidate_id"
            ],
        )


        print(
            "TMAP 거리:",
            route[
                "total_distance_m"
            ],
            "m",
        )


        print(
            "TMAP ETA:",
            route[
                "tmap_eta_min"
            ],
            "분",
        )


        print(
            "LINK 수:",
            mapping[
                "matched_link_count"
            ],
        )


        print(
            "연결률:",
            mapping[
                "connectivity_percent"
            ],
            "%",
        )


        print(
            "Coverage:",
            mapping[
                "coverage_percent"
            ],
            "%",
        )


        print(
            "길이비:",
            mapping[
                "length_ratio"
            ],
        )


        print(
            "품질:",
            mapping[
                "quality"
            ],
        )


    print()

    print(
        "결과 저장:"
    )

    print(
        OUTPUT_FILE
    )


    print()

    print(
        "========================================"
    )

    print(
        "Universal LINK Mapping 완료"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()