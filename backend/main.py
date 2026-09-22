from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from pydantic import (
    BaseModel,
)


# ============================================================
# 기존 Mock / Prototype 서비스
# ============================================================

from backend.services.flow_feed_service import (
    get_routes,
    find_route,
    get_route_snapshot,
)


# ============================================================
# 실제 TMAP / MOCT_LINK Integration 서비스
# ============================================================

from backend.services.integration_route_service import (
    get_integration_status,
    get_od_detail,
    get_integration_route,
    get_integration_route_links,
    get_integration_route_geometry,
)


# ============================================================
# 실제 TMAP POI 검색 서비스
# ============================================================

from backend.services.location_service import (
    search_location_candidates,
)


# ============================================================
# 실제 Dynamic Route 서비스
#
# Flutter에서 선택한 정확한 POI 좌표
# →
# TMAP A/B/C
# →
# MOCT_LINK
# →
# 성남 분류
# →
# AI Coverage
# ============================================================

from backend.services.dynamic_route_service import (
    generate_dynamic_routes,
)

# ============================================================
# Navigation API Router
# ============================================================

from backend.routers.navigation import (
    router as navigation_router,
)


# ============================================================
# Dynamic Route Request Models
# ============================================================

class DynamicPoiInput(BaseModel):

    poi_id: str | None = None

    name: str

    address: str | None = ""

    lat: float

    lon: float

    source: str | None = "tmap_poi"


class DynamicRouteRequest(BaseModel):

    origin: DynamicPoiInput

    destination: DynamicPoiInput

    # True:
    # 기존 Route Cache를 무시하고
    # TMAP A/B/C를 새로 요청
    #
    # False:
    # 같은 좌표의 Cache가 있으면 재사용
    force_refresh: bool = False


# ============================================================
# FastAPI
# ============================================================

app = FastAPI(

    title="언제가 API",

    description=(
        "언제가(FLOW:MATE) "
        "자동차 퇴근수요 예측·분산 서비스 API"
    ),

    version="3.3.0",

)


# ============================================================
# CORS
#
# Flutter Web 개발 과정에서는
# localhost 포트가 계속 바뀔 수 있으므로
# 개발 단계에서는 전체 Origin 허용
# ============================================================

app.add_middleware(

    CORSMiddleware,

    allow_origins=[
        "*",
    ],

    allow_credentials=False,

    allow_methods=[
        "*",
    ],

    allow_headers=[
        "*",
    ],

)


# ============================================================
# Navigation API Router 등록
#
# /api/navigation/start
# /api/navigation/update
# /api/navigation/sessions/{session_id}
# ============================================================

app.include_router(
    navigation_router
)


# ============================================================
# ROOT
#
# GET /
# ============================================================

@app.get("/")
def root():

    return {

        "service":
            "언제가 API",

        "status":
            "running",

        "version":
            "3.3.0",

        "message":
            "언제가 FastAPI 서버가 정상 실행 중입니다.",

        "mock_api":
            True,

        "real_integration_api":
            True,

        "poi_search_api":
            True,

        "dynamic_route_api":
            True,

    }


# ============================================================
# ============================================================
#
# 기존 Mock / Prototype API
#
# 기존 테스트 및 Prototype 보호를 위해 유지
#
# ============================================================
# ============================================================


# ============================================================
# 기존 Route A/B/C 목록
#
# GET
# /api/routes
# ============================================================

@app.get(
    "/api/routes"
)
def routes():

    try:

        return get_routes()


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# 기존 특정 Route 상세
#
# GET
# /api/routes/route_A
# /api/routes/route_B
# /api/routes/route_C
# ============================================================

@app.get(
    "/api/routes/{route_id}"
)
def route_detail(
    route_id: str,
):

    try:

        route = (
            find_route(
                route_id
            )
        )


        if route is None:

            raise HTTPException(

                status_code=404,

                detail=(
                    "존재하지 않는 "
                    "route_id입니다: "
                    f"{route_id}"
                ),

            )


        return {

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
                    {},
                ),

            "destination":
                route.get(
                    "destination",
                    {},
                ),

            "summary":
                route.get(
                    "summary",
                    {},
                ),

            "link_count":
                route.get(

                    "link_count",

                    len(
                        route.get(
                            "links",
                            [],
                        )
                    ),

                ),

            "mapping_quality":
                route.get(
                    "mapping_quality",
                    {},
                ),

        }


    except HTTPException:

        raise


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# 기존 미래 Snapshot
#
# 예:
#
# GET
# /api/routes/route_A/snapshot
# ?offset_min=30
# &scenario=before
#
# 현재 Mock / Prototype
# ============================================================

