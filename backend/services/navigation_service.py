from backend.services.navigation_guidance import (
    find_nearest_route_position,
)


# ============================================================
# 언제가 Navigation Service
#
# 현재 GPS
# → Route 상 현재 위치
# → Route 이탈 여부 판정
# → 다음 Guidance 탐색
# → 남은 거리 계산
# → Turn-by-Turn 안내 생성
# → 목적지 도착 판정
# ============================================================


# ============================================================
# Route Snap 허용 거리
#
# GPS가 Route에서 100m보다 멀면
# 강제로 Route에 붙이지 않고 GPS_NOT_MATCHED 처리
# ============================================================

MAX_ROUTE_SNAP_DISTANCE_M = 100.0


# ============================================================
# 목적지 도착 판정 거리
#
# 마지막 E Guidance까지 30m 이내이면
# ARRIVING 처리
# ============================================================

ARRIVAL_THRESHOLD_M = 30.0


# ============================================================
# 거리 표시
# ============================================================

def format_navigation_distance(
    distance_m,
):

    if distance_m is None:
        return None

    distance_m = max(
        0.0,
        float(distance_m),
    )

    # --------------------------------------------------------
    # 1km 이상
    # --------------------------------------------------------

    if distance_m >= 1000:

        distance_km = (
            distance_m / 1000.0
        )

        return f"{distance_km:.1f}km"

    # --------------------------------------------------------
    # 500m 이상
    # → 100m 단위
    # --------------------------------------------------------

    if distance_m >= 500:

        rounded = (
            round(
                distance_m / 100.0
            )
            * 100
        )

        return f"{int(rounded)}m"

    # --------------------------------------------------------
    # 100m 이상
    # → 50m 단위
    # --------------------------------------------------------

    if distance_m >= 100:

        rounded = (
            round(
                distance_m / 50.0
            )
            * 50
        )

        return f"{int(rounded)}m"

    # --------------------------------------------------------
    # 30m 이상
    # → 10m 단위
    # --------------------------------------------------------

    if distance_m >= 30:

        rounded = (
            round(
                distance_m / 10.0
            )
            * 10
        )

        return f"{int(rounded)}m"

    # --------------------------------------------------------
    # 30m 미만
    # --------------------------------------------------------

    return "곧"


# ============================================================
# Guidance → 짧은 행동명
# ============================================================

def get_maneuver_action(
    guidance,
):

    description = (
        guidance.get(
            "description"
        )
        or ""
    )

    if "우회전" in description:
        return "우회전"

    if "좌회전" in description:
        return "좌회전"

    if "유턴" in description:
        return "유턴"

    if "오른쪽 방향" in description:
        return "오른쪽 방향"

    if "왼쪽 방향" in description:
        return "왼쪽 방향"

    if "직진" in description:
        return "직진"

    if "터널" in description:
        return "터널 진입"

    if "고속도로" in description:
        return "도시고속도로 진입"

    if "도착" in description:
        return "도착"

    if description:
        return description

    return "경로를 따라 이동"


# ============================================================
# 다음 Guidance 찾기
# ============================================================

def find_next_guidance(
    navigation_guidance,
    current_route_position_m,
    passed_tolerance_m=10.0,
):

    if (
        navigation_guidance is None
        or
        current_route_position_m is None
    ):
        return None

    for guidance in navigation_guidance:

        route_position_m = (
            guidance.get(
                "route_position_m"
            )
        )

        if route_position_m is None:
            continue

        point_type = (
            guidance.get(
                "point_type"
            )
        )

        # ----------------------------------------------------
        # 시작점 Guidance는 안내 대상에서 제외
        # ----------------------------------------------------

        if point_type == "S":
            continue

        # ----------------------------------------------------
        # 현재 위치보다 뒤쪽에 완전히 지나간 Guidance는 제외
        #
        # tolerance를 약간 두는 이유:
        # GPS 위치 오차 때문에 Guidance 직전/직후가
        # 흔들리는 것을 줄이기 위함
        # ----------------------------------------------------

        if (
            float(route_position_m)
            >=
            float(current_route_position_m)
            - passed_tolerance_m
        ):
            return guidance

    return None


# ============================================================
# Turn-by-Turn 문구 생성
# ============================================================

