import os
import json
from datetime import datetime

from tmap_service import get_route


# ============================================================
# 테스트 출발지 / 목적지
#
# 성남시청 → 판교역
# ============================================================

START = {
    "name": "성남시청",
    "longitude": 127.12476187,
    "latitude": 37.41975164,
}


END = {
    "name": "판교역(신분당선)",
    "longitude": 127.11123599,
    "latitude": 37.39589305,
}


# ============================================================
# TMAP 후보 경로
#
# A = 추천 경로
# B = 최소시간 경로
# C = 최단거리 경로
#
# searchOption
# 0  = 교통최적 + 추천
# 2  = 교통최적 + 최소시간
# 10 = 최단거리
# ============================================================

CANDIDATES = [
    {
        "candidate_id": "A",
        "route_id": "route_A",
        "search_option": "0",
        "option_name": "추천 경로",
    },

    {
        "candidate_id": "B",
        "route_id": "route_B",
        "search_option": "2",
        "option_name": "최소시간 경로",
    },

    {
        "candidate_id": "C",
        "route_id": "route_C",
        "search_option": "10",
        "option_name": "최단거리 경로",
    },
]


# ============================================================
# 저장 위치
# ============================================================

OUTPUT_DIR = os.path.join(
    "data",
    "routes",
)


os.makedirs(
    OUTPUT_DIR,
    exist_ok=True,
)


# ============================================================
# TMAP 결과 → FLOW 공통 Route JSON
# ============================================================

def build_route_json(
    candidate,
    route,
):

    # ========================================================
    # 전체 경로 좌표
    # ========================================================

    route_path = route.get(
        "route_path",
        [],
    )


    coordinates = []


    for point in route_path:

        longitude = point.get(
            "longitude"
        )

        latitude = point.get(
            "latitude"
        )


        if (
            longitude is None
            or
            latitude is None
        ):
            continue


        coordinates.append([
            float(longitude),
            float(latitude),
        ])


    # ========================================================
    # 도로 Segment
    # ========================================================

    segments = []


    road_segments = route.get(
        "road_segments",
        [],
    )


    for index, segment in enumerate(
        road_segments
    ):

        segments.append({

            "segment_index":
                index,

            "road_name":
                str(
                    segment.get(
                        "road_name",
                        ""
                    )
                    or ""
                ),

            "distance_m":
                float(
                    segment.get(
                        "distance_m",
                        0
                    )
                    or 0
                ),

            "duration_sec":
                float(
                    segment.get(
                        "duration_sec",
                        0
                    )
                    or 0
                ),

            "traffic":
                segment.get(
                    "traffic"
                ),

            # -----------------------------------------------
            # 다음 LINK_ID 매핑 단계에서 채워짐
            # -----------------------------------------------

            "link_ids":
                [],
        })


    # ========================================================
    # 총 거리 / 시간
    # ========================================================

    distance_km = float(
        route.get(
            "distance_km",
            0
        )
        or 0
    )


    time_min = float(
        route.get(
            "time_min",
            0
        )
        or 0
    )


    # ========================================================
    # Route JSON
    # ========================================================

    result = {

        "route_id":
            candidate[
                "route_id"
            ],

        "candidate_id":
            candidate[
                "candidate_id"
            ],

        "source":
            "TMAP",

        "search_option":
            candidate[
                "search_option"
            ],

        "search_option_name":
            candidate[
                "option_name"
            ],

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),


        # ====================================================
        # 출발지
        # ====================================================

        "origin": {

            "name":
                START[
                    "name"
                ],

            "longitude":
                START[
                    "longitude"
                ],

            "latitude":
                START[
                    "latitude"
                ],
        },


        # ====================================================
        # 목적지
        # ====================================================

        "destination": {

            "name":
                END[
                    "name"
                ],

            "longitude":
                END[
                    "longitude"
                ],

            "latitude":
                END[
                    "latitude"
                ],
        },


        # ====================================================
        # 경로 요약
        # ====================================================

        "summary": {

            "distance_m":
                round(
                    distance_km
                    *
                    1000
                ),

            "duration_sec":
                round(
                    time_min
                    *
                    60
                ),

            "toll_fare":
                int(
                    route.get(
                        "total_fare",
                        0
                    )
                    or 0
                ),

            "taxi_fare":
                int(
                    route.get(
                        "taxi_fare",
                        0
                    )
                    or 0
                ),
        },


        # ====================================================
        # 전체 경로 Geometry
        # ====================================================

        "geometry": {

            "type":
                "LineString",

            "coordinates":
                coordinates,
        },


        # ====================================================
        # TMAP 도로 Segment
        # ====================================================

        "segments":
            segments,


        # ====================================================
        # 국가표준 LINK 매핑
        #
        # 다음 단계에서 채워짐
        # ====================================================

        "link_mapping": {

            "status":
                "not_mapped",

            "matched_link_ids":
                [],

            "coverage_ratio":
                0.0,
        },
    }


    return result


# ============================================================
# Geometry Signature
#
# A/B/C가 완전히 동일한 경로인지
# 간단하게 확인하는 용도
# ============================================================

def geometry_signature(
    route_json,
):

    coordinates = (
        route_json
        .get(
            "geometry",
            {}
        )
        .get(
            "coordinates",
            []
        )
    )


    if not coordinates:

        return ""


    # ========================================================
    # 최대 약 25개 지점 샘플링
    # ========================================================

    step = max(
        1,
        len(coordinates)
        //
        25
    )


    sampled = coordinates[
        ::step
    ]


    signature_parts = []


    for coordinate in sampled:

        if len(
            coordinate
        ) < 2:

            continue


        longitude = float(
            coordinate[0]
        )

        latitude = float(
            coordinate[1]
        )


        signature_parts.append(

            f"{longitude:.5f},"
            f"{latitude:.5f}"
        )


    return "|".join(
        signature_parts
    )


