import os
import json
import heapq

import pandas as pd
import pyogrio

from pyproj import CRS, Transformer

from shapely.geometry import (
    LineString,
    Point,
)

from shapely.ops import (
    transform,
    unary_union,
)


# ============================================================
# 경로
# ============================================================

LINK_FILE = os.path.join(
    "data",
    "national_links",
    "MOCT_LINK.shp",
)

ROUTE_DIR = os.path.join(
    "data",
    "routes",
)

ROUTE_FILES = [
    "route_A.json",
    "route_B.json",
    "route_C.json",
]


# ============================================================
# V2 설정
# ============================================================

# Shapefile을 처음 읽을 때 사용할 최대 범위
LOAD_MARGIN_M = 350

# Coverage 계산용
COVERAGE_BUFFER_M = 30

# 시작/종료 후보 LINK 최대 개수
MAX_ENDPOINT_CANDIDATES = 20

# Graph 탐색 최대 LINK 수
MAX_HOPS = 180


# ============================================================
# 탐색 단계
#
# strict부터 시도하고 실패하면 점점 완화
# ============================================================

SEARCH_ATTEMPTS = [
    {
        "name": "strict",
        "corridor_m": 75,
        "backtrack_m": 40,
        "endpoint_span_m": 250,
    },
    {
        "name": "normal",
        "corridor_m": 130,
        "backtrack_m": 100,
        "endpoint_span_m": 400,
    },
    {
        "name": "wide",
        "corridor_m": 220,
        "backtrack_m": 220,
        "endpoint_span_m": 700,
    },
]


# ============================================================
# ID 정리
# ============================================================

