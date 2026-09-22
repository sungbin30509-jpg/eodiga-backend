from pathlib import Path
import json
import hashlib

import requests

from backend.services.location_service import (
    get_tmap_app_key,
    resolve_location,
)

from backend.services.navigation_guidance import (
    extract_navigation_guidance,
)


# ============================================================
# FLOW:MATE
# Universal TMAP Route Engine
#
# 장소명
# →
# Location Resolver
# →
# 좌표
# →
# TMAP 자동차 경로 A / B / C
# →
# Route Geometry
# →
# Navigation Guidance
# →
# Route Cache
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

CURRENT_FILE = Path(__file__).resolve()

ROOT = CURRENT_FILE.parents[2]


CACHE_DIR = (
    ROOT
    / "cache"
    / "routes"
)


CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. TMAP 자동차 경로 API
# ============================================================

TMAP_ROUTE_URL = (
    "https://apis.openapi.sk.com/tmap/routes"
)


# ============================================================
# 3. FLOW:MATE 경로 후보
#
# A : searchOption 0
# B : searchOption 2
# C : searchOption 10
# ============================================================

ROUTE_OPTIONS = {

    "A": {

        "search_option":
            "0",

        "label":
            "traffic_optimal",

    },

    "B": {

        "search_option":
            "2",

        "label":
            "minimum_time",

    },

    "C": {

        "search_option":
            "10",

        "label":
            "shortest",

    },

}


# ============================================================
# 4. Route Cache Key
# ============================================================

def make_route_cache_key(
    origin,
    destination,
):

    raw = (

        f"{origin['lat']:.7f},"
        f"{origin['lon']:.7f}|"
        f"{destination['lat']:.7f},"
        f"{destination['lon']:.7f}"

    )


    return (

        hashlib
        .sha256(
            raw.encode(
                "utf-8"
            )
        )
        .hexdigest()[:24]

    )


# ============================================================
# 5. Cache 파일 경로
# ============================================================

def get_route_cache_file(
    origin,
    destination,
):

    cache_key = (
        make_route_cache_key(
            origin,
            destination,
        )
    )


    return (

        CACHE_DIR
        / f"{cache_key}.json"

    )


# ============================================================
# 6. TMAP feature에서 geometry 추출
# ============================================================

def extract_route_geometry(
    features,
):

    coordinates = []


    for feature in features:

        geometry = (
            feature.get(
                "geometry",
                {}
            )
        )


        geometry_type = (
            geometry.get(
                "type"
            )
        )


        geometry_coordinates = (
            geometry.get(
                "coordinates"
            )
        )


        if not geometry_coordinates:

            continue


        # ----------------------------------------------------
        # LineString
        # ----------------------------------------------------

        if geometry_type == "LineString":

            for coordinate in geometry_coordinates:

                if (
                    isinstance(
                        coordinate,
                        list,
                    )
                    and
                    len(coordinate) >= 2
                ):

                    lon = float(
                        coordinate[0]
                    )

                    lat = float(
                        coordinate[1]
                    )


                    point = [
                        lon,
                        lat,
                    ]


                    # 연속 중복 좌표 제거
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



# ============================================================
# 6-1. TMAP 현재 교통정보 구간 추출
#
# trafficInfo = "Y"일 때
# TMAP 자동차 경로의 LineString geometry에는
#
# traffic = [
#     시작 index,
#     마지막 index,
#     혼잡도,
#     속도
# ]
#
# 가 포함될 수 있다.
#
# congestion_level
#
# 0 = 정보없음
# 1 = 원활
# 2 = 서행
# 3 = 지체
# 4 = 정체
#
# 중요:
# 이것은 현재 시점 TMAP 교통정보이다.
# LightGBM 미래 교통예측 결과가 아니다.
# ============================================================

