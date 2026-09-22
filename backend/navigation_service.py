from backend.services.navigation_guidance import (
    find_nearest_route_position,
)


# ============================================================
# FLOW:MATE Navigation Service
#
# 현재 GPS
# →
# Route 위 현재 위치
# →
# 다음 TMAP Guidance 탐색
# →
# 남은 거리
# →
# "100m 앞 우회전" 형태의 안내 생성
# ============================================================


# ============================================================
# 1. 거리 표시값 정리
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


    # 1km 이상
    if distance_m >= 1000:

        distance_km = (
            distance_m
            / 1000.0
        )

        return (
            f"{distance_km:.1f}km"
        )


    # 500m 이상
    if distance_m >= 500:

        rounded = (
            round(
                distance_m
                / 100.0
            )
            * 100
        )

        return (
            f"{int(rounded)}m"
        )


    # 100~500m
    if distance_m >= 100:

        rounded = (
            round(
                distance_m
                / 50.0
            )
            * 50
        )

        return (
            f"{int(rounded)}m"
        )


    # 30~100m
    if distance_m >= 30:

        rounded = (
            round(
                distance_m
                / 10.0
            )
            * 10
        )

        return (
            f"{int(rounded)}m"
        )


    # 30m 미만
    return "곧"


# ============================================================
# 2. TMAP description에서 짧은 행동명 추출
# ============================================================

def get_maneuver_action(
    guidance,
):

    description = (
        guidance.get(
            "description"
        )
        or
        ""
    )


    # description을 우선 사용
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


    # TMAP 원문을 그대로 쓰는 fallback
    if description:

        return description


    return "경로를 따라 이동"


# ============================================================
# 3. 다음 Guidance 찾기
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


        # 출발점 S는 다음 안내 대상에서 제외
        if point_type == "S":
            continue


        # 아직 지나지 않은 가장 가까운 안내
        if (
            route_position_m
            >=
            current_route_position_m
            -
            passed_tolerance_m
        ):

            return guidance


    return None


# ============================================================
# 4. 안내 메시지 생성
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
    # "곧 우회전"
    # --------------------------------------------------------

    if distance_text == "곧":

        primary_text = (
            f"곧 {action}"
        )


    # --------------------------------------------------------
    # "100m 앞 우회전"
    # --------------------------------------------------------

    else:

        primary_text = (
            f"{distance_text} 앞 {action}"
        )


    # --------------------------------------------------------
    # 도로명
    # --------------------------------------------------------

    secondary_text = None


    if (
        next_road_name
        and
        next_road_name
        not in {
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
# 5. Navigation 현재 상태 계산
# ============================================================

def get_navigation_state(
    route,
    current_lat,
    current_lon,
):

    geometry = (
        route.get(
            "geometry",
            []
        )
    )


    navigation_guidance = (
        route.get(
            "navigation_guidance",
            []
        )
    )


    # --------------------------------------------------------
    # GPS → Route 위 위치
    # --------------------------------------------------------

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


    current_route_position_m = (
        current_position.get(
            "route_position_m"
        )
    )


    # --------------------------------------------------------
    # 다음 안내 찾기
    # --------------------------------------------------------

    next_guidance = (
        find_next_guidance(

            navigation_guidance,

            current_route_position_m,

        )
    )


    # --------------------------------------------------------
    # 안내가 더 이상 없으면 도착 처리
    # --------------------------------------------------------

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
                current_position.get(
                    "snap_distance_m"
                ),

            "distance_to_next_m":
                None,

            "next_guidance":
                None,

            "primary_text":
                "목적지에 도착했습니다.",

            "secondary_text":
                None,

        }


    # --------------------------------------------------------
    # 현재 위치 → 다음 안내까지 남은 거리
    # --------------------------------------------------------

    next_route_position_m = (
        next_guidance.get(
            "route_position_m"
        )
    )


    distance_to_next_m = max(

        0.0,

        next_route_position_m
        -
        current_route_position_m,

    )


    message = (
        build_instruction_text(

            next_guidance,

            distance_to_next_m,

        )
    )


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
            current_position.get(
                "snap_distance_m"
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