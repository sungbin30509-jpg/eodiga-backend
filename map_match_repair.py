import os
import json
import math
import heapq
import copy

import pandas as pd
import pyogrio

from pyproj import CRS
from pyproj import Transformer

from shapely.geometry import LineString
from shapely.ops import transform


# ============================================================
# 파일 경로
# ============================================================

REFINED_ROUTE_FILE = os.path.join(
    "data",
    "routes",
    "route_test_001_refined.json"
)


LINK_FILE = os.path.join(
    "data",
    "national_links",
    "MOCT_LINK.shp"
)


OUTPUT_JSON = os.path.join(
    "data",
    "routes",
    "route_test_001_repaired.json"
)


OUTPUT_CSV = os.path.join(
    "data",
    "routes",
    "route_test_001_repaired_links.csv"
)


# ============================================================
# 연결 보정 설정
# ============================================================

# TMAP 경로 주변에서 LINK 검색 범위
SEARCH_MARGIN_M = 150


# 하나의 끊긴 구간을 연결할 때
# 최대 몇 개 LINK까지 추가할지
MAX_HOPS = 6


# 빠진 연결 경로가 너무 길면
# 잘못된 우회 연결일 가능성이 있으므로 제외
MAX_BRIDGE_LENGTH_M = 800


# TMAP 경로에서 멀리 떨어진 LINK에
# 패널티를 얼마나 줄지
ROUTE_DISTANCE_WEIGHT = 3.0


# ============================================================
# ID 문자열 정리
# ============================================================

def normalize_id(value):

    if value is None:
        return ""


    text = str(value)


    if text.endswith(".0"):

        text = text[:-2]


    return text


# ============================================================
# 파일 확인
# ============================================================

print()
print("======================================")
print("FLOW 3차 LINK 연결 보정")
print("======================================")


if not os.path.exists(
    REFINED_ROUTE_FILE
):

    print()
    print(
        "2차 매칭 결과 파일이 없습니다."
    )

    print(
        REFINED_ROUTE_FILE
    )

    raise SystemExit


if not os.path.exists(
    LINK_FILE
):

    print()
    print(
        "MOCT_LINK.shp 파일이 없습니다."
    )

    print(
        LINK_FILE
    )

    raise SystemExit


# ============================================================
# 1. 2차 매칭 결과 JSON 읽기
# ============================================================

with open(
    REFINED_ROUTE_FILE,
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


link_mapping = route_data.get(
    "link_mapping",
    {}
)


original_sequence = link_mapping.get(
    "link_sequence",
    []
)


if len(original_sequence) == 0:

    print()
    print(
        "link_sequence가 없습니다."
    )

    raise SystemExit


print()
print(
    "route_id:",
    route_id
)

print(
    "2차 LINK sequence:",
    len(original_sequence),
    "개"
)


# ============================================================
# 2. TMAP 경로 geometry 읽기
# ============================================================

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
        "TMAP geometry가 없습니다."
    )

    raise SystemExit


route_wgs84 = LineString(
    coordinates
)


# ============================================================
# 3. 국가표준 LINK 좌표계 확인
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
# 4. TMAP 경로 좌표계 변환
#
# WGS84 → 국가표준 LINK CRS
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


route_length_m = (
    route_projected.length
)


print(
    "TMAP 경로 길이:",
    round(
        route_length_m / 1000,
        3
    ),
    "km"
)


# ============================================================
# 5. TMAP 경로 주변 국가표준 LINK만 읽기
# ============================================================

search_area = (
    route_projected.buffer(
        SEARCH_MARGIN_M
    )
)


bbox = (
    search_area.bounds
)


