from backend.services.location_service import (
    resolve_location,
)

from backend.services.route_engine import (
    request_tmap_route,
)

from backend.services.navigation_service import (
    get_navigation_state,
)

from backend.services.navigation_guidance import (
    calculate_route_cumulative_distances,
)


# ============================================================
# FLOW:MATE Navigation Simulator
#
# 실제 자동차를 타지 않고
# TMAP Route Geometry 위에서 GPS가 이동하는 것처럼
# 가상 주행 테스트
# ============================================================


def find_geometry_index_for_distance(
    cumulative_distances,
    target_distance_m,
):

    best_index = 0
    best_difference = None

    for index, distance_m in enumerate(
        cumulative_distances
    ):

        difference = abs(
            distance_m
            - target_distance_m
        )

        if (
            best_difference is None
            or
            difference < best_difference
        ):

            best_difference = difference
            best_index = index

    return best_index


def main():

    print()
    print(
        "========================================"
    )
    print(
        "FLOW:MATE Navigation Simulator"
    )
    print(
        "========================================"
    )
    print()


    # --------------------------------------------------------
    # 출발 / 도착
    # --------------------------------------------------------

    origin = resolve_location(
        "성남시청",
        region_hint="성남",
    )

    destination = resolve_location(
        "강남역",
        region_hint="서울",
    )


    print(
        "출발:",
        origin.get("name")
    )

    print(
        "도착:",
        destination.get("name")
    )

    print()


    # --------------------------------------------------------
    # TMAP Route A 한 개만 호출
    # --------------------------------------------------------

    print(
        "TMAP Route A 요청 중..."
    )

    route = request_tmap_route(
        origin,
        destination,
        "A",
    )


    print(
        "Route A 수신 완료"
    )

    print(
        "거리:",
        route.get(
            "total_distance_m"
        ),
        "m"
    )

    print(
        "ETA:",
        route.get(
            "tmap_eta_min"
        ),
        "분"
    )

    print(
        "Guidance:",
        route.get(
            "navigation_guidance_count"
        ),
        "개"
    )

    print()


    geometry = route[
        "geometry"
    ]


    cumulative_distances = (
        calculate_route_cumulative_distances(
            geometry
        )
    )


    if not cumulative_distances:

        raise RuntimeError(
            "Route 누적거리 계산 실패"
        )


    route_length_m = (
        cumulative_distances[-1]
    )


    print(
        "Geometry 기준 Route 길이:",
        round(
            route_length_m,
            1,
        ),
        "m"
    )

    print()

    print(
        "========================================"
    )

    print(
        "가상 주행 시작"
    )

    print(
        "========================================"
    )

    print()


    # --------------------------------------------------------
    # 약 20m 간격으로 Route 위를 가상 이동
    # --------------------------------------------------------

    simulation_interval_m = (
        20.0
    )


    target_distance_m = (
        0.0
    )


    previous_primary_text = None
    previous_guidance_sequence = None


    while (
        target_distance_m
        <=
        route_length_m
    ):

        geometry_index = (
            find_geometry_index_for_distance(

                cumulative_distances,

                target_distance_m,

            )
        )


        coordinate = (
            geometry[
                geometry_index
            ]
        )


        current_lon = float(
            coordinate[0]
        )

        current_lat = float(
            coordinate[1]
        )


        state = (
            get_navigation_state(

                route,

                current_lat,
                current_lon,

            )
        )


        next_guidance = (
            state.get(
                "next_guidance"
            )
        )


        guidance_sequence = (

            next_guidance.get(
                "sequence"
            )

            if
            next_guidance

            else
            None

        )


        primary_text = (
            state.get(
                "primary_text"
            )
        )


        # ----------------------------------------------------
        # 안내가 달라지는 순간만 출력
        # ----------------------------------------------------

        if (
            primary_text
            !=
            previous_primary_text
            or
            guidance_sequence
            !=
            previous_guidance_sequence
        ):

            print(
                "----------------------------------------"
            )

            print(
                "현재 Route 위치:",
                round(
                    state.get(
                        "current_route_position_m"
                    )
                    or
                    0.0,
                    1,
                ),
                "m"
            )


            print(
                "다음 안내까지:",
                state.get(
                    "distance_to_next_m"
                ),
                "m"
            )


            print(
                "▶",
                primary_text
            )


            secondary_text = (
                state.get(
                    "secondary_text"
                )
            )


            if secondary_text:

                print(
                    " ",
                    secondary_text
                )


            if next_guidance:

                print(
                    "TMAP:",
                    next_guidance.get(
                        "description"
                    )
                )

                print(
                    "turnType:",
                    next_guidance.get(
                        "turn_type"
                    )
                )


            print()


            previous_primary_text = (
                primary_text
            )

            previous_guidance_sequence = (
                guidance_sequence
            )


        target_distance_m += (
            simulation_interval_m
        )


    print(
        "========================================"
    )

    print(
        "가상 주행 완료"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()