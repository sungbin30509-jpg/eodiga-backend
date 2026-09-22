from pathlib import Path
from functools import lru_cache
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
# FLOW:MATE
# Universal LINK Matcher
#
# 역할
# ------------------------------------------------------------
# TMAP Route Geometry
#        ↓
# 국가표준 MOCT_LINK 후보 추출
#        ↓
# Topology-first 경로 탐색
#        ↓
# 순서가 있는 LINK_ID sequence
#
#
# 중요
# ------------------------------------------------------------
# A/B/C 중 특정 후보가 LINK Mapping에 실패해도
# 전체 Pipeline은 중단하지 않는다.
#
# 성공 후보:
#   status = "mapped"
#
# 실패 후보:
#   status = "failed"
#
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[2]


LINK_FILE = (
    ROOT
    / "data"
    / "national_links"
    / "MOCT_LINK.shp"
)


# ============================================================
# 2. V2 설정
# ============================================================

# Route 주변에서 SHP 후보를 읽을 최대 거리
LOAD_MARGIN_M = 350


# Coverage 계산용 Buffer
COVERAGE_BUFFER_M = 30


# 시작 / 종료 후보 LINK 최대 개수
MAX_ENDPOINT_CANDIDATES = 20


# Graph 탐색 최대 LINK 수
MAX_HOPS = 180


# ============================================================
# 3. Topology 탐색 단계
#
# strict부터 시작
# 실패하면 normal → wide 순으로 완화
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
# 4. ID 정리
# ============================================================

def normalize_id(
    value,
):

    if value is None:

        return ""


    text = (
        str(value)
        .strip()
    )


    if text.endswith(
        ".0"
    ):

        text = text[:-2]


    return text


# ============================================================
# 5. 안전한 float 변환
# ============================================================

def safe_float(
    value,
    default=0.0,
):

    try:

        if pd.isna(
            value
        ):

            return float(
                default
            )


        return float(
            value
        )


    except (
        TypeError,
        ValueError,
    ):

        return float(
            default
        )


# ============================================================
# 6. 국가표준 LINK CRS 준비
#
# 매번 SHP 정보를 읽지 않도록 cache
# ============================================================

@lru_cache(maxsize=1)
def prepare_crs():

    if not LINK_FILE.exists():

        raise FileNotFoundError(

            "MOCT_LINK.shp를 찾을 수 없습니다.\n"
            f"{LINK_FILE}"

        )


    info = (
        pyogrio.read_info(
            LINK_FILE
        )
    )


    link_crs = (
        CRS.from_user_input(
            info[
                "crs"
            ]
        )
    )


    # --------------------------------------------------------
    # WGS84
    # →
    # MOCT_LINK CRS
    # --------------------------------------------------------

    to_link = (
        Transformer.from_crs(

            "EPSG:4326",

            link_crs,

            always_xy=True,

        )
    )


    # --------------------------------------------------------
    # MOCT_LINK CRS
    # →
    # WGS84
    # --------------------------------------------------------

    to_wgs84 = (
        Transformer.from_crs(

            link_crs,

            "EPSG:4326",

            always_xy=True,

        )
    )


    return (
        link_crs,
        to_link,
        to_wgs84,
    )


# ============================================================
# 7. TMAP Route Geometry 정리
#
# 아래 두 형태 모두 허용
#
# 1.
# [
#   [127.xxx, 37.xxx],
#   ...
# ]
#
#
# 2.
# {
#   "type": "LineString",
#   "coordinates": [...]
# }
# ============================================================