# ============================================================
# 실행
# ============================================================

def main():

    print()
    print(
        "======================================"
    )

    print(
        "TMAP 후보 경로 A/B/C 생성"
    )

    print(
        "======================================"
    )


    results = []

    signatures = {}


    # ========================================================
    # A / B / C 생성
    # ========================================================

    for candidate in CANDIDATES:

        candidate_id = candidate[
            "candidate_id"
        ]


        search_option = candidate[
            "search_option"
        ]


        print()
        print(
            "--------------------------------------"
        )

        print(
            "후보:",
            candidate_id
        )

        print(
            "옵션:",
            candidate[
                "option_name"
            ]
        )

        print(
            "searchOption:",
            search_option
        )

        print(
            "--------------------------------------"
        )


        # ====================================================
        # TMAP API 호출
        # ====================================================

        try:

            route = get_route(

                START[
                    "longitude"
                ],

                START[
                    "latitude"
                ],

                END[
                    "longitude"
                ],

                END[
                    "latitude"
                ],

                END[
                    "name"
                ],

                search_option=
                    search_option,
            )


        except Exception as error:

            print()
            print(
                "❌ TMAP 경로 생성 실패"
            )

            print(
                "후보:",
                candidate_id
            )

            print(
                "searchOption:",
                search_option
            )

            print(
                "오류:",
                error
            )

            continue


        # ====================================================
        # TMAP → FLOW JSON
        # ====================================================

        route_json = build_route_json(

            candidate,

            route,
        )


        # ====================================================
        # Geometry 확인
        # ====================================================

        coordinates = (
            route_json[
                "geometry"
            ][
                "coordinates"
            ]
        )


        if len(
            coordinates
        ) < 2:

            print()
            print(
                "❌ 정상적인 경로 geometry가 없습니다."
            )

            continue


        # ====================================================
        # 경로 중복 확인
        # ====================================================

        signature = geometry_signature(
            route_json
        )


        duplicate_of = None


        for (
            previous_candidate,
            previous_signature
        ) in signatures.items():

            if (
                signature
                and
                signature
                ==
                previous_signature
            ):

                duplicate_of = (
                    previous_candidate
                )

                break


        signatures[
            candidate_id
        ] = signature


        route_json[
            "duplicate_of"
        ] = duplicate_of


        # ====================================================
        # JSON 저장
        # ====================================================

        output_file = os.path.join(

            OUTPUT_DIR,

            f"{candidate['route_id']}.json"
        )


        with open(
            output_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(

                route_json,

                file,

                ensure_ascii=False,

                indent=2,
            )


        # ====================================================
        # 결과 출력
        # ====================================================

        summary = route_json[
            "summary"
        ]


        segments = route_json.get(
            "segments",
            []
        )


        print()
        print(
            "거리:",
            round(
                summary[
                    "distance_m"
                ]
                /
                1000,
                3
            ),
            "km"
        )


        print(
            "시간:",
            round(
                summary[
                    "duration_sec"
                ]
                /
                60,
                1
            ),
            "분"
        )


        print(
            "통행료:",
            summary[
                "toll_fare"
            ],
            "원"
        )


        print(
            "택시요금:",
            summary[
                "taxi_fare"
            ],
            "원"
        )


        print(
            "경로 좌표:",
            len(
                coordinates
            ),
            "개"
        )


        print(
            "도로 Segment:",
            len(
                segments
            ),
            "개"
        )


        if duplicate_of is None:

            print(
                "중복 여부: ✅ 다른 경로"
            )

        else:

            print(
                "중복 여부: ⚠️",
                duplicate_of,
                "와 동일/매우 유사"
            )


        print(
            "저장:",
            output_file
        )


        results.append(
            route_json
        )


    # ========================================================
    # A/B/C 전체 결과
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "A/B/C 후보 경로 비교"
    )

    print(
        "======================================"
    )


    if not results:

        print()
        print(
            "❌ 생성된 후보 경로가 없습니다."
        )

        return


    for route in results:

        summary = route[
            "summary"
        ]


        print()
        print(
            "경로:",
            route[
                "candidate_id"
            ]
        )


        print(
            "route_id:",
            route[
                "route_id"
            ]
        )


        print(
            "옵션:",
            route[
                "search_option_name"
            ]
        )


        print(
            "searchOption:",
            route[
                "search_option"
            ]
        )


        print(
            "거리:",
            round(
                summary[
                    "distance_m"
                ]
                /
                1000,
                3
            ),
            "km"
        )


        print(
            "시간:",
            round(
                summary[
                    "duration_sec"
                ]
                /
                60,
                1
            ),
            "분"
        )


        print(
            "좌표:",
            len(
                route[
                    "geometry"
                ][
                    "coordinates"
                ]
            ),
            "개"
        )


        duplicate = route.get(
            "duplicate_of"
        )


        if duplicate is None:

            print(
                "중복: 없음"
            )

        else:

            print(
                "중복:",
                duplicate,
                "경로와 동일/유사"
            )


    # ========================================================
    # 생성 여부 최종 확인
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "생성 파일 확인"
    )

    print(
        "======================================"
    )


    for candidate in CANDIDATES:

        filepath = os.path.join(

            OUTPUT_DIR,

            f"{candidate['route_id']}.json"
        )


        if os.path.exists(
            filepath
        ):

            print(
                "✅",
                filepath
            )

        else:

            print(
                "❌",
                filepath
            )


    print()
    print(
        "======================================"
    )

    print(
        "후보 경로 생성 완료"
    )

    print(
        "======================================"
    )


# ============================================================
# 직접 실행
# ============================================================

if __name__ == "__main__":
    main()