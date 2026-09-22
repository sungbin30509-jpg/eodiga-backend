import os
import json
import math
from datetime import datetime

import pandas as pd
import pyogrio

from pyproj import CRS
from pyproj import Transformer

from shapely.geometry import LineString
from shapely.geometry import mapping
from shapely.ops import transform


# ============================================================
# 파일 경로
# ============================================================

ROUTE_FILE = os.path.join(
    "data",
    "routes",
    "route_test_001_repaired.json"
)

LINK_FILE = os.path.join(
    "data",
    "national_links",
    "MOCT_LINK.shp"
)

TRAFFIC_OUTPUT = os.path.join(
    "docs",
    "api",
    "mock_traffic_forecast.json"
)

MAP_OUTPUT = os.path.join(
    "docs",
    "api",
    "mock_flow_map_feed.json"
)


# ============================================================
# 시간 설정
#
# +5, +10, +15 ... +60
# 총 12개 시점
# ============================================================

TIME_OFFSETS = list(
    range(5, 61, 5)
)


# ============================================================
# LINK_ID 정리
# ============================================================

def normalize_id(value):

    if value is None:
        return ""

    text = str(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


# ============================================================
# 숫자 안전 변환
# ============================================================

def to_float(
    value,
    default_value
):

    try:

        if pd.isna(value):
            return float(default_value)

        return float(value)

    except (
        TypeError,
        ValueError
    ):

        return float(default_value)


# ============================================================
# 혼잡 단계 판정
#
# 속도 / 제한속도 비율 기준
#
# 0 = 원활
# 1 = 서행
# 2 = 혼잡
# ============================================================

def get_congestion(
    speed,
    speed_limit
):

    if speed_limit <= 0:
        speed_limit = 60


    ratio = (
        speed
        /
        speed_limit
    )


    if ratio >= 0.72:

        return {
            "level": 0,
            "label": "smooth"
        }


    elif ratio >= 0.45:

        return {
            "level": 1,
            "label": "slow"
        }


    else:

        return {
            "level": 2,
            "label": "congested"
        }


# ============================================================
# Mock 현재속도 생성
#
# 실제 AI가 완성되면 이 부분을
# 실제 교통 데이터로 교체하면 됨
# ============================================================

def make_current_speed(
    speed_limit,
    sequence
):

    # LINK마다 약간 다른 현재 상태를 만들어
    # 지도에서 모든 도로가 똑같이 보이지 않게 함

    variation = (
        sequence % 6
    ) * 0.035


    ratio = (
        0.78
        -
        variation
    )


    speed = (
        speed_limit
        *
        ratio
    )


    return round(
        max(
            10,
            speed
        ),
        1
    )


# ============================================================
# Mock 미래속도 생성
#
# Before:
# 퇴근시간 혼잡이 증가한다고 가정
#
# After:
# FLOW 참여로 혼잡 일부 완화
#
# 실제 AI가 완성되면
# 이 함수 결과만 교체하면 됨
# ============================================================

def make_forecast_speed(
    current_speed,
    speed_limit,
    offset_min,
    sequence,
    scenario
):

    # --------------------------------------------------------
    # 30~40분 부근에 혼잡이 커지는 형태
    # --------------------------------------------------------

    wave = math.sin(
        math.pi
        *
        offset_min
        /
        60
    )


    # 도로마다 약간 다른 혼잡 강도
    link_factor = (
        0.85
        +
        (
            sequence % 7
        ) * 0.035
    )


    congestion_drop = (
        speed_limit
        *
        0.30
        *
        wave
        *
        link_factor
    )


    # ========================================================
    # FLOW 적용 전
    # ========================================================

    before_speed = (
        current_speed
        -
        congestion_drop
    )


    before_speed = max(
        8,
        before_speed
    )


    # ========================================================
    # FLOW 적용 후
    #
    # 혼잡으로 감소한 속도의 일부가 회복된다고 가정
    # ========================================================

    recovered_speed = (
        congestion_drop
        *
        0.45
    )


    after_speed = (
        before_speed
        +
        recovered_speed
    )


    after_speed = min(
        speed_limit,
        after_speed
    )


    if scenario == "before":

        return round(
            before_speed,
            1
        )


    return round(
        after_speed,
        1
    )


# ============================================================
# 파일 확인
# ============================================================

print()
print(
    "======================================"
)

print(
    "FLOW Mock Traffic 데이터 생성"
)

print(
    "======================================"
)


if not os.path.exists(
    ROUTE_FILE
):

    print(
        "최종 Route JSON이 없습니다."
    )

    print(
        ROUTE_FILE
    )

    raise SystemExit


if not os.path.exists(
    LINK_FILE
):

    print(
        "국가표준 LINK 파일이 없습니다."
    )

    print(
        LINK_FILE
    )

    raise SystemExit


# ============================================================
# Route JSON 읽기
# ============================================================

with open(
    ROUTE_FILE,
    "r",
    encoding="utf-8"
) as file:

    route_data = json.load(
        file
    )


route_id = route_data.get(
    "route_id",
    "route_test_001"
)


candidate_id = route_data.get(
    "candidate_id",
    "A"
)


# ============================================================
# 최종 국가표준 LINK sequence 가져오기
# ============================================================

link_mapping = route_data.get(
    "link_mapping",
    {}
)


link_sequence = link_mapping.get(
    "link_sequence",
    []
)


if len(link_sequence) == 0:

    print(
        "최종 LINK sequence가 없습니다."
    )

    raise SystemExit


print()
print(
    "route_id:",
    route_id
)

print(
    "candidate_id:",
    candidate_id
)

print(
    "최종 LINK:",
    len(link_sequence),
    "개"
)


# ============================================================
# LINK_ID 목록
# ============================================================

matched_link_ids = [

    normalize_id(
        item.get(
            "LINK_ID"
        )
    )

    for item
    in link_sequence
]


matched_link_id_set = set(
    matched_link_ids
)


# ============================================================
# TMAP 경로 geometry
# ============================================================

route_coordinates = (
    route_data
    .get(
        "geometry",
        {}
    )
    .get(
        "coordinates",
        []
    )
)


if len(route_coordinates) < 2:

    print(
        "TMAP 경로 geometry가 없습니다."
    )

    raise SystemExit


route_wgs84 = LineString(
    route_coordinates
)


# ============================================================
# 국가표준 LINK 좌표계
# ============================================================

link_info = pyogrio.read_info(
    LINK_FILE
)


link_crs = CRS.from_user_input(
    link_info["crs"]
)


# ============================================================
# TMAP 경로를 국가표준 좌표계로 변환
# ============================================================

to_link_crs = Transformer.from_crs(

    "EPSG:4326",

    link_crs,

    always_xy=True
)


route_projected = transform(

    to_link_crs.transform,

    route_wgs84
)


# ============================================================
# 경로 주변 LINK만 읽기
# ============================================================

bbox = (
    route_projected
    .buffer(
        250
    )
    .bounds
)


print()
print(
    "국가표준 LINK geometry 읽는 중..."
)


links = pyogrio.read_dataframe(

    LINK_FILE,

    bbox=bbox,

    columns=[
        "LINK_ID",
        "ROAD_NAME",
        "LENGTH",
        "MAX_SPD"
    ]
)


links["LINK_ID"] = (
    links["LINK_ID"]
    .apply(
        normalize_id
    )
)


# ============================================================
# 우리가 사용하는 46개 LINK만 남김
# ============================================================

links = links[
    links["LINK_ID"]
    .isin(
        matched_link_id_set
    )
].copy()


print(
    "Geometry 확보 LINK:",
    len(links),
    "개"
)


# ============================================================
# 국가표준 LINK → WGS84
# ============================================================

to_wgs84 = Transformer.from_crs(

    link_crs,

    "EPSG:4326",

    always_xy=True
)


# ============================================================
# LINK lookup
# ============================================================

link_lookup = {}


for _, row in links.iterrows():


    geometry_wgs84 = transform(

        to_wgs84.transform,

        row.geometry
    )


    link_lookup[
        row["LINK_ID"]
    ] = {

        "road_name":
            (
                ""
                if pd.isna(
                    row["ROAD_NAME"]
                )
                else str(
                    row["ROAD_NAME"]
                )
            ),

        "length_m":
            to_float(
                row["LENGTH"],
                row.geometry.length
            ),

        "speed_limit_kmh":
            to_float(
                row["MAX_SPD"],
                60
            ),

        "geometry":
            mapping(
                geometry_wgs84
            )
    }


# ============================================================
# Mock Traffic Forecast 생성
# ============================================================

traffic_links = []


for sequence_index, sequence_item in enumerate(
    link_sequence
):


    link_id = normalize_id(
        sequence_item.get(
            "LINK_ID"
        )
    )


    link_info_data = link_lookup.get(
        link_id,
        {}
    )


    road_name = link_info_data.get(
        "road_name"
    )


    if not road_name:

        road_name = sequence_item.get(
            "ROAD_NAME",
            ""
        )


    speed_limit = link_info_data.get(
        "speed_limit_kmh",
        60
    )


    if speed_limit <= 0:

        speed_limit = 60


    current_speed = (
        make_current_speed(
            speed_limit,
            sequence_index
        )
    )


    current_congestion = (
        get_congestion(
            current_speed,
            speed_limit
        )
    )


    forecasts = []


    # ========================================================
    # +5 ~ +60
    # ========================================================

    for offset_min in TIME_OFFSETS:


        before_speed = (
            make_forecast_speed(

                current_speed,

                speed_limit,

                offset_min,

                sequence_index,

                "before"
            )
        )


        after_speed = (
            make_forecast_speed(

                current_speed,

                speed_limit,

                offset_min,

                sequence_index,

                "after"
            )
        )


        before_congestion = (
            get_congestion(
                before_speed,
                speed_limit
            )
        )


        after_congestion = (
            get_congestion(
                after_speed,
                speed_limit
            )
        )


        forecasts.append({

            "offset_min":
                offset_min,

            "before": {

                "speed_kmh":
                    before_speed,

                "congestion_level":
                    before_congestion[
                        "level"
                    ],

                "congestion_label":
                    before_congestion[
                        "label"
                    ]
            },

            "after": {

                "speed_kmh":
                    after_speed,

                "congestion_level":
                    after_congestion[
                        "level"
                    ],

                "congestion_label":
                    after_congestion[
                        "label"
                    ]
            }
        })


    traffic_links.append({

        "sequence":
            sequence_index,

        "link_id":
            link_id,

        "road_name":
            road_name,

        "speed_limit_kmh":
            speed_limit,

        "current": {

            "speed_kmh":
                current_speed,

            "congestion_level":
                current_congestion[
                    "level"
                ],

            "congestion_label":
                current_congestion[
                    "label"
                ]
        },

        "forecast":
            forecasts
    })


# ============================================================
# mock_traffic_forecast.json
# ============================================================

traffic_output = {

    "schema_version":
        "1.0",

    "data_mode":
        "mock",

    "description":
        (
            "FLOW 지도 및 Flutter UI 검증용 "
            "모의 교통예측 데이터"
        ),

    "generated_at":
        datetime.now()
        .astimezone()
        .isoformat(),

    "route_id":
        route_id,

    "interval_min":
        5,

    "horizon_min":
        60,

    "time_offsets_min":
        TIME_OFFSETS,

    "scenario_options": [
        "before",
        "after"
    ],

    "links":
        traffic_links
}


# ============================================================
# traffic lookup
# ============================================================

traffic_lookup = {

    item["link_id"]:
        item

    for item
    in traffic_links
}


# ============================================================
# Flutter 지도용 Link 데이터 생성
# ============================================================

map_links = []


for sequence_index, sequence_item in enumerate(
    link_sequence
):


    link_id = normalize_id(
        sequence_item.get(
            "LINK_ID"
        )
    )


    link_info_data = (
        link_lookup.get(
            link_id,
            {}
        )
    )


    traffic_data = (
        traffic_lookup.get(
            link_id
        )
    )


    if traffic_data is None:

        continue


    # ========================================================
    # 0분 = 현재
    #
    # 현재 상태에서는 Before/After가 동일하게 시작
    # ========================================================

    timeline = {

        "0": {

            "before":
                traffic_data[
                    "current"
                ],

            "after":
                traffic_data[
                    "current"
                ]
        }

    }


    # ========================================================
    # +5 ~ +60분
    # ========================================================

    for forecast in traffic_data[
        "forecast"
    ]:


        key = str(
            forecast[
                "offset_min"
            ]
        )


        timeline[
            key
        ] = {

            "before":
                forecast[
                    "before"
                ],

            "after":
                forecast[
                    "after"
                ]
        }


    map_links.append({

        "sequence":
            sequence_index,

        "link_id":
            link_id,

        "road_name":
            traffic_data[
                "road_name"
            ],

        "geometry":
            link_info_data.get(
                "geometry"
            ),

        "timeline":
            timeline
    })


# ============================================================
# Flutter에서 바로 사용할 Map Feed
#
# route 배열 구조로 만들어
# 나중에 A/B/C 추가 가능
# ============================================================

map_output = {

    "schema_version":
        "1.0",

    "data_mode":
        "mock",

    "generated_at":
        datetime.now()
        .astimezone()
        .isoformat(),

    "time_slider": {

        "min_offset_min":
            0,

        "max_offset_min":
            60,

        "step_min":
            5,

        "values": [
            0,
            *TIME_OFFSETS
        ]
    },

    "scenario_options": [
        "before",
        "after"
    ],

    "routes": [

        {

            "route_id":
                route_id,

            "candidate_id":
                candidate_id,

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

            "geometry":
                route_data.get(
                    "geometry",
                    {}
                ),

            "link_count":
                len(
                    map_links
                ),

            "links":
                map_links
        }

    ]
}


# ============================================================
# 출력 폴더 생성
# ============================================================

os.makedirs(
    os.path.dirname(
        TRAFFIC_OUTPUT
    ),
    exist_ok=True
)


# ============================================================
# JSON 저장
# ============================================================

with open(
    TRAFFIC_OUTPUT,
    "w",
    encoding="utf-8"
) as file:

    json.dump(

        traffic_output,

        file,

        ensure_ascii=False,

        indent=2
    )


with open(
    MAP_OUTPUT,
    "w",
    encoding="utf-8"
) as file:

    json.dump(

        map_output,

        file,

        ensure_ascii=False,

        indent=2
    )


# ============================================================
# 완료 출력
# ============================================================

print()
print(
    "======================================"
)

print(
    "Mock 데이터 생성 완료"
)

print(
    "======================================"
)


print(
    "교통예측 LINK:",
    len(
        traffic_links
    ),
    "개"
)


print(
    "지도 LINK:",
    len(
        map_links
    ),
    "개"
)


print(
    "미래 시점:",
    len(
        TIME_OFFSETS
    ),
    "개"
)


print()
print(
    "Traffic Forecast:"
)

print(
    TRAFFIC_OUTPUT
)


print()
print(
    "FLOW Map Feed:"
)

print(
    MAP_OUTPUT
)