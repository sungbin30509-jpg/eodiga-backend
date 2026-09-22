import os
import json
import math
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
# 파일
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
# 매칭 설정
# ============================================================

SEARCH_MARGIN_M = 180

SAMPLE_INTERVAL_M = 20

MAX_SAMPLE_DISTANCE_M = 45

MAX_ROUTE_DISTANCE_M = 70

COVERAGE_BUFFER_M = 30

MAX_REPAIR_HOPS = 5


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
# 안전 float
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
# Shapefile CRS
# ============================================================

LINK_INFO = pyogrio.read_info(
    LINK_FILE
)


LINK_CRS = CRS.from_user_input(
    LINK_INFO["crs"]
)


TO_LINK_CRS = Transformer.from_crs(
    "EPSG:4326",
    LINK_CRS,
    always_xy=True,
)


TO_WGS84 = Transformer.from_crs(
    LINK_CRS,
    "EPSG:4326",
    always_xy=True,
)


# ============================================================
# 경로 방향상의 위치
# ============================================================

def route_position(
    route_line,
    geometry,
):

    try:

        point = geometry.interpolate(
            0.5,
            normalized=True,
        )

        return route_line.project(
            point
        )

    except Exception:

        return 0.0


# ============================================================
# LINK가 경로 진행방향과 대략 같은지
#
# 국가표준 geometry의 시작→끝이
# TMAP 진행방향과 반대인 링크를
# 가능하면 제외하는 용도
# ============================================================

def direction_score(
    route_line,
    link_geometry,
):

    try:

        coords = list(
            link_geometry.coords
        )

        if len(coords) < 2:
            return 0


        start_point = Point(
            coords[0]
        )

        end_point = Point(
            coords[-1]
        )


        start_position = route_line.project(
            start_point
        )

        end_position = route_line.project(
            end_point
        )


        if end_position > start_position:
            return 1

        if end_position < start_position:
            return -1

        return 0

    except Exception:

        return 0


# ============================================================
# TMAP 경로 샘플 생성
# ============================================================

def sample_route(
    route_line,
):

    length = route_line.length

    samples = []

    distance = 0.0


    while distance <= length:

        samples.append(
            (
                distance,
                route_line.interpolate(
                    distance
                ),
            )
        )

        distance += (
            SAMPLE_INTERVAL_M
        )


    # 마지막 점 보장
    if not samples:

        samples.append(
            (
                0.0,
                route_line.interpolate(
                    0
                ),
            )
        )


    elif (
        length
        -
        samples[-1][0]
        >
        1
    ):

        samples.append(
            (
                length,
                route_line.interpolate(
                    length
                ),
            )
        )


    return samples


# ============================================================
# 후보 LINK 불러오기
# ============================================================

