import os
import json
import math
import copy

import pyogrio

from pyproj import CRS
from pyproj import Transformer

from shapely.geometry import LineString
from shapely.ops import transform
from shapely.ops import nearest_points
from shapely.ops import unary_union


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
    "route_test_001_mapped.json"
)


OUTPUT_CSV = os.path.join(
    "data",
    "routes",
    "route_test_001_link_matches.csv"
)


# ============================================================
# Map Matching 설정값
# ============================================================

# TMAP 경로 주변 몇 m 안의 링크를 매칭 대상으로 볼 것인지
MATCH_BUFFER_M = 35


# SHP에서 후보를 읽어올 범위
# 경로 주변 150m 정도만 읽음
SEARCH_MARGIN_M = 150


# 링크 중 어느 정도가 경로 주변에 들어와야 하는지
MIN_OVERLAP_RATIO = 0.15


# 경로와 링크 진행방향 차이 허용값
MAX_DIRECTION_DIFF = 75


# Coverage 계산할 때 사용할 거리
COVERAGE_BUFFER_M = 30


# ============================================================
# 1. 파일 존재 확인
# ============================================================

print()
print("======================================")
print("FLOW TMAP → 국가표준 LINK 매칭")
print("======================================")


if not os.path.exists(ROUTE_FILE):

    print()
    print("TMAP Route JSON을 찾을 수 없습니다.")
    print("경로:", ROUTE_FILE)

    raise SystemExit


if not os.path.exists(LINK_FILE):

    print()
    print("국가표준 LINK SHP를 찾을 수 없습니다.")
    print("경로:", LINK_FILE)

    raise SystemExit


print()
print("TMAP Route:", ROUTE_FILE)
print("국가표준 LINK:", LINK_FILE)


# ============================================================
# 2. TMAP Route JSON 읽기
# ============================================================

with open(
    ROUTE_FILE,
    "r",
    encoding="utf-8"
) as file:

    route_data = json.load(file)


route_id = route_data.get(
    "route_id",
    "unknown"
)


coordinates = (
    route_data
    .get("geometry", {})
    .get("coordinates", [])
)


if len(coordinates) < 2:

    print(
        "TMAP 경로 좌표가 부족합니다."
    )

    raise SystemExit


print()
print("route_id:", route_id)
print(
    "TMAP 좌표 개수:",
    len(coordinates)
)


# ============================================================
# 3. TMAP 경로를 LineString으로 변환
#
# TMAP 좌표:
#
# [경도, 위도]
#
# WGS84 = EPSG:4326
# ============================================================

route_wgs84 = LineString(
    coordinates
)


# ============================================================
# 4. 국가표준 LINK 좌표계 확인
# ============================================================

link_info = pyogrio.read_info(
    LINK_FILE
)


link_crs_text = link_info[
    "crs"
]


link_crs = CRS.from_user_input(
    link_crs_text
)


print()
print(
    "국가표준 LINK CRS:",
    link_crs
)


# ============================================================
# 5. TMAP WGS84 → 국가표준 LINK 좌표계 변환
#
# 중요:
#
# TMAP = 위경도
# MOCT_LINK = 미터 기반 투영좌표계
#
# 같은 좌표계로 만들어야 거리 계산 가능
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


print()
print(
    "TMAP 경로 길이:",
    round(
        route_length_m / 1000,
        3
    ),
    "km"
)


# ============================================================
# 6. TMAP 경로 주변 검색 범위 생성
# ============================================================

search_area = (
    route_projected.buffer(
        SEARCH_MARGIN_M
    )
)


bbox = search_area.bounds


print()
print(
    "국가표준 LINK 후보 검색 중..."
)


# ============================================================
# 7. 전국 LINK 중 경로 주변 데이터만 읽기
#
# 전국 155만 개를 전부 메모리에 올리지 않음
# ============================================================

columns = [

    "LINK_ID",

    "F_NODE",

    "T_NODE",

    "ROAD_NAME",

    "LENGTH"
]


links = pyogrio.read_dataframe(

    LINK_FILE,

    bbox=bbox,

    columns=columns
)


print(
    "BBox 후보 LINK:",
    len(links),
    "개"
)


# ============================================================
# 8. geometry 없는 데이터 제거
# ============================================================

links = links[
    links.geometry.notna()
].copy()


links = links[
    ~links.geometry.is_empty
].copy()


# ============================================================
# 9. 실제 경로 주변 35m 후보만 선택
# ============================================================

match_buffer = (
    route_projected.buffer(
        MATCH_BUFFER_M
    )
)


links = links[
    links.geometry.intersects(
        match_buffer
    )
].copy()


print(
    "경로 주변 후보 LINK:",
    len(links),
    "개"
)


if len(links) == 0:

    print()
    print(
        "주변 국가표준 LINK를 찾지 못했습니다."
    )

    raise SystemExit


