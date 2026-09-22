from tmap_service import (
    search_place,
    get_route
)

from route_exporter import (
    build_route_json,
    save_route_json
)


# ============================================================
# FLOW TMAP Route Export Test
# ============================================================

print()
print(
    "======================================"
)

print(
    "FLOW TMAP 경로 JSON 생성 테스트"
)

print(
    "======================================"
)


# ============================================================
# 1. 출발지 검색
# ============================================================

print()
print(
    "[1] 출발지 검색"
)


origin = search_place(
    "성남시청"
)


if origin is None:

    print(
        "성남시청 검색 실패"
    )

    exit()


print()
print(
    "출발지:",
    origin["name"]
)

print(
    "위도:",
    origin["latitude"]
)

print(
    "경도:",
    origin["longitude"]
)


# ============================================================
# 2. 목적지 검색
# ============================================================

print()
print(
    "[2] 목적지 검색"
)


destination = search_place(
    "판교역"
)


if destination is None:

    print(
        "판교역 검색 실패"
    )

    exit()


print()
print(
    "목적지:",
    destination["name"]
)

print(
    "위도:",
    destination["latitude"]
)

print(
    "경도:",
    destination["longitude"]
)


# ============================================================
# 3. TMAP 자동차 경로 탐색
# ============================================================

print()
print(
    "[3] TMAP 경로 탐색"
)


route = get_route(

    origin["longitude"],
    origin["latitude"],

    destination["longitude"],
    destination["latitude"],

    destination["name"]
)


if route is None:

    print(
        "TMAP 경로 탐색 실패"
    )

    exit()


print()
print(
    "총 거리:",
    route["distance_km"],
    "km"
)

print(
    "총 시간:",
    route["time_min"],
    "분"
)


# ============================================================
# 4. FLOW 표준 Route JSON 생성
# ============================================================

print()
print(
    "[4] FLOW Route JSON 생성"
)


route_json = build_route_json(

    route_id=
        "route_test_001",

    candidate_id=
        "A",

    origin=origin,

    destination=destination,

    tmap_route=route
)


# ============================================================
# 5. JSON 저장
# ============================================================

output_path = (
    "data/routes/"
    "route_test_001.json"
)


save_route_json(

    route_json,

    output_path
)


# ============================================================
# 완료
# ============================================================

print()
print(
    "======================================"
)

print(
    "테스트 완료"
)

print(
    "======================================"
)

print()
print(
    "다음 파일을 확인하세요:"
)

print(
    output_path
)