def load_candidate_links(
    route_projected,
):

    bbox = (
        route_projected
        .buffer(
            SEARCH_MARGIN_M
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


    # 경로에서 너무 멀리 떨어진 LINK 제거
    links["route_distance_m"] = (
        links.geometry.distance(
            route_projected
        )
    )


    links = links[
        links[
            "route_distance_m"
        ]
        <=
        MAX_ROUTE_DISTANCE_M
    ].copy()


    # 경로상의 위치
    links["route_position_m"] = (
        links.geometry.apply(
            lambda geometry:
                route_position(
                    route_projected,
                    geometry,
                )
        )
    )


    # 진행방향
    links["direction_score"] = (
        links.geometry.apply(
            lambda geometry:
                direction_score(
                    route_projected,
                    geometry,
                )
        )
    )


    return links


# ============================================================
# Sample → 가장 적절한 LINK 선택
# ============================================================

def match_samples(
    route_projected,
    links,
):

    samples = sample_route(
        route_projected
    )


    matched = []


    for sample_position, point in samples:

        distances = (
            links.geometry.distance(
                point
            )
        )


        nearby = links[
            distances
            <=
            MAX_SAMPLE_DISTANCE_M
        ].copy()


        if nearby.empty:
            continue


        nearby[
            "sample_distance_m"
        ] = distances[
            nearby.index
        ]


        # 가능하면 정방향 LINK 우선
        forward = nearby[
            nearby[
                "direction_score"
            ]
            >=
            0
        ]


        if not forward.empty:

            nearby = forward


        # ----------------------------------------------------
        # 점까지 거리 + 경로 전체와 거리
        # ----------------------------------------------------

        nearby["score"] = (

            nearby[
                "sample_distance_m"
            ]

            +

            nearby[
                "route_distance_m"
            ]
            *
            0.35
        )


        best_index = (
            nearby[
                "score"
            ]
            .idxmin()
        )


        best = nearby.loc[
            best_index
        ]


        matched.append({

            "sample_position_m":
                float(
                    sample_position
                ),

            "LINK_ID":
                normalize_id(
                    best[
                        "LINK_ID"
                    ]
                ),

            "F_NODE":
                normalize_id(
                    best[
                        "F_NODE"
                    ]
                ),

            "T_NODE":
                normalize_id(
                    best[
                        "T_NODE"
                    ]
                ),

            "ROAD_NAME":
                (
                    ""
                    if pd.isna(
                        best[
                            "ROAD_NAME"
                        ]
                    )
                    else str(
                        best[
                            "ROAD_NAME"
                        ]
                    )
                ),

            "distance_to_sample_m":
                round(
                    float(
                        best[
                            "sample_distance_m"
                        ]
                    ),
                    2,
                ),

            "route_distance_m":
                round(
                    float(
                        best[
                            "route_distance_m"
                        ]
                    ),
                    2,
                ),
        })


    return (
        samples,
        matched
    )


# ============================================================
# 연속 중복 LINK 제거
# ============================================================

def remove_consecutive_duplicates(
    matched,
):

    result = []

    previous_link_id = None


    for item in matched:

        link_id = item[
            "LINK_ID"
        ]


        if (
            link_id
            ==
            previous_link_id
        ):

            continue


        result.append(
            item
        )


        previous_link_id = (
            link_id
        )


    return result


# ============================================================
# LINK lookup
# ============================================================

def build_link_lookup(
    links,
):

    lookup = {}


    for _, row in links.iterrows():

        link_id = normalize_id(
            row[
                "LINK_ID"
            ]
        )


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
                    ],
                    999999,
                ),

            "route_position_m":
                safe_float(
                    row[
                        "route_position_m"
                    ],
                    0,
                ),

            "geometry":
                row.geometry,
        }


    return lookup


# ============================================================
# Node adjacency
#
# F_NODE → T_NODE 방향
# ============================================================