# ============================================================
# 진행방향 계산 함수
# ============================================================

def get_line_heading(line):

    """
    LineString 시작점 → 끝점 방향 계산
    """

    if line is None:

        return None


    coords = list(
        line.coords
    )


    if len(coords) < 2:

        return None


    x1, y1 = coords[0]

    x2, y2 = coords[-1]


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
# TMAP 경로의 특정 위치 주변 진행방향 계산
# ============================================================

def get_route_heading(
    route,
    position
):

    """
    route 상에서 ±15m 지점을 이용하여
    해당 부분의 진행방향을 계산
    """

    before_position = max(

        0,

        position - 15
    )


    after_position = min(

        route.length,

        position + 15
    )


    point_before = route.interpolate(
        before_position
    )


    point_after = route.interpolate(
        after_position
    )


    dx = (
        point_after.x -
        point_before.x
    )


    dy = (
        point_after.y -
        point_before.y
    )


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
# 두 진행방향 차이
#
# 0도 = 같은 방향
# 180도 = 반대 방향
# ============================================================

def heading_difference(
    heading1,
    heading2
):

    if (
        heading1 is None
        or
        heading2 is None
    ):

        return 180


    difference = abs(
        heading1 -
        heading2
    )


    return min(

        difference,

        360 - difference
    )


# ============================================================
# 10. 후보 LINK 점수 계산
# ============================================================

match_results = []


print()
print(
    "LINK geometry 매칭 계산 중..."
)


for index, row in links.iterrows():


    geometry = row.geometry


    if geometry is None:

        continue


    if geometry.length == 0:

        continue


    # --------------------------------------------------------
    # TMAP 경로와 LINK 사이 최소거리
    # --------------------------------------------------------

    distance_m = geometry.distance(
        route_projected
    )


    # --------------------------------------------------------
    # LINK 중 얼마나 많은 부분이
    # TMAP 경로 35m 주변에 들어오는지
    # --------------------------------------------------------

    intersection = geometry.intersection(
        match_buffer
    )


    overlap_length_m = (
        intersection.length
    )


    overlap_ratio = (

        overlap_length_m
        /
        geometry.length

    )


    # --------------------------------------------------------
    # LINK와 가장 가까운 TMAP 경로 위치 찾기
    # --------------------------------------------------------

    route_point, link_point = (
        nearest_points(
            route_projected,
            geometry
        )
    )


    route_position = (
        route_projected.project(
            route_point
        )
    )


    # --------------------------------------------------------
    # 진행방향 비교
    # --------------------------------------------------------

    link_heading = (
        get_line_heading(
            geometry
        )
    )


    route_heading = (
        get_route_heading(
            route_projected,
            route_position
        )
    )


    direction_diff = (
        heading_difference(
            link_heading,
            route_heading
        )
    )


    # ========================================================
    # 1차 필터
    # ========================================================

    if distance_m > MATCH_BUFFER_M:

        continue


    if overlap_ratio < MIN_OVERLAP_RATIO:

        continue


    if direction_diff > MAX_DIRECTION_DIFF:

        continue


    # ========================================================
    # 매칭 점수
    #
    # overlap  : 50%
    # 거리     : 30%
    # 진행방향 : 20%
    # ========================================================

    distance_score = max(

        0,

        1 -
        (
            distance_m
            /
            MATCH_BUFFER_M
        )
    )


    direction_score = max(

        0,

        1 -
        (
            direction_diff
            /
            MAX_DIRECTION_DIFF
        )
    )


    overlap_score = min(

        overlap_ratio,

        1
    )


    total_score = (

        overlap_score * 0.50

        +

        distance_score * 0.30

        +

        direction_score * 0.20

    )


    # ========================================================
    # 저장
    # ========================================================

    match_results.append({

        "LINK_ID":
            str(
                row["LINK_ID"]
            ),

        "ROAD_NAME":
            (
                ""
                if row["ROAD_NAME"] is None
                else str(
                    row["ROAD_NAME"]
                )
            ),

        "F_NODE":
            str(
                row["F_NODE"]
            ),

        "T_NODE":
            str(
                row["T_NODE"]
            ),

        "LENGTH":
            row["LENGTH"],

        "distance_m":
            round(
                float(distance_m),
                2
            ),

        "overlap_ratio":
            round(
                float(overlap_ratio),
                4
            ),

        "direction_diff":
            round(
                float(direction_diff),
                2
            ),

        "score":
            round(
                float(total_score),
                4
            ),

        # TMAP 경로상 위치
        # 출발점부터 몇 m 지점인지
        "route_position_m":
            round(
                float(route_position),
                2
            ),

        "_geometry":
            geometry
    })


# ============================================================
# 11. 경로 순서대로 정렬
# ============================================================

