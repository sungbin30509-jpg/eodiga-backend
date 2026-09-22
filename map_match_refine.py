import os
import json
import math
import heapq

import pandas as pd
import geopandas as gpd
import pyogrio

from pyproj import CRS
from pyproj import Transformer

from shapely.geometry import LineString
from shapely.geometry import Point
from shapely.ops import transform


# ============================================================
# 파일 경로
# ============================================================

ROUTE_FILE = os.path.join(
    "data",
    "routes",
    "route_test_001.json"
)

LINK_FILE = os.path.join(
    "data",
    "national_links",
    "MOCT_LINK.shp"
)

OUTPUT_JSON = os.path.join(
    "data",
    "routes",
    "route_test_001_refined.json"
)

OUTPUT_CSV = os.path.join(
    "data",
    "routes",
    "route_test_001_final_links.csv"
)


# ============================================================
# 2차 Map Matching 설정
# ============================================================

# TMAP 경로를 몇 m 간격으로 검사할지
SAMPLE_INTERVAL_M = 20

# 각 TMAP 샘플 포인트에서
# 국가표준 링크를 몇 m 이내까지 후보로 볼지
MAX_DISTANCE_M = 45

# 방향 차이 허용
MAX_DIRECTION_DIFF = 80

# SHP를 읽어올 경로 주변 범위
SEARCH_MARGIN_M = 120


# ============================================================
# ID 정리 함수
#
# 12345.0 → "12345"
# ============================================================

