import os
import json
import math
import hashlib
import shutil

from datetime import datetime


# ============================================================
# 입력 / 출력 경로
# ============================================================

ROUTE_DIR = os.path.join(
    "data",
    "routes",
)

API_DIR = os.path.join(
    "docs",
    "api",
)


# V2에서 생성한 최종 국가표준 LINK 경로
ROUTE_FILES = [
    "route_A_v2.json",
    "route_B_v2.json",
    "route_C_v2.json",
]


TRAFFIC_FORECAST_FILE = os.path.join(
    API_DIR,
    "mock_traffic_forecast.json",
)


FLOW_MAP_FEED_FILE = os.path.join(
    API_DIR,
    "mock_flow_map_feed.json",
)


# ============================================================
# 시간
#
# 현재 0분
# +5 ~ +60분
# ============================================================

OFFSETS = list(
    range(
        0,
        61,
        5,
    )
)


# ============================================================
# congestion level
#
# 0 = 원활
# 1 = 서행
# 2 = 혼잡
# ============================================================

CONGESTION_LABELS = {
    0: "smooth",
    1: "slow",
    2: "congested",
}


# ============================================================
# 경로별 혼잡 강도
#
# 테스트용 Mock 값
#
# A = 추천 경로
# B = 최소시간
# C = 최단거리
#
# 실제 AI 완성 후 제거/교체 예정
# ============================================================

ROUTE_CONGESTION_WEIGHT = {
    "A": 1.00,
    "B": 0.90,
    "C": 1.10,
}


# ============================================================
# 폴더 생성
# ============================================================

os.makedirs(
    API_DIR,
    exist_ok=True,
)


# ============================================================
# JSON 로드
# ============================================================

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


# ============================================================
# JSON 저장
# ============================================================

def save_json(
    path,
    data,
):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# 기존 파일 백업
# ============================================================

def backup_file(path):

    if not os.path.exists(
        path
    ):
        return None


    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )


    backup_path = (
        f"{path}.bak_{timestamp}"
    )


    shutil.copy2(
        path,
        backup_path,
    )


    return backup_path


# ============================================================
# deterministic 값
#
# Python 기본 hash()는 실행할 때마다 바뀔 수 있으므로
# hashlib 사용
# ============================================================

def stable_value(
    text,
    minimum=0.0,
    maximum=1.0,
):

    digest = hashlib.md5(
        text.encode(
            "utf-8"
        )
    ).hexdigest()


    integer = int(
        digest[:8],
        16,
    )


    ratio = (
        integer
        /
        0xFFFFFFFF
    )


    return (
        minimum
        +
        (
            maximum
            -
            minimum
        )
        *
        ratio
    )


# ============================================================
# 제한
# ============================================================

def clamp(
    value,
    minimum,
    maximum,
):

    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


# ============================================================
# 기준 제한속도
# ============================================================

def get_reference_speed(
    link,
):

    max_speed = link.get(
        "MAX_SPD",
        0,
    )


    try:

        max_speed = float(
            max_speed
        )

    except (
        TypeError,
        ValueError,
    ):

        max_speed = 0


    # 국가표준 데이터에 속도가 비어 있는 경우
    if max_speed <= 0:

        max_speed = 50.0


    return max_speed


# ============================================================
# congestion level 계산
#
# 제한속도 대비 현재 속도 비율
# ============================================================

def get_congestion_level(
    speed,
    reference_speed,
):

    if reference_speed <= 0:

        return 1


    ratio = (
        speed
        /
        reference_speed
    )


    if ratio >= 0.70:

        return 0


    if ratio >= 0.40:

        return 1


    return 2


# ============================================================
# 시간별 혼잡 강도
#
# 0분       → 낮음
# +30분     → 최고
# +60분     → 다시 완화
#
# 테스트용 Mock 패턴
# ============================================================

def get_time_peak(
    offset_min,
):

    if offset_min <= 0:

        return 0.0


    radians = (
        math.pi
        *
        offset_min
        /
        60
    )


    return max(
        0.0,
        math.sin(
            radians
        ),
    )


# ============================================================
# LINK 한 개의 시점별 Mock 교통상태 생성
# ============================================================