match_results.sort(

    key=lambda x:
        x["route_position_m"]
)


print()
print(
    "1차 매칭 LINK:",
    len(match_results),
    "개"
)


if len(match_results) == 0:

    print()
    print(
        "매칭 결과가 없습니다."
    )

    print(
        "MATCH_BUFFER_M을 "
        "50 정도로 높여 다시 테스트할 수 있습니다."
    )

    raise SystemExit


# ============================================================
# 12. 중복 LINK 제거
# ============================================================

unique_matches = []

seen_link_ids = set()


for result in match_results:


    link_id = result[
        "LINK_ID"
    ]


    if link_id in seen_link_ids:

        continue


    seen_link_ids.add(
        link_id
    )


    unique_matches.append(
        result
    )


match_results = (
    unique_matches
)


# ============================================================
# 13. Coverage 계산
#
# 선택된 국가표준 LINK 주변 30m를
# TMAP 경로가 얼마나 통과하는지 계산
# ============================================================

matched_geometries = [

    result["_geometry"]

    for result
    in match_results
]


matched_buffers = [

    geometry.buffer(
        COVERAGE_BUFFER_M
    )

    for geometry
    in matched_geometries
]


matched_area = unary_union(
    matched_buffers
)


covered_route = (
    route_projected
    .intersection(
        matched_area
    )
)


covered_length_m = (
    covered_route.length
)


coverage_ratio = (

    covered_length_m
    /
    route_length_m

    if route_length_m > 0

    else 0

)


coverage_ratio = min(

    coverage_ratio,

    1.0
)


# ============================================================
# 14. 터미널 출력
# ============================================================

print()
print(
    "======================================"
)

print(
    "TMAP → 국가표준 LINK 매칭 결과"
)

print(
    "======================================"
)


print(
    "route_id:",
    route_id
)


print(
    "TMAP 경로 길이:",
    round(
        route_length_m / 1000,
        3
    ),
    "km"
)


print(
    "최종 매칭 LINK:",
    len(match_results),
    "개"
)


print(
    "Coverage:",
    round(
        coverage_ratio * 100,
        2
    ),
    "%"
)


print()
print(
    "======================================"
)

print(
    "매칭된 LINK 목록"
)

print(
    "======================================"
)


for order, result in enumerate(
    match_results,
    start=1
):


    print()

    print(
        f"[{order}]"
    )

    print(
        "LINK_ID:",
        result["LINK_ID"]
    )

    print(
        "도로명:",
        result["ROAD_NAME"]
    )

    print(
        "경로와 거리:",
        result["distance_m"],
        "m"
    )

    print(
        "겹침비율:",
        round(
            result[
                "overlap_ratio"
            ] * 100,
            1
        ),
        "%"
    )

    print(
        "방향차이:",
        result[
            "direction_diff"
        ],
        "도"
    )

    print(
        "매칭점수:",
        result["score"]
    )


# ============================================================
# 15. geometry 제외하고 JSON용 결과 만들기
# ============================================================

json_matches = []


for result in match_results:


    clean_result = {

        key: value

        for key, value
        in result.items()

        if key != "_geometry"
    }


    json_matches.append(
        clean_result
    )


# ============================================================
# 16. 기존 Route JSON 복사
# ============================================================

mapped_route = copy.deepcopy(
    route_data
)


matched_link_ids = [

    result["LINK_ID"]

    for result
    in json_matches
]


# ============================================================
# 17. link_mapping 업데이트
# ============================================================

mapped_route[
    "link_mapping"
] = {

    "status":
        (
            "mapped"
            if len(
                matched_link_ids
            ) > 0
            else "failed"
        ),

    "method":
        "geometry_buffer_direction_v1",

    "source":
        "MOCT_LINK",

    "matched_link_count":
        len(
            matched_link_ids
        ),

    "matched_link_ids":
        matched_link_ids,

    "coverage_ratio":
        round(
            coverage_ratio,
            4
        ),

    "coverage_percent":
        round(
            coverage_ratio * 100,
            2
        ),

    "match_buffer_m":
        MATCH_BUFFER_M,

    "matches":
        json_matches
}


# ============================================================
# 18. 새로운 JSON으로 저장
#
# 원본 route_test_001.json은 보존
# ============================================================

with open(
    OUTPUT_JSON,
    "w",
    encoding="utf-8"
) as file:


    json.dump(

        mapped_route,

        file,

        ensure_ascii=False,

        indent=2
    )


# ============================================================
# 19. CSV도 저장
# ============================================================

import pandas as pd


match_dataframe = (
    pd.DataFrame(
        json_matches
    )
)


match_dataframe.to_csv(

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
    "매칭 파일 저장 완료"
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


print()
print(
    "★ 원본 route_test_001.json은"
    " 수정하지 않았습니다."
)