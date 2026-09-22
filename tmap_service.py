import requests


# ============================================================
# TMAP APP KEY
# ============================================================
#
# 네가 발급받은 실제 App Key를 여기에 넣어.
#
# 주의:
# GitHub 등에 올릴 예정이면 나중에는 .env로 분리하는 것이 좋다.
#
# 절대로 채팅에 실제 KEY를 보내지 마.
# ============================================================

APP_KEY = "lBJ7tVIA5k12jKBMuki2N3Ymogs8MtUsa0hq6c5E"


# ============================================================
# TMAP API 주소
# ============================================================

POI_URL = "https://apis.openapi.sk.com/tmap/pois"

ROUTE_URL = "https://apis.openapi.sk.com/tmap/routes"


# ============================================================
# 공통 Headers
# ============================================================

def get_headers():

    return {
        "appKey": APP_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ============================================================
# 장소 검색
#
# 예:
# search_place("판교역")
#
# 반환:
#
# {
#     "name": "판교역",
#     "longitude": 127.xxx,
#     "latitude": 37.xxx,
#     "address": "경기 성남시 ..."
# }
# ============================================================

def search_place(keyword):

    if not keyword:
        raise ValueError(
            "검색어가 비어 있습니다."
        )


    params = {
        "version": "1",

        "format": "json",

        "searchKeyword": keyword,

        "count": 10,

        "page": 1,

        "searchType": "all",

        "reqCoordType": "WGS84GEO",

        "resCoordType": "WGS84GEO",
    }


    response = requests.get(
        POI_URL,
        headers=get_headers(),
        params=params,
        timeout=15,
    )


    if response.status_code != 200:

        raise RuntimeError(
            "TMAP 장소검색 API 오류\n"
            f"status_code: {response.status_code}\n"
            f"response: {response.text}"
        )


    data = response.json()


    pois = (
        data
        .get("searchPoiInfo", {})
        .get("pois", {})
        .get("poi", [])
    )


    if not pois:

        return None


    poi = pois[0]


    # ========================================================
    # 좌표
    # ========================================================

    longitude = (
        poi.get("frontLon")
        or poi.get("noorLon")
    )

    latitude = (
        poi.get("frontLat")
        or poi.get("noorLat")
    )


    if longitude is None or latitude is None:

        raise RuntimeError(
            "검색된 장소에서 좌표를 찾지 못했습니다."
        )


    # ========================================================
    # 주소
    # ========================================================

    upper_addr = poi.get(
        "upperAddrName",
        ""
    )

    middle_addr = poi.get(
        "middleAddrName",
        ""
    )

    lower_addr = poi.get(
        "lowerAddrName",
        ""
    )

    detail_addr = poi.get(
        "detailAddrName",
        ""
    )


    address_parts = [
        upper_addr,
        middle_addr,
        lower_addr,
        detail_addr,
    ]


    address = " ".join(
        part
        for part in address_parts
        if part
    )


    return {
        "name":
            poi.get(
                "name",
                keyword
            ),

        "longitude":
            float(longitude),

        "latitude":
            float(latitude),

        "address":
            address,
    }


# ============================================================
# 자동차 경로 탐색
#
# search_option:
#
# "0" = 추천 경로
# "1" = 최소시간 계열 후보
# "5" = 일반도로 우선 계열 후보
#
# 앞으로 A/B/C 후보 경로 생성 시 사용
#
# 예:
#
# get_route(
#     start_lon,
#     start_lat,
#     end_lon,
#     end_lat,
#     "판교역",
#     search_option="0"
# )
# ============================================================

def get_route(
    start_lon,
    start_lat,
    end_lon,
    end_lat,
    end_name,
    search_option="0",
):

    # ========================================================
    # 좌표 숫자 변환
    # ========================================================

    start_lon = float(start_lon)
    start_lat = float(start_lat)

    end_lon = float(end_lon)
    end_lat = float(end_lat)


    # ========================================================
    # API Query Parameter
    # ========================================================

    params = {
        "version": "1",

        "format": "json",
    }


    # ========================================================
    # TMAP 요청 Body
    # ========================================================

    payload = {
        "startX":
            str(start_lon),

        "startY":
            str(start_lat),

        "endX":
            str(end_lon),

        "endY":
            str(end_lat),

        "startName":
            "출발지",

        "endName":
            str(end_name),

        "reqCoordType":
            "WGS84GEO",

        "resCoordType":
            "WGS84GEO",

        # ----------------------------------------------------
        # 후보경로 A/B/C를 만들기 위해
        # 탐색 옵션을 외부에서 받을 수 있게 함
        # ----------------------------------------------------

        "searchOption":
            str(search_option),

        # ----------------------------------------------------
        # 교통정보를 반영한 경로 탐색
        # ----------------------------------------------------

        "trafficInfo":
            "Y",
    }


    # ========================================================
    # TMAP 호출
    # ========================================================

    response = requests.post(
        ROUTE_URL,
        headers=get_headers(),
        params=params,
        json=payload,
        timeout=20,
    )


    if response.status_code != 200:

        raise RuntimeError(
            "TMAP 경로탐색 API 오류\n"
            f"status_code: {response.status_code}\n"
            f"searchOption: {search_option}\n"
            f"response: {response.text}"
        )


    data = response.json()


    # ========================================================
    # Features
    # ========================================================

    features = data.get(
        "features",
        []
    )


    if not features:

        raise RuntimeError(
            "TMAP 경로 결과에 features가 없습니다."
        )


    # ========================================================
    # 결과 변수
    # ========================================================

    total_distance = 0

    total_time = 0

    total_fare = 0

    taxi_fare = 0


    route_path = []

    road_segments = []


    # ========================================================
    # TMAP Feature 분석
    # ========================================================

    for feature in features:

        geometry = feature.get(
            "geometry",
            {}
        )

        properties = feature.get(
            "properties",
            {}
        )


        geometry_type = geometry.get(
            "type"
        )


        # ====================================================
        # 전체 경로 정보
        #
        # 첫 Point 등에 들어있는 경우가 많기 때문에
        # 값이 존재하면 저장
        # ====================================================

        if properties.get(
            "totalDistance"
        ) is not None:

            total_distance = float(
                properties.get(
                    "totalDistance",
                    0
                )
            )


        if properties.get(
            "totalTime"
        ) is not None:

            total_time = float(
                properties.get(
                    "totalTime",
                    0
                )
            )


        if properties.get(
            "totalFare"
        ) is not None:

            total_fare = float(
                properties.get(
                    "totalFare",
                    0
                )
            )


        if properties.get(
            "taxiFare"
        ) is not None:

            taxi_fare = float(
                properties.get(
                    "taxiFare",
                    0
                )
            )


        # ====================================================
        # LineString
        #
        # 실제 차량 경로
        # ====================================================

        if geometry_type == "LineString":

            coordinates = geometry.get(
                "coordinates",
                []
            )


            # ------------------------------------------------
            # 전체 Polyline 좌표 저장
            # ------------------------------------------------

            for coordinate in coordinates:

                if len(coordinate) < 2:

                    continue


                longitude = float(
                    coordinate[0]
                )

                latitude = float(
                    coordinate[1]
                )


                route_path.append({

                    "longitude":
                        longitude,

                    "latitude":
                        latitude,
                })


            # ------------------------------------------------
            # 도로 Segment
            # ------------------------------------------------

            road_name = (
                properties.get("name")
                or properties.get("roadName")
                or properties.get("description")
                or ""
            )


            distance_m = (
                properties.get(
                    "distance",
                    0
                )
                or 0
            )


            duration_sec = (
                properties.get(
                    "time",
                    0
                )
                or 0
            )


            # ------------------------------------------------
            # TMAP 응답 버전에 따라
            # traffic 관련 key가 다를 수 있으므로
            # 존재하는 값을 순서대로 사용
            # ------------------------------------------------

            traffic = (
                properties.get(
                    "traffic"
                )
                or properties.get(
                    "trafficIndex"
                )
                or properties.get(
                    "trafficType"
                )
            )


            road_segments.append({

                "road_name":
                    str(road_name),

                "distance_m":
                    float(
                        distance_m
                    ),

                "duration_sec":
                    float(
                        duration_sec
                    ),

                "traffic":
                    traffic,
            })


    # ========================================================
    # 전체 distance/time이 없는 경우
    # segment 합으로 보정
    # ========================================================

    if total_distance <= 0:

        total_distance = sum(

            segment[
                "distance_m"
            ]

            for segment
            in road_segments
        )


    if total_time <= 0:

        total_time = sum(

            segment[
                "duration_sec"
            ]

            for segment
            in road_segments
        )


    # ========================================================
    # 중복 연속 좌표 제거
    #
    # TMAP Feature 경계에서
    # 마지막/첫 좌표가 중복될 수 있음
    # ========================================================

    cleaned_route_path = []

    previous_coordinate = None


    for point in route_path:

        current_coordinate = (

            point[
                "longitude"
            ],

            point[
                "latitude"
            ]
        )


        if (
            current_coordinate
            ==
            previous_coordinate
        ):

            continue


        cleaned_route_path.append(
            point
        )


        previous_coordinate = (
            current_coordinate
        )


    route_path = (
        cleaned_route_path
    )


    # ========================================================
    # 최종 결과
    #
    # 기존 FLOW 코드와 호환되는 필드 유지
    # ========================================================

    result = {

        # ----------------------------------------------------
        # 총 거리
        # ----------------------------------------------------

        "distance_km":
            round(
                total_distance
                /
                1000,
                3
            ),


        # ----------------------------------------------------
        # 총 시간
        # ----------------------------------------------------

        "time_min":
            round(
                total_time
                /
                60,
                1
            ),


        # ----------------------------------------------------
        # 요금
        # ----------------------------------------------------

        "total_fare":
            int(
                total_fare
            ),

        "taxi_fare":
            int(
                taxi_fare
            ),


        # ----------------------------------------------------
        # 전체 경로 좌표
        # ----------------------------------------------------

        "route_path":
            route_path,


        # ----------------------------------------------------
        # 도로별 Segment
        # ----------------------------------------------------

        "road_segments":
            road_segments,


        # ----------------------------------------------------
        # 출발 / 도착 좌표
        # ----------------------------------------------------

        "start_latitude":
            start_lat,

        "start_longitude":
            start_lon,

        "end_latitude":
            end_lat,

        "end_longitude":
            end_lon,


        # ----------------------------------------------------
        # 어떤 TMAP 탐색 옵션인지 기록
        # ----------------------------------------------------

        "search_option":
            str(
                search_option
            ),
    }


    return result