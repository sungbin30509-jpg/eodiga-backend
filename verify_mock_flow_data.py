import os
import json


# ============================================================
# 파일 경로
# ============================================================

TRAFFIC_FILE = os.path.join(
    "docs",
    "api",
    "mock_traffic_forecast.json"
)

MAP_FILE = os.path.join(
    "docs",
    "api",
    "mock_flow_map_feed.json"
)


EXPECTED_OFFSETS = [
    5, 10, 15, 20, 25, 30,
    35, 40, 45, 50, 55, 60
]

EXPECTED_TIMELINE = [
    0, 5, 10, 15, 20, 25, 30,
    35, 40, 45, 50, 55, 60
]


# ============================================================
# 시작
# ============================================================

print()
print("======================================")
print("FLOW Mock 데이터 검증")
print("======================================")


# ============================================================
# 파일 존재 여부
# ============================================================

if not os.path.exists(TRAFFIC_FILE):

    print("❌ 파일 없음:")
    print(TRAFFIC_FILE)

    raise SystemExit


if not os.path.exists(MAP_FILE):

    print("❌ 파일 없음:")
    print(MAP_FILE)

    raise SystemExit


print()
print("✅ JSON 파일 존재 확인 완료")


# ============================================================
# JSON 읽기
# ============================================================

with open(
    TRAFFIC_FILE,
    "r",
    encoding="utf-8"
) as file:

    traffic_data = json.load(file)


with open(
    MAP_FILE,
    "r",
    encoding="utf-8"
) as file:

    map_data = json.load(file)


# ============================================================
# Traffic Forecast 검사
# ============================================================

print()
print("======================================")
print("1. Traffic Forecast 검사")
print("======================================")


traffic_links = traffic_data.get(
    "links",
    []
)


print(
    "LINK 개수:",
    len(traffic_links)
)


offsets = traffic_data.get(
    "time_offsets_min",
    []
)


print(
    "미래 시점:",
    offsets
)


if offsets == EXPECTED_OFFSETS:

    print(
        "✅ +5 ~ +60분 정상"
    )

else:

    print(
        "❌ 미래 시점 구조 이상"
    )


# ============================================================
# 각 LINK의 forecast 검사
# ============================================================

forecast_error_count = 0

before_after_speed_change_count = 0

before_after_congestion_change_count = 0


for link in traffic_links:

    forecasts = link.get(
        "forecast",
        []
    )


    if len(forecasts) != 12:

        forecast_error_count += 1


    for forecast in forecasts:

        before = forecast.get(
            "before",
            {}
        )

        after = forecast.get(
            "after",
            {}
        )


        before_speed = before.get(
            "speed_kmh"
        )

        after_speed = after.get(
            "speed_kmh"
        )


        if (
            before_speed is not None
            and
            after_speed is not None
            and
            before_speed != after_speed
        ):

            before_after_speed_change_count += 1


        before_level = before.get(
            "congestion_level"
        )

        after_level = after.get(
            "congestion_level"
        )


        if (
            before_level is not None
            and
            after_level is not None
            and
            before_level != after_level
        ):

            before_after_congestion_change_count += 1


print()
print(
    "forecast 구조 오류 LINK:",
    forecast_error_count,
    "개"
)


print(
    "Before/After 속도 변화:",
    before_after_speed_change_count,
    "개 시점"
)


print(
    "Before/After 혼잡등급 변화:",
    before_after_congestion_change_count,
    "개 시점"
)


# ============================================================
# Map Feed 검사
# ============================================================

print()
print("======================================")
print("2. FLOW Map Feed 검사")
print("======================================")


routes = map_data.get(
    "routes",
    []
)


print(
    "경로 개수:",
    len(routes)
)


if len(routes) == 0:

    print(
        "❌ route가 없습니다."
    )

    raise SystemExit


route = routes[0]


print(
    "route_id:",
    route.get(
        "route_id"
    )
)


print(
    "candidate_id:",
    route.get(
        "candidate_id"
    )
)


map_links = route.get(
    "links",
    []
)