def normalize_id(value):

    if value is None:
        return ""

    text = str(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


# ============================================================
# 각도 계산
# ============================================================

def calculate_heading(
    x1,
    y1,
    x2,
    y2
):

    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        return None

    angle = math.degrees(
        math.atan2(
            dy,
            dx
        )
    )

    return (
        angle + 360
    ) % 360


# ============================================================
# 두 방향 차이
# ============================================================

def heading_difference(
    h1,
    h2
):

    if h1 is None or h2 is None:
        return 180

    diff = abs(
        h1 - h2
    )

    return min(
        diff,
        360 - diff
    )


# ============================================================
# TMAP 경로상의 특정 위치에서 진행방향 계산
# ============================================================

def get_route_heading(
    route,
    position
):

    before = max(
        0,
        position - 10
    )

    after = min(
        route.length,
        position + 10
    )

    p1 = route.interpolate(
        before
    )

    p2 = route.interpolate(
        after
    )

    return calculate_heading(
        p1.x,
        p1.y,
        p2.x,
        p2.y
    )


# ============================================================
# 국가표준 LINK의 진행방향 계산
# ============================================================

def get_link_heading(
    geometry
):

    if geometry is None:
        return None

    coords = list(
        geometry.coords
    )

    if len(coords) < 2:
        return None

    x1, y1 = coords[0]
    x2, y2 = coords[-1]

    return calculate_heading(
        x1,
        y1,
        x2,
        y2
    )


# ============================================================
# 기본 파일 확인
# ============================================================

print()
print("======================================")
print("FLOW 2차 LINK sequence 매칭")
print("======================================")


if not os.path.exists(
    ROUTE_FILE
):

    print(
        "route_test_001.json이 없습니다."
    )

    raise SystemExit


if not os.path.exists(
    LINK_FILE
):

    print(
        "MOCT_LINK.shp가 없습니다."
    )

    raise SystemExit


# ============================================================
# TMAP Route 읽기
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


coordinates = (
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


if len(coordinates) < 2:

    print(
        "TMAP 경로 좌표가 부족합니다."
    )

    raise SystemExit


route_wgs84 = LineString(
    coordinates
)


# ============================================================
# 국가표준 LINK 좌표계 확인
# ============================================================

link_info = pyogrio.read_info(
    LINK_FILE
)


link_crs = CRS.from_user_input(
    link_info["crs"]
)


print(
    "국가표준 LINK CRS:",
    link_crs
)


# ============================================================
# TMAP WGS84 → 국가표준 LINK 좌표계
# ============================================================

transformer = Transformer.from_crs(

    "EPSG:4326",

    link_crs,

    always_xy=True
)


route_projected = transform(

    transformer.transform,

    route_wgs84
)


route_length = (
    route_projected.length
)


print()
print(
    "route_id:",
    route_id
)

print(
    "TMAP 경로 길이:",
    round(
        route_length / 1000,
        3
    ),
    "km"
)


# ============================================================
# 경로 주변 BBOX만 SHP에서 읽기
# ============================================================

search_area = (
    route_projected.buffer(
        SEARCH_MARGIN_M
    )
)


bbox = search_area.bounds


print()
print(
    "국가표준 LINK 후보 읽는 중..."
)


links = pyogrio.read_dataframe(

    LINK_FILE,

    bbox=bbox,

    columns=[
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "ROAD_NAME",
        "LENGTH"
    ]
)


links = links[
    links.geometry.notna()
].copy()


links = links[
    ~links.geometry.is_empty
].copy()


print(
    "주변 LINK:",
    len(links),
    "개"
)


# ============================================================
# LINK 데이터 전처리
# ============================================================

links["LINK_ID"] = (
    links["LINK_ID"]
    .apply(
        normalize_id
    )
)


links["F_NODE"] = (
    links["F_NODE"]
    .apply(
        normalize_id
    )
)


links["T_NODE"] = (
    links["T_NODE"]
    .apply(
        normalize_id
    )
)


links = links.reset_index(
    drop=True
)


# ============================================================
# Spatial Index 생성
# ============================================================

spatial_index = (
    links.sindex
)


# ============================================================
# TMAP 경로를 20m 간격으로 샘플링
# ============================================================

sample_positions = []


position = 0.0


while position < route_length:

    sample_positions.append(
        position
    )

    position += (
        SAMPLE_INTERVAL_M
    )


# 마지막 목적지 포함
sample_positions.append(
    route_length
)


print(
    "TMAP 샘플 포인트:",
    len(sample_positions),
    "개"
)


# ============================================================
# 각 샘플 위치별 후보 LINK 생성
# ============================================================

all_candidates = []


print()
print(
    "샘플 포인트별 LINK 후보 계산 중..."
)


for sample_index, route_position in enumerate(
    sample_positions
):

    route_point = (
        route_projected.interpolate(
            route_position
        )
    )


    route_heading = (
        get_route_heading(
            route_projected,
            route_position
        )
    )


    # --------------------------------------------------------
    # 해당 점 주변 공간검색
    # --------------------------------------------------------

    search_box = (
        route_point.buffer(
            MAX_DISTANCE_M
        ).bounds
    )


    possible_indexes = list(

        spatial_index.intersection(
            search_box
        )
    )


    sample_candidates = []


    for link_index in possible_indexes:

        row = links.iloc[
            link_index
        ]


        geometry = (
            row.geometry
        )


        distance = geometry.distance(
            route_point
        )


        if distance > MAX_DISTANCE_M:
            continue


        link_heading = (
            get_link_heading(
                geometry
            )
        )


        direction_diff = (
            heading_difference(
                route_heading,
                link_heading
            )
        )


        # 진행방향이 너무 다르면 제외
        if direction_diff > MAX_DIRECTION_DIFF:
            continue


        # ----------------------------------------------------
        # 거리 점수
        # ----------------------------------------------------

        distance_score = max(

            0,

            1 -
            (
                distance /
                MAX_DISTANCE_M
            )
        )


        # ----------------------------------------------------
        # 방향 점수
        # ----------------------------------------------------

        direction_score = max(

            0,

            1 -
            (
                direction_diff /
                MAX_DIRECTION_DIFF
            )
        )


        # ----------------------------------------------------
        # 최종 관측 점수
        # ----------------------------------------------------

        observation_score = (

            distance_score * 0.65

            +

            direction_score * 0.35

        )


        sample_candidates.append({

            "link_index":
                link_index,

            "LINK_ID":
                row["LINK_ID"],

            "F_NODE":
                row["F_NODE"],

            "T_NODE":
                row["T_NODE"],

            "ROAD_NAME":
                (
                    ""
                    if pd.isna(
                        row["ROAD_NAME"]
                    )
                    else str(
                        row["ROAD_NAME"]
                    )
                ),

            "distance_m":
                float(
                    distance
                ),

            "direction_diff":
                float(
                    direction_diff
                ),

            "observation_score":
                float(
                    observation_score
                )
        })


    all_candidates.append(
        sample_candidates
    )


# ============================================================
# 후보가 없는 샘플 통계
# ============================================================

empty_samples = sum(

    1

    for candidates
    in all_candidates

    if len(candidates) == 0
)


print(
    "후보 없는 샘플:",
    empty_samples,
    "/",
    len(all_candidates)
)


# ============================================================
# Viterbi 형태 Dynamic Programming
#
# TMAP 경로를 따라가면서
# 이전 LINK → 현재 LINK 연결 여부를 반영
# ============================================================

dp = []

backtrack = []


# ============================================================
# 첫 번째 샘플
# ============================================================

first_candidates = (
    all_candidates[0]
)


first_dp = {}


for i, candidate in enumerate(
    first_candidates
):

    # 점수가 높을수록 비용이 낮음
    cost = (
        1 -
        candidate[
            "observation_score"
        ]
    )

    first_dp[i] = cost


dp.append(
    first_dp
)


backtrack.append(
    {}
)


# ============================================================
# 이후 샘플
# ============================================================

for sample_index in range(
    1,
    len(all_candidates)
):


    current_candidates = (
        all_candidates[
            sample_index
        ]
    )


    previous_candidates = (
        all_candidates[
            sample_index - 1
        ]
    )


    current_dp = {}

    current_backtrack = {}


    # 후보 없는 경우
    if (
        len(current_candidates) == 0
        or
        len(previous_candidates) == 0
    ):

        dp.append(
            current_dp
        )

        backtrack.append(
            current_backtrack
        )

        continue


    for current_index, current in enumerate(
        current_candidates
    ):


        best_cost = None
        best_previous = None


        observation_cost = (

            1 -
            current[
                "observation_score"
            ]
        )


        for previous_index, previous in enumerate(
            previous_candidates
        ):


            if previous_index not in dp[
                sample_index - 1
            ]:

                continue


            previous_cost = dp[
                sample_index - 1
            ][
                previous_index
            ]


            # =================================================
            # Transition Cost
            # =================================================

            # 같은 LINK 유지
            if (
                previous["LINK_ID"]
                ==
                current["LINK_ID"]
            ):

                transition_cost = 0.0


            # 정상적인 F_NODE → T_NODE 연결
            elif (
                previous["T_NODE"]
                ==
                current["F_NODE"]
            ):

                transition_cost = 0.15


            # 노드 하나를 공유하지만
            # 방향이 완벽하지 않은 경우
            elif (
                previous["T_NODE"]
                ==
                current["T_NODE"]
                or
                previous["F_NODE"]
                ==
                current["F_NODE"]
                or
                previous["F_NODE"]
                ==
                current["T_NODE"]
            ):

                transition_cost = 1.2


            # 완전히 떨어진 LINK
            else:

                transition_cost = 4.0


            total_cost = (

                previous_cost

                +

                transition_cost

                +

                observation_cost
            )


            if (
                best_cost is None
                or
                total_cost < best_cost
            ):

                best_cost = (
                    total_cost
                )

                best_previous = (
                    previous_index
                )


        if best_cost is not None:

            current_dp[
                current_index
            ] = (
                best_cost
            )


            current_backtrack[
                current_index
            ] = (
                best_previous
            )


    dp.append(
        current_dp
    )


    backtrack.append(
        current_backtrack
    )


# ============================================================
# 후보가 끊기는 경우를 대비하여
# 각 샘플에서 최적 후보를 별도로 추출
# ============================================================

selected_samples = []


last_selected = None


for sample_index, candidates in enumerate(
    all_candidates
):


    if len(candidates) == 0:

        selected_samples.append(
            None
        )

        continue


    # --------------------------------------------------------
    # 직전 선택 링크를 우선 연결
    # --------------------------------------------------------

    best_candidate = None
    best_cost = None


    for candidate in candidates:


        observation_cost = (

            1 -
            candidate[
                "observation_score"
            ]
        )


        transition_cost = 0


        if last_selected is not None:


            if (
                last_selected["LINK_ID"]
                ==
                candidate["LINK_ID"]
            ):

                transition_cost = 0


            elif (
                last_selected["T_NODE"]
                ==
                candidate["F_NODE"]
            ):

                transition_cost = 0.1


            elif (
                last_selected["T_NODE"]
                in [
                    candidate["F_NODE"],
                    candidate["T_NODE"]
                ]
            ):

                transition_cost = 0.8


            else:

                transition_cost = 2.5


        total_cost = (

            observation_cost

            +

            transition_cost
        )


        if (
            best_cost is None
            or
            total_cost < best_cost
        ):

            best_cost = (
                total_cost
            )

            best_candidate = (
                candidate
            )


    selected_samples.append(
        best_candidate
    )


    if best_candidate is not None:

        last_selected = (
            best_candidate
        )


# ============================================================
# 샘플별 선택 LINK → LINK sequence 변환
#
# 같은 LINK가 연속으로 반복되면 하나만 유지
# ============================================================

link_sequence = []


previous_link_id = None


for sample_index, candidate in enumerate(
    selected_samples
):


    if candidate is None:
        continue


    link_id = (
        candidate["LINK_ID"]
    )


    if (
        link_id ==
        previous_link_id
    ):

        continue


    sequence_item = {

        "sequence":
            len(link_sequence),

        "LINK_ID":
            candidate[
                "LINK_ID"
            ],

        "F_NODE":
            candidate[
                "F_NODE"
            ],

        "T_NODE":
            candidate[
                "T_NODE"
            ],

        "ROAD_NAME":
            candidate[
                "ROAD_NAME"
            ],

        "sample_position_m":
            round(
                sample_positions[
                    sample_index
                ],
                2
            ),

        "distance_to_tmap_m":
            round(
                candidate[
                    "distance_m"
                ],
                2
            ),

        "direction_diff_deg":
            round(
                candidate[
                    "direction_diff"
                ],
                2
            )
    }


    link_sequence.append(
        sequence_item
    )


    previous_link_id = (
        link_id
    )


# ============================================================
# 연결성 검사
# ============================================================

connected_count = 0


for i in range(
    len(link_sequence) - 1
):


    current = (
        link_sequence[i]
    )

    next_link = (
        link_sequence[i + 1]
    )


    if (
        current["LINK_ID"]
        ==
        next_link["LINK_ID"]
        or
        current["T_NODE"]
        ==
        next_link["F_NODE"]
    ):

        connected_count += 1


connection_pairs = max(

    len(link_sequence) - 1,

    0
)


connection_ratio = (

    connected_count
    /
    connection_pairs

    if connection_pairs > 0

    else 0
)


# ============================================================
# 샘플 Coverage
# ============================================================

matched_sample_count = sum(

    1

    for item
    in selected_samples

    if item is not None
)


sample_coverage = (

    matched_sample_count
    /
    len(sample_positions)

    if len(
        sample_positions
    ) > 0

    else 0
)


# ============================================================
# 터미널 출력
# ============================================================

print()
print(
    "======================================"
)

print(
    "2차 LINK sequence 결과"
)

print(
    "======================================"
)


print(
    "route_id:",
    route_id
)


print(
    "경로 길이:",
    round(
        route_length / 1000,
        3
    ),
    "km"
)


print(
    "샘플 포인트:",
    len(sample_positions),
    "개"
)


print(
    "매칭된 샘플:",
    matched_sample_count,
    "개"
)


print(
    "Sample Coverage:",
    round(
        sample_coverage * 100,
        2
    ),
    "%"
)


print(
    "최종 LINK sequence:",
    len(link_sequence),
    "개"
)


print(
    "LINK 연결률:",
    round(
        connection_ratio * 100,
        2
    ),
    "%"
)


print()
print(
    "======================================"
)

print(
    "최종 LINK_ID 순서"
)

print(
    "======================================"
)


for item in link_sequence:

    print()

    print(
        f"[{item['sequence']}]"
    )

    print(
        "LINK_ID:",
        item["LINK_ID"]
    )

    print(
        "도로명:",
        item["ROAD_NAME"]
    )

    print(
        "F_NODE:",
        item["F_NODE"]
    )

    print(
        "T_NODE:",
        item["T_NODE"]
    )

    print(
        "TMAP 거리:",
        item[
            "distance_to_tmap_m"
        ],
        "m"
    )


# ============================================================
# JSON 저장용 데이터
# ============================================================

output_data = dict(
    route_data
)


output_data[
    "link_mapping"
] = {

    "status":
        "refined",

    "method":
        "sample_direction_node_chain_v2",

    "sample_interval_m":
        SAMPLE_INTERVAL_M,

    "max_distance_m":
        MAX_DISTANCE_M,

    "sample_count":
        len(
            sample_positions
        ),

    "matched_sample_count":
        matched_sample_count,

    "sample_coverage_ratio":
        round(
            sample_coverage,
            4
        ),

    "sample_coverage_percent":
        round(
            sample_coverage * 100,
            2
        ),

    "final_link_count":
        len(
            link_sequence
        ),

    "connection_ratio":
        round(
            connection_ratio,
            4
        ),

    "connection_percent":
        round(
            connection_ratio * 100,
            2
        ),

    "matched_link_ids": [

        item[
            "LINK_ID"
        ]

        for item
        in link_sequence
    ],

    "link_sequence":
        link_sequence
}


# ============================================================
# JSON 저장
# ============================================================

with open(
    OUTPUT_JSON,
    "w",
    encoding="utf-8"
) as file:

    json.dump(

        output_data,

        file,

        ensure_ascii=False,

        indent=2
    )


# ============================================================
# CSV 저장
# ============================================================

df = pd.DataFrame(
    link_sequence
)


df.to_csv(

    OUTPUT_CSV,

    index=False,

    encoding="utf-8-sig"
)


# ============================================================
# 완료
# ============================================================

print()
print(
    "======================================"
)

print(
    "2차 매칭 저장 완료"
)

print(
    "======================================"
)


print(
    "JSON:",
    OUTPUT_JSON
)


print(
    "CSV:",
    OUTPUT_CSV
)