def build_adjacency(
    link_lookup,
):

    adjacency = {}


    for link_id, link in (
        link_lookup.items()
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
# 두 LINK 사이 연결경로 탐색
#
# current.T_NODE
#   ↓
# ...
#   ↓
# next.F_NODE
# ============================================================

def find_repair_path(
    current_link,
    next_link,
    link_lookup,
    adjacency,
):

    start_node = current_link[
        "T_NODE"
    ]

    target_node = next_link[
        "F_NODE"
    ]


    if not start_node or not target_node:

        return None


    if start_node == target_node:

        return []


    current_pos = current_link[
        "route_position_m"
    ]

    next_pos = next_link[
        "route_position_m"
    ]


    lower_pos = min(
        current_pos,
        next_pos
    ) - 100


    upper_pos = max(
        current_pos,
        next_pos
    ) + 100


    # --------------------------------------------------------
    # heap:
    #
    # cost
    # hops
    # node
    # path_link_ids
    # --------------------------------------------------------

    queue = [
        (
            0.0,
            0,
            start_node,
            [],
        )
    ]


    best_cost = {
        start_node:
            0.0
    }


    while queue:

        (
            cost,
            hops,
            node,
            path,
        ) = heapq.heappop(
            queue
        )


        if node == target_node:

            return path


        if hops >= MAX_REPAIR_HOPS:

            continue


        for link_id in adjacency.get(
            node,
            []
        ):

            link = link_lookup[
                link_id
            ]


            position = link[
                "route_position_m"
            ]


            # 너무 멀리 떨어진 경로는 제외
            if not (
                lower_pos
                <=
                position
                <=
                upper_pos
            ):

                continue


            # 경로와 너무 먼 링크 제외
            if (
                link[
                    "route_distance_m"
                ]
                >
                MAX_ROUTE_DISTANCE_M
            ):

                continue


            next_node = link[
                "T_NODE"
            ]


            if not next_node:

                continue


            link_length = max(
                1.0,
                link[
                    "LENGTH"
                ],
            )


            # ------------------------------------------------
            # 경로에서 멀면 추가 패널티
            # ------------------------------------------------

            new_cost = (

                cost

                +

                link_length

                +

                link[
                    "route_distance_m"
                ]
                *
                5
            )


            previous_best = (
                best_cost.get(
                    next_node
                )
            )


            if (
                previous_best
                is not None
                and
                previous_best
                <=
                new_cost
            ):

                continue


            best_cost[
                next_node
            ] = new_cost


            heapq.heappush(

                queue,

                (
                    new_cost,

                    hops + 1,

                    next_node,

                    path
                    +
                    [
                        link_id
                    ],
                )
            )


    return None


# ============================================================
# LINK chain 보정
# ============================================================

def repair_sequence(
    sequence_ids,
    link_lookup,
):

    if not sequence_ids:

        return (
            [],
            0,
        )


    repaired = [
        sequence_ids[0]
    ]


    inserted_count = 0


    adjacency = build_adjacency(
        link_lookup
    )


    for next_link_id in (
        sequence_ids[1:]
    ):

        current_link_id = (
            repaired[-1]
        )


        current_link = (
            link_lookup.get(
                current_link_id
            )
        )


        next_link = (
            link_lookup.get(
                next_link_id
            )
        )


        if (
            current_link is None
            or next_link is None
        ):

            repaired.append(
                next_link_id
            )

            continue


        # 이미 직접 연결
        if (
            current_link[
                "T_NODE"
            ]
            ==
            next_link[
                "F_NODE"
            ]
        ):

            repaired.append(
                next_link_id
            )

            continue


        # -----------------------------------------------
        # 중간 LINK 탐색
        # -----------------------------------------------

        bridge = find_repair_path(

            current_link,

            next_link,

            link_lookup,

            adjacency,
        )


        if bridge is not None:

            for bridge_id in bridge:

                if (
                    bridge_id
                    ==
                    current_link_id
                    or
                    bridge_id
                    ==
                    next_link_id
                ):

                    continue


                if (
                    repaired
                    and
                    repaired[-1]
                    ==
                    bridge_id
                ):

                    continue


                repaired.append(
                    bridge_id
                )


                inserted_count += 1


        repaired.append(
            next_link_id
        )


    # --------------------------------------------------------
    # 연속 중복 제거
    # --------------------------------------------------------

    cleaned = []

    previous = None


    for link_id in repaired:

        if link_id == previous:

            continue


        cleaned.append(
            link_id
        )


        previous = link_id


    return (
        cleaned,
        inserted_count,
    )


# ============================================================
# LINK 연결률
# ============================================================

def calculate_connectivity(
    sequence_ids,
    link_lookup,
):

    if len(sequence_ids) <= 1:

        return (
            100.0,
            0,
        )


    total_connections = (
        len(sequence_ids)
        -
        1
    )


    connected = 0

    broken = 0


    for index in range(
        total_connections
    ):

        first = link_lookup.get(
            sequence_ids[
                index
            ]
        )

        second = link_lookup.get(
            sequence_ids[
                index + 1
            ]
        )


        if (
            first
            and
            second
            and
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


    ratio = (
        connected
        /
        total_connections
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
    sequence_ids,
    link_lookup,
):

    geometries = []


    for link_id in sequence_ids:

        link = link_lookup.get(
            link_id
        )

        if link is None:

            continue


        geometry = link[
            "geometry"
        ]


        if geometry is None:
            continue


        geometries.append(
            geometry
        )


    if not geometries:

        return 0.0


    merged = unary_union(
        geometries
    )


    matched_area = merged.buffer(
        COVERAGE_BUFFER_M
    )


    matched_length = (
        route_projected
        .intersection(
            matched_area
        )
        .length
    )


    if route_projected.length <= 0:

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
            ratio,
            100
        ),
        2,
    )


# ============================================================
# 출력용 LINK 정보
# ============================================================