def extract_tmap_traffic_segments(
    features,
):

    traffic_segments = []

    sequence = 0


    congestion_labels = {

        0:
            "정보없음",

        1:
            "원활",

        2:
            "서행",

        3:
            "지체",

        4:
            "정체",

    }


    for feature in features:

        if not isinstance(
            feature,
            dict,
        ):

            continue


        # ----------------------------------------------------
        # Geometry
        # ----------------------------------------------------

        geometry = (
            feature.get(
                "geometry",
                {},
            )
        )


        if not isinstance(
            geometry,
            dict,
        ):

            continue


        if (
            geometry.get(
                "type"
            )
            !=
            "LineString"
        ):

            continue


        coordinates = (
            geometry.get(
                "coordinates",
                [],
            )
        )


        if (
            not isinstance(
                coordinates,
                list,
            )
            or
            len(
                coordinates
            )
            < 2
        ):

            continue


        # ----------------------------------------------------
        # Properties
        # ----------------------------------------------------

        properties = (
            feature.get(
                "properties",
                {},
            )
        )


        if not isinstance(
            properties,
            dict,
        ):

            properties = {}


        # ----------------------------------------------------
        # TMAP Traffic
        #
        # 공식 자동차 경로응답:
        #
        # geometry.traffic
        #
        # 예:
        #
        # [0, 5, 2, 17]
        #
        # 0   → 시작 coordinate index
        # 5   → 마지막 coordinate index
        # 2   → 서행
        # 17  → 17 km/h
        # ----------------------------------------------------

        traffic = (
            geometry.get(
                "traffic"
            )
        )


        # ----------------------------------------------------
        # API 응답 변형을 고려한 방어적 fallback
        # ----------------------------------------------------

        if traffic is None:

            traffic = (
                feature.get(
                    "traffic"
                )
            )


        if traffic is None:

            traffic = (
                properties.get(
                    "traffic"
                )
            )


        # 문자열 형태가 들어온 경우도 방어적으로 처리
        if isinstance(
            traffic,
            str,
        ):

            try:

                traffic = (
                    json.loads(
                        traffic
                    )
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ):

                traffic = None


        # ----------------------------------------------------
        # Traffic 배열 정규화
        #
        # 일반:
        #
        # [start, end, level, speed]
        #
        # 혹시 중첩:
        #
        # [
        #   [start, end, level, speed],
        #   ...
        # ]
        #
        # 형태가 와도 처리.
        # ----------------------------------------------------

        traffic_items = []


        if isinstance(
            traffic,
            (
                list,
                tuple,
            ),
        ):

            if (
                len(
                    traffic
                )
                >= 4
                and
                not isinstance(
                    traffic[0],
                    (
                        list,
                        tuple,
                    ),
                )
            ):

                traffic_items = [
                    traffic
                ]


            else:

                traffic_items = [

                    item

                    for item
                    in traffic

                    if (
                        isinstance(
                            item,
                            (
                                list,
                                tuple,
                            ),
                        )
                        and
                        len(
                            item
                        )
                        >= 4
                    )

                ]


        # ----------------------------------------------------
        # 교통정보 없는 LineString
        #
        # Geometry 자체는 버리지 않고
        # 정보없음(level=0)으로 Flutter에 전달.
        #
        # 나중에 회색 선으로 표시한다.
        # ----------------------------------------------------

        if not traffic_items:

            traffic_segments.append({

                "sequence":
                    sequence,

                "feature_index":
                    properties.get(
                        "index"
                    ),

                "line_index":
                    properties.get(
                        "lineIndex"
                    ),

                "road_name":
                    properties.get(
                        "name"
                    ),

                "start_index":
                    0,

                "end_index":
                    (
                        len(
                            coordinates
                        )
                        - 1
                    ),

                "congestion_level":
                    0,

                "congestion_label":
                    congestion_labels[
                        0
                    ],

                "speed_kmh":
                    None,

                "geometry":
                    coordinates,

                "coordinate_order":
                    "lon_lat",

                "source":
                    "tmap_current",

            })


            sequence += 1

            continue


        # ----------------------------------------------------
        # Traffic 구간별 처리
        # ----------------------------------------------------

        for item in traffic_items:

            try:

                start_index = int(
                    float(
                        item[0]
                    )
                )


                end_index = int(
                    float(
                        item[1]
                    )
                )


                congestion_level = int(
                    float(
                        item[2]
                    )
                )


                speed_kmh = (

                    float(
                        item[3]
                    )

                    if (
                        item[3]
                        is not None
                    )

                    else None

                )


            except (
                TypeError,
                ValueError,
                IndexError,
            ):

                continue


            # ------------------------------------------------
            # Index 범위 보호
            # ------------------------------------------------

            start_index = max(

                0,

                min(
                    start_index,
                    len(
                        coordinates
                    )
                    - 1,
                ),

            )


            end_index = max(

                0,

                min(
                    end_index,
                    len(
                        coordinates
                    )
                    - 1,
                ),

            )


            # ------------------------------------------------
            # 시작/끝이 뒤집힌 경우
            # ------------------------------------------------

            if (
                end_index
                <
                start_index
            ):

                (
                    start_index,
                    end_index,
                ) = (
                    end_index,
                    start_index,
                )


            # ------------------------------------------------
            # 점 하나만 선택된 경우
            #
            # Polyline을 만들려면 최소 2점 필요
            # ------------------------------------------------

            if (
                end_index
                ==
                start_index
            ):

                if (
                    end_index + 1
                    <
                    len(
                        coordinates
                    )
                ):

                    end_index += 1


                elif (
                    start_index
                    >
                    0
                ):

                    start_index -= 1


            # ------------------------------------------------
            # 해당 교통구간 Geometry
            # ------------------------------------------------

            segment_geometry = (
                coordinates[
                    start_index:
                    end_index + 1
                ]
            )


            if (
                len(
                    segment_geometry
                )
                < 2
            ):

                continue


            # ------------------------------------------------
            # 공식 혼잡도 이외 값 보호
            # ------------------------------------------------

            if (
                congestion_level
                not in {
                    0,
                    1,
                    2,
                    3,
                    4,
                }
            ):

                congestion_level = 0


            # ------------------------------------------------
            # 결과
            # ------------------------------------------------

            traffic_segments.append({

                "sequence":
                    sequence,

                "feature_index":
                    properties.get(
                        "index"
                    ),

                "line_index":
                    properties.get(
                        "lineIndex"
                    ),

                "road_name":
                    properties.get(
                        "name"
                    ),

                "start_index":
                    start_index,

                "end_index":
                    end_index,

                "congestion_level":
                    congestion_level,

                "congestion_label":
                    congestion_labels[
                        congestion_level
                    ],

                "speed_kmh":
                    speed_kmh,

                "geometry":
                    segment_geometry,

                "coordinate_order":
                    "lon_lat",

                "source":
                    "tmap_current",

            })


            sequence += 1


    return traffic_segments