def normalize_route_coordinates(
    route_geometry,
):

    if isinstance(
        route_geometry,
        dict,
    ):

        coordinates = (

            route_geometry
            .get(
                "coordinates",
                [],
            )

        )


    else:

        coordinates = (
            route_geometry
        )


    if not isinstance(
        coordinates,
        list,
    ):

        raise ValueError(

            "Route Geometry 좌표 형식이 "
            "올바르지 않습니다."

        )


    cleaned = []


    for coordinate in coordinates:

        if (

            not isinstance(
                coordinate,
                (list, tuple),
            )

            or

            len(
                coordinate
            )
            <
            2

        ):

            continue


        try:

            lon = float(
                coordinate[0]
            )


            lat = float(
                coordinate[1]
            )


        except (
            TypeError,
            ValueError,
        ):

            continue


        point = [

            lon,

            lat,

        ]


        # ----------------------------------------------------
        # 연속 중복 좌표 제거
        # ----------------------------------------------------

        if (

            not cleaned

            or

            cleaned[-1]
            !=
            point

        ):

            cleaned.append(
                point
            )


    if len(
        cleaned
    ) < 2:

        raise ValueError(

            "Route Geometry에 "
            "유효한 좌표가 2개 미만입니다."

        )


    return cleaned


# ============================================================
# 8. LINK가 TMAP Route의 어느 위치에 있는지 계산
# ============================================================

