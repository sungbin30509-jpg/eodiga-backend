from backend.services.location_service import (
    resolve_location,
    search_location_candidates,
)


# ============================================================
# FLOW:MATE Location Resolver Test
# ============================================================


TEST_LOCATIONS = [

    (
        "판교역",
        "성남시",
    ),

    (
        "강남역",
        "서울특별시",
    ),

    (
        "성남시청",
        "성남시",
    ),

]


def main():

    print()
    print(
        "========================================"
    )

    print(
        "FLOW:MATE Location Resolver Test"
    )

    print(
        "========================================"
    )


    for query, region_hint in TEST_LOCATIONS:

        print()

        print(
            "----------------------------------------"
        )

        print(
            "검색:",
            query,
        )

        print(
            "지역 힌트:",
            region_hint,
        )

        print(
            "----------------------------------------"
        )


        result = resolve_location(

            query,

            region_hint=region_hint,

        )


        print(
            "TMAP 이름:",
            result[
                "name"
            ],
        )


        print(
            "주소:",
            result[
                "address"
            ],
        )


        print(
            "위도:",
            result[
                "lat"
            ],
        )


        print(
            "경도:",
            result[
                "lon"
            ],
        )


        print(
            "Match Score:",
            result[
                "match_score"
            ],
        )


        print(
            "Cache:",
            result[
                "cached"
            ],
        )


    print()
    print(
        "========================================"
    )

    print(
        "테스트 완료"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()