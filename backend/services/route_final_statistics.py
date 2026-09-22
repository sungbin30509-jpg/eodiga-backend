from pathlib import Path
import json
import hashlib
import math

import requests

from backend.services.location_service import (
    get_tmap_app_key,
    resolve_location,
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
# 7. TMAP Summary 추출
# ============================================================

def extract_route_summary(
    features,
):

    total_distance_m = None

    total_time_sec = None


    # TMAP은 일반적으로 첫 번째 Point Feature에
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
# 8. Navigation Utility
#
# GPS / TMAP Point Feature를
# Route Geometry 위의 위치(m)와 연결하기 위한 함수
# ============================================================

def navigation_distance_m(
    lon1,
    lat1,
    lon2,
    lat2,
):
    """
    WGS84 좌표 두 점 사이의 직선거리(m)를 계산한다.
    Haversine 공식 사용.
    """

    earth_radius_m = (
        6371000.0
    )


    lat1_rad = math.radians(
        lat1
    )

    lat2_rad = math.radians(
        lat2
    )


    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )


    a = (

        math.sin(
            delta_lat / 2.0
        ) ** 2

        +

        math.cos(
            lat1_rad
        )

        *

        math.cos(
            lat2_rad
        )

        *

        math.sin(
            delta_lon / 2.0
        ) ** 2

    )


    c = (

        2.0

        *

        math.atan2(

            math.sqrt(
                a
            ),

            math.sqrt(
                max(
                    0.0,
                    1.0 - a,
                )
            ),

        )

    )


    return (
        earth_radius_m
        *
        c
    )


# ============================================================
# 9. Route Geometry 누적거리
#
# [
#   0.0,
#   12.5,
#   27.9,
#   ...
# ]
#
# 형태로 각 geometry point까지의
# Route 시작점 기준 누적거리 생성
# ============================================================

def calculate_route_cumulative_distances(
    geometry,
):

    if not geometry:

        return []


    cumulative_distances = [
        0.0
    ]


    total_distance = (
        0.0
    )


    for index in range(
        1,
        len(
            geometry
        ),
    ):

        previous = (
            geometry[
                index - 1
            ]
        )


        current = (
            geometry[
                index
            ]
        )


        distance = (
            navigation_distance_m(

                float(
                    previous[0]
                ),

                float(
                    previous[1]
                ),

                float(
                    current[0]
                ),

                float(
                    current[1]
                ),

            )
        )


        total_distance += (
            distance
        )


        cumulative_distances.append(
            total_distance
        )


    return (
        cumulative_distances
    )


# ============================================================
# 10. 특정 좌표의 Route상 위치 찾기
#
# MVP 단계에서는
# 가장 가까운 Geometry Point 기준으로 snap
#
# 반환:
#
# route_geometry_index
# route_position_m
# snap_distance_m
# ============================================================

def find_nearest_route_position(
    lon,
    lat,
    geometry,
    cumulative_distances=None,
):

    if not geometry:

        return {

            "route_geometry_index":
                None,

            "route_position_m":
                None,

            "snap_distance_m":
                None,

        }


    if cumulative_distances is None:

        cumulative_distances = (
            calculate_route_cumulative_distances(
                geometry
            )
        )


    best_index = None

    best_distance = None


    for index, coordinate in enumerate(
        geometry
    ):

        if (
            not isinstance(
                coordinate,
                (list, tuple),
            )
            or
            len(
                coordinate
            ) < 2
        ):

            continue


        route_lon = float(
            coordinate[0]
        )


        route_lat = float(
            coordinate[1]
        )


        distance = (
            navigation_distance_m(

                float(
                    lon
                ),

                float(
                    lat
                ),

                route_lon,

                route_lat,

            )
        )


        if (
            best_distance is None
            or
            distance < best_distance
        ):

            best_distance = (
                distance
            )

            best_index = (
                index
            )


    if best_index is None:

        return {

            "route_geometry_index":
                None,

            "route_position_m":
                None,

            "snap_distance_m":
                None,

        }


    route_position_m = (
        cumulative_distances[
            best_index
        ]
    )


    return {

        "route_geometry_index":
            best_index,

        "route_position_m":
            round(
                route_position_m,
                2,
            ),

        "snap_distance_m":
            round(
                best_distance,
                2,
            ),

    }


# ============================================================
# 11. TMAP Navigation Guidance 추출
#
# TMAP Point Feature에서
#
# - turnType
# - pointType
# - description
# - nextRoadName
# - name
#
# 등을 보존한다.
#
#
# 중요
# ------------------------------------------------------------
# turnType의 의미를 여기서 임의 해석하지 않는다.
# TMAP 원본 값을 그대로 보존한다.
#
# 이후 Navigation Service / Flutter에서
# 실제 안내문 생성에 활용한다.
# ============================================================