def build_instruction_text(
    guidance,
    distance_to_next_m,
):

    if guidance is None:

        return {
            "primary_text":
                "목적지에 가까워지고 있습니다.",

            "secondary_text":
                None,

            "distance_text":
                None,
        }

    action = (
        get_maneuver_action(
            guidance
        )
    )

    distance_text = (
        format_navigation_distance(
            distance_to_next_m
        )
    )

    next_road_name = (
        guidance.get(
            "next_road_name"
        )
    )

    # --------------------------------------------------------
    # 거리 + 행동
    # --------------------------------------------------------

    if distance_text == "곧":

        primary_text = (
            f"곧 {action}"
        )

    else:

        primary_text = (
            f"{distance_text} 앞 {action}"
        )

    # --------------------------------------------------------
    # 다음 도로명
    # --------------------------------------------------------

    secondary_text = None

    if (
        next_road_name
        and
        next_road_name not in {
            "",
            "일반도로",
        }
    ):

        secondary_text = (
            f"{next_road_name} 방면"
        )

    return {
        "primary_text":
            primary_text,

        "secondary_text":
            secondary_text,

        "distance_text":
            distance_text,
    }


# ============================================================
# GPS_NOT_MATCHED 응답
# ============================================================

def build_gps_not_matched_state(
    *,
    primary_text,
    secondary_text=None,
    current_position=None,
):

    current_position = (
        current_position
        or {}
    )

    snap_distance_m = (
        current_position.get(
            "snap_distance_m"
        )
    )

    if snap_distance_m is not None:

        snap_distance_m = round(
            float(
                snap_distance_m
            ),
            1,
        )

    return {
        "status":
            "GPS_NOT_MATCHED",

        "current_route_position_m":
            current_position.get(
                "route_position_m"
            ),

        "route_geometry_index":
            current_position.get(
                "route_geometry_index"
            ),

        "gps_snap_distance_m":
            snap_distance_m,

        "distance_to_next_m":
            None,

        "next_guidance":
            None,

        "primary_text":
            primary_text,

        "secondary_text":
            secondary_text,

        "distance_text":
            None,
    }


# ============================================================
# 현재 Navigation 상태 계산
# ============================================================