# ============================================================
# 7. TMAP Summary 추출
# ============================================================

def extract_route_summary(
    features,
):

    total_distance_m = None
    total_time_sec = None


    # TMAP은 일반적으로 첫 번째 Point feature에
    # totalDistance / totalTime을 제공
    for feature in features:

        properties = (
            feature.get(
                "properties",
                {}
            )
        )


        if (
            total_distance_m
            is None
            and
            properties.get(
                "totalDistance"
            )
            is not None
        ):

            try:

                total_distance_m = int(

                    float(
                        properties[
                            "totalDistance"
                        ]
                    )

                )

            except (
                TypeError,
                ValueError,
            ):

                pass


        if (
            total_time_sec
            is None
            and
            properties.get(
                "totalTime"
            )
            is not None
        ):

            try:

                total_time_sec = int(

                    float(
                        properties[
                            "totalTime"
                        ]
                    )

                )

            except (
                TypeError,
                ValueError,
            ):

                pass


    return (
        total_distance_m,
        total_time_sec,
    )


# ============================================================
# 8. TMAP 경로 1개 호출
# ============================================================

def request_tmap_route(
    origin,
    destination,
    candidate_id,
):

    if candidate_id not in ROUTE_OPTIONS:

        raise ValueError(
            f"지원하지 않는 경로 후보입니다: {candidate_id}"
        )


    option = (
        ROUTE_OPTIONS[
            candidate_id
        ]
    )


    app_key = (
        get_tmap_app_key()
    )


    headers = {

        "appKey":
            app_key,

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

    }


    payload = {

        "startX":
            str(
                origin[
                    "lon"
                ]
            ),

        "startY":
            str(
                origin[
                    "lat"
                ]
            ),

        "endX":
            str(
                destination[
                    "lon"
                ]
            ),

        "endY":
            str(
                destination[
                    "lat"
                ]
            ),

        "reqCoordType":
            "WGS84GEO",

        "resCoordType":
            "WGS84GEO",

        "searchOption":
            option[
                "search_option"
            ],

        "trafficInfo":
            "Y",

    }


    try:

        response = requests.post(

            TMAP_ROUTE_URL,

            headers=headers,

            json=payload,

            timeout=30,

        )


    except requests.RequestException as error:

        raise RuntimeError(

            "TMAP 경로 API 연결 실패\n"
            f"{error}"

        ) from error


    if response.status_code != 200:

        raise RuntimeError(

            "TMAP 경로 검색 실패\n"
            "\n"
            f"Candidate: {candidate_id}\n"
            f"Search Option: {option['search_option']}\n"
            f"HTTP Status: {response.status_code}\n"
            "\n"
            f"Response:\n"
            f"{response.text[:1500]}"

        )


    try:

        data = (
            response.json()
        )


    except ValueError as error:

        raise RuntimeError(

            "TMAP 경로 응답이 "
            "올바른 JSON이 아닙니다."

        ) from error


    features = (
        data.get(
            "features",
            []
        )
    )


    if not features:

        raise RuntimeError(

            "TMAP 경로 결과에 "
            "features가 없습니다. "
            f"Candidate: {candidate_id}"

        )


    # ========================================================
    # Route Geometry
    # ========================================================

    geometry = (
        extract_route_geometry(
            features
        )
    )


    # ========================================================
    # TMAP Summary
    # ========================================================

    total_distance_m, total_time_sec = (
        extract_route_summary(
            features
        )
    )


    if not geometry:

        raise RuntimeError(

            "TMAP 경로에서 "
            "LineString geometry를 "
            f"찾지 못했습니다: {candidate_id}"

        )


    # ========================================================
    # Navigation Guidance
    #
    # TMAP Point Feature의
    # turnType / pointType / description / nextRoadName 등을
    # Route Geometry상 위치와 연결
    # ========================================================

    navigation_guidance = (
        extract_navigation_guidance(
            features,
            geometry,
        )
    )


    # ========================================================
    # TMAP Current Traffic
    #
    # 현재 경로 응답에 포함된 교통상태를
    # Geometry 구간별로 추출한다.
    #
    # AI 미래예측값이 아니다.
    # ========================================================

    traffic_segments = (
        extract_tmap_traffic_segments(
            features
        )
    )


    # ========================================================
    # 결과
    # ========================================================

    return {

        "candidate_id":
            candidate_id,

        "route_label":
            option[
                "label"
            ],

        "search_option":
            option[
                "search_option"
            ],

        "origin": {

            "name":
                origin.get(
                    "name"
                ),

            "lat":
                origin[
                    "lat"
                ],

            "lon":
                origin[
                    "lon"
                ],

        },

        "destination": {

            "name":
                destination.get(
                    "name"
                ),

            "lat":
                destination[
                    "lat"
                ],

            "lon":
                destination[
                    "lon"
                ],

        },

        "total_distance_m":
            total_distance_m,

        "tmap_eta_sec":
            total_time_sec,

        "tmap_eta_min":
            (
                round(
                    total_time_sec
                    / 60,
                    1,
                )

                if total_time_sec
                is not None

                else None
            ),

        # ====================================================
        # Route Geometry
        # ====================================================

        "geometry":
            geometry,

        "geometry_point_count":
            len(
                geometry
            ),

        # ====================================================
        # Navigation Guidance
        # ====================================================

        "navigation_guidance":
            navigation_guidance,

        "navigation_guidance_count":
            len(
                navigation_guidance
            ),

        "navigation_schema_version":
            "navigation_guidance_v1",

        # ====================================================
        # TMAP Current Traffic
        # ====================================================

        "traffic_segments":
            traffic_segments,

        "traffic_segment_count":
            len(
                traffic_segments
            ),

        "traffic_schema_version":
            "tmap_current_traffic_v1",

        "traffic_source":
            "tmap_current",

        "source":
            "tmap",

    }


