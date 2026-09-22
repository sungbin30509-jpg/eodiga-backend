import json
import os


# ============================================================
# FLOW Mock Map Feed
# ============================================================

BASE_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
    )
)


MAP_FEED_FILE = os.path.join(
    BASE_DIR,
    "docs",
    "api",
    "mock_flow_map_feed.json",
)


# ============================================================
# JSON 읽기
# ============================================================

def load_map_feed():

    if not os.path.exists(
        MAP_FEED_FILE
    ):

        raise FileNotFoundError(
            f"FLOW Map Feed 파일을 찾을 수 없습니다.\n"
            f"{MAP_FEED_FILE}"
        )


    with open(
        MAP_FEED_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(
            file
        )


    return data


# ============================================================
# 전체 경로 목록
#
# GET /api/routes
# ============================================================

def get_routes():

    data = load_map_feed()


    routes = data.get(
        "routes",
        [],
    )


    result = []


    for route in routes:

        result.append({

            "route_id":
                route.get(
                    "route_id"
                ),

            "candidate_id":
                route.get(
                    "candidate_id"
                ),

            "source":
                route.get(
                    "source"
                ),

            "search_option":
                route.get(
                    "search_option"
                ),

            "search_option_name":
                route.get(
                    "search_option_name"
                ),

            "origin":
                route.get(
                    "origin",
                    {}
                ),

            "destination":
                route.get(
                    "destination",
                    {}
                ),

            "summary":
                route.get(
                    "summary",
                    {}
                ),

            "link_count":
                route.get(
                    "link_count",
                    len(
                        route.get(
                            "links",
                            []
                        )
                    )
                ),

            "mapping_quality":
                route.get(
                    "mapping_quality",
                    {}
                ),
        })


    return {
        "routes":
            result
    }


# ============================================================
# route_id로 경로 찾기
# ============================================================

def find_route(
    route_id,
):

    data = load_map_feed()


    routes = data.get(
        "routes",
        [],
    )


    for route in routes:

        if (
            route.get(
                "route_id"
            )
            ==
            route_id
        ):

            return route


    return None


# ============================================================
# 특정 LINK의 특정 시점 Traffic 찾기
# ============================================================

def get_link_traffic(
    forecast,
    offset_min,
    scenario,
):

    for forecast_item in forecast:

        if (
            forecast_item.get(
                "offset_min"
            )
            !=
            offset_min
        ):

            continue


        traffic = forecast_item.get(
            scenario
        )


        if traffic is None:

            return None


        return {

            "offset_min":
                offset_min,

            "scenario":
                scenario,

            "speed_kmh":
                traffic.get(
                    "speed_kmh"
                ),

            "congestion_level":
                traffic.get(
                    "congestion_level"
                ),

            "congestion_label":
                traffic.get(
                    "congestion_label"
                ),
        }


    return None


# ============================================================
# 특정 경로 Snapshot
#
# 예:
#
# route_A
# +30분
# before
#
# ↓
#
# 해당 시점의 LINK 상태만 반환
# ============================================================

def get_route_snapshot(
    route_id,
    offset_min,
    scenario,
):

    # ========================================================
    # Parameter 검증
    # ========================================================

    if scenario not in (
        "before",
        "after",
    ):

        raise ValueError(
            "scenario은 "
            "'before' 또는 'after'만 가능합니다."
        )


    if (
        offset_min < 0
        or
        offset_min > 60
        or
        offset_min % 5 != 0
    ):

        raise ValueError(
            "offset_min은 "
            "0~60 사이의 5분 단위 값이어야 합니다."
        )


    # ========================================================
    # 경로 찾기
    # ========================================================

    route = find_route(
        route_id
    )


    if route is None:

        raise KeyError(
            f"존재하지 않는 route_id입니다: {route_id}"
        )


    output_links = []


    # ========================================================
    # LINK별 해당 시간 Traffic 추출
    # ========================================================

    for link in route.get(
        "links",
        [],
    ):

        forecast = link.get(
            "forecast",
            [],
        )


        traffic = get_link_traffic(

            forecast,

            offset_min,

            scenario,
        )


        if traffic is None:

            continue


        output_links.append({

            "sequence":
                link.get(
                    "sequence"
                ),

            "link_id":
                link.get(
                    "link_id"
                ),

            "road_name":
                link.get(
                    "road_name",
                    ""
                ),

            "f_node":
                link.get(
                    "f_node"
                ),

            "t_node":
                link.get(
                    "t_node"
                ),

            "length_m":
                link.get(
                    "length_m"
                ),

            "max_speed_kmh":
                link.get(
                    "max_speed_kmh"
                ),

            "geometry":
                link.get(
                    "geometry"
                ),

            "traffic":
                traffic,
        })


    # ========================================================
    # Snapshot
    # ========================================================

    return {

        "route_id":
            route.get(
                "route_id"
            ),

        "candidate_id":
            route.get(
                "candidate_id"
            ),

        "origin":
            route.get(
                "origin",
                {}
            ),

        "destination":
            route.get(
                "destination",
                {}
            ),

        "summary":
            route.get(
                "summary",
                {}
            ),

        "mapping_quality":
            route.get(
                "mapping_quality",
                {}
            ),

        "offset_min":
            offset_min,

        "scenario":
            scenario,

        "link_count":
            len(
                output_links
            ),

        "links":
            output_links,
    }