def get_navigation_state(
    route,
    current_lat,
    current_lon,
):

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


    # ========================================================
    # 1. Route 없음
    # ========================================================

    if not geometry:

        return {
            "status":
                "NO_ROUTE",

            "primary_text":
                "경로 정보가 없습니다.",

            "secondary_text":
                None,

            "distance_text":
                None,

            "gps_snap_distance_m":
                None,
        }


    # ========================================================
    # 2. 현재 GPS를 Route에 Snap
    # ========================================================

    current_position = (
        find_nearest_route_position(

            float(
                current_lon
            ),

            float(
                current_lat
            ),

            geometry,

        )
    )


    # ========================================================
    # 3. Route 위치 계산 실패
    # ========================================================

    if not current_position:

        return (
            build_gps_not_matched_state(
                primary_text=(
                    "현재 위치를 경로에 "
                    "연결할 수 없습니다."
                ),
            )
        )


    current_route_position_m = (
        current_position.get(
            "route_position_m"
        )
    )

    gps_snap_distance_m = (
        current_position.get(
            "snap_distance_m"
        )
    )


    if current_route_position_m is None:

        return (
            build_gps_not_matched_state(

                primary_text=(
                    "현재 위치를 경로에 "
                    "연결할 수 없습니다."
                ),

                current_position=
                    current_position,
            )
        )


    # ========================================================
    # 4. Route 이탈 판정
    # ========================================================

    if (
        gps_snap_distance_m is not None
        and
        float(
            gps_snap_distance_m
        )
        >
        MAX_ROUTE_SNAP_DISTANCE_M
    ):

        distance_m = (
            float(
                gps_snap_distance_m
            )
        )

        if distance_m >= 1000:

            distance_text = (
                f"{distance_m / 1000.0:.1f}km"
            )

        else:

            distance_text = (
                f"{int(round(distance_m))}m"
            )

        return (
            build_gps_not_matched_state(

                primary_text=
                    "경로에서 벗어났습니다.",

                secondary_text=(
                    f"현재 위치가 경로에서 "
                    f"약 {distance_text} "
                    f"떨어져 있습니다."
                ),

                current_position=
                    current_position,
            )
        )


    # ========================================================
    # 5. 다음 Guidance 찾기
    # ========================================================

    next_guidance = (
        find_next_guidance(

            navigation_guidance,

            current_route_position_m,

        )
    )


    # ========================================================
    # 6. 다음 Guidance 없음
    #
    # Route의 모든 Guidance를 통과한 상태
    # ========================================================

    if next_guidance is None:

        return {
            "status":
                "ARRIVING",

            "current_route_position_m":
                current_route_position_m,

            "route_geometry_index":
                current_position.get(
                    "route_geometry_index"
                ),

            "gps_snap_distance_m":
                (
                    round(
                        float(
                            gps_snap_distance_m
                        ),
                        1,
                    )
                    if gps_snap_distance_m
                    is not None
                    else None
                ),

            "distance_to_next_m":
                0.0,

            "next_guidance":
                None,

            "primary_text":
                "목적지에 도착했습니다.",

            "secondary_text":
                None,

            "distance_text":
                "도착",
        }


    # ========================================================
    # 7. 다음 Guidance까지 남은 거리
    # ========================================================

    next_route_position_m = (
        next_guidance.get(
            "route_position_m"
        )
    )


    if next_route_position_m is None:

        return {
            "status":
                "NAVIGATING",

            "current_route_position_m":
                current_route_position_m,

            "route_geometry_index":
                current_position.get(
                    "route_geometry_index"
                ),

            "gps_snap_distance_m":
                (
                    round(
                        float(
                            gps_snap_distance_m
                        ),
                        1,
                    )
                    if gps_snap_distance_m
                    is not None
                    else None
                ),

            "distance_to_next_m":
                None,

            "next_guidance":
                next_guidance,

            "primary_text":
                "경로를 따라 이동하세요.",

            "secondary_text":
                None,

            "distance_text":
                None,
        }


    distance_to_next_m = max(
        0.0,

        float(
            next_route_position_m
        )
        -
        float(
            current_route_position_m
        ),
    )


    # ========================================================
    # 8. 목적지 도착 판정
    #
    # 마지막 Guidance의 point_type이 E이고
    # 목적지까지 30m 이내이면 ARRIVING
    # ========================================================

    if (
        next_guidance.get(
            "point_type"
        )
        ==
        "E"
        and
        distance_to_next_m
        <=
        ARRIVAL_THRESHOLD_M
    ):

        return {
            "status":
                "ARRIVING",

            "current_route_position_m":
                current_route_position_m,

            "route_geometry_index":
                current_position.get(
                    "route_geometry_index"
                ),

            "gps_snap_distance_m":
                (
                    round(
                        float(
                            gps_snap_distance_m
                        ),
                        1,
                    )
                    if gps_snap_distance_m
                    is not None
                    else None
                ),

            "distance_to_next_m":
                round(
                    distance_to_next_m,
                    1,
                ),

            "next_guidance":
                next_guidance,

            "primary_text":
                "목적지에 도착했습니다.",

            "secondary_text":
                None,

            "distance_text":
                "도착",
        }


    # ========================================================
    # 9. 일반 Turn-by-Turn 안내
    # ========================================================

    message = (
        build_instruction_text(

            next_guidance,

            distance_to_next_m,

        )
    )


    # ========================================================
    # 10. 정상 NAVIGATING
    # ========================================================

    return {
        "status":
            "NAVIGATING",

        "current_route_position_m":
            current_route_position_m,

        "route_geometry_index":
            current_position.get(
                "route_geometry_index"
            ),

        "gps_snap_distance_m":
            (
                round(
                    float(
                        gps_snap_distance_m
                    ),
                    1,
                )
                if gps_snap_distance_m
                is not None
                else None
            ),

        "distance_to_next_m":
            round(
                distance_to_next_m,
                1,
            ),

        "next_guidance":
            next_guidance,

        "primary_text":
            message[
                "primary_text"
            ],

        "secondary_text":
            message[
                "secondary_text"
            ],

        "distance_text":
            message[
                "distance_text"
            ],
    }