def build_link_forecast(
    candidate_id,
    link,
):

    link_id = str(
        link.get(
            "LINK_ID",
            ""
        )
    )


    reference_speed = (
        get_reference_speed(
            link
        )
    )


    # --------------------------------------------------------
    # 링크마다 서로 다른 기본 교통상태를 주기 위한 값
    # --------------------------------------------------------

    link_variation = stable_value(
        f"{candidate_id}:{link_id}:base",
        0.02,
        0.22,
    )


    # --------------------------------------------------------
    # 각 링크의 FLOW 효과 차이
    # --------------------------------------------------------

    flow_effect = stable_value(
        f"{candidate_id}:{link_id}:flow",
        0.30,
        0.55,
    )


    route_weight = (
        ROUTE_CONGESTION_WEIGHT.get(
            candidate_id,
            1.0,
        )
    )


    forecast = []


    for offset_min in OFFSETS:

        peak = get_time_peak(
            offset_min
        )


        # ====================================================
        # BEFORE
        #
        # FLOW를 적용하지 않은 미래교통
        # ====================================================

        congestion_pressure = (

            link_variation

            +

            peak
            *
            0.55
            *
            route_weight
        )


        congestion_pressure = clamp(
            congestion_pressure,
            0.0,
            0.80,
        )


        before_speed = (

            reference_speed

            *
            (
                1.0
                -
                congestion_pressure
            )
        )


        # 너무 비현실적으로 낮아지는 것 방지
        before_speed = clamp(
            before_speed,
            8.0,
            reference_speed,
        )


        # ====================================================
        # AFTER
        #
        # FLOW 참여로 혼잡 손실의 일부가 회복되었다고 가정
        #
        # 현재(0분)는 Before / After 동일
        # ====================================================

        if offset_min == 0:

            after_speed = (
                before_speed
            )

        else:

            lost_speed = (

                reference_speed

                -
                before_speed
            )


            recovered_speed = (

                lost_speed

                *
                flow_effect
            )


            after_speed = (

                before_speed

                +
                recovered_speed
            )


            after_speed = clamp(
                after_speed,
                8.0,
                reference_speed,
            )


        # ====================================================
        # 등급
        # ====================================================

        before_level = (
            get_congestion_level(
                before_speed,
                reference_speed,
            )
        )


        after_level = (
            get_congestion_level(
                after_speed,
                reference_speed,
            )
        )


        forecast.append({

            "offset_min":
                offset_min,


            "before": {

                "speed_kmh":
                    round(
                        before_speed,
                        1,
                    ),

                "congestion_level":
                    before_level,

                "congestion_label":
                    CONGESTION_LABELS[
                        before_level
                    ],
            },


            "after": {

                "speed_kmh":
                    round(
                        after_speed,
                        1,
                    ),

                "congestion_level":
                    after_level,

                "congestion_label":
                    CONGESTION_LABELS[
                        after_level
                    ],
            },
        })


    return forecast


# ============================================================
# V2 경로 → FLOW Mock 경로
# ============================================================