@app.get(
    "/api/routes/{route_id}/snapshot"
)
def route_snapshot(

    route_id: str,

    offset_min: int = Query(

        default=0,

        ge=0,

        le=60,

        description=(
            "현재 시점으로부터 몇 분 뒤인지 지정합니다. "
            "0~60분, 5분 단위."
        ),

    ),

    scenario: str = Query(

        default="before",

        description=(
            "before = FLOW 적용 전, "
            "after = FLOW 적용 후"
        ),

    ),

):

    # ========================================================
    # 5분 단위 검사
    # ========================================================

    if offset_min % 5 != 0:

        raise HTTPException(

            status_code=400,

            detail=(
                "offset_min은 "
                "5분 단위여야 합니다."
            ),

        )


    # ========================================================
    # Scenario 검사
    # ========================================================

    if scenario not in (
        "before",
        "after",
    ):

        raise HTTPException(

            status_code=400,

            detail=(
                "scenario는 "
                "'before' 또는 "
                "'after'만 가능합니다."
            ),

        )


    try:

        return get_route_snapshot(

            route_id=route_id,

            offset_min=offset_min,

            scenario=scenario,

        )


    except KeyError as error:

        raise HTTPException(

            status_code=404,

            detail=str(
                error
            ),

        )


    except ValueError as error:

        raise HTTPException(

            status_code=400,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# ============================================================
#
# 실제 TMAP POI API
#
# ============================================================
# ============================================================


# ============================================================
# 실제 TMAP POI 검색
#
# GET
# /api/integration/pois/search
#
# 예:
#
# /api/integration/pois/search
# ?keyword=판교역
# &count=5
#
# 주의:
# 실제 TMAP POI API 호출 발생
# ============================================================

@app.get(
    "/api/integration/pois/search"
)
def integration_poi_search(

    keyword: str = Query(

        ...,

        min_length=1,

        description=(
            "검색할 장소명"
        ),

    ),

    count: int = Query(

        default=10,

        ge=1,

        le=20,

        description=(
            "검색 결과 개수"
        ),

    ),

):

    keyword = (
        keyword
        .strip()
    )


    if not keyword:

        raise HTTPException(

            status_code=400,

            detail=(
                "검색어를 입력해주세요."
            ),

        )


    try:

        results = (
            search_location_candidates(

                query=keyword,

                count=count,

            )
        )


        return {

            "status":
                "success",

            "query":
                keyword,

            "result_count":
                len(
                    results
                ),

            "results":
                results,

            # 이 API는 실제 TMAP POI API 호출
            "tmap_api_called":
                True,

        }


    except ValueError as error:

        raise HTTPException(

            status_code=400,

            detail=str(
                error
            ),

        )


    except RuntimeError as error:

        raise HTTPException(

            status_code=502,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# ============================================================
#
# 실제 Dynamic Route API
#
# Flutter에서 선택한 정확한 좌표 사용
#
# POI 이름을 다시 검색하지 않음
#
# ============================================================
# ============================================================


# ============================================================
# 실제 동적 A/B/C Route 생성
#
# POST
# /api/integration/routes/generate
#
#
# 입력:
#
# origin
# - name
# - address
# - lat
# - lon
#
# destination
# - name
# - address
# - lat
# - lon
#
#
# 처리:
#
# 정확한 좌표
# ↓
# TMAP A/B/C
# ↓
# MOCT_LINK Mapping
# ↓
# 성남 내부/외부 분류
# ↓
# 현재 AI Coverage
#
#
# 중요:
#
# force_refresh=false 이고
# 같은 좌표 Route Cache가 있다면
#
# → TMAP Route 신규 호출 없음
#
# Cache가 없다면
#
# → A/B/C 총 3회 TMAP Route 요청
# ============================================================

@app.post(
    "/api/integration/routes/generate"
)
def integration_generate_routes(
    request: DynamicRouteRequest,
):

    try:

        result = (
            generate_dynamic_routes(

                origin=(
                    request
                    .origin
                    .model_dump()
                ),

                destination=(
                    request
                    .destination
                    .model_dump()
                ),

                force_refresh=(
                    request
                    .force_refresh
                ),

                save_result=True,

            )
        )


        return result


    except ValueError as error:

        raise HTTPException(

            status_code=400,

            detail=str(
                error
            ),

        )


    except RuntimeError as error:

        # 예:
        #
        # TMAP API 오류
        # QUOTA_EXCEEDED
        # 네트워크 오류
        # Route 생성 실패
        raise HTTPException(

            status_code=502,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# ============================================================
#
# 저장된 실제 TMAP / MOCT_LINK Integration API
#
# 기존 성공 OD 데이터 조회
#
# 여기의 조회 API는:
#
# TMAP Route 신규 호출 없음
# LightGBM 신규 호출 없음
#
# ============================================================
# ============================================================


# ============================================================
# Integration 전체 상태
#
# GET
# /api/integration/status
# ============================================================

@app.get(
    "/api/integration/status"
)
def integration_status():

    try:

        return (
            get_integration_status()
        )


    except FileNotFoundError as error:

        raise HTTPException(

            status_code=503,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# 저장된 실제 OD 상세
#
# 예:
#
# GET
# /api/integration/ods/OD_000324
#
# 반환:
# - 출발지
# - 목적지
# - user_count
# - Route A/B/C
# ============================================================

@app.get(
    "/api/integration/ods/{od_id}"
)
def integration_od_detail(
    od_id: str,
):

    try:

        result = (
            get_od_detail(
                od_id
            )
        )


        if result is None:

            raise HTTPException(

                status_code=404,

                detail=(
                    "사용 가능한 실제 OD를 "
                    "찾을 수 없습니다: "
                    f"{od_id}"
                ),

            )


        return result


    except HTTPException:

        raise


    except FileNotFoundError as error:

        raise HTTPException(

            status_code=503,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# 저장된 실제 Route 상세
#
# 예:
#
# GET
# /api/integration/routes/OD_000324_A
#
# 반환:
# - 거리
# - TMAP ETA
# - Mapping 품질
# - 성남 구간
# - 현재 AI Coverage
# ============================================================

@app.get(
    "/api/integration/routes/{route_id}"
)
def integration_route_detail(
    route_id: str,
):

    try:

        result = (
            get_integration_route(
                route_id
            )
        )


        if result is None:

            raise HTTPException(

                status_code=404,

                detail=(
                    "실제 Route를 "
                    "찾을 수 없습니다: "
                    f"{route_id}"
                ),

            )


        return result


    except HTTPException:

        raise


    except FileNotFoundError as error:

        raise HTTPException(

            status_code=503,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# 저장된 실제 Route LINK Sequence
#
# 예:
#
# GET
# /api/integration/routes/OD_000324_A/links
#
# 반환:
# - LINK_ID
# - F_NODE
# - T_NODE
# - 도로명
# - LINK 길이
# - 제한속도
# - 성남 여부
# - 현재 AI 지원 여부
# - traffic_source
# ============================================================

@app.get(
    "/api/integration/routes/{route_id}/links"
)
def integration_route_links(
    route_id: str,
):

    try:

        result = (
            get_integration_route_links(
                route_id
            )
        )


        if result is None:

            raise HTTPException(

                status_code=404,

                detail=(
                    "실제 Route LINK를 "
                    "찾을 수 없습니다: "
                    f"{route_id}"
                ),

            )


        return result


    except HTTPException:

        raise


    except FileNotFoundError as error:

        raise HTTPException(

            status_code=503,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )


# ============================================================
# 저장된 실제 Route Geometry
#
# 예:
#
# GET
# /api/integration/routes/OD_000324_A/geometry
#
# 반환:
# - 출발지
# - 목적지
# - 실제 TMAP Polyline
#
# 좌표 순서:
#
# [longitude, latitude]
#
#
# 저장된 데이터를 읽으므로
# TMAP Route 신규 호출 없음
# ============================================================

@app.get(
    "/api/integration/routes/{route_id}/geometry"
)
def integration_route_geometry(
    route_id: str,
):

    try:

        result = (
            get_integration_route_geometry(
                route_id
            )
        )


        if result is None:

            raise HTTPException(

                status_code=404,

                detail=(
                    "실제 Route Geometry를 "
                    "찾을 수 없습니다: "
                    f"{route_id}"
                ),

            )


        return result


    except HTTPException:

        raise


    except FileNotFoundError as error:

        raise HTTPException(

            status_code=503,

            detail=str(
                error
            ),

        )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(
                error
            ),

        )