def extract_navigation_guidance(
    features,
    geometry,
):

    guidance = []


    cumulative_distances = (
        calculate_route_cumulative_distances(
            geometry
        )
    )


    for feature_index, feature in enumerate(
        features
    ):

        if not isinstance(
            feature,
            dict,
        ):

            continue


        feature_geometry = (
            feature.get(
                "geometry",
                {}
            )
        )


        if (
            feature_geometry.get(
                "type"
            )
            !=
            "Point"
        ):

            continue


        coordinates = (
            feature_geometry.get(
                "coordinates"
            )
        )


        if (
            not isinstance(
                coordinates,
                (list, tuple),
            )
            or
            len(
                coordinates
            ) < 2
        ):

            continue


        try:

            lon = float(
                coordinates[0]
            )

            lat = float(
                coordinates[1]
            )

        except (
            TypeError,
            ValueError,
        ):

            continue


        properties = (
            feature.get(
                "properties",
                {}
            )
        )


        if not isinstance(
            properties,
            dict,
        ):

            properties = {}


        route_position = (
            find_nearest_route_position(

                lon,

                lat,

                geometry,

                cumulative_distances,

            )
        )


        guidance.append({

            "sequence":
                len(
                    guidance
                ),

            # -----------------------------------------------
            # TMAP 원본 Feature 위치
            # -----------------------------------------------

            "feature_index":
                feature_index,

            "tmap_index":
                properties.get(
                    "index"
                ),

            "point_index":
                properties.get(
                    "pointIndex"
                ),

            # -----------------------------------------------
            # TMAP Navigation 원본값
            # -----------------------------------------------

            "point_type":
                properties.get(
                    "pointType"
                ),

            "turn_type":
                properties.get(
                    "turnType"
                ),

            "name":
                properties.get(
                    "name"
                ),

            "description":
                properties.get(
                    "description"
                ),

            "next_road_name":
                properties.get(
                    "nextRoadName"
                ),

            "facility_type":
                properties.get(
                    "facilityType"
                ),

            # -----------------------------------------------
            # 실제 좌표
            # -----------------------------------------------

            "lon":
                lon,

            "lat":
                lat,

            # -----------------------------------------------
            # FLOW:MATE Route상 위치
            # -----------------------------------------------

            "route_geometry_index":
                route_position[
                    "route_geometry_index"
                ],

            "route_position_m":
                route_position[
                    "route_position_m"
                ],

            "snap_distance_m":
                route_position[
                    "snap_distance_m"
                ],

        })


    # ========================================================
    # Route 진행순서 기준 정렬
    # ========================================================

    guidance.sort(

        key=lambda item: (

            item[
                "route_position_m"
            ]

            if
            item[
                "route_position_m"
            ]
            is not None

            else
            float(
                "inf"
            )

        )

    )


    # ========================================================
    # 정렬 후 sequence 다시 부여
    # ========================================================

    for index, item in enumerate(
        guidance
    ):

        item[
            "sequence"
        ] = index


    return guidance


# ============================================================
# 12. TMAP 경로 1개 호출
# ============================================================

def request_tmap_route(
    origin,
    destination,
    candidate_id,
):

    if (
        candidate_id
        not in
        ROUTE_OPTIONS
    ):

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

        response = (
            requests.post(

                TMAP_ROUTE_URL,

                headers=headers,

                json=payload,

                timeout=30,

            )
        )


    except requests.RequestException as error:

        raise RuntimeError(

            "TMAP 경로 API 연결 실패\n"
            f"{error}"

        ) from error


    if (
        response.status_code
        !=
        200
    ):

        raise RuntimeError(

            "TMAP 경로 검색 실패\n"
            "\n"
            f"Candidate: {candidate_id}\n"
            f"Search Option: {option['search_option']}\n"
            f"HTTP Status: {response.status_code}\n"
            "\n"
            "Response:\n"
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
    # Geometry
    # ========================================================

    geometry = (
        extract_route_geometry(
            features
        )
    )


    # ========================================================
    # Summary
    # ========================================================

    (
        total_distance_m,
        total_time_sec,
    ) = (
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
    # Point Feature를 Route Geometry상 위치와 연결
    # ========================================================

    navigation_guidance = (
        extract_navigation_guidance(

            features,

            geometry,

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

                if
                total_time_sec
                is not None

                else
                None

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
        # Navigation
        # ====================================================

        "navigation_guidance":
            navigation_guidance,

        "navigation_guidance_count":
            len(
                navigation_guidance
            ),

        "navigation_schema_version":
            "navigation_guidance_v1",

        "source":
            "tmap",

    }


# ============================================================
# 13. A/B/C 세 경로 생성
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
            f"{route['navigation_guidance_count']} guidance"

        )


    return routes


# ============================================================
# 14. 핵심 함수
#
# 장소명 → A/B/C Route
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


    # ========================================================
    # Route Cache
    # ========================================================

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


        return (
            cached_data
        )


    # ========================================================
    # A/B/C 생성
    # ========================================================

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


    # ========================================================
    # Cache 저장
    # ========================================================

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
# 15. 직접 실행 테스트
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

            # 기존 Cache에는 navigation_guidance가 없을 수 있으므로
            # Navigation 최초 테스트 시 True 사용
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
            ]
        )

        print(
            "Label:",
            route[
                "route_label"
            ]
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
            ][
                :10
            ]
        ):

            print(

                guidance[
                    "sequence"
                ],

                "| position=",

                guidance[
                    "route_position_m"
                ],

                "m | turnType=",

                guidance[
                    "turn_type"
                ],

                "| pointType=",

                guidance[
                    "point_type"
                ],

                "|",

                guidance[
                    "description"
                ],

                "| nextRoad=",

                guidance[
                    "next_road_name"
                ],

            )


        print()