def build_output_sequence(
    sequence_ids,
    link_lookup,
    original_ids,
):

    result = []


    original_set = set(
        original_ids
    )


    for index, link_id in enumerate(
        sequence_ids
    ):

        link = link_lookup.get(
            link_id
        )


        if link is None:
            continue


        geometry_wgs84 = transform(

            TO_WGS84.transform,

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

            "repair_inserted":
                (
                    link_id
                    not in
                    original_set
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
        "처리:",
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

        return


    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

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
            "❌ route geometry 없음"
        )

        return


    # --------------------------------------------------------
    # WGS84 route
    # --------------------------------------------------------

    route_wgs84 = LineString(
        coordinates
    )


    # --------------------------------------------------------
    # 국가표준 좌표계
    # --------------------------------------------------------

    route_projected = transform(

        TO_LINK_CRS.transform,

        route_wgs84,
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
        "길이:",
        round(
            route_projected.length
            /
            1000,
            3,
        ),
        "km"
    )


    # --------------------------------------------------------
    # 주변 국가표준 LINK
    # --------------------------------------------------------

    print()
    print(
        "국가표준 LINK 후보 검색..."
    )


    links = load_candidate_links(
        route_projected
    )


    print(
        "주변 후보 LINK:",
        len(
            links
        ),
        "개"
    )


    if links.empty:

        print(
            "❌ 후보 LINK 없음"
        )

        return


    link_lookup = build_link_lookup(
        links
    )


    # --------------------------------------------------------
    # Sample matching
    # --------------------------------------------------------

    print()
    print(
        "경로 Sample 매칭..."
    )


    samples, matched = (
        match_samples(
            route_projected,
            links,
        )
    )


    matched_sequence = (
        remove_consecutive_duplicates(
            matched
        )
    )


    original_ids = [

        item[
            "LINK_ID"
        ]

        for item
        in matched_sequence
    ]


    print(
        "Sample 포인트:",
        len(
            samples
        ),
        "개"
    )


    print(
        "매칭 Sample:",
        len(
            matched
        ),
        "개"
    )


    print(
        "1차 LINK sequence:",
        len(
            original_ids
        ),
        "개"
    )


    # --------------------------------------------------------
    # 연결 보정
    # --------------------------------------------------------

    print()
    print(
        "F_NODE / T_NODE 연결 보정..."
    )


    (
        repaired_ids,
        inserted_count,
    ) = repair_sequence(

        original_ids,

        link_lookup,
    )


    # --------------------------------------------------------
    # 결과 계산
    # --------------------------------------------------------

    connectivity, broken = (
        calculate_connectivity(

            repaired_ids,

            link_lookup,
        )
    )


    coverage = calculate_coverage(

        route_projected,

        repaired_ids,

        link_lookup,
    )


    print()
    print(
        "기존 LINK:",
        len(
            original_ids
        ),
        "개"
    )


    print(
        "자동 삽입:",
        inserted_count,
        "개"
    )


    print(
        "최종 LINK:",
        len(
            repaired_ids
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


    # --------------------------------------------------------
    # 출력 sequence
    # --------------------------------------------------------

    output_sequence = (
        build_output_sequence(

            repaired_ids,

            link_lookup,

            original_ids,
        )
    )


    # --------------------------------------------------------
    # JSON 업데이트
    # --------------------------------------------------------

    route_data[
        "link_mapping"
    ] = {

        "status":
            (
                "mapped"
                if repaired_ids
                else "failed"
            ),

        "method":
            "sample_topology_repair_v1",

        "source":
            "MOCT_LINK",

        "original_link_count":
            len(
                original_ids
            ),

        "repair_inserted_count":
            inserted_count,

        "matched_link_count":
            len(
                repaired_ids
            ),

        "matched_link_ids":
            repaired_ids,

        "coverage_percent":
            coverage,

        "connectivity_percent":
            connectivity,

        "broken_connections":
            broken,

        "link_sequence":
            output_sequence,
    }


    # --------------------------------------------------------
    # 저장
    # --------------------------------------------------------

    output_json = os.path.join(

        ROUTE_DIR,

        f"{route_id}_repaired.json"
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


    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

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

            "repair_inserted":
                item[
                    "repair_inserted"
                ],
        })


    output_csv = os.path.join(

        ROUTE_DIR,

        f"{route_id}_links.csv"
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
        "✅ 저장 완료"
    )


    print(
        output_json
    )


    print(
        output_csv
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
        "FLOW A/B/C 국가표준 LINK 자동 매핑"
    )

    print(
        "======================================"
    )


    if not os.path.exists(
        LINK_FILE
    ):

        print(
            "❌ MOCT_LINK.shp를 찾을 수 없습니다."
        )

        print(
            LINK_FILE
        )

        return


    for filename in ROUTE_FILES:

        process_route(
            filename
        )


    print()
    print(
        "======================================"
    )

    print(
        "전체 후보 경로 처리 완료"
    )

    print(
        "======================================"
    )


if __name__ == "__main__":
    main()