def normalize_id(value):

    if value is None:
        return ""

    text = str(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


# ============================================================
# 안전 float 변환
# ============================================================

def safe_float(
    value,
    default=0.0,
):

    try:

        if pd.isna(value):
            return float(default)

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return float(default)


# ============================================================
# 국가표준 LINK CRS 정보
# ============================================================

def prepare_crs():

    info = pyogrio.read_info(
        LINK_FILE
    )

    link_crs = CRS.from_user_input(
        info["crs"]
    )

    to_link = Transformer.from_crs(
        "EPSG:4326",
        link_crs,
        always_xy=True,
    )

    to_wgs84 = Transformer.from_crs(
        link_crs,
        "EPSG:4326",
        always_xy=True,
    )

    return (
        link_crs,
        to_link,
        to_wgs84,
    )


# ============================================================
# LINK의 route 상 위치 계산
# ============================================================

def calculate_route_positions(
    route_line,
    geometry,
):

    try:

        coords = list(
            geometry.coords
        )

        if len(coords) < 2:

            return (
                0.0,
                0.0,
                0.0,
                0,
            )


        start_point = Point(
            coords[0]
        )

        end_point = Point(
            coords[-1]
        )

        middle_point = (
            geometry.interpolate(
                0.5,
                normalized=True,
            )
        )


        start_pos = route_line.project(
            start_point
        )

        end_pos = route_line.project(
            end_point
        )

        middle_pos = route_line.project(
            middle_point
        )


        if end_pos > start_pos:

            direction = 1

        elif end_pos < start_pos:

            direction = -1

        else:

            direction = 0


        return (
            float(start_pos),
            float(end_pos),
            float(middle_pos),
            direction,
        )


    except Exception:

        return (
            0.0,
            0.0,
            0.0,
            0,
        )


# ============================================================
# TMAP route 주변 국가표준 LINK 읽기
# ============================================================

def load_links(
    route_projected,
):

    bbox = (
        route_projected
        .buffer(
            LOAD_MARGIN_M
        )
        .bounds
    )


    columns = [
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "ROAD_NAME",
        "LENGTH",
        "MAX_SPD",
    ]


    links = pyogrio.read_dataframe(
        LINK_FILE,
        bbox=bbox,
        columns=columns,
    )


    if links.empty:

        return links


    links = links[
        links.geometry.notna()
    ].copy()


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


    # ========================================================
    # TMAP 경로와 LINK 사이 거리
    # ========================================================

    links["route_distance_m"] = (
        links.geometry.distance(
            route_projected
        )
    )


    # ========================================================
    # 출발 / 도착점 거리
    # ========================================================

    start_point = Point(
        route_projected.coords[0]
    )

    end_point = Point(
        route_projected.coords[-1]
    )


    links["start_distance_m"] = (
        links.geometry.distance(
            start_point
        )
    )


    links["end_distance_m"] = (
        links.geometry.distance(
            end_point
        )
    )


    # ========================================================
    # route 위치 / 방향
    # ========================================================

    start_positions = []
    end_positions = []
    middle_positions = []
    directions = []


    for geometry in links.geometry:

        (
            start_pos,
            end_pos,
            middle_pos,
            direction,
        ) = calculate_route_positions(

            route_projected,

            geometry,
        )


        start_positions.append(
            start_pos
        )

        end_positions.append(
            end_pos
        )

        middle_positions.append(
            middle_pos
        )

        directions.append(
            direction
        )


    links["route_start_pos_m"] = (
        start_positions
    )

    links["route_end_pos_m"] = (
        end_positions
    )

    links["route_position_m"] = (
        middle_positions
    )

    links["direction_score"] = (
        directions
    )


    # geometry 실제 길이
    links["geometry_length_m"] = (
        links.geometry.length
    )


    return links


# ============================================================
# Lookup 생성
# ============================================================

def build_lookup(
    links,
):

    lookup = {}


    for _, row in links.iterrows():

        link_id = normalize_id(
            row["LINK_ID"]
        )


        if not link_id:

            continue


        lookup[link_id] = {

            "LINK_ID":
                link_id,

            "F_NODE":
                normalize_id(
                    row["F_NODE"]
                ),

            "T_NODE":
                normalize_id(
                    row["T_NODE"]
                ),

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

            "LENGTH":
                safe_float(
                    row["LENGTH"],
                    row.geometry.length,
                ),

            "MAX_SPD":
                safe_float(
                    row["MAX_SPD"],
                    0,
                ),

            "route_distance_m":
                safe_float(
                    row[
                        "route_distance_m"
                    ]
                ),

            "start_distance_m":
                safe_float(
                    row[
                        "start_distance_m"
                    ]
                ),

            "end_distance_m":
                safe_float(
                    row[
                        "end_distance_m"
                    ]
                ),

            "route_position_m":
                safe_float(
                    row[
                        "route_position_m"
                    ]
                ),

            "direction_score":
                int(
                    row[
                        "direction_score"
                    ]
                ),

            "geometry_length_m":
                safe_float(
                    row[
                        "geometry_length_m"
                    ],
                    row.geometry.length,
                ),

            "geometry":
                row.geometry,
        }


    return lookup


# ============================================================
# F_NODE → LINK adjacency
# ============================================================

def build_adjacency(
    lookup,
):

    adjacency = {}


    for link_id, link in (
        lookup.items()
    ):

        f_node = link[
            "F_NODE"
        ]


        if not f_node:

            continue


        adjacency.setdefault(
            f_node,
            []
        )


        adjacency[
            f_node
        ].append(
            link_id
        )


    return adjacency


# ============================================================
# LINK 자체 cost
#
# TMAP 경로에서 멀수록 비싸게
# 역방향 링크도 추가 패널티
# ============================================================

def link_cost(
    link,
):

    length = max(
        1.0,
        link[
            "geometry_length_m"
        ],
    )


    route_distance = link[
        "route_distance_m"
    ]


    cost = (
        length
        +
        route_distance
        *
        8.0
    )


    if (
        link[
            "direction_score"
        ]
        <
        0
    ):

        cost += 220


    return cost


# ============================================================
# 시작 / 끝 후보 LINK 선정
# ============================================================

def select_endpoint_candidates(
    lookup,
    route_length,
    corridor_m,
    endpoint_span_m,
):

    start_candidates = []

    end_candidates = []


    for link_id, link in (
        lookup.items()
    ):

        # corridor 밖이면 제외
        if (
            link[
                "route_distance_m"
            ]
            >
            corridor_m
        ):

            continue


        position = link[
            "route_position_m"
        ]


        # ====================================================
        # 출발 후보
        # ====================================================

        if (
            position
            <=
            endpoint_span_m
            or
            link[
                "start_distance_m"
            ]
            <=
            corridor_m
            *
            1.5
        ):

            score = (

                link[
                    "start_distance_m"
                ]
                *
                4

                +

                position
                *
                0.5

                +

                link[
                    "route_distance_m"
                ]
                *
                3
            )


            if (
                link[
                    "direction_score"
                ]
                <
                0
            ):

                score += 200


            start_candidates.append(
                (
                    score,
                    link_id,
                )
            )


        # ====================================================
        # 도착 후보
        # ====================================================

        remaining = abs(
            route_length
            -
            position
        )


        if (
            remaining
            <=
            endpoint_span_m
            or
            link[
                "end_distance_m"
            ]
            <=
            corridor_m
            *
            1.5
        ):

            score = (

                link[
                    "end_distance_m"
                ]
                *
                4

                +

                remaining
                *
                0.5

                +

                link[
                    "route_distance_m"
                ]
                *
                3
            )


            if (
                link[
                    "direction_score"
                ]
                <
                0
            ):

                score += 200


            end_candidates.append(
                (
                    score,
                    link_id,
                )
            )


    start_candidates.sort()
    end_candidates.sort()


    start_candidates = (
        start_candidates[
            :MAX_ENDPOINT_CANDIDATES
        ]
    )


    end_candidates = (
        end_candidates[
            :MAX_ENDPOINT_CANDIDATES
        ]
    )


    return (
        start_candidates,
        end_candidates,
    )


# ============================================================
# Topology 우선 경로 탐색
#
# 핵심:
#
# 현재.T_NODE == 다음.F_NODE
#
# 인 경우만 이동 가능
# ============================================================

def find_connected_path(
    lookup,
    route_length,
    corridor_m,
    backtrack_m,
    endpoint_span_m,
):

    adjacency = build_adjacency(
        lookup
    )


    (
        start_candidates,
        end_candidates,
    ) = select_endpoint_candidates(

        lookup,

        route_length,

        corridor_m,

        endpoint_span_m,
    )


    if not start_candidates:

        return None


    if not end_candidates:

        return None


    end_score_lookup = {

        link_id:
            score

        for score, link_id
        in end_candidates
    }


    end_ids = set(
        end_score_lookup.keys()
    )


    # ========================================================
    # Multi-source Dijkstra
    # ========================================================

    queue = []

    best_cost = {}

    previous = {}

    hop_count = {}


    for (
        endpoint_score,
        link_id,
    ) in start_candidates:

        link = lookup[
            link_id
        ]


        initial_cost = (

            endpoint_score

            +

            link_cost(
                link
            )
        )


        if (
            link_id
            not in best_cost
            or
            initial_cost
            <
            best_cost[
                link_id
            ]
        ):

            best_cost[
                link_id
            ] = initial_cost

            previous[
                link_id
            ] = None

            hop_count[
                link_id
            ] = 1


            heapq.heappush(

                queue,

                (
                    initial_cost,
                    1,
                    link_id,
                )
            )


    best_end_id = None
    best_end_total = float(
        "inf"
    )


    while queue:

        (
            current_cost,
            hops,
            current_id,
        ) = heapq.heappop(
            queue
        )


        if (
            current_cost
            >
            best_cost.get(
                current_id,
                float("inf")
            )
        ):

            continue


        # ====================================================
        # 이미 좋은 끝 경로보다 비싸면 종료 가능
        # ====================================================

        if (
            current_cost
            >
            best_end_total
        ):

            break


        current = lookup[
            current_id
        ]


        # ====================================================
        # 목적 LINK 도착
        # ====================================================

        if current_id in end_ids:

            total_cost = (

                current_cost

                +

                end_score_lookup[
                    current_id
                ]
            )


            if (
                total_cost
                <
                best_end_total
            ):

                best_end_total = (
                    total_cost
                )

                best_end_id = (
                    current_id
                )


        if hops >= MAX_HOPS:

            continue


        next_links = adjacency.get(

            current[
                "T_NODE"
            ],

            [],
        )


        for next_id in next_links:

            if next_id == current_id:

                continue


            next_link = lookup.get(
                next_id
            )


            if next_link is None:

                continue


            # =================================================
            # corridor 밖 LINK 제외
            # =================================================

            if (
                next_link[
                    "route_distance_m"
                ]
                >
                corridor_m
            ):

                continue


            current_position = current[
                "route_position_m"
            ]

            next_position = next_link[
                "route_position_m"
            ]


            # =================================================
            # 너무 심한 역주행/후퇴 금지
            # =================================================

            backward_amount = (

                current_position

                -

                next_position
            )


            if (
                backward_amount
                >
                backtrack_m
            ):

                continue


            transition_penalty = 0.0


            # 조금 후퇴하는 건 허용하지만 비용 증가
            if backward_amount > 0:

                transition_penalty += (

                    backward_amount
                    *
                    10
                )


            # 역방향 geometry 추가 패널티
            if (
                next_link[
                    "direction_score"
                ]
                <
                0
            ):

                transition_penalty += (
                    220
                )


            new_cost = (

                current_cost

                +

                link_cost(
                    next_link
                )

                +

                transition_penalty
            )


            if (
                new_cost
                >=
                best_cost.get(
                    next_id,
                    float("inf")
                )
            ):

                continue


            best_cost[
                next_id
            ] = new_cost


            previous[
                next_id
            ] = current_id


            hop_count[
                next_id
            ] = hops + 1


            heapq.heappush(

                queue,

                (
                    new_cost,
                    hops + 1,
                    next_id,
                )
            )


    # ========================================================
    # 경로 없음
    # ========================================================

    if best_end_id is None:

        return None


    # ========================================================
    # Path 복원
    # ========================================================

    path = []

    current_id = (
        best_end_id
    )


    while current_id is not None:

        path.append(
            current_id
        )


        current_id = (
            previous.get(
                current_id
            )
        )


    path.reverse()


    return path


# ============================================================
# 연결률 계산
# ============================================================

def calculate_connectivity(
    path,
    lookup,
):

    if len(path) <= 1:

        return (
            100.0,
            0,
        )


    connected = 0
    broken = 0


    for index in range(
        len(path)
        -
        1
    ):

        first = lookup[
            path[index]
        ]

        second = lookup[
            path[index + 1]
        ]


        if (
            first[
                "T_NODE"
            ]
            ==
            second[
                "F_NODE"
            ]
        ):

            connected += 1

        else:

            broken += 1


    total = (
        len(path)
        -
        1
    )


    ratio = (

        connected

        /

        total

        *

        100
    )


    return (
        round(
            ratio,
            2
        ),
        broken,
    )


# ============================================================
# Coverage
# ============================================================

def calculate_coverage(
    route_projected,
    path,
    lookup,
):

    geometries = []


    for link_id in path:

        link = lookup.get(
            link_id
        )


        if link is None:

            continue


        geometries.append(
            link[
                "geometry"
            ]
        )


    if not geometries:

        return 0.0


    merged = unary_union(
        geometries
    )


    matched_area = (
        merged.buffer(
            COVERAGE_BUFFER_M
        )
    )


    matched_length = (

        route_projected
        .intersection(
            matched_area
        )
        .length
    )


    if (
        route_projected.length
        <=
        0
    ):

        return 0.0


    ratio = (

        matched_length

        /

        route_projected.length

        *

        100
    )


    return round(
        min(
            100.0,
            ratio
        ),
        2,
    )


# ============================================================
# Path geometry 총 길이
# ============================================================

def calculate_path_length(
    path,
    lookup,
):

    total = 0.0


    for link_id in path:

        link = lookup.get(
            link_id
        )


        if link is None:

            continue


        total += link[
            "geometry_length_m"
        ]


    return total


# ============================================================
# 출력용 sequence
# ============================================================

def build_output_sequence(
    path,
    lookup,
    to_wgs84,
):

    result = []


    for index, link_id in enumerate(
        path
    ):

        link = lookup[
            link_id
        ]


        geometry_wgs84 = transform(

            to_wgs84.transform,

            link[
                "geometry"
            ],
        )


        coordinates = [

            [
                float(x),
                float(y),
            ]

            for x, y
            in geometry_wgs84.coords
        ]


        result.append({

            "sequence":
                index,

            "LINK_ID":
                link_id,

            "F_NODE":
                link[
                    "F_NODE"
                ],

            "T_NODE":
                link[
                    "T_NODE"
                ],

            "ROAD_NAME":
                link[
                    "ROAD_NAME"
                ],

            "LENGTH":
                round(
                    link[
                        "LENGTH"
                    ],
                    2,
                ),

            "MAX_SPD":
                link[
                    "MAX_SPD"
                ],

            "route_distance_m":
                round(
                    link[
                        "route_distance_m"
                    ],
                    2,
                ),

            "route_position_m":
                round(
                    link[
                        "route_position_m"
                    ],
                    2,
                ),

            "geometry": {

                "type":
                    "LineString",

                "coordinates":
                    coordinates,
            },
        })


    return result


# ============================================================
# 경로 하나 처리
# ============================================================

def process_route(
    filename,
    to_link,
    to_wgs84,
):

    input_path = os.path.join(
        ROUTE_DIR,
        filename,
    )


    print()
    print(
        "======================================"
    )

    print(
        "V2 처리:",
        filename
    )

    print(
        "======================================"
    )


    if not os.path.exists(
        input_path
    ):

        print(
            "❌ 파일 없음:",
            input_path
        )

        return None


    # ========================================================
    # Route JSON
    # ========================================================

    with open(
        input_path,
        "r",
        encoding="utf-8",
    ) as file:

        route_data = json.load(
            file
        )


    route_id = route_data.get(
        "route_id",
        os.path.splitext(
            filename
        )[0],
    )


    candidate_id = route_data.get(
        "candidate_id",
        "?",
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
            "❌ route geometry가 없습니다."
        )

        return None


    # ========================================================
    # WGS84 → 국가표준 CRS
    # ========================================================

    route_wgs84 = LineString(
        coordinates
    )


    route_projected = transform(

        to_link.transform,

        route_wgs84,
    )


    route_length = (
        route_projected.length
    )


    print(
        "경로:",
        candidate_id
    )

    print(
        "route_id:",
        route_id
    )

    print(
        "TMAP geometry 길이:",
        round(
            route_length
            /
            1000,
            3
        ),
        "km"
    )


    # ========================================================
    # 국가표준 후보
    # ========================================================

    print()
    print(
        "국가표준 LINK 후보 검색..."
    )


    links = load_links(
        route_projected
    )


    print(
        "BBox 후보 LINK:",
        len(
            links
        ),
        "개"
    )


    if links.empty:

        print(
            "❌ 후보 LINK 없음"
        )

        return None


    lookup = build_lookup(
        links
    )


    # ========================================================
    # strict → normal → wide 탐색
    # ========================================================

    best_path = None
    used_attempt = None


    for attempt in SEARCH_ATTEMPTS:

        print()
        print(
            "Topology 탐색:",
            attempt[
                "name"
            ]
        )


        print(
            "corridor:",
            attempt[
                "corridor_m"
            ],
            "m"
        )


        path = find_connected_path(

            lookup,

            route_length,

            attempt[
                "corridor_m"
            ],

            attempt[
                "backtrack_m"
            ],

            attempt[
                "endpoint_span_m"
            ],
        )


        if path:

            best_path = path

            used_attempt = attempt

            print(
                "✅ 연결 경로 발견"
            )

            break


        print(
            "⚠️ 연결 경로 없음"
        )


    # ========================================================
    # 실패
    # ========================================================

    if not best_path:

        print()
        print(
            "❌ V2 topology 경로를 찾지 못했습니다."
        )

        return None


    # ========================================================
    # 품질
    # ========================================================

    (
        connectivity,
        broken,
    ) = calculate_connectivity(

        best_path,

        lookup,
    )


    coverage = calculate_coverage(

        route_projected,

        best_path,

        lookup,
    )


    matched_length = (
        calculate_path_length(

            best_path,

            lookup,
        )
    )


    if route_length > 0:

        length_ratio = (

            matched_length

            /

            route_length
        )

    else:

        length_ratio = 0.0


    print()
    print(
        "======================================"
    )

    print(
        "V2 결과"
    )

    print(
        "======================================"
    )


    print(
        "탐색 모드:",
        used_attempt[
            "name"
        ]
    )


    print(
        "최종 LINK:",
        len(
            best_path
        ),
        "개"
    )


    print(
        "남은 끊김:",
        broken,
        "개"
    )


    print(
        "연결률:",
        connectivity,
        "%"
    )


    print(
        "Coverage:",
        coverage,
        "%"
    )


    print(
        "LINK geometry 총길이:",
        round(
            matched_length
            /
            1000,
            3
        ),
        "km"
    )


    print(
        "TMAP 대비 길이 비율:",
        round(
            length_ratio,
            3
        )
    )


    # ========================================================
    # 품질 판정
    # ========================================================

    if (
        connectivity
        ==
        100.0
        and
        coverage
        >=
        90.0
        and
        0.75
        <=
        length_ratio
        <=
        1.50
    ):

        quality = "good"

        print(
            "품질 판정: ✅ GOOD"
        )


    elif (
        connectivity
        ==
        100.0
        and
        coverage
        >=
        85.0
    ):

        quality = "review"

        print(
            "품질 판정: ⚠️ REVIEW"
        )


    else:

        quality = "poor"

        print(
            "품질 판정: ❌ POOR"
        )


    # ========================================================
    # 출력 sequence
    # ========================================================

    output_sequence = (
        build_output_sequence(

            best_path,

            lookup,

            to_wgs84,
        )
    )


    # ========================================================
    # JSON
    # ========================================================

    route_data[
        "link_mapping_v2"
    ] = {

        "status":
            "mapped",

        "method":
            "topology_route_corridor_v2",

        "source":
            "MOCT_LINK",

        "search_mode":
            used_attempt[
                "name"
            ],

        "corridor_m":
            used_attempt[
                "corridor_m"
            ],

        "matched_link_count":
            len(
                best_path
            ),

        "matched_link_ids":
            best_path,

        "connectivity_percent":
            connectivity,

        "broken_connections":
            broken,

        "coverage_percent":
            coverage,

        "tmap_geometry_length_m":
            round(
                route_length,
                2
            ),

        "matched_geometry_length_m":
            round(
                matched_length,
                2
            ),

        "length_ratio":
            round(
                length_ratio,
                4
            ),

        "quality":
            quality,

        "link_sequence":
            output_sequence,
    }


    output_json = os.path.join(

        ROUTE_DIR,

        f"{route_id}_v2.json"
    )


    with open(
        output_json,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(

            route_data,

            file,

            ensure_ascii=False,

            indent=2,
        )


    # ========================================================
    # CSV
    # ========================================================

    csv_rows = []


    for item in output_sequence:

        csv_rows.append({

            "sequence":
                item[
                    "sequence"
                ],

            "LINK_ID":
                item[
                    "LINK_ID"
                ],

            "F_NODE":
                item[
                    "F_NODE"
                ],

            "T_NODE":
                item[
                    "T_NODE"
                ],

            "ROAD_NAME":
                item[
                    "ROAD_NAME"
                ],

            "LENGTH":
                item[
                    "LENGTH"
                ],

            "MAX_SPD":
                item[
                    "MAX_SPD"
                ],

            "route_distance_m":
                item[
                    "route_distance_m"
                ],

            "route_position_m":
                item[
                    "route_position_m"
                ],
        })


    output_csv = os.path.join(

        ROUTE_DIR,

        f"{route_id}_v2_links.csv"
    )


    pd.DataFrame(
        csv_rows
    ).to_csv(

        output_csv,

        index=False,

        encoding="utf-8-sig",
    )


    print()
    print(
        "✅ 저장:"
    )

    print(
        output_json
    )

    print(
        output_csv
    )


    return {

        "candidate_id":
            candidate_id,

        "route_id":
            route_id,

        "link_count":
            len(
                best_path
            ),

        "connectivity":
            connectivity,

        "coverage":
            coverage,

        "length_ratio":
            round(
                length_ratio,
                3
            ),

        "quality":
            quality,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "======================================"
    )

    print(
        "FLOW A/B/C LINK Mapping V2"
    )

    print(
        "Topology-first 방식"
    )

    print(
        "======================================"
    )


    if not os.path.exists(
        LINK_FILE
    ):

        print(
            "❌ MOCT_LINK.shp 없음:"
        )

        print(
            LINK_FILE
        )

        return


    (
        link_crs,
        to_link,
        to_wgs84,
    ) = prepare_crs()


    print()
    print(
        "국가표준 LINK CRS:"
    )

    print(
        link_crs
    )


    results = []


    for filename in ROUTE_FILES:

        result = process_route(

            filename,

            to_link,

            to_wgs84,
        )


        if result:

            results.append(
                result
            )


    # ========================================================
    # 최종 비교
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "A/B/C V2 최종 비교"
    )

    print(
        "======================================"
    )


    for result in results:

        print()
        print(
            "경로:",
            result[
                "candidate_id"
            ]
        )

        print(
            "최종 LINK:",
            result[
                "link_count"
            ]
        )

        print(
            "연결률:",
            result[
                "connectivity"
            ],
            "%"
        )

        print(
            "Coverage:",
            result[
                "coverage"
            ],
            "%"
        )

        print(
            "길이비:",
            result[
                "length_ratio"
            ]
        )

        print(
            "품질:",
            result[
                "quality"
            ]
        )


    print()
    print(
        "======================================"
    )

    print(
        "V2 처리 완료"
    )

    print(
        "======================================"
    )


if __name__ == "__main__":
    main()