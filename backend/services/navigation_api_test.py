import requests

from backend.services.location_service import (
    resolve_location,
)

from backend.services.route_engine import (
    request_tmap_route,
)


API_BASE_URL = "http://127.0.0.1:8000"


def main():

    print()
    print("========================================")
    print("FLOW:MATE Navigation API Test")
    print("========================================")
    print()


    # ========================================================
    # 1. 출발지 / 목적지
    # ========================================================

    print("[1] 장소 확인")

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


    # ========================================================
    # 2. Route A 생성
    # ========================================================

    print("[2] TMAP Route A 요청")

    route = request_tmap_route(
        origin,
        destination,
        "A",
    )

    print(
        "Route:",
        route.get("candidate_id")
    )

    print(
        "Distance:",
        route.get("total_distance_m"),
        "m"
    )

    print(
        "ETA:",
        route.get("tmap_eta_min"),
        "min"
    )

    print(
        "Geometry:",
        route.get(
            "geometry_point_count"
        )
    )

    print(
        "Guidance:",
        route.get(
            "navigation_guidance_count"
        )
    )

    print()


    # ========================================================
    # 3. Navigation Start
    # ========================================================

    print(
        "[3] POST /api/navigation/start"
    )

    response = requests.post(

        f"{API_BASE_URL}/api/navigation/start",

        json={
            "route": route,
        },

        timeout=30,

    )

    print(
        "HTTP:",
        response.status_code
    )

    print(
        "Response:",
        response.text
    )

    print()


    if response.status_code != 200:

        raise RuntimeError(
            "Navigation Start 실패"
        )


    start_result = (
        response.json()
    )

    session_id = (
        start_result[
            "session_id"
        ]
    )

    print(
        "Session ID:",
        session_id
    )

    print()


    # ========================================================
    # 4. Route 시작 좌표를 가상 GPS로 사용
    # ========================================================

    geometry = route[
        "geometry"
    ]

    first_point = (
        geometry[0]
    )

    current_lon = float(
        first_point[0]
    )

    current_lat = float(
        first_point[1]
    )


    # ========================================================
    # 5. Navigation Update
    # ========================================================

    print(
        "[4] POST /api/navigation/update"
    )

    update_response = requests.post(

        f"{API_BASE_URL}/api/navigation/update",

        json={

            "session_id":
                session_id,

            "current_lat":
                current_lat,

            "current_lon":
                current_lon,

        },

        timeout=30,

    )

    print(
        "HTTP:",
        update_response.status_code
    )

    print()


    if update_response.status_code != 200:

        print(
            update_response.text
        )

        raise RuntimeError(
            "Navigation Update 실패"
        )


    state = (
        update_response.json()
    )


    print(
        "Status:",
        state.get(
            "status"
        )
    )

    print(
        "현재 Route 위치:",
        state.get(
            "current_route_position_m"
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

    print()

    print(
        "▶",
        state.get(
            "primary_text"
        )
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


    next_guidance = (
        state.get(
            "next_guidance"
        )
    )


    if next_guidance:

        print()

        print(
            "turnType:",
            next_guidance.get(
                "turn_type"
            )
        )

        print(
            "TMAP:",
            next_guidance.get(
                "description"
            )
        )


    print()

    print(
        "========================================"
    )

    print(
        "Navigation API Test 성공"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()