def calculate_route_positions(
    route_line,
    geometry,
):

    try:

        coords = list(
            geometry.coords
        )


        if len(
            coords
        ) < 2:

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


        start_pos = (

            route_line.project(
                start_point
            )

        )


        end_pos = (

            route_line.project(
                end_point
            )

        )


        middle_pos = (

            route_line.project(
                middle_point
            )

        )


        # ----------------------------------------------------
        # TMAP 진행방향과 LINK Geometry 방향 비교
        # ----------------------------------------------------

        if end_pos > start_pos:

            direction = 1


        elif end_pos < start_pos:

            direction = -1


        else:

            direction = 0


        return (

            float(
                start_pos
            ),

            float(
                end_pos
            ),

            float(
                middle_pos
            ),

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
# 9. TMAP Route 주변 국가표준 LINK 읽기
# ============================================================

def load_links(
    route_projected,
):

    # --------------------------------------------------------
    # Route 주변 BBox
    # --------------------------------------------------------

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


    links = (

        pyogrio.read_dataframe(

            LINK_FILE,

            bbox=bbox,

            columns=columns,

        )

    )


    if links.empty:

        return links


    # --------------------------------------------------------
    # 정상 geometry만 사용
    # --------------------------------------------------------

    links = links[

        links.geometry.notna()

    ].copy()


    links = links[

        ~links.geometry.is_empty

    ].copy()


    # --------------------------------------------------------
    # ID 정규화
    # --------------------------------------------------------

    links[
        "LINK_ID"
    ] = (

        links[
            "LINK_ID"
        ]

        .apply(
            normalize_id
        )

    )


    links[
        "F_NODE"
    ] = (

        links[
            "F_NODE"
        ]

        .apply(
            normalize_id
        )

    )


    links[
        "T_NODE"
    ] = (

        links[
            "T_NODE"
        ]

        .apply(
            normalize_id
        )

    )


    # ========================================================
    # TMAP Route ↔ LINK 거리
    # ========================================================

    links[
        "route_distance_m"
    ] = (

        links
        .geometry
        .distance(
            route_projected
        )

    )


    # ========================================================
    # 출발 / 도착점
    # ========================================================

    start_point = Point(
        route_projected.coords[0]
    )


    end_point = Point(
        route_projected.coords[-1]
    )


    links[
        "start_distance_m"
    ] = (

        links
        .geometry
        .distance(
            start_point
        )

    )


    links[
        "end_distance_m"
    ] = (

        links
        .geometry
        .distance(
            end_point
        )

    )


    # ========================================================
    # Route 상 위치 / 방향
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


    links[
        "route_start_pos_m"
    ] = (
        start_positions
    )


    links[
        "route_end_pos_m"
    ] = (
        end_positions
    )


    links[
        "route_position_m"
    ] = (
        middle_positions
    )


    links[
        "direction_score"
    ] = (
        directions
    )


    # ========================================================
    # LINK geometry 길이
    # ========================================================

    links[
        "geometry_length_m"
    ] = (

        links
        .geometry
        .length

    )


    return links


# ============================================================
# 10. Lookup 생성
# ============================================================

def build_lookup(
    links,
):

    lookup = {}


    for _, row in links.iterrows():

        link_id = normalize_id(
            row[
                "LINK_ID"
            ]
        )


        if not link_id:

            continue


        lookup[
            link_id
        ] = {

            "LINK_ID":
            link_id,

            "F_NODE":
            normalize_id(
                row[
                    "F_NODE"
                ]
            ),

            "T_NODE":
            normalize_id(
                row[
                    "T_NODE"
                ]
            ),

            "ROAD_NAME":
            (
                ""
                if pd.isna(
                    row[
                        "ROAD_NAME"
                    ]
                )
                else str(
                    row[
                        "ROAD_NAME"
                    ]
                )
            ),

            "LENGTH":
            safe_float(

                row[
                    "LENGTH"
                ],

                row.geometry.length,

            ),

            "MAX_SPD":
            safe_float(

                row[
                    "MAX_SPD"
                ],

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
# 11. F_NODE → LINK adjacency
# ============================================================

def build_adjacency(
    lookup,
):

    adjacency = {}


    for (
        link_id,
        link,
    ) in lookup.items():

        f_node = (
            link[
                "F_NODE"
            ]
        )


        if not f_node:

            continue


        adjacency.setdefault(

            f_node,

            [],

        )


        adjacency[
            f_node
        ].append(
            link_id
        )


    return adjacency


# ============================================================
# 12. LINK 자체 Cost
#
# Route에서 멀수록 비싸게
# 진행방향 반대 LINK도 패널티
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


    route_distance = (
        link[
            "route_distance_m"
        ]
    )


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
# 13. 시작 / 끝 후보 LINK 선정
# ============================================================

def select_endpoint_candidates(
    lookup,
    route_length,
    corridor_m,
    endpoint_span_m,
):

    start_candidates = []

    end_candidates = []


    for (
        link_id,
        link,
    ) in lookup.items():

        # ----------------------------------------------------
        # Corridor 밖 LINK 제외
        # ----------------------------------------------------

        if (

            link[
                "route_distance_m"
            ]

            >

            corridor_m

        ):

            continue


        position = (
            link[
                "route_position_m"
            ]
        )


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


    return (

        start_candidates[
            :MAX_ENDPOINT_CANDIDATES
        ],

        end_candidates[
            :MAX_ENDPOINT_CANDIDATES
        ],

    )


# ============================================================
# 14. Topology 우선 경로 탐색
#
# 핵심:
#
# 현재.T_NODE == 다음.F_NODE
# ============================================================

def find_connected_path(
    lookup,
    route_length,
    corridor_m,
    backtrack_m,
    endpoint_span_m,
):

    adjacency = (
        build_adjacency(
            lookup
        )
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
            not in
            best_cost

            or

            initial_cost
            <
            best_cost[
                link_id
            ]

        ):

            best_cost[
                link_id
            ] = (
                initial_cost
            )


            previous[
                link_id
            ] = None


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


    # ========================================================
    # Dijkstra
    # ========================================================

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

                float(
                    "inf"
                ),

            )

        ):

            continue


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


        # ====================================================
        # current.T_NODE == next.F_NODE
        # ====================================================

        next_links = (

            adjacency.get(

                current[
                    "T_NODE"
                ],

                [],

            )

        )


        for next_id in next_links:

            if next_id == current_id:

                continue


            next_link = (
                lookup.get(
                    next_id
                )
            )


            if next_link is None:

                continue


            # ------------------------------------------------
            # Corridor 밖
            # ------------------------------------------------

            if (

                next_link[
                    "route_distance_m"
                ]

                >

                corridor_m

            ):

                continue


            current_position = (

                current[
                    "route_position_m"
                ]

            )


            next_position = (

                next_link[
                    "route_position_m"
                ]

            )


            backward_amount = (

                current_position

                -

                next_position

            )


            # ------------------------------------------------
            # 너무 심한 후퇴 금지
            # ------------------------------------------------

            if (

                backward_amount

                >

                backtrack_m

            ):

                continue


            transition_penalty = 0.0


            # ------------------------------------------------
            # 약간 후퇴하면 추가 비용
            # ------------------------------------------------

            if backward_amount > 0:

                transition_penalty += (

                    backward_amount

                    *

                    10

                )


            # ------------------------------------------------
            # Geometry 방향 반대 패널티
            # ------------------------------------------------

            if (

                next_link[
                    "direction_score"
                ]

                <
                0

            ):

                transition_penalty += 220


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

                    float(
                        "inf"
                    ),

                )

            ):

                continue


            best_cost[
                next_id
            ] = (
                new_cost
            )


            previous[
                next_id
            ] = (
                current_id
            )


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
# 15. 연결률 계산
# ============================================================