# ============================================================
# 9. A/B/C 세 경로 생성
# ============================================================

def build_route_candidates(
    origin,
    destination,
):

    routes = []


    for candidate_id in [

        "A",
        "B",
        "C",

    ]:

        print(
            f"TMAP Route {candidate_id} 요청 중..."
        )


        route = (
            request_tmap_route(

                origin,

                destination,

                candidate_id,

            )
        )


        routes.append(
            route
        )


        print(

            f"Route {candidate_id} 완료 | "
            f"{route['total_distance_m']} m | "
            f"{route['tmap_eta_min']} min | "
            f"{route['geometry_point_count']} points | "
            f"{route['navigation_guidance_count']} guidance | "
            f"{route['traffic_segment_count']} traffic segments"

        )


    return routes


# ============================================================
# 10. 핵심 함수
#
# 장소명 → A/B/C
# ============================================================

def get_routes_by_place_names(
    origin_query,
    destination_query,
    origin_region_hint=None,
    destination_region_hint=None,
    force_refresh=False,
):

    # --------------------------------------------------------
    # 장소 → 좌표
    # --------------------------------------------------------

    origin = (
        resolve_location(

            origin_query,

            region_hint=(
                origin_region_hint
            ),

        )
    )


    destination = (
        resolve_location(

            destination_query,

            region_hint=(
                destination_region_hint
            ),

        )
    )


    cache_file = (
        get_route_cache_file(

            origin,

            destination,

        )
    )


    # --------------------------------------------------------
    # Route Cache
    # --------------------------------------------------------

    if (
        cache_file.exists()
        and
        not force_refresh
    ):

        with open(

            cache_file,

            "r",

            encoding="utf-8",

        ) as file:

            cached_data = (
                json.load(
                    file
                )
            )


        cached_data[
            "cached"
        ] = True


        return cached_data


    # --------------------------------------------------------
    # A/B/C 생성
    # --------------------------------------------------------

    routes = (
        build_route_candidates(

            origin,

            destination,

        )
    )


    result = {

        "origin_query":
            origin_query,

        "destination_query":
            destination_query,

        "origin":
            {

                "poi_id":
                    origin.get(
                        "poi_id"
                    ),

                "name":
                    origin.get(
                        "name"
                    ),

                "address":
                    origin.get(
                        "address"
                    ),

                "lat":
                    origin.get(
                        "lat"
                    ),

                "lon":
                    origin.get(
                        "lon"
                    ),

            },

        "destination":
            {

                "poi_id":
                    destination.get(
                        "poi_id"
                    ),

                "name":
                    destination.get(
                        "name"
                    ),

                "address":
                    destination.get(
                        "address"
                    ),

                "lat":
                    destination.get(
                        "lat"
                    ),

                "lon":
                    destination.get(
                        "lon"
                    ),

            },

        "routes":
            routes,

        "candidate_count":
            len(
                routes
            ),

        "cached":
            False,

    }


    # --------------------------------------------------------
    # Cache 저장
    # --------------------------------------------------------

    with open(

        cache_file,

        "w",

        encoding="utf-8",

    ) as file:

        json.dump(

            result,

            file,

            ensure_ascii=False,

            indent=2,

        )


    return result


