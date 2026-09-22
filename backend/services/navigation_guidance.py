import math


# ============================================================
# FLOW:MATE Navigation Guidance Utility
#
# TMAP Point Feature
# →
# Route geometry 상 위치 계산
# →
# turnType / pointType / description 보존
# ============================================================


def navigation_distance_m(
    lon1,
    lat1,
    lon2,
    lat2,
):
    """
    WGS84 두 좌표 사이 거리(m)
    """

    radius = 6371000.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2.0) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(delta_lon / 2.0) ** 2
    )

    c = (
        2.0
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(
                max(
                    0.0,
                    1.0 - a,
                )
            ),
        )
    )

    return radius * c


# ============================================================
# Route Geometry 누적거리
# ============================================================

def calculate_route_cumulative_distances(
    geometry,
):

    if not geometry:
        return []

    cumulative = [
        0.0
    ]

    total = 0.0

    for index in range(
        1,
        len(geometry),
    ):

        previous = geometry[
            index - 1
        ]

        current = geometry[
            index
        ]

        distance = navigation_distance_m(

            float(previous[0]),
            float(previous[1]),

            float(current[0]),
            float(current[1]),

        )

        total += distance

        cumulative.append(
            total
        )

    return cumulative


# ============================================================
# 좌표 → Route상 위치
# ============================================================

def find_nearest_route_position(
    lon,
    lat,
    geometry,
    cumulative_distances=None,
):

    if not geometry:

        return {
            "route_geometry_index": None,
            "route_position_m": None,
            "snap_distance_m": None,
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
            len(coordinate) < 2
        ):
            continue

        route_lon = float(
            coordinate[0]
        )

        route_lat = float(
            coordinate[1]
        )

        distance = navigation_distance_m(

            float(lon),
            float(lat),

            route_lon,
            route_lat,

        )

        if (
            best_distance is None
            or
            distance < best_distance
        ):

            best_distance = distance
            best_index = index

    if best_index is None:

        return {
            "route_geometry_index": None,
            "route_position_m": None,
            "snap_distance_m": None,
        }

    return {

        "route_geometry_index":
            best_index,

        "route_position_m":
            round(
                cumulative_distances[
                    best_index
                ],
                2,
            ),

        "snap_distance_m":
            round(
                best_distance,
                2,
            ),

    }


# ============================================================
# TMAP Point Feature → Navigation Guidance
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

        feature_geometry = feature.get(
            "geometry",
            {}
        )

        # 회전/안내 정보는 Point Feature
        if (
            feature_geometry.get(
                "type"
            )
            !=
            "Point"
        ):
            continue

        coordinates = feature_geometry.get(
            "coordinates"
        )

        if (
            not isinstance(
                coordinates,
                (list, tuple),
            )
            or
            len(coordinates) < 2
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

        properties = feature.get(
            "properties",
            {}
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
                len(guidance),

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

            "lon":
                lon,

            "lat":
                lat,

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

    # Route 진행순서대로 정렬
    guidance.sort(

        key=lambda item: (

            item["route_position_m"]

            if
            item["route_position_m"]
            is not None

            else
            float("inf")

        )

    )

    # sequence 재부여
    for index, item in enumerate(
        guidance
    ):

        item[
            "sequence"
        ] = index

    return guidance