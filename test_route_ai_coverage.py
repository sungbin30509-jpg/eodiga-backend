from pathlib import Path
import json

from backend.services.link_classifier import (
    classify_route_candidates,
)

from backend.services.ai_coverage_service import (
    apply_ai_coverage_to_candidates,
)


# ============================================================
# FLOW:MATE
# Route → Seongnam → AI Coverage Test
#
# 기존에 성공한
# universal_route_link_test.json
# 재사용
#
# TMAP API 재호출 없음
# ============================================================


ROOT = Path(__file__).resolve().parent


INPUT_FILE = (
    ROOT
    / "data"
    / "routes"
    / "universal_route_link_test.json"
)


OUTPUT_FILE = (
    ROOT
    / "data"
    / "routes"
    / "universal_route_ai_coverage_test.json"
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
        "Seongnam + AI Coverage Test"
    )

    print(
        "========================================"
    )


    # ========================================================
    # 기존 LINK Mapping 결과 로드
    # ========================================================

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"입력 파일이 없습니다: {INPUT_FILE}"
        )


    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        matched_result = (
            json.load(
                file
            )
        )


    # ========================================================
    # 1. 성남 내부 / 외부 분류
    # ========================================================

    print()
    print(
        "[1/2] 성남 내부 / 외부 판별"
    )


    classified_result = (
        classify_route_candidates(
            matched_result
        )
    )


    # ========================================================
    # 2. AI Coverage
    # ========================================================

    print()
    print(
        "[2/2] LightGBM 지원 Coverage 계산"
    )


    final_result = (
        apply_ai_coverage_to_candidates(
            classified_result
        )
    )


    # ========================================================
    # 저장
    # ========================================================

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(

            final_result,

            file,

            ensure_ascii=False,

            indent=2,

        )


    # ========================================================
    # 결과 출력
    # ========================================================

    print()
    print(
        "========================================"
    )

    print(
        "A/B/C Coverage 결과"
    )

    print(
        "========================================"
    )


    for route in final_result[
        "routes"
    ]:

        candidate_id = (
            route[
                "candidate_id"
            ]
        )


        classification = (
            route[
                "seongnam_classification"
            ]
        )


        coverage = (
            route[
                "ai_coverage"
            ]
        )


        print()
        print(
            "----------------------------------------"
        )

        print(
            "경로:",
            candidate_id,
        )

        print(
            "----------------------------------------"
        )


        print(
            "전체 LINK:",
            classification[
                "total_link_count"
            ],
        )


        print(
            "성남 완전 내부:",
            classification[
                "inside_link_count"
            ],
        )


        print(
            "성남 경계 교차:",
            classification[
                "boundary_crossing_link_count"
            ],
        )


        print(
            "성남 외부:",
            classification[
                "outside_link_count"
            ],
        )


        print()


        print(
            "AI 지원 LINK:",
            coverage[
                "ai_supported_link_count"
            ],
        )


        print(
            "TMAP fallback LINK:",
            coverage[
                "tmap_fallback_link_count"
            ],
        )


        print(
            "외부 TMAP LINK:",
            coverage[
                "outside_seongnam_link_count"
            ],
        )


        print()


        print(
            "AI LINK Coverage:",
            coverage[
                "link_count_coverage_percent"
            ],
            "%",
        )


        print(
            "AI Distance Coverage:",
            coverage[
                "distance_coverage_percent"
            ],
            "%",
        )


        print(
            "성남 구간:",
            round(
                coverage[
                    "seongnam_route_distance_m"
                ]
                /
                1000,
                3,
            ),
            "km",
        )


        print(
            "AI 담당:",
            round(
                coverage[
                    "ai_covered_distance_m"
                ]
                /
                1000,
                3,
            ),
            "km",
        )


        print(
            "TMAP fallback:",
            round(
                coverage[
                    "tmap_fallback_distance_m"
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
                coverage[
                    "outside_seongnam_distance_m"
                ]
                /
                1000,
                3,
            ),
            "km",
        )


        print(
            "미지원 LINK 예시:",
            coverage[
                "unsupported_link_ids"
            ][:10],
        )


    print()
    print(
        "========================================"
    )

    print(
        "결과 저장:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()