print()
print(
    "경로 주변 국가표준 LINK 읽는 중..."
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
# 6. ID 정리
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


# ============================================================
# 7. LINK lookup 생성
# ============================================================

link_lookup = {}


for _, row in links.iterrows():

    link_id = row[
        "LINK_ID"
    ]


    link_lookup[
        link_id
    ] = row


# ============================================================
# 8. 방향 그래프 생성
#
# F_NODE → T_NODE
# ============================================================

graph = {}


for _, row in links.iterrows():

    f_node = row[
        "F_NODE"
    ]

    t_node = row[
        "T_NODE"
    ]

    link_id = row[
        "LINK_ID"
    ]


    if not f_node or not t_node:

        continue


    if f_node not in graph:

        graph[
            f_node
        ] = []


    geometry = row.geometry


    # --------------------------------------------------------
    # 실제 LINK 길이
    # --------------------------------------------------------

    geometry_length = (
        geometry.length
    )


    # --------------------------------------------------------
    # TMAP 경로와 LINK의 거리
    # --------------------------------------------------------

    distance_to_route = (
        geometry.distance(
            route_projected
        )
    )


    # --------------------------------------------------------
    # Cost
    #
    # 링크 길이 +
    # TMAP 경로에서 떨어진 거리 패널티
    # --------------------------------------------------------

    cost = (

        geometry_length

        +

        distance_to_route
        * ROUTE_DISTANCE_WEIGHT

    )


    graph[
        f_node
    ].append({

        "LINK_ID":
            link_id,

        "F_NODE":
            f_node,

        "T_NODE":
            t_node,

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

        "length_m":
            float(
                geometry_length
            ),

        "distance_to_route_m":
            float(
                distance_to_route
            ),

        "cost":
            float(
                cost
            )
    })


# ============================================================
# 9. 최단 연결 LINK 경로 찾기
#
# start_node → target_node
#
# Dijkstra 기반
# ============================================================

def find_bridge_path(
    start_node,
    target_node
):


    # 이미 같은 NODE
    if start_node == target_node:

        return []


    # --------------------------------------------------------
    # Heap
    #
    # (누적 cost, hop 수, 현재 NODE, 사용 LINK 목록)
    # --------------------------------------------------------

    queue = [

        (
            0.0,
            0,
            start_node,
            []
        )

    ]


    visited = {}


    while queue:


        total_cost, hops, current_node, path = (
            heapq.heappop(
                queue
            )
        )


        # ----------------------------------------------------
        # 목적지 NODE 도착
        # ----------------------------------------------------

        if current_node == target_node:

            return path


        # ----------------------------------------------------
        # Hop 제한
        # ----------------------------------------------------

        if hops >= MAX_HOPS:

            continue


        # ----------------------------------------------------
        # 이미 더 좋은 값으로 방문했다면 제외
        # ----------------------------------------------------

        if current_node in visited:

            if (
                visited[current_node]
                <= total_cost
            ):

                continue


        visited[
            current_node
        ] = total_cost


        # ----------------------------------------------------
        # 다음 LINK 탐색
        # ----------------------------------------------------

        for edge in graph.get(
            current_node,
            []
        ):


            new_path = (
                path
                +
                [edge]
            )


            bridge_length = sum(

                item[
                    "length_m"
                ]

                for item
                in new_path
            )


            # ------------------------------------------------
            # 연결 경로가 지나치게 길면 제외
            # ------------------------------------------------

            if (
                bridge_length
                >
                MAX_BRIDGE_LENGTH_M
            ):

                continue


            new_cost = (

                total_cost

                +

                edge[
                    "cost"
                ]
            )


            heapq.heappush(

                queue,

                (
                    new_cost,

                    hops + 1,

                    edge[
                        "T_NODE"
                    ],

                    new_path
                )
            )


    return None


# ============================================================
# 10. 2차 sequence ID 정리
# ============================================================

sequence = []


for item in original_sequence:


    cleaned = dict(
        item
    )


    cleaned["LINK_ID"] = (
        normalize_id(
            cleaned.get(
                "LINK_ID"
            )
        )
    )


    cleaned["F_NODE"] = (
        normalize_id(
            cleaned.get(
                "F_NODE"
            )
        )
    )


    cleaned["T_NODE"] = (
        normalize_id(
            cleaned.get(
                "T_NODE"
            )
        )
    )


    sequence.append(
        cleaned
    )


# ============================================================
# 11. 끊긴 구간 찾기
# ============================================================

gaps = []


for i in range(
    len(sequence) - 1
):


    current_link = (
        sequence[i]
    )


    next_link = (
        sequence[i + 1]
    )


    if (
        current_link[
            "T_NODE"
        ]
        !=
        next_link[
            "F_NODE"
        ]
    ):


        gaps.append({

            "index":
                i,

            "current":
                current_link,

            "next":
                next_link
        })


print()
print(
    "======================================"
)

print(
    "연결 끊김 검사"
)

print(
    "======================================"
)


print(
    "끊긴 구간:",
    len(gaps),
    "개"
)


# ============================================================
# 12. Gap 출력
# ============================================================

for gap_number, gap in enumerate(
    gaps,
    start=1
):


    current_link = gap[
        "current"
    ]


    next_link = gap[
        "next"
    ]


    print()

    print(
        f"[Gap {gap_number}]"
    )


    print(
        "현재 LINK:",
        current_link[
            "LINK_ID"
        ]
    )


    print(
        "현재 T_NODE:",
        current_link[
            "T_NODE"
        ]
    )


    print(
        "다음 LINK:",
        next_link[
            "LINK_ID"
        ]
    )


    print(
        "다음 F_NODE:",
        next_link[
            "F_NODE"
        ]
    )


# ============================================================
# 13. Gap 사이에 빠진 LINK 탐색 및 삽입
# ============================================================

repaired_sequence = []


inserted_links = []


unresolved_gaps = []


for i in range(
    len(sequence) - 1
):


    current_link = (
        sequence[i]
    )


    next_link = (
        sequence[i + 1]
    )


    # 현재 LINK 추가
    repaired_sequence.append(
        current_link
    )


    # ========================================================
    # 정상 연결
    # ========================================================

    if (
        current_link[
            "T_NODE"
        ]
        ==
        next_link[
            "F_NODE"
        ]
    ):

        continue


    # ========================================================
    # 연결이 끊긴 경우
    # ========================================================

    start_node = (
        current_link[
            "T_NODE"
        ]
    )


    target_node = (
        next_link[
            "F_NODE"
        ]
    )


    print()
    print(
        "--------------------------------------"
    )

    print(
        "Gap 보정 시도"
    )

    print(
        "--------------------------------------"
    )


    print(
        current_link[
            "LINK_ID"
        ],
        "→",
        next_link[
            "LINK_ID"
        ]
    )


    print(
        start_node,
        "→",
        target_node
    )


    bridge = find_bridge_path(

        start_node,

        target_node
    )


    # ========================================================
    # 연결 경로 못 찾음
    # ========================================================

    if bridge is None:


        print(
            "❌ 연결 LINK를 찾지 못했습니다."
        )


        unresolved_gaps.append({

            "current_link_id":
                current_link[
                    "LINK_ID"
                ],

            "next_link_id":
                next_link[
                    "LINK_ID"
                ],

            "start_node":
                start_node,

            "target_node":
                target_node
        })


        continue


    # ========================================================
    # 연결 LINK 발견
    # ========================================================

    print(
        "✅ 연결 경로 발견:",
        len(bridge),
        "개 LINK"
    )


    for bridge_link in bridge:


        bridge_link_id = (
            bridge_link[
                "LINK_ID"
            ]
        )


        # 현재 LINK나 다음 LINK 자체가
        # Bridge에 포함되면 중복 방지
        if (
            bridge_link_id
            ==
            current_link[
                "LINK_ID"
            ]
            or
            bridge_link_id
            ==
            next_link[
                "LINK_ID"
            ]
        ):

            continue


        bridge_item = {

            "sequence":
                0,

            "LINK_ID":
                bridge_link[
                    "LINK_ID"
                ],

            "F_NODE":
                bridge_link[
                    "F_NODE"
                ],

            "T_NODE":
                bridge_link[
                    "T_NODE"
                ],

            "ROAD_NAME":
                bridge_link[
                    "ROAD_NAME"
                ],

            "sample_position_m":
                None,

            "distance_to_tmap_m":
                round(
                    bridge_link[
                        "distance_to_route_m"
                    ],
                    2
                ),

            "direction_diff_deg":
                None,

            "repair_inserted":
                True
        }


        repaired_sequence.append(
            bridge_item
        )


        inserted_links.append(
            bridge_item
        )


# ============================================================
# 마지막 LINK 추가
# ============================================================

repaired_sequence.append(
    sequence[-1]
)


# ============================================================
# 14. 연속 중복 제거
# ============================================================

deduplicated_sequence = []


previous_id = None


for item in repaired_sequence:


    link_id = item[
        "LINK_ID"
    ]


    if link_id == previous_id:

        continue


    deduplicated_sequence.append(
        item
    )


    previous_id = link_id


repaired_sequence = (
    deduplicated_sequence
)


# ============================================================
# 15. sequence 번호 재부여
# ============================================================

for index, item in enumerate(
    repaired_sequence
):


    item[
        "sequence"
    ] = index


# ============================================================
# 16. 최종 연결률 계산
# ============================================================

connected_count = 0


broken_pairs = []


for i in range(
    len(repaired_sequence) - 1
):


    current_link = (
        repaired_sequence[i]
    )


    next_link = (
        repaired_sequence[i + 1]
    )


    if (
        current_link[
            "T_NODE"
        ]
        ==
        next_link[
            "F_NODE"
        ]
    ):


        connected_count += 1


    else:


        broken_pairs.append({

            "current_link_id":
                current_link[
                    "LINK_ID"
                ],

            "next_link_id":
                next_link[
                    "LINK_ID"
                ],

            "current_t_node":
                current_link[
                    "T_NODE"
                ],

            "next_f_node":
                next_link[
                    "F_NODE"
                ]
        })


pair_count = max(

    len(
        repaired_sequence
    ) - 1,

    0
)


connection_ratio = (

    connected_count
    /
    pair_count

    if pair_count > 0

    else 0
)


# ============================================================
# 17. 결과 출력
# ============================================================

print()
print(
    "======================================"
)

print(
    "3차 LINK 연결 보정 결과"
)

print(
    "======================================"
)


print(
    "기존 LINK:",
    len(sequence),
    "개"
)


print(
    "자동 삽입 LINK:",
    len(inserted_links),
    "개"
)


print(
    "최종 LINK:",
    len(repaired_sequence),
    "개"
)


print(
    "남은 끊김:",
    len(broken_pairs),
    "개"
)


print(
    "최종 LINK 연결률:",
    round(
        connection_ratio * 100,
        2
    ),
    "%"
)


# ============================================================
# 18. 삽입된 LINK 확인
# ============================================================

if len(inserted_links) > 0:


    print()
    print(
        "======================================"
    )

    print(
        "자동 삽입된 LINK"
    )

    print(
        "======================================"
    )


    for item in inserted_links:


        print()

        print(
            "LINK_ID:",
            item[
                "LINK_ID"
            ]
        )


        print(
            "도로명:",
            item[
                "ROAD_NAME"
            ]
        )


        print(
            "F_NODE:",
            item[
                "F_NODE"
            ]
        )


        print(
            "T_NODE:",
            item[
                "T_NODE"
            ]
        )


        print(
            "TMAP 경로 거리:",
            item[
                "distance_to_tmap_m"
            ],
            "m"
        )


# ============================================================
# 19. 아직 끊긴 구간
# ============================================================

if len(broken_pairs) > 0:


    print()
    print(
        "======================================"
    )

    print(
        "아직 연결되지 않은 구간"
    )

    print(
        "======================================"
    )


    for gap in broken_pairs:


        print()

        print(
            gap[
                "current_link_id"
            ],
            "→",
            gap[
                "next_link_id"
            ]
        )


        print(
            gap[
                "current_t_node"
            ],
            "→",
            gap[
                "next_f_node"
            ]
        )


# ============================================================
# 20. JSON 결과 생성
# ============================================================

output_data = copy.deepcopy(
    route_data
)


previous_mapping = (
    output_data.get(
        "link_mapping",
        {}
    )
)


output_data[
    "link_mapping"
] = {

    "status":
        (
            "repaired"
            if len(
                broken_pairs
            ) == 0
            else "partially_repaired"
        ),

    "method":
        "node_graph_gap_repair_v3",

    "previous_method":
        previous_mapping.get(
            "method"
        ),

    "sample_coverage_percent":
        previous_mapping.get(
            "sample_coverage_percent"
        ),

    "original_link_count":
        len(
            sequence
        ),

    "inserted_link_count":
        len(
            inserted_links
        ),

    "final_link_count":
        len(
            repaired_sequence
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

    "remaining_gap_count":
        len(
            broken_pairs
        ),

    "matched_link_ids": [

        item[
            "LINK_ID"
        ]

        for item
        in repaired_sequence
    ],

    "link_sequence":
        repaired_sequence,

    "remaining_gaps":
        broken_pairs
}


# ============================================================
# 21. JSON 저장
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
# 22. CSV 저장
# ============================================================

csv_rows = []


for item in repaired_sequence:


    csv_rows.append({

        "sequence":
            item.get(
                "sequence"
            ),

        "LINK_ID":
            item.get(
                "LINK_ID"
            ),

        "F_NODE":
            item.get(
                "F_NODE"
            ),

        "T_NODE":
            item.get(
                "T_NODE"
            ),

        "ROAD_NAME":
            item.get(
                "ROAD_NAME"
            ),

        "distance_to_tmap_m":
            item.get(
                "distance_to_tmap_m"
            ),

        "repair_inserted":
            item.get(
                "repair_inserted",
                False
            )
    })


df = pd.DataFrame(
    csv_rows
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
    "3차 보정 저장 완료"
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