def build_route_data(
    route_data,
):

    route_id = route_data.get(
        "route_id"
    )


    candidate_id = str(
        route_data.get(
            "candidate_id",
            "?"
        )
    )


    mapping = route_data.get(
        "link_mapping_v2",
        {},
    )


    link_sequence = mapping.get(
        "link_sequence",
        [],
    )


    if not link_sequence:

        raise ValueError(
            f"{route_id}: "
            "link_mapping_v2.link_sequence가 없습니다."
        )


    flow_links = []

    traffic_links = []


    for link in link_sequence:

        link_id = str(
            link.get(
                "LINK_ID",
                ""
            )
        )


        if not link_id:

            continue


        forecast = (
            build_link_forecast(
                candidate_id,
                link,
            )
        )


        # ====================================================
        # 지도용
        # ====================================================

        flow_links.append({

            "sequence":
                link.get(
                    "sequence"
                ),

            "link_id":
                link_id,

            "road_name":
                link.get(
                    "ROAD_NAME",
                    ""
                ),

            "f_node":
                link.get(
                    "F_NODE"
                ),

            "t_node":
                link.get(
                    "T_NODE"
                ),

            "length_m":
                link.get(
                    "LENGTH"
                ),

            "max_speed_kmh":
                link.get(
                    "MAX_SPD"
                ),

            "geometry":
                link.get(
                    "geometry"
                ),

            "forecast":
                forecast,
        })


        # ====================================================
        # AI / 교통 예측용
        # ====================================================

        traffic_links.append({

            "sequence":
                link.get(
                    "sequence"
                ),

            "link_id":
                link_id,

            "road_name":
                link.get(
                    "ROAD_NAME",
                    ""
                ),

            "max_speed_kmh":
                link.get(
                    "MAX_SPD"
                ),

            "forecast":
                forecast,
        })


    route_common = {

        "route_id":
            route_id,

        "candidate_id":
            candidate_id,

        "source":
            route_data.get(
                "source",
                "TMAP"
            ),

        "search_option":
            route_data.get(
                "search_option"
            ),

        "search_option_name":
            route_data.get(
                "search_option_name"
            ),

        "origin":
            route_data.get(
                "origin",
                {}
            ),

        "destination":
            route_data.get(
                "destination",
                {}
            ),

        "summary":
            route_data.get(
                "summary",
                {}
            ),

        "link_count":
            len(
                flow_links
            ),

        "mapping_quality": {

            "quality":
                mapping.get(
                    "quality"
                ),

            "coverage_percent":
                mapping.get(
                    "coverage_percent"
                ),

            "connectivity_percent":
                mapping.get(
                    "connectivity_percent"
                ),

            "length_ratio":
                mapping.get(
                    "length_ratio"
                ),
        },
    }


    flow_route = {
        **route_common,

        "links":
            flow_links,
    }


    traffic_route = {

        "route_id":
            route_id,

        "candidate_id":
            candidate_id,

        "link_count":
            len(
                traffic_links
            ),

        "links":
            traffic_links,
    }


    return (
        flow_route,
        traffic_route,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "======================================"
    )

    print(
        "FLOW A/B/C Multi Route Mock 생성"
    )

    print(
        "======================================"
    )


    # ========================================================
    # 입력 파일 확인
    # ========================================================

    for filename in ROUTE_FILES:

        path = os.path.join(
            ROUTE_DIR,
            filename,
        )


        if not os.path.exists(
            path
        ):

            print()
            print(
                "❌ 입력 파일 없음:"
            )

            print(
                path
            )

            return


    # ========================================================
    # 기존 Mock 백업
    # ========================================================

    forecast_backup = (
        backup_file(
            TRAFFIC_FORECAST_FILE
        )
    )


    map_backup = (
        backup_file(
            FLOW_MAP_FEED_FILE
        )
    )


    if forecast_backup:

        print()
        print(
            "기존 Traffic Forecast 백업:"
        )

        print(
            forecast_backup
        )


    if map_backup:

        print()
        print(
            "기존 FLOW Map Feed 백업:"
        )

        print(
            map_backup
        )


    # ========================================================
    # 전체 데이터
    # ========================================================

    flow_routes = []

    traffic_routes = []


    for filename in ROUTE_FILES:

        path = os.path.join(
            ROUTE_DIR,
            filename,
        )


        print()
        print(
            "--------------------------------------"
        )

        print(
            "읽는 중:",
            filename
        )


        route_data = load_json(
            path
        )


        (
            flow_route,
            traffic_route,
        ) = build_route_data(
            route_data
        )


        flow_routes.append(
            flow_route
        )


        traffic_routes.append(
            traffic_route
        )


        print(
            "경로:",
            flow_route[
                "candidate_id"
            ]
        )


        print(
            "route_id:",
            flow_route[
                "route_id"
            ]
        )


        print(
            "LINK:",
            flow_route[
                "link_count"
            ],
            "개"
        )


        print(
            "Coverage:",
            flow_route[
                "mapping_quality"
            ][
                "coverage_percent"
            ],
            "%"
        )


        print(
            "연결률:",
            flow_route[
                "mapping_quality"
            ][
                "connectivity_percent"
            ],
            "%"
        )


    generated_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )


    # ========================================================
    # mock_traffic_forecast.json
    # ========================================================

    traffic_output = {

        "schema_version":
            "2.0",

        "generated_at":
            generated_at,

        "data_type":
            "FLOW multi-route mock traffic forecast",

        "mock_data":
            True,

        "offsets_min":
            OFFSETS,

        "scenarios": [
            "before",
            "after",
        ],

        "routes":
            traffic_routes,
    }


    # ========================================================
    # mock_flow_map_feed.json
    # ========================================================

    map_output = {

        "schema_version":
            "2.0",

        "generated_at":
            generated_at,

        "data_type":
            "FLOW multi-route map feed",

        "mock_data":
            True,

        "offsets_min":
            OFFSETS,

        "scenarios": [
            "before",
            "after",
        ],

        "routes":
            flow_routes,
    }


    # ========================================================
    # 저장
    # ========================================================

    save_json(
        TRAFFIC_FORECAST_FILE,
        traffic_output,
    )


    save_json(
        FLOW_MAP_FEED_FILE,
        map_output,
    )


    # ========================================================
    # 결과
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "Multi Route Mock 생성 완료"
    )

    print(
        "======================================"
    )


    print()
    print(
        "경로 개수:",
        len(
            flow_routes
        )
    )


    for route in flow_routes:

        print(
            f"경로 {route['candidate_id']}"
            f" → {route['route_id']}"
            f" → LINK {route['link_count']}개"
        )


    print()
    print(
        "시간 시점:"
    )

    print(
        OFFSETS
    )


    print()
    print(
        "Scenario:"
    )

    print(
        "before / after"
    )


    print()
    print(
        "Traffic Forecast:"
    )

    print(
        TRAFFIC_FORECAST_FILE
    )


    print()
    print(
        "FLOW Map Feed:"
    )

    print(
        FLOW_MAP_FEED_FILE
    )


    print()
    print(
        "✅ A/B/C + 0~60분 + Before/After 생성 완료"
    )


if __name__ == "__main__":
    main()