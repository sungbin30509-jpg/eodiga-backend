import requests


# ============================================================
# 1. TMAP App Key
# ============================================================

APP_KEY = "lBJ7tVIA5k12jKBMuki2N3Ymogs8MtUsa0hq6c5E"


# ============================================================
# 2. 장소 검색 함수
# ============================================================

def search_place(keyword):

    url = "https://apis.openapi.sk.com/tmap/pois"

    headers = {
        "Accept": "application/json",
        "appKey": APP_KEY
    }

    params = {
        "version": "1",
        "searchKeyword": keyword,
        "searchType": "all",
        "page": "1",
        "count": "5",
        "resCoordType": "WGS84GEO"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    print()
    print("장소 검색 HTTP 상태 코드:", response.status_code)

    # 검색 실패
    if response.status_code != 200:
        print("장소 검색 실패")
        print(response.text)
        return None

    result = response.json()

    # 검색 결과 확인
    try:
        pois = result["searchPoiInfo"]["pois"]["poi"]

    except KeyError:
        print("검색 결과가 없습니다.")
        return None


    # ========================================================
    # 검색 결과 출력
    # ========================================================

    print()
    print("======================================")
    print(f"'{keyword}' 검색 결과")
    print("======================================")

    for i, poi in enumerate(pois):

        name = poi.get("name", "")

        upper = poi.get("upperAddrName", "")
        middle = poi.get("middleAddrName", "")
        lower = poi.get("lowerAddrName", "")

        address = f"{upper} {middle} {lower}"

        print()
        print(f"{i + 1}. {name}")
        print(f"   주소: {address}")


    # ========================================================
    # 사용자가 장소 선택
    # ========================================================

    while True:

        try:

            choice = int(
                input("\n목적지 번호를 선택하세요: ")
            )

            if 1 <= choice <= len(pois):
                break

            print("목록에 있는 번호를 입력해주세요.")

        except ValueError:

            print("숫자를 입력해주세요.")


    selected = pois[choice - 1]


    # ========================================================
    # 좌표 가져오기
    # ========================================================

    # 가능하면 실제 진입점 좌표 사용
    longitude = selected.get("frontLon")
    latitude = selected.get("frontLat")

    # 진입점 좌표가 없으면 중심점 좌표 사용
    if not longitude or not latitude:

        longitude = selected.get("noorLon")
        latitude = selected.get("noorLat")


    place = {
        "name": selected.get("name"),
        "longitude": float(longitude),
        "latitude": float(latitude)
    }


    print()
    print("======================================")
    print("선택한 목적지")
    print("======================================")

    print("장소:", place["name"])
    print("경도:", place["longitude"])
    print("위도:", place["latitude"])

    return place


# ============================================================
# 3. TMAP 자동차 경로 탐색 함수
# ============================================================

def get_route(
    start_lon,
    start_lat,
    end_lon,
    end_lat,
    end_name
):

    url = "https://apis.openapi.sk.com/tmap/routes"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appKey": APP_KEY
    }

    params = {
        "version": "1"
    }

    data = {

        # 출발지
        "startX": start_lon,
        "startY": start_lat,
        "startName": "현재 위치",

        # 목적지
        "endX": end_lon,
        "endY": end_lat,
        "endName": end_name,

        # 좌표계
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",

        # 교통 최적 + 추천
        "searchOption": "0",

        # 교통정보 포함
        "trafficInfo": "Y"
    }


    response = requests.post(
        url,
        headers=headers,
        params=params,
        json=data
    )


    print()
    print("경로 탐색 HTTP 상태 코드:", response.status_code)


    # ========================================================
    # 성공
    # ========================================================

    if response.status_code == 200:

        result = response.json()

        properties = result["features"][0]["properties"]

        total_distance = properties["totalDistance"]
        total_time = properties["totalTime"]

        total_fare = properties.get("totalFare", 0)
        taxi_fare = properties.get("taxiFare", 0)


        distance_km = total_distance / 1000
        time_min = total_time / 60


        print()
        print("======================================")
        print("TMAP 경로 탐색 성공")
        print("======================================")

        print(f"목적지         : {end_name}")
        print(f"총 거리        : {distance_km:.2f} km")
        print(f"예상 소요시간  : {time_min:.1f} 분")
        print(f"통행료         : {total_fare:,} 원")
        print(f"택시 예상요금  : {taxi_fare:,} 원")


    # ========================================================
    # 실패
    # ========================================================

    else:

        print()
        print("======================================")
        print("TMAP 경로 탐색 실패")
        print("======================================")

        print(response.text)


# ============================================================
# 4. 프로그램 시작
# ============================================================

print()
print("======================================")
print("       FLOWMATE 목적지 검색")
print("======================================")


# 사용자에게 목적지 입력 받기

destination_keyword = input(
    "목적지를 입력하세요: "
)


# ============================================================
# 5. 목적지 검색
# ============================================================

destination = search_place(
    destination_keyword
)


# ============================================================
# 6. 목적지가 정상적으로 검색됐을 때
# ============================================================

if destination is not None:


    # --------------------------------------------------------
    # 현재는 출발지 좌표를 임시로 직접 사용
    #
    # 나중에 휴대폰 GPS로 교체할 예정
    # --------------------------------------------------------

    START_LONGITUDE = 127.1268
    START_LATITUDE = 37.4200


    # --------------------------------------------------------
    # 경로 탐색
    # --------------------------------------------------------

    get_route(

        START_LONGITUDE,
        START_LATITUDE,

        destination["longitude"],
        destination["latitude"],

        destination["name"]
    )