# ============================================================
# 11. 직접 실행 테스트
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Universal Route Engine"
    )

    print(
        "========================================"
    )


    result = (
        get_routes_by_place_names(

            origin_query=
                "성남시청",

            destination_query=
                "강남역",

            origin_region_hint=
                "성남",

            destination_region_hint=
                "서울",

            # Navigation Guidance가 없는 기존 cache를
            # 사용하지 않고 새 응답을 받기 위한 테스트 옵션.
            #
            # 600개 OD 전체를 다시 받는 것이 아니라
            # 이 테스트 OD 한 건의 A/B/C만 새로 호출한다.
            force_refresh=True,

        )
    )


    print()

    print(
        "========================================"
    )

    print(
        "Route Summary"
    )

    print(
        "========================================"
    )


    print(
        "출발:",
        result[
            "origin"
        ][
            "name"
        ],
    )


    print(
        "도착:",
        result[
            "destination"
        ][
            "name"
        ],
    )


    print(
        "Cache:",
        result[
            "cached"
        ],
    )


    print()


    for route in result[
        "routes"
    ]:

        print(
            "----------------------------------------"
        )

        print(
            "Route:",
            route[
                "candidate_id"
            ],
        )

        print(
            "Label:",
            route[
                "route_label"
            ],
        )

        print(
            "Distance:",
            route[
                "total_distance_m"
            ],
            "m",
        )

        print(
            "ETA:",
            route[
                "tmap_eta_min"
            ],
            "min",
        )

        print(
            "Geometry:",
            route[
                "geometry_point_count"
            ],
            "points",
        )

        print(
            "Navigation:",
            route[
                "navigation_guidance_count"
            ],
            "guidance points",
        )


        print()

        print(
            "[Navigation Guidance Sample]"
        )


        for guidance in (
            route[
                "navigation_guidance"
            ][:10]
        ):

            print(

                guidance.get(
                    "sequence"
                ),

                "| position=",

                guidance.get(
                    "route_position_m"
                ),

                "m | turnType=",

                guidance.get(
                    "turn_type"
                ),

                "| pointType=",

                guidance.get(
                    "point_type"
                ),

                "| description=",

                guidance.get(
                    "description"
                ),

                "| nextRoad=",

                guidance.get(
                    "next_road_name"
                ),

            )


        print()