def calculate_connectivity(
    path,
    lookup,
):

    if len(
        path
    ) <= 1:

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
            2,
        ),

        broken,

    )


# ============================================================
# 16. TMAP Geometry Coverage
# ============================================================

def calculate_coverage(
    route_projected,
    path,
    lookup,
):

    geometries = []


    for link_id in path:

        link = (
            lookup.get(
                link_id
            )
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


    merged = (
        unary_union(
            geometries
        )
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

            ratio,

        ),

        2,

    )


# ============================================================
# 17. Path LINK geometry 총 길이
# ============================================================

def calculate_path_length(
    path,
    lookup,
):

    total = 0.0


    for link_id in path:

        link = (
            lookup.get(
                link_id
            )
        )


        if link is None:

            continue


        total += (

            link[
                "geometry_length_m"
            ]

        )


    return total


# ============================================================
# 18. LINK Geometry → WGS84
# ============================================================

def geometry_to_wgs84_coordinates(
    geometry,
    to_wgs84,
):

    geometry_wgs84 = transform(

        to_wgs84.transform,

        geometry,

    )


    # ========================================================
    # LineString
    # ========================================================

    if (

        geometry_wgs84.geom_type

        ==

        "LineString"

    ):

        return [

            [
                float(x),
                float(y),
            ]

            for x, y
            in geometry_wgs84.coords

        ]


    # ========================================================
    # MultiLineString 방어
    # ========================================================

    if (

        geometry_wgs84.geom_type

        ==

        "MultiLineString"

    ):

        coordinates = []


        for line in geometry_wgs84.geoms:

            for x, y in line.coords:

                point = [

                    float(x),

                    float(y),

                ]


                if (

                    not coordinates

                    or

                    coordinates[-1]
                    !=
                    point

                ):

                    coordinates.append(
                        point
                    )


        return coordinates


    return []


# ============================================================
# 19. 출력용 LINK Sequence
# ============================================================

def build_output_sequence(
    path,
    lookup,
    to_wgs84,
):

    result = []


    for (
        index,
        link_id,
    ) in enumerate(
        path
    ):

        link = lookup[
            link_id
        ]


        coordinates = (
            geometry_to_wgs84_coordinates(

                link[
                    "geometry"
                ],

                to_wgs84,

            )
        )


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

            "geometry":
            {

                "type":
                "LineString",

                "coordinates":
                coordinates,

            },

        })


    return result


# ============================================================
# 20. 핵심 함수
#
# TMAP Geometry 1개
# →
# 국가표준 LINK Sequence
# ============================================================

