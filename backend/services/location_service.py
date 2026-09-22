from pathlib import Path
import json
import os

import requests


# ============================================================
# FLOW:MATE
# TMAP Location Resolver
#
# 역할
# ------------------------------------------------------------
# 장소명 입력
#       ↓
# TMAP POI 검색
#       ↓
# 실제 위도 / 경도 반환
#       ↓
# location_cache.json 저장
#
# 예:
# 판교역
# 강남역
# 성남시청
# 판교테크노밸리 기업명
# 아파트명
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

CURRENT_FILE = Path(__file__).resolve()

# 현재:
# FLOWMATE/backend/services/location_service.py
#
# parents[0] = services
# parents[1] = backend
# parents[2] = FLOWMATE

ROOT = CURRENT_FILE.parents[2]


# ============================================================
# 2. Cache 경로
# ============================================================

CACHE_DIR = (
    ROOT
    / "cache"
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


CACHE_FILE = (
    CACHE_DIR
    / "location_cache.json"
)


# ============================================================
# 3. .env 경로
# ============================================================

ENV_FILE = (
    ROOT
    / ".env"
)


# ============================================================
# 4. TMAP POI API
# ============================================================

TMAP_POI_URL = (
    "https://apis.openapi.sk.com/tmap/pois"
)


# ============================================================
# 5. .env 파일 직접 읽기
#
# python-dotenv가 없어도 사용할 수 있도록 직접 구현
#
# .env 예:
#
# TMAP_APP_KEY=xxxxxxxxxxxxxxxx
# ============================================================

def load_env_file():

    if not ENV_FILE.exists():

        return


    with open(
        ENV_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        for raw_line in file:

            line = (
                raw_line
                .strip()
            )


            # 빈 줄
            if not line:
                continue


            # 주석
            if line.startswith("#"):
                continue


            # KEY=VALUE 형식이 아니면 무시
            if "=" not in line:
                continue


            key, value = (
                line.split(
                    "=",
                    1,
                )
            )


            key = (
                key
                .strip()
            )


            value = (
                value
                .strip()
                .strip('"')
                .strip("'")
            )


            # 이미 OS 환경변수로 설정되어 있다면
            # 그것을 우선 사용
            if key not in os.environ:

                os.environ[
                    key
                ] = value


# ============================================================
# 6. TMAP APP KEY 가져오기
# ============================================================

def get_tmap_app_key():

    load_env_file()


    app_key = (
        os.getenv(
            "TMAP_APP_KEY"
        )
    )


    if not app_key:

        raise ValueError(

            "TMAP_APP_KEY를 찾을 수 없습니다.\n"
            "\n"
            "아래 파일을 확인하세요:\n"
            f"{ENV_FILE}\n"
            "\n"
            ".env 파일 안에 다음 형식으로 저장해야 합니다.\n"
            "\n"
            "TMAP_APP_KEY=본인의_TMAP_APP_KEY\n"

        )


    return (
        app_key
        .strip()
    )


# ============================================================
# 7. Location Cache 읽기
# ============================================================

def load_location_cache():

    if not CACHE_FILE.exists():

        return {}


    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = (
                json.load(
                    file
                )
            )


        if not isinstance(
            data,
            dict,
        ):

            return {}


        return data


    except (
        json.JSONDecodeError,
        OSError,
    ):

        return {}


# ============================================================
# 8. Location Cache 저장
# ============================================================

def save_location_cache(
    cache,
):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(

            cache,

            file,

            ensure_ascii=False,

            indent=2,

        )


# ============================================================
# 9. Cache Key 생성
#
# 같은 장소명이라도
#
# 판교역 + 성남시
# 판교역 + 다른 지역
#
# 등을 구분할 수 있도록 region_hint 포함
# ============================================================

def make_cache_key(
    query,
    region_hint=None,
):

    query_normalized = (

        str(query)
        .strip()
        .lower()

    )


    region_normalized = (

        str(
            region_hint
            or
            ""
        )
        .strip()
        .lower()

    )


    return (
        f"{query_normalized}||{region_normalized}"
    )


# ============================================================
# 10. TMAP POI 주소 조합
# ============================================================

def build_address(
    poi,
):

    address_parts = []


    fields = [

        "upperAddrName",

        "middleAddrName",

        "lowerAddrName",

        "detailAddrName",

    ]


    for field in fields:

        value = (
            poi.get(
                field
            )
        )


        if value:

            value = (
                str(value)
                .strip()
            )


            if value:

                address_parts.append(
                    value
                )


    return (
        " ".join(
            address_parts
        )
        .strip()
    )


# ============================================================
# 11. POI 좌표 추출
#
# TMAP POI:
# frontLat / frontLon 우선
#
# 없으면:
# noorLat / noorLon
# ============================================================

def extract_coordinates(
    poi,
):

    lat = (
        poi.get(
            "frontLat"
        )
    )


    lon = (
        poi.get(
            "frontLon"
        )
    )


    # --------------------------------------------------------
    # front 좌표가 없으면 noor 좌표 사용
    # --------------------------------------------------------

    if not lat:

        lat = (
            poi.get(
                "noorLat"
            )
        )


    if not lon:

        lon = (
            poi.get(
                "noorLon"
            )
        )


    if (
        lat is None
        or
        lon is None
    ):

        raise ValueError(
            "TMAP POI 결과에 좌표가 없습니다."
        )


    try:

        lat = float(
            lat
        )

        lon = float(
            lon
        )


    except (
        TypeError,
        ValueError,
    ):

        raise ValueError(
            "TMAP POI 좌표를 숫자로 변환할 수 없습니다."
        )


    return (
        lat,
        lon,
    )


# ============================================================
# 12. TMAP POI 후보 검색
#
# 장소명을 검색해서
# 여러 후보를 반환
# ============================================================

def search_location_candidates(
    query,
    count=20,
):

    query = (
        str(query)
        .strip()
    )


    if not query:

        raise ValueError(
            "검색할 장소명이 비어 있습니다."
        )


    app_key = (
        get_tmap_app_key()
    )


    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    headers = {

        "appKey":
        app_key,

        "Accept":
        "application/json",

    }


    # --------------------------------------------------------
    # TMAP Parameters
    # --------------------------------------------------------

    params = {

        "version":
        "1",

        "searchKeyword":
        query,

        "count":
        int(count),

        "page":
        1,

        "reqCoordType":
        "WGS84GEO",

        "resCoordType":
        "WGS84GEO",

    }


    # --------------------------------------------------------
    # API 호출
    # --------------------------------------------------------

    try:

        response = requests.get(

            TMAP_POI_URL,

            headers=headers,

            params=params,

            timeout=20,

        )


    except requests.RequestException as error:

        raise RuntimeError(

            "TMAP POI API 연결 중 오류가 발생했습니다.\n"
            f"{error}"

        ) from error


    # --------------------------------------------------------
    # HTTP 오류
    # --------------------------------------------------------

    if response.status_code != 200:

        raise RuntimeError(

            "TMAP POI 검색 실패\n"
            "\n"
            f"HTTP Status: {response.status_code}\n"
            "\n"
            f"Response:\n{response.text[:1000]}"

        )


    # --------------------------------------------------------
    # JSON 변환
    # --------------------------------------------------------

    try:

        data = (
            response.json()
        )


    except ValueError as error:

        raise RuntimeError(

            "TMAP 응답을 JSON으로 읽을 수 없습니다.\n"
            f"{response.text[:1000]}"

        ) from error


    # --------------------------------------------------------
    # POI 목록 추출
    # --------------------------------------------------------

    try:

        pois = (

            data[
                "searchPoiInfo"
            ][
                "pois"
            ][
                "poi"
            ]

        )


    except (
        KeyError,
        TypeError,
    ):

        pois = []


    if not pois:

        return []


    # POI 하나만 object로 오는 경우 방어
    if isinstance(
        pois,
        dict,
    ):

        pois = [
            pois
        ]


    results = []


    # --------------------------------------------------------
    # 후보 정리
    # --------------------------------------------------------

    for poi in pois:

        try:

            lat, lon = (
                extract_coordinates(
                    poi
                )
            )


        except ValueError:

            continue


        name = (
            poi.get(
                "name"
            )
            or
            ""
        )


        address = (
            build_address(
                poi
            )
        )


        result = {

            "poi_id":
            str(
                poi.get(
                    "id",
                    "",
                )
            ),

            "name":
            str(
                name
            ),

            "address":
            address,

            "lat":
            lat,

            "lon":
            lon,

            "upper_addr":
            str(
                poi.get(
                    "upperAddrName",
                    "",
                )
            ),

            "middle_addr":
            str(
                poi.get(
                    "middleAddrName",
                    "",
                )
            ),

            "lower_addr":
            str(
                poi.get(
                    "lowerAddrName",
                    "",
                )
            ),

            "detail_addr":
            str(
                poi.get(
                    "detailAddrName",
                    "",
                )
            ),

            "source":
            "tmap_poi",

        }


        results.append(
            result
        )


    return results


# ============================================================
# 13. 문자열 정규화
# ============================================================

def normalize_text(
    value,
):

    return (

        str(
            value
            or
            ""
        )

        .replace(
            " ",
            "",
        )

        .lower()

        .strip()

    )


# ============================================================
# 14. 후보 점수 계산
#
# 이름 일치
# +
# 지역 힌트
#
# 로 가장 적절한 장소 선택
# ============================================================

def calculate_candidate_score(
    candidate,
    query,
    region_hint=None,
):

    score = 0


    query_normalized = (
        normalize_text(
            query
        )
    )


    name_normalized = (
        normalize_text(
            candidate.get(
                "name"
            )
        )
    )


    # --------------------------------------------------------
    # 이름 완전 일치
    # --------------------------------------------------------

    if (
        name_normalized
        ==
        query_normalized
    ):

        score += 100


    # --------------------------------------------------------
    # 검색어가 POI 이름 안에 포함
    # --------------------------------------------------------

    elif (

        query_normalized

        and

        query_normalized
        in
        name_normalized

    ):

        score += 60


    # --------------------------------------------------------
    # POI 이름이 검색어 안에 포함
    # --------------------------------------------------------

    elif (

        name_normalized

        and

        name_normalized
        in
        query_normalized

    ):

        score += 40


    # --------------------------------------------------------
    # 지역 힌트 점수
    # --------------------------------------------------------

    if region_hint:

        region_normalized = (
            normalize_text(
                region_hint
            )
        )


        address_text = (

            str(
                candidate.get(
                    "address",
                    "",
                )
            )

            + " "

            + str(
                candidate.get(
                    "upper_addr",
                    "",
                )
            )

            + " "

            + str(
                candidate.get(
                    "middle_addr",
                    "",
                )
            )

            + " "

            + str(
                candidate.get(
                    "lower_addr",
                    "",
                )
            )

        )


        address_normalized = (
            normalize_text(
                address_text
            )
        )


        if (

            region_normalized

            and

            region_normalized
            in
            address_normalized

        ):

            score += 50


    return score


# ============================================================
# 15. 가장 좋은 후보 선택
# ============================================================

def choose_best_candidate(
    candidates,
    query,
    region_hint=None,
):

    if not candidates:

        return None


    scored_candidates = []


    for candidate in candidates:

        score = (
            calculate_candidate_score(

                candidate,

                query,

                region_hint,

            )
        )


        scored_candidates.append(

            (
                score,
                candidate,
            )

        )


    # --------------------------------------------------------
    # 점수 높은 순
    # --------------------------------------------------------

    scored_candidates.sort(

        key=lambda item:
        item[0],

        reverse=True,

    )


    best_score, best_candidate = (
        scored_candidates[0]
    )


    result = (
        best_candidate.copy()
    )


    result[
        "match_score"
    ] = (
        best_score
    )


    return result


# ============================================================
# 16. 핵심 함수
#
# 장소명
# →
# 좌표
#
# 예:
#
# resolve_location(
#     "판교역",
#     region_hint="성남시",
# )
# ============================================================

def resolve_location(
    query,
    region_hint=None,
    force_refresh=False,
):

    query = (
        str(query)
        .strip()
    )


    if not query:

        raise ValueError(
            "장소명이 비어 있습니다."
        )


    # --------------------------------------------------------
    # Cache Key
    # --------------------------------------------------------

    cache_key = (
        make_cache_key(

            query,

            region_hint,

        )
    )


    cache = (
        load_location_cache()
    )


    # --------------------------------------------------------
    # Cache에 있으면 TMAP 호출하지 않음
    # --------------------------------------------------------

    if (

        not force_refresh

        and

        cache_key
        in
        cache

    ):

        cached_result = (

            cache[
                cache_key
            ]
            .copy()

        )


        cached_result[
            "cached"
        ] = True


        return cached_result


    # --------------------------------------------------------
    # TMAP POI 검색
    # --------------------------------------------------------

    candidates = (
        search_location_candidates(

            query,

            count=20,

        )
    )


    if not candidates:

        raise ValueError(

            "TMAP에서 장소를 찾지 못했습니다: "
            f"{query}"

        )


    # --------------------------------------------------------
    # 최적 후보 선택
    # --------------------------------------------------------

    best = (
        choose_best_candidate(

            candidates,

            query,

            region_hint,

        )
    )


    if best is None:

        raise ValueError(

            "적합한 장소 후보를 찾지 못했습니다: "
            f"{query}"

        )


    # --------------------------------------------------------
    # 최종 결과
    # --------------------------------------------------------

    result = {

        "query":
        query,

        "region_hint":
        (
            region_hint
            if region_hint
            else None
        ),

        "poi_id":
        best.get(
            "poi_id"
        ),

        "name":
        best.get(
            "name"
        ),

        "address":
        best.get(
            "address"
        ),

        "lat":
        best.get(
            "lat"
        ),

        "lon":
        best.get(
            "lon"
        ),

        "match_score":
        best.get(
            "match_score"
        ),

        "source":
        "tmap_poi",

        "cached":
        False,

    }


    # --------------------------------------------------------
    # Cache 저장
    # --------------------------------------------------------

    cache[
        cache_key
    ] = {

        key:
        value

        for key, value
        in result.items()

        if key
        !=
        "cached"

    }


    save_location_cache(
        cache
    )


    return result


# ============================================================
# 17. 특정 장소 다시 검색
#
# Cache를 무시하고 TMAP을 다시 호출
# ============================================================

def refresh_location(
    query,
    region_hint=None,
):

    return (
        resolve_location(

            query,

            region_hint=region_hint,

            force_refresh=True,

        )
    )


# ============================================================
# 18. Cache 초기화
#
# 개발 테스트용
# ============================================================

def clear_location_cache():

    save_location_cache(
        {}
    )


# ============================================================
# 19. 직접 실행 테스트
#
# python backend/services/location_service.py
#
# 로도 간단한 테스트 가능
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "========================================"
    )

    print(
        "FLOW:MATE Location Service"
    )

    print(
        "========================================"
    )


    test_result = (
        resolve_location(

            "판교역",

            region_hint="성남시",

        )
    )


    print()
    print(
        json.dumps(

            test_result,

            ensure_ascii=False,

            indent=2,

        )
    )