print(
    "지도 LINK:",
    len(map_links),
    "개"
)


# ============================================================
# Slider 검사
# ============================================================

slider = map_data.get(
    "time_slider",
    {}
)


slider_values = slider.get(
    "values",
    []
)


print()
print(
    "Slider:",
    slider_values
)


if slider_values == EXPECTED_TIMELINE:

    print(
        "✅ 0 ~ 60분 5분 단위 정상"
    )

else:

    print(
        "❌ Slider 값 이상"
    )


# ============================================================
# Geometry 검사
# ============================================================

geometry_success = 0

geometry_error = 0


for link in map_links:

    geometry = link.get(
        "geometry"
    )


    if not geometry:

        geometry_error += 1
        continue


    geometry_type = geometry.get(
        "type"
    )


    coordinates = geometry.get(
        "coordinates",
        []
    )


    if (
        geometry_type == "LineString"
        and
        len(coordinates) >= 2
    ):

        geometry_success += 1

    else:

        geometry_error += 1


print()
print(
    "정상 Geometry:",
    geometry_success,
    "개"
)


print(
    "Geometry 오류:",
    geometry_error,
    "개"
)


# ============================================================
# Timeline 검사
# ============================================================

timeline_error_count = 0


expected_keys = {

    str(value)

    for value
    in EXPECTED_TIMELINE
}


for link in map_links:

    timeline = link.get(
        "timeline",
        {}
    )


    actual_keys = set(
        timeline.keys()
    )


    if actual_keys != expected_keys:

        timeline_error_count += 1
        continue


    for value in EXPECTED_TIMELINE:

        state = timeline.get(
            str(value),
            {}
        )


        if (
            "before" not in state
            or
            "after" not in state
        ):

            timeline_error_count += 1
            break


print()
print(
    "Timeline 오류 LINK:",
    timeline_error_count,
    "개"
)


# ============================================================
# 첫 번째 LINK 예시 출력
# ============================================================

if len(map_links) > 0:

    example = map_links[0]

    print()
    print("======================================")
    print("3. 첫 번째 LINK 예시")
    print("======================================")

    print(
        "LINK_ID:",
        example.get(
            "link_id"
        )
    )

    print(
        "도로명:",
        example.get(
            "road_name"
        )
    )


    timeline = example.get(
        "timeline",
        {}
    )


    for offset in [
        0,
        5,
        30,
        60
    ]:

        state = timeline.get(
            str(offset),
            {}
        )


        print()
        print(
            f"[+{offset}분]"
        )

        print(
            "Before:",
            state.get(
                "before"
            )
        )

        print(
            "After :",
            state.get(
                "after"
            )
        )


# ============================================================
# 최종 판정
# ============================================================

print()
print("======================================")
print("최종 검증 결과")
print("======================================")


success = True


if len(traffic_links) != 46:

    print(
        "❌ Traffic LINK 개수가 46개가 아닙니다."
    )

    success = False


if len(map_links) != 46:

    print(
        "❌ Map LINK 개수가 46개가 아닙니다."
    )

    success = False


if forecast_error_count > 0:

    print(
        "❌ Forecast 구조에 문제가 있습니다."
    )

    success = False


if geometry_error > 0:

    print(
        "❌ Geometry에 문제가 있습니다."
    )

    success = False


if timeline_error_count > 0:

    print(
        "❌ Timeline 구조에 문제가 있습니다."
    )

    success = False


if offsets != EXPECTED_OFFSETS:

    success = False


if slider_values != EXPECTED_TIMELINE:

    success = False


if success:

    print()
    print(
        "✅ FLOW Mock 데이터 구조 정상"
    )

    print(
        "✅ 46개 LINK"
    )

    print(
        "✅ +5 ~ +60분 12개 미래 시점"
    )

    print(
        "✅ Before / After"
    )

    print(
        "✅ 국가표준 LINK Geometry"
    )

    print(
        "✅ Flutter 시간 Slider 사용 가능"
    )


else:

    print()
    print(
        "⚠️ 일부 데이터를 수정해야 합니다."
    )