def match_route_to_links(
    route_geometry,
    candidate_id=None,
    verbose=True,
):

    # ========================================================
    # Geometry 정리
    # ========================================================

    coordinates = (
        normalize_route_coordinates(
            route_geometry
        )
    )


    (
        _,
        to_link,
        to_wgs84,
    ) = prepare_crs()


    # ========================================================
    # WGS84 Route
    # ========================================================

    route_wgs84 = LineString(
        coordinates
    )


    # ========================================================
    # WGS84 → MOCT_LINK CRS
    # ========================================================

    route_projected = transform(

        to_link.transform,

        route_wgs84,

    )


    route_length = (
        route_projected.length
    )


    if verbose:

        print()

        print(
            "======================================"
        )

        print(
            "LINK Mapping:",
            candidate_id
            or
            "route",
        )

        print(
            "======================================"
        )


        print(

            "TMAP geometry 길이:",

            round(

                route_length
                /
                1000,

                3,

            ),

            "km",

        )


    # ========================================================
    # Route 주변 국가표준 LINK
    # ========================================================

    links = (
        load_links(
            route_projected
        )
    )


    if verbose:

        print(

            "BBox 후보 LINK:",

            len(
                links
            ),

            "개",

        )


    if links.empty:

        raise RuntimeError(

            "TMAP 경로 주변에서 "
            "MOCT_LINK 후보를 찾지 못했습니다."

        )


    lookup = (
        build_lookup(
            links
        )
    )


    best_path = None

    used_attempt = None


    # ========================================================
    # strict → normal → wide
    # ========================================================

    for attempt in SEARCH_ATTEMPTS:

        if verbose:

            print()

            print(

                "Topology 탐색:",

                attempt[
                    "name"
                ],

                "| corridor:",

                attempt[
                    "corridor_m"
                ],

                "m",

            )


        path = (
            find_connected_path(

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
        )


        if path:

            best_path = (
                path
            )


            used_attempt = (
                attempt
            )


            if verbose:

                print(
                    "✅ 연결 경로 발견"
                )


            break


        if verbose:

            print(
                "⚠️ 연결 경로 없음"
            )


    # ========================================================
    # 모든 탐색 실패
    # ========================================================

    if not best_path:

        raise RuntimeError(

            "Topology 기반 LINK 경로를 "
            "찾지 못했습니다."

        )


    # ========================================================
    # 품질 계산
    # ========================================================

    (
        connectivity,
        broken,
    ) = calculate_connectivity(

        best_path,

        lookup,

    )


    coverage = (
        calculate_coverage(

            route_projected,

            best_path,

            lookup,

        )
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


    else:

        quality = "poor"


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
    # 최종 결과
    # ========================================================

    result = {

        "status":
            "mapped",

        "candidate_id":
            candidate_id,

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

                2,

            ),

        "matched_geometry_length_m":
            round(

                matched_length,

                2,

            ),

        "length_ratio":
            round(

                length_ratio,

                4,

            ),

        "quality":
            quality,

        "link_sequence":
            output_sequence,

    }


    if verbose:

        print()

        print(
            "======================================"
        )

        print(
            "LINK Mapping 결과"
        )

        print(
            "======================================"
        )


        print(
            "경로:",
            candidate_id
            or
            "-",
        )


        print(
            "탐색 모드:",
            used_attempt[
                "name"
            ],
        )


        print(
            "최종 LINK:",
            len(
                best_path
            ),
            "개",
        )


        print(
            "연결률:",
            connectivity,
            "%",
        )


        print(
            "Coverage:",
            coverage,
            "%",
        )


        print(

            "TMAP geometry:",

            round(

                route_length
                /
                1000,

                3,

            ),

            "km",

        )


        print(

            "LINK geometry:",

            round(

                matched_length
                /
                1000,

                3,

            ),

            "km",

        )


        print(

            "길이비:",

            round(
                length_ratio,
                3,
            ),

        )


        print(

            "품질:",

            quality.upper(),

        )


    return result


# ============================================================
# 21. 실패한 Mapping 객체 생성
# ============================================================

def build_failed_mapping(
    candidate_id,
    error_type,
    error_message,
):

    return {

        "status":
            "failed",

        "candidate_id":
            candidate_id,

        "method":
            "topology_route_corridor_v2",

        "source":
            "MOCT_LINK",

        "error_type":
            error_type,

        "error":
            error_message,

        "matched_link_count":
            0,

        "matched_link_ids":
            [],

        "connectivity_percent":
            0.0,

        "broken_connections":
            None,

        "coverage_percent":
            0.0,

        "tmap_geometry_length_m":
            None,

        "matched_geometry_length_m":
            0.0,

        "length_ratio":
            0.0,

        "quality":
            "failed",

        "link_sequence":
            [],

    }


# ============================================================
# 22. A/B/C 전체 LINK Mapping
#
# 중요:
# 한 후보 실패해도 전체 Pipeline은 계속
# ============================================================

def match_route_candidates(
    route_result,
    verbose=True,
):

    routes = (
        route_result.get(
            "routes",
            [],
        )
    )


    if not routes:

        raise ValueError(

            "Route Engine 결과에 "
            "routes가 없습니다."

        )


    matched_routes = []


    # ========================================================
    # 각 후보 독립 처리
    # ========================================================

    for route in routes:

        candidate_id = (
            route.get(
                "candidate_id"
            )
        )


        geometry = (
            route.get(
                "geometry"
            )
        )


        route_copy = (
            route.copy()
        )


        # ====================================================
        # Geometry 자체가 없는 경우
        # ====================================================

        if not geometry:

            mapping = (
                build_failed_mapping(

                    candidate_id,

                    "MissingGeometry",

                    "Route geometry가 없습니다.",

                )
            )


            if verbose:

                print()

                print(
                    "======================================"
                )

                print(
                    f"⚠️ Route {candidate_id} LINK Mapping 실패"
                )

                print(
                    "======================================"
                )

                print(
                    "원인: Route geometry가 없습니다."
                )


        # ====================================================
        # 정상 Mapping 시도
        # ====================================================

        else:

            try:

                mapping = (
                    match_route_to_links(

                        geometry,

                        candidate_id=(
                            candidate_id
                        ),

                        verbose=verbose,

                    )
                )


            # =================================================
            # 해당 후보만 실패 처리
            # =================================================

            except Exception as error:

                mapping = (
                    build_failed_mapping(

                        candidate_id,

                        type(
                            error
                        ).__name__,

                        str(
                            error
                        ),

                    )
                )


                if verbose:

                    print()

                    print(
                        "======================================"
                    )

                    print(
                        f"⚠️ Route {candidate_id} LINK Mapping 실패"
                    )

                    print(
                        "======================================"
                    )


                    print(
                        "오류 종류:",
                        type(
                            error
                        ).__name__,
                    )


                    print(
                        "오류 내용:",
                        str(
                            error
                        ),
                    )


                    print()

                    print(
                        "이 후보만 제외하고 "
                        "다른 후보 처리를 계속합니다."
                    )


        route_copy[
            "link_mapping_v2"
        ] = (
            mapping
        )


        matched_routes.append(
            route_copy
        )


    # ========================================================
    # 성공 / 실패 개수 계산
    # ========================================================

    success_count = sum(

        1

        for route
        in matched_routes

        if (

            route

            .get(
                "link_mapping_v2",
                {},
            )

            .get(
                "status"
            )

            ==

            "mapped"

        )

    )


    failed_count = (

        len(
            matched_routes
        )

        -

        success_count

    )


    result = (
        route_result.copy()
    )


    result[
        "routes"
    ] = (
        matched_routes
    )


    result[
        "link_mapping_summary"
    ] = {

        "candidate_count":
            len(
                matched_routes
            ),

        "mapping_success_count":
            success_count,

        "mapping_failed_count":
            failed_count,

        "has_usable_candidate":
            (
                success_count
                >
                0
            ),

    }


    return result


# ============================================================
# 23. 모듈 직접 실행 확인
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Universal LINK Matcher"
    )

    print(
        "========================================"
    )


    print()

    print(
        "MOCT_LINK:"
    )


    print(
        LINK_FILE
    )


    (
        link_crs,
        _,
        _,
    ) = prepare_crs()


    print()

    print(
        "LINK CRS:"
    )


    print(
        link_crs
    )


    print()

    print(
        "========================================"
    )

    print(
        "link_matcher.py 준비 완료"
    )